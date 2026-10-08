"""Short-lived exact-order requests for Today's authenticated Purchases bridge."""
import re
import time
import uuid

from flask import abort, jsonify, request
import ebay_mail

TIMEOUT = 120


def snapshot(row):
    return {key: row[key] for key in ('id', 'order_id', 'status', 'message')}


def expire(db):
    db.execute("UPDATE ebay_purchase_requests SET status='failed',message=? "
               "WHERE status IN ('queued','reading') AND requested_at<?",
               ('The Mac purchase reader did not finish. Keep Today and signed-in Chrome open, then try Check again.',
                time.time() - TIMEOUT))


def ensure(db, note):
    """Queue only missing entered eBay orders, not every ordinary Check."""
    note = dict(note)
    number = (note.get('order_number') or '').strip()
    if note.get('marketplace') not in (None, '', 'eBay') or not re.fullmatch(r'\d{2}-\d{5}-\d{5}', number):
        return None
    if not ebay_mail.configured():
        return None
    if db.execute('SELECT 1 FROM ebay_order_items i JOIN ebay_purchase_observations o '
                  'ON o.line_key=i.line_key WHERE i.order_id=? LIMIT 1', (number,)).fetchone():
        return None
    enabled = db.execute('SELECT enabled FROM ebay_mail_connection WHERE id=1').fetchone()
    if enabled and not enabled[0]:
        return dict(status='failed', message='Purchase updates are paused. Resume them in eBay Orders before checking this order.')
    expire(db)
    row = db.execute('SELECT * FROM ebay_purchase_requests WHERE order_id=?', (number,)).fetchone()
    if not row or (row['status'] not in ('queued', 'reading') and row['requested_at'] < time.time() - 15):
        db.execute('INSERT INTO ebay_purchase_requests (id,order_id,requested_at,status,message) VALUES (?,?,?,?,?) '
                   'ON CONFLICT(order_id) DO UPDATE SET id=excluded.id,requested_at=excluded.requested_at, '
                   'status=excluded.status,message=excluded.message',
                   (uuid.uuid4().hex, number, time.time(), 'queued', 'Waiting for the Mac to read this order from eBay Purchases...'))
        row = db.execute('SELECT * FROM ebay_purchase_requests WHERE order_id=?', (number,)).fetchone()
    db.commit()
    return snapshot(row)


def claim(db):
    db.execute('BEGIN IMMEDIATE')
    expire(db)
    enabled = db.execute('SELECT enabled FROM ebay_mail_connection WHERE id=1').fetchone()
    row = None if enabled and not enabled[0] else db.execute(
        "SELECT * FROM ebay_purchase_requests WHERE status='queued' ORDER BY requested_at LIMIT 1").fetchone()
    if row:
        db.execute("UPDATE ebay_purchase_requests SET status='reading',message=? WHERE id=?",
                   ('Reading the exact order from eBay Purchases...', row['id']))
    db.commit()
    return dict(id=row['id'], order_id=row['order_id']) if row else None


def complete(db, payload):
    """Only acknowledge validated evidence for the claimed order, never a sibling."""
    if not isinstance(payload.get('id'), str) or not re.fullmatch(r'[a-f0-9]{32}', payload['id']):
        raise ValueError('Invalid purchase request')
    db.execute('BEGIN IMMEDIATE')
    expire(db)
    row = db.execute('SELECT * FROM ebay_purchase_requests WHERE id=?', (payload.get('id'),)).fetchone()
    if not row or row['status'] != 'reading':
        db.rollback()
        raise ValueError('Purchase request expired or is no longer active')
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
        result = ebay_mail.apply_purchases(db, items, observed, auto_match=False)
        stored = {r[0] for r in db.execute('SELECT item_id FROM ebay_order_items WHERE order_id=?', (row['order_id'],))}
        if result['skipped'] or result['items_accepted'] != len(items) or any(i['item_id'] not in stored for i in items):
            db.rollback()
            raise ValueError('Purchase identity could not be confirmed')
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
        response = jsonify(snapshot(row))
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
                return jsonify(ok=True, request=claim(db))
            if payload.get('action') == 'complete':
                return jsonify(complete(db, payload))
        except ValueError as exc:
            db.rollback()
            return jsonify(error=str(exc)), 409
        except Exception:
            db.rollback()
            raise
        abort(400)
