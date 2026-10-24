"""Short-lived exact-order requests for Today's authenticated Purchases bridge."""
import re
import time
import uuid

from flask import abort, jsonify, request
import ebay_mail
import ebay_listing_captures
import ebay_purchase_prices
import market_purchase_capture

TIMEOUT = 120
SESSION_TIMEOUT = 600
SESSION_RETRY = 8


def session_for(db, request_id):
    return db.execute('SELECT * FROM ebay_purchase_request_sessions WHERE request_id=?', (request_id,)).fetchone()


def snapshot(row, session=None):
    result = {key: row[key] for key in ('id', 'order_id', 'status', 'message')}
    result['expires_at'] = session['expires_at'] if session else row['requested_at'] + TIMEOUT
    if session:
        if row['status'] in ('queued', 'reading') and session['state'] in ('sign_in_required', 'challenge_required'):
            result['status'] = session['state']
        elif row['status'] == 'failed' and session['state'] == 'cancelled':
            result['status'] = 'cancelled'
    return result


def current_order(db, order_id):
    return db.execute("SELECT 1 FROM banknotes WHERE order_number=? "
                      "AND COALESCE(marketplace,'') IN ('','eBay') LIMIT 1", (order_id,)).fetchone()


def expire(db):
    db.execute("UPDATE ebay_purchase_requests SET status='failed',message=? "
               "WHERE status IN ('queued','reading') AND COALESCE("
               "(SELECT expires_at FROM ebay_purchase_request_sessions s WHERE s.request_id=ebay_purchase_requests.id),"
               "requested_at+?)<?",
               ('The purchase check expired before it could finish. Press Check to try again.', TIMEOUT, time.time()))


def ensure(db, note):
    """Refresh missing orders and public listings through the signed-in browser."""
    note = dict(note)
    number = (note.get('order_number') or '').strip()
    if note.get('marketplace') not in (None, '', 'eBay') or not re.fullmatch(r'\d{2}-\d{5}-\d{5}', number):
        return None
    if not ebay_mail.configured():
        return None
    cached = db.execute('SELECT i.item_id,i.quantity,i.attention,o.status_text FROM ebay_order_items i JOIN ebay_purchase_observations o '
                        'ON o.line_key=i.line_key WHERE i.order_id=?', (number,)).fetchall()
    # Older readers misclassified this normal new-order state. Refresh the
    # observation instead of preserving that historical warning indefinitely.
    if cached and not any(r['status_text'].lower() == 'order processing' and
                          r['attention'] == 'Order processing; shipment or delivery not confirmed' for r in cached):
        needs_price = ('price' in note and not str(note.get('price') or '').strip() and len(cached) == 1
                       and not db.execute('SELECT 1 FROM ebay_purchase_prices p JOIN ebay_order_items i '
                                          'ON i.line_key=p.line_key WHERE i.order_id=? AND i.item_id=?',
                                          (number, cached[0]['item_id'])).fetchone())
        if len(cached) != 1 or cached[0]['quantity'] != 1 or (not needs_price and ebay_listing_captures.html(
                db, 'https://www.ebay.com/itm/' + cached[0]['item_id'])):
            return None
        recent = db.execute('SELECT status,requested_at FROM ebay_purchase_requests WHERE order_id=?', (number,)).fetchone()
        # A completed browser attempt may legitimately have no readable listing.
        # Continue with available evidence instead of polling forever.
        if recent and recent['status'] == 'done' and recent['requested_at'] > time.time() - 300:
            return None
    enabled = db.execute('SELECT enabled FROM ebay_mail_connection WHERE id=1').fetchone()
    if enabled and not enabled[0]:
        return dict(status='failed', message='Purchase updates are paused. Resume them in eBay Orders before checking this order.')
    expire(db)
    row = db.execute('SELECT * FROM ebay_purchase_requests WHERE order_id=?', (number,)).fetchone()
    if not row or (row['status'] not in ('queued', 'reading') and row['requested_at'] < time.time() - 15):
        if row:
            db.execute('DELETE FROM ebay_purchase_request_sessions WHERE request_id=?', (row['id'],))
        db.execute('INSERT INTO ebay_purchase_requests (id,order_id,requested_at,status,message) VALUES (?,?,?,?,?) '
                   'ON CONFLICT(order_id) DO UPDATE SET id=excluded.id,requested_at=excluded.requested_at, '
                   'status=excluded.status,message=excluded.message',
                   (uuid.uuid4().hex, number, time.time(), 'queued', 'Waiting for the Mac to read this order from eBay Purchases...'))
        row = db.execute('SELECT * FROM ebay_purchase_requests WHERE order_id=?', (number,)).fetchone()
        db.execute('INSERT INTO ebay_purchase_request_sessions(request_id,expires_at) VALUES (?,?)',
                   (row['id'], row['requested_at'] + SESSION_TIMEOUT))
    db.commit()
    return snapshot(row, session_for(db, row['id']))


def claim(db):
    db.execute('BEGIN IMMEDIATE')
    expire(db)
    enabled = db.execute('SELECT enabled FROM ebay_mail_connection WHERE id=1').fetchone()
    row = None if enabled and not enabled[0] else db.execute(
        "SELECT q.* FROM ebay_purchase_requests q LEFT JOIN ebay_purchase_request_sessions s ON s.request_id=q.id "
        "WHERE q.status='queued' AND COALESCE(s.next_attempt_at,0)<=? ORDER BY q.requested_at LIMIT 1",
        (time.time(),)).fetchone()
    result = None
    if row:
        if not current_order(db, row['order_id']):
            db.execute("UPDATE ebay_purchase_requests SET status='failed',message=? WHERE id=?",
                       ('This purchase request no longer matches a banknote order.', row['id']))
        else:
            session = session_for(db, row['id'])
            message = row['message'] if session and session['state'] != 'ready' else 'Reading the exact order from eBay Purchases...'
            db.execute("UPDATE ebay_purchase_requests SET status='reading',message=? WHERE id=?", (message, row['id']))
            result = dict(id=row['id'], order_id=row['order_id'],
                          expires_at=session['expires_at'] if session else row['requested_at'] + TIMEOUT)
            if session:
                result['session_recovery'] = dict(open_browser=not bool(session['open_reserved']))
                db.execute('UPDATE ebay_purchase_request_sessions SET open_reserved=1 WHERE request_id=?', (row['id'],))
    db.commit()
    return result


def complete_session(db, row, payload):
    session = payload.get('session')
    if (not session_for(db, row['id']) or not isinstance(session, dict)
            or set(session) - {'state', 'reason'} or any(k in payload for k in ('items', 'receipt', 'listing', 'error'))):
        raise ValueError('Invalid purchase session outcome')
    state, reason = session.get('state'), session.get('reason')
    if (state not in ('sign_in_required', 'challenge_required', 'unavailable')
            or reason not in (None, 'unsupported_browser', 'browser_access', 'wrong_account', 'expired')
            or (state != 'unavailable' and reason is not None)):
        raise ValueError('Invalid purchase session outcome')
    messages = {
        'sign_in_required': 'Sign in to eBay in the browser that opened. Check will continue automatically.',
        'challenge_required': 'Complete the eBay verification in the browser that opened. Check will continue automatically.',
        'unsupported_browser': 'Check needs the signed-in Chrome browser on the designated Mac. Its default browser is not supported.',
        'browser_access': 'Check could not access Chrome on the designated Mac. Open Chrome and try Check again.',
        'wrong_account': 'Chrome is signed in to a different eBay account. Sign in to the connected account, then try Check again.',
        'expired': 'The purchase check expired before it could finish. Press Check to try again.',
        'unavailable': 'Check could not open eBay on the designated Mac. Open Chrome and try Check again.',
    }
    message = messages[reason or state]
    db.execute('UPDATE ebay_purchase_request_sessions SET state=?,reason=?,next_attempt_at=? WHERE request_id=?',
               (state, reason, time.time() + SESSION_RETRY, row['id']))
    db.execute('UPDATE ebay_purchase_requests SET status=?,message=? WHERE id=?',
               ('failed' if state == 'unavailable' else 'queued', message, row['id']))
    db.commit()
    return dict(ok=True)


def complete(db, payload):
    """Only acknowledge validated evidence for the claimed order, never a sibling."""
    if payload.get('kind') == 'market_purchase' or any(k in payload for k in ('search_item_id','search_complete')):
        raise ValueError('A targeted purchase search cannot complete an exact-order request')
    if not isinstance(payload.get('id'), str) or not re.fullmatch(r'[a-f0-9]{32}', payload['id']):
        raise ValueError('Invalid purchase request')
    db.execute('BEGIN IMMEDIATE')
    expire(db)
    row = db.execute('SELECT * FROM ebay_purchase_requests WHERE id=?', (payload.get('id'),)).fetchone()
    if not row or row['status'] != 'reading':
        db.rollback()
        raise ValueError('Purchase request expired or is no longer active')
    if not current_order(db, row['order_id']):
        raise ValueError('This purchase request no longer matches a banknote order')
    if 'session' in payload:
        return complete_session(db, row, payload)
    messages = {
        'not_found': 'This order was not found in the available eBay Purchases pages. Confirm the order number and signed-in account.',
        'unreadable': 'eBay did not provide readable details for this order. No item was selected; try Check again later.',
        'browser': 'The Mac could not read eBay Purchases. Keep Chrome signed in and try Check again.',
    }
    error = payload.get('error')
    if error:
        if error not in messages:
            db.rollback()
            raise ValueError('Invalid purchase lookup outcome')
        status, message = 'failed', messages[error]
    else:
        account, observed, items, skipped = ebay_mail.purchase_snapshot(payload)
        ebay_mail.check_account(db, account)
        if skipped or not items or any(i['order_id'] != row['order_id'] for i in items):
            db.rollback()
            raise ValueError('Purchase result must contain only the complete requested order')
        # The owner requested this exact order for a current banknote. Keep all
        # its items even when the seller title lacks discovery words such as
        # banknote or PMG; quantity and sibling checks still apply downstream.
        result = ebay_mail.apply_purchases(db, items, observed, auto_match=False,
                                          requested_order=row['order_id'])
        stored = {r[0] for r in db.execute('SELECT item_id FROM ebay_order_items WHERE order_id=?', (row['order_id'],))}
        if result['skipped'] or result['items_accepted'] != len(items) or any(i['item_id'] not in stored for i in items):
            db.rollback()
            raise ValueError('Purchase identity could not be confirmed')
        ebay_listing_captures.save(db, payload.get('listing'), items)
        ebay_purchase_prices.save(db, payload.get('receipt'), items, row['requested_at'])
        status, message = 'done', 'Order found. Checking the purchased item...'
    db.execute('UPDATE ebay_purchase_requests SET status=?,message=? WHERE id=?', (status, message, row['id']))
    db.commit()
    return dict(ok=True)


def register(app, get_db, require_owner):
    @app.get('/banknotes/<record_id>/purchase-refresh/<request_id>')
    def banknote_purchase_refresh(record_id, request_id):
        require_owner()
        db = get_db()
        expire(db)
        db.commit()
        row = db.execute('SELECT q.* FROM ebay_purchase_requests q JOIN banknotes n '
                         'ON n.order_number=q.order_id WHERE n.id=? AND q.id=? '
                         "AND COALESCE(n.marketplace,'') IN ('','eBay')", (record_id, request_id)).fetchone()
        if not row:
            abort(404)
        response = jsonify(snapshot(row, session_for(db, row['id'])))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/banknotes/<record_id>/purchase-refresh/<request_id>/cancel')
    def banknote_purchase_refresh_cancel(record_id, request_id):
        require_owner()
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        row = db.execute('SELECT q.* FROM ebay_purchase_requests q JOIN banknotes n '
                         'ON n.order_number=q.order_id WHERE n.id=? AND q.id=? '
                         "AND COALESCE(n.marketplace,'') IN ('','eBay')", (record_id, request_id)).fetchone()
        if not row:
            db.rollback()
            abort(404)
        if row['status'] in ('queued', 'reading'):
            db.execute("INSERT INTO ebay_purchase_request_sessions(request_id,expires_at,state) VALUES (?,?,'cancelled') "
                       "ON CONFLICT(request_id) DO UPDATE SET state='cancelled'",
                       (row['id'], row['requested_at'] + TIMEOUT))
            db.execute("UPDATE ebay_purchase_requests SET status='failed',message=? WHERE id=?",
                       ('Purchase check cancelled. Nothing was changed.', row['id']))
        db.commit()
        row = db.execute('SELECT * FROM ebay_purchase_requests WHERE id=?', (request_id,)).fetchone()
        response = jsonify(snapshot(row, session_for(db, row['id'])))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.post('/ebay/today/requests')
    def ebay_purchase_requests():
        ebay_mail.authenticate()
        if request.content_length is None or request.content_length > 200000:
            abort(413)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            abort(400)
        db = get_db()
        try:
            if payload.get('action') == 'claim':
                claimed = claim(db) or market_purchase_capture.claim(db)
                account = db.execute('SELECT account_name FROM ebay_purchase_account WHERE id=1').fetchone()
                if not account:
                    account = db.execute('SELECT account_name FROM ebay_connection WHERE id=1').fetchone()
                return jsonify(ok=True, request=claimed, expected_account=account[0] if account else None)
            if payload.get('action') == 'complete':
                handler = market_purchase_capture.complete if payload.get('kind') == 'market_purchase' else complete
                return jsonify(handler(db, payload))
        except ValueError as exc:
            db.rollback()
            # Evidence is atomic: reject it all, then report only the failed
            # attempt. Never leave a rejected completion looking like a slow
            # Mac, or let an old request fail its replacement for this order.
            request_id = payload.get('id')
            if payload.get('kind') == 'market_purchase':
                if isinstance(request_id,str) and re.fullmatch(r'[a-f0-9]{32}',request_id):
                    market_purchase_capture.reject(db,request_id,str(exc))
                return jsonify(error=str(exc)),409
            if (payload.get('action') == 'complete' and isinstance(request_id, str)
                    and re.fullmatch(r'[a-f0-9]{32}', request_id)):
                message = ('The purchase evidence was rejected: ' + str(exc)[:200].rstrip('.')
                           + '. Nothing was changed.')
                db.execute("UPDATE ebay_purchase_requests SET status='failed',message=? "
                           "WHERE id=? AND status='reading' AND COALESCE("
                           "(SELECT expires_at FROM ebay_purchase_request_sessions s WHERE s.request_id=ebay_purchase_requests.id),"
                           "requested_at+?)>=?",
                           (message, request_id, TIMEOUT, time.time()))
                db.commit()
            return jsonify(error=str(exc)), 409
        except Exception:
            db.rollback()
            raise
        abort(400)
