"""Capture one explicitly selected eBay purchase through the existing Today reader.

The queue never submits checkout, opens a browser, or changes eBay. Only a fresh,
complete Purchases search can link the selected exact item to its collection row.
"""
from datetime import datetime, timezone
import re
import time
import uuid
from zoneinfo import ZoneInfo

from flask import abort, g, jsonify
import ebay_mail
import ebay_orders
import market_ebay_feed
import purchase_orders

LIFETIME = 86400
RETRY_SECONDS = 60
LEASE_SECONDS = 180
FRESH_SECONDS = 300
PAID_STATES = {'paid', 'awaiting shipment', 'order processing',
               'shipped', 'in transit', 'out for delivery', 'delivered'}
ACTIVE = ('queued', 'reading')


def init(db):
    db.execute("""CREATE TABLE IF NOT EXISTS market_purchase_captures (
        id TEXT PRIMARY KEY, record_id TEXT NOT NULL UNIQUE REFERENCES banknotes(id) ON DELETE CASCADE,
        item_id TEXT NOT NULL, listing_url TEXT NOT NULL, listing_title TEXT NOT NULL,
        expected_account TEXT NOT NULL, requested_at REAL NOT NULL, expires_at REAL NOT NULL,
        status TEXT NOT NULL CHECK(status IN ('queued','reading','done','review','expired','cancelled')),
        message TEXT NOT NULL, next_attempt_at REAL NOT NULL DEFAULT 0,
        claimed_at REAL, attempts INTEGER NOT NULL DEFAULT 0, browser_state TEXT NOT NULL DEFAULT '',
        already_paid INTEGER NOT NULL DEFAULT 0 CHECK(already_paid IN (0,1))
    )""")
    if 'already_paid' not in {r['name'] for r in db.execute('PRAGMA table_info(market_purchase_captures)')}:
        db.execute('ALTER TABLE market_purchase_captures ADD COLUMN already_paid INTEGER NOT NULL DEFAULT 0')
    db.execute('CREATE INDEX IF NOT EXISTS market_purchase_captures_pending '
               'ON market_purchase_captures(status,next_attempt_at)')


def _exists(db):
    return db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_purchase_captures'").fetchone()


def _account(db):
    try:
        return market_ebay_feed.expected_account(db)
    except ValueError:
        return None


def _source_ids(note):
    found = set()
    for line in (note['description'] or '').splitlines():
        if line.strip().startswith('Listing: '):
            number = market_ebay_feed.item_id(line.strip()[9:])
            if number:
                found.add(number)
    for line in (note['note_references'] or '').splitlines():
        if re.match(r'^Market Scan \d{4}-\d{2}-\d{2}:', line):
            for url in re.findall(r'https?://\S+', line):
                number = market_ebay_feed.item_id(url)
                if number:
                    found.add(number)
    return found


def _binding_problem(db, row):
    note = db.execute('SELECT * FROM banknotes WHERE id=?', [row['record_id']]).fetchone()
    if not note:
        return 'This collection record was removed; automatic order capture stopped.'
    if note['order_number'] is not None:
        return 'The order number was edited; automatic order capture stopped.'
    if note['marketplace'] not in (None, '', 'eBay'):
        return 'The marketplace was edited; automatic order capture stopped.'
    if _source_ids(note) != {row['item_id']}:
        return 'The purchase listing was removed or changed; automatic order capture stopped.'
    if _account(db) != row['expected_account']:
        return 'The connected eBay account changed; automatic order capture stopped.'
    return ''


def _recent_enough(row, item):
    if row['already_paid']:
        return True
    day = datetime.fromtimestamp(row['requested_at'],ZoneInfo('America/New_York')).date().isoformat()
    return bool(item['ordered_at'] and item['ordered_at'][:10] >= day)


def _confirmed_order(db, row):
    """A parallel authoritative sync may finish the same queued capture first."""
    note = db.execute('SELECT * FROM banknotes WHERE id=?',[row['record_id']]).fetchone()
    if (not note or not note['order_number'] or note['marketplace'] != 'eBay'
            or _source_ids(note) != {row['item_id']} or _account(db) != row['expected_account']):
        return None
    matches = db.execute('SELECT i.*,o.status_text FROM banknote_ebay_links l '
                         'JOIN ebay_order_items i ON i.line_key=l.line_key '
                         'JOIN ebay_purchase_observations o ON o.line_key=i.line_key '
                         'WHERE l.banknote_id=? AND i.item_id=? AND i.order_id=?',
                         [row['record_id'],row['item_id'],note['order_number']]).fetchall()
    if (len(matches) != 1 or matches[0]['quantity'] != 1 or matches[0]['attention'] or matches[0]['ignored']
            or matches[0]['status_text'].lower() not in PAID_STATES or not _recent_enough(row,matches[0])
            or db.execute('SELECT count(*) FROM ebay_order_items WHERE item_id=?',[row['item_id']]).fetchone()[0] != 1):
        return None
    return note['order_number']


def state(db, record_id):
    """Read-only status for the detail view and polling endpoint."""
    if not _exists(db):
        return None
    row = db.execute('SELECT * FROM market_purchase_captures WHERE record_id=?', [record_id]).fetchone()
    if not row:
        return None
    result = {key: row[key] for key in ('id', 'status', 'message', 'expires_at', 'browser_state')}
    if result['status'] in ACTIVE:
        confirmed = _confirmed_order(db,row)
        problem = _binding_problem(db, row)
        if confirmed:
            result.update(status='done',message='Order '+confirmed+' confirmed from eBay Purchases.')
        elif problem:
            result.update(status='cancelled', message=problem)
        elif row['expires_at'] <= time.time():
            result.update(status='expired', message='Automatic order capture expired. Enter the paid order number or use Check to finish.')
    note = db.execute('SELECT * FROM banknotes WHERE id=?', [record_id]).fetchone()
    result['order_reference'] = (purchase_orders.order_reference(db, 'banknotes', note)
                                 if note and note['order_number'] else None)
    return result


def enqueue(db, record_id, listing_url, title=None, already_paid=False, commit=True):
    """Only the explicit Buy/Bought handler calls this after filing its record."""
    if not market_ebay_feed.enabled():
        return None
    item_id = market_ebay_feed.item_id(listing_url)
    account = _account(db)
    note = db.execute('SELECT * FROM banknotes WHERE id=?', [record_id]).fetchone()
    if not item_id or not account or not note or note['order_number'] is not None:
        return None
    title = str(title or (note['description'] or '').split('\n', 1)[0]).strip()[:500]
    if not title:
        return None
    pending = dict(record_id=record_id, item_id=item_id, expected_account=account)
    if _binding_problem(db, pending):
        return None
    init(db)
    old = db.execute('SELECT * FROM market_purchase_captures WHERE record_id=?', [record_id]).fetchone()
    now = time.time()
    if old and old['item_id'] == item_id and old['expected_account'] == account and (
            old['status'] == 'done' or old['status'] in ACTIVE and old['expires_at'] > now):
        if already_paid is True and not old['already_paid']:
            db.execute('UPDATE market_purchase_captures SET already_paid=1 WHERE id=?',[old['id']])
            if commit:
                db.commit()
        return state(db, record_id)
    db.execute('INSERT INTO market_purchase_captures '
               '(id,record_id,item_id,listing_url,listing_title,expected_account,requested_at,expires_at,status,message,already_paid) '
               "VALUES(?,?,?,?,?,?,?,?,'queued',?,?) ON CONFLICT(record_id) DO UPDATE SET "
               'id=excluded.id,item_id=excluded.item_id,listing_url=excluded.listing_url,listing_title=excluded.listing_title,'
               'expected_account=excluded.expected_account,requested_at=excluded.requested_at,expires_at=excluded.expires_at,'
               "status='queued',message=excluded.message,already_paid=excluded.already_paid,next_attempt_at=0,claimed_at=NULL,attempts=0,browser_state=''",
               [uuid.uuid4().hex, record_id, item_id, listing_url, title, account, now, now+LIFETIME,
                'After payment, the order number will be captured from eBay Purchases.',int(already_paid is True)])
    if commit:
        db.commit()
    return state(db, record_id)


def claim(db):
    if not market_ebay_feed.enabled() or not _exists(db):
        return None
    db.execute('BEGIN IMMEDIATE')
    now = time.time()
    db.execute("UPDATE market_purchase_captures SET status='expired',message=? WHERE status IN ('queued','reading') AND expires_at<=?",
               ['Automatic order capture expired. Enter the paid order number or use Check to finish.', now])
    db.execute("UPDATE market_purchase_captures SET status='queued',next_attempt_at=?,message=? "
               "WHERE status='reading' AND claimed_at<? AND expires_at>?",
               [now, 'Waiting for the Mac to retry eBay Purchases.', now-LEASE_SECONDS, now])
    enabled = db.execute('SELECT enabled FROM ebay_mail_connection WHERE id=1').fetchone()
    if enabled and not enabled[0]:
        db.execute("UPDATE market_purchase_captures SET message=? WHERE status='queued'",
                   ['eBay purchase updates are paused. Resume them in eBay Orders to capture the order number.'])
        db.commit()
        return None
    rows = db.execute("SELECT * FROM market_purchase_captures WHERE status='queued' AND next_attempt_at<=? ORDER BY requested_at", [now]).fetchall()
    for row in rows:
        confirmed = _confirmed_order(db,row)
        if confirmed:
            db.execute("UPDATE market_purchase_captures SET status='done',message=? WHERE id=?",
                       ['Order '+confirmed+' confirmed from eBay Purchases.',row['id']])
            continue
        problem = _binding_problem(db, row)
        if problem:
            db.execute("UPDATE market_purchase_captures SET status='cancelled',message=? WHERE id=?", [problem,row['id']])
            continue
        db.execute("UPDATE market_purchase_captures SET status='reading',claimed_at=?,attempts=attempts+1,message=? WHERE id=?",
                   [now, 'Checking eBay Purchases for the paid order.', row['id']])
        db.commit()
        return dict(id=row['id'], kind='market_purchase', item_id=row['item_id'],
                    listing_title=row['listing_title'], expires_at=row['expires_at'])
    db.commit()
    return None


def reject(db, request_id, message):
    """Called after an invalid completion has been rolled back in full."""
    if _exists(db):
        db.execute("UPDATE market_purchase_captures SET status='review',message=? WHERE id=? AND status='reading'",
                   ['Order capture needs review: ' + str(message)[:200].rstrip('.') + '. Nothing was changed.', request_id])
        db.commit()


def _retry(db, row, message, browser_state=''):
    db.execute("UPDATE market_purchase_captures SET status='queued',message=?,next_attempt_at=?,browser_state=? WHERE id=?",
               [message, time.time()+RETRY_SECONDS, browser_state, row['id']])
    db.commit()
    return dict(ok=True, status='queued')


def complete(db, payload):
    if not isinstance(payload.get('id'), str) or not re.fullmatch(r'[a-f0-9]{32}', payload['id']):
        raise ValueError('Invalid market purchase request')
    if not market_ebay_feed.enabled() or not _exists(db):
        raise ValueError('Automatic order capture is unavailable')
    db.execute('BEGIN IMMEDIATE')
    row = db.execute('SELECT * FROM market_purchase_captures WHERE id=?', [payload['id']]).fetchone()
    if not row or row['status'] != 'reading' or row['expires_at'] <= time.time():
        raise ValueError('Purchase capture expired or is no longer active')
    confirmed = _confirmed_order(db,row)
    if confirmed:
        db.execute("UPDATE market_purchase_captures SET status='done',message=?,browser_state='' WHERE id=?",
                   ['Order '+confirmed+' confirmed from eBay Purchases.',row['id']])
        db.commit()
        return dict(ok=True,status='done')
    problem = _binding_problem(db, row)
    if problem:
        raise ValueError(problem)
    enabled = db.execute('SELECT enabled FROM ebay_mail_connection WHERE id=1').fetchone()
    if enabled and not enabled[0]:
        raise ValueError('eBay purchase updates are paused')
    session = payload.get('session')
    if session is not None:
        if not isinstance(session, dict) or any(k in payload for k in ('items','receipt','listing','error')):
            raise ValueError('Invalid purchase session outcome')
        messages = {
            'sign_in_required': 'Sign in to the connected eBay account in Chrome on the designated Mac; order capture will retry.',
            'challenge_required': 'Complete the eBay verification in Chrome on the designated Mac; order capture will retry.',
            'unavailable': 'Order capture is waiting for the designated Mac and its signed-in Chrome browser.',
        }
        browser_state = session.get('state')
        if browser_state not in messages:
            raise ValueError('Invalid purchase session outcome')
        message = messages[browser_state]
        if session.get('reason') == 'wrong_account':
            message = 'Chrome is signed in to a different eBay account. Switch to the connected account; order capture will retry.'
        return _retry(db, row, message, browser_state)
    if payload.get('error'):
        if payload['error'] not in ('browser','unreadable','not_found'):
            raise ValueError('Invalid purchase capture outcome')
        return _retry(db, row, 'The Mac could not confirm this purchase yet. Automatic order capture will retry.', payload['error'])
    if payload.get('account') != row['expected_account'] or _account(db) != row['expected_account']:
        raise ValueError('The purchase account does not match the queued account')
    try:
        observed = datetime.fromisoformat(str(payload.get('observed_at') or '').replace('Z','+00:00'))
        if observed.tzinfo is None:
            raise ValueError()
        stamp = observed.timestamp()
    except (TypeError, ValueError):
        raise ValueError('Invalid purchase observation time') from None
    now = time.time()
    if not max(row['requested_at'],row['claimed_at'] or 0)-1 <= stamp <= now+60 or stamp < now-FRESH_SECONDS:
        raise ValueError('Purchase evidence is not a fresh observation for this request')
    if (payload.get('search_item_id') != row['item_id'] or payload.get('search_complete') is not True
            or type(payload.get('pages')) is not int or not 1 <= payload['pages'] <= 100
            or not isinstance(payload.get('skipped'), list) or payload['skipped']):
        raise ValueError('The exact-item purchase search is incomplete')
    raw = payload.get('items')
    if not isinstance(raw, list) or len(raw)>2000 or any(not isinstance(item,dict) or item.get('item_id') != row['item_id'] for item in raw):
        raise ValueError('Purchase search must contain only the requested exact item')
    items, skipped = ebay_mail.validate_purchases(raw)
    if skipped:
        raise ValueError('The exact-item purchase evidence needs review')
    if not items:
        return _retry(db,row,'No paid order found yet. Order capture will retry after payment.')
    if len(items) != 1 or items[0]['quantity'] != 1:
        raise ValueError('Multiple purchases or quantities match this listing; choose the exact order manually')
    item = items[0]
    paid_state = item['status_text'].lower()
    if paid_state not in PAID_STATES:
        return _retry(db,row,'Payment is not confirmed in eBay Purchases yet. Order capture will retry.')
    if item['attention']:
        raise ValueError('This purchase requires review before it can be linked')
    if not _recent_enough(row,item):
        return _retry(db,row,'Only an earlier purchase was found for this listing. Order capture will retry after payment.')
    # A complete exact-item search does not excuse conflicting older evidence or
    # another physical note already linked to the same purchase.
    stored = db.execute('SELECT * FROM ebay_order_items WHERE item_id=?', [row['item_id']]).fetchall()
    if len(stored)>1 or any(old['order_id'] != item['order_id'] or old['quantity'] != 1 or old['ignored'] for old in stored):
        raise ValueError('This listing has a conflicting or repeated stored purchase')
    existing_link = db.execute('SELECT l.*,i.order_id,i.item_id FROM banknote_ebay_links l JOIN ebay_order_items i ON i.line_key=l.line_key '
                               'WHERE l.banknote_id=? OR i.item_id=?', [row['record_id'],row['item_id']]).fetchall()
    if any(link['banknote_id'] != row['record_id'] or link['order_id'] != item['order_id'] or link['item_id'] != row['item_id'] for link in existing_link):
        raise ValueError('The purchase is already linked to a different record or order')
    candidates = ebay_orders.listing_candidates(db)
    if candidates.get(row['item_id']) != {row['record_id']} or sum(row['record_id'] in ids for ids in candidates.values()) != 1:
        raise ValueError('The exact purchase source matches more than one record or listing')
    ebay_mail.check_account(db,row['expected_account'])
    evidence_time = observed.astimezone(timezone.utc).isoformat()
    result = ebay_mail.apply_purchases(db,items,evidence_time,auto_match=False,requested_order=item['order_id'],capture_order_numbers=False)
    if result['skipped'] or result['items_accepted'] != 1:
        raise ValueError('The exact purchased item could not be saved')
    saved = db.execute('SELECT i.*,o.status_text FROM ebay_order_items i JOIN ebay_purchase_observations o ON o.line_key=i.line_key '
                       'WHERE i.item_id=? AND i.order_id=?', [row['item_id'],item['order_id']]).fetchall()
    if len(saved) != 1 or saved[0]['status_text'].lower() not in PAID_STATES or saved[0]['attention']:
        raise ValueError('The saved purchase is not uniquely confirmed paid')
    purchased = saved[0]
    if not existing_link:
        db.execute('INSERT INTO banknote_ebay_links(banknote_id,line_key,matched_by,matched_at,match_evidence) '
                   "VALUES(?,?,'listing',?,?)", [row['record_id'],purchased['line_key'],ebay_orders.now_iso(),
                    'Explicit market purchase; exact eBay item '+row['item_id']])
        ebay_orders.event(db,row['record_id'],None,purchased['delivery_status'],'Today: selected market purchase',
                          purchased['delivered_at'] or purchased['shipped_at'] or purchased['ordered_at'])
    columns = {r['name'] for r in db.execute('PRAGMA table_info(banknotes)')}
    assignments = "order_number=?,marketplace='eBay'"
    values = [item['order_id']]
    if 'updated_at' in columns:
        assignments += ',updated_at=?'
        values.append(ebay_orders.now_iso())
    changed = db.execute('UPDATE banknotes SET '+assignments+
                         " WHERE id=? AND order_number IS NULL AND (marketplace IS NULL OR marketplace IN ('','eBay'))",
                         values+[row['record_id']]).rowcount
    if changed != 1:
        raise ValueError('The record changed before its order number could be saved')
    db.execute("UPDATE market_purchase_captures SET status='done',message=?,browser_state='' WHERE id=?",
               ['Order '+item['order_id']+' captured from eBay Purchases.',row['id']])
    db.commit()
    return dict(ok=True,status='done')


def register(app, get_db, require_owner):
    @app.context_processor
    def market_purchase_context():
        def current(record_id):
            user = g.get('current_user')
            return None if user and user.get('role') != 'owner' else state(get_db(),record_id)
        return dict(market_purchase_capture=current)

    @app.get('/banknotes/<record_id>/market-purchase-status')
    def banknote_market_purchase_status(record_id):
        require_owner()
        result = state(get_db(),record_id)
        if result is None:
            abort(404)
        response = jsonify(result)
        response.headers['Cache-Control'] = 'private, no-store'
        return response
