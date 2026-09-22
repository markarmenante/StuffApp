"""Receive minimal eBay order evidence from Today's existing Apple Mail reader."""
import hmac
import os
import re
import uuid

from flask import Blueprint, abort, jsonify, request

import ebay_orders as ebay


def configured():
    return len(os.environ.get('STUFFAPP_TODAY_TOKEN', '')) >= 32


def validate_event(raw):
    if not isinstance(raw, dict):
        raise ValueError('Invalid email evidence')
    patterns = {'message_id': r'[a-f0-9]{64}', 'item_id': r'\d{9,15}', 'order_id': r'\d{2}-\d{5}-\d{5}'}
    for key, pattern in patterns.items():
        if not isinstance(raw.get(key), str) or not re.fullmatch(pattern, raw[key]):
            raise ValueError('Missing exact email or order identity')
    if not isinstance(raw.get('status'), str) or raw['status'] not in ebay.RANK:
        raise ValueError('Invalid shipment status')
    when = ebay.timestamp(raw.get('observed_at'), observed=True)
    if not when:
        raise ValueError('Invalid email timestamp')
    quantity = raw.get('quantity')
    if type(quantity) is not int or not 1 <= quantity <= 999:
        raise ValueError('Invalid item quantity')
    for key, limit in [('title', 500), ('seller', 150), ('evidence', 300)]:
        if not isinstance(raw.get(key), str) or not raw[key].strip() or len(raw[key]) > limit:
            raise ValueError('Incomplete email evidence')
    result = {key: raw[key] for key in (*patterns, 'status', 'quantity', 'title', 'seller', 'evidence')}
    result['observed_at'] = when
    return result


def apply_events(db, events):
    totals = {'items_seen': 0, 'matched': 0, 'updated': 0}
    for evidence in sorted(events, key=lambda e: e['observed_at']):
        if db.execute('SELECT 1 FROM ebay_mail_receipts WHERE message_id=?', (evidence['message_id'],)).fetchone():
            continue
        # Reuse an API-imported order if present; ambiguous API rows stay held.
        rows = db.execute('SELECT * FROM ebay_order_items WHERE order_id=? AND item_id=?',
                          (evidence['order_id'], evidence['item_id'])).fetchall()
        if len(rows) > 1:
            continue
        old = rows[0] if rows else None
        key = old['line_key'] if old else 'mail:' + evidence['order_id'] + ':' + evidence['item_id']
        status = evidence['status']
        item = {
            'line_key': key, 'item_id': evidence['item_id'], 'order_id': evidence['order_id'],
            'title': evidence['title'], 'seller': evidence['seller'],
            'seller_key': old['seller_key'] if old else '',
            'quantity': max(old['quantity'] if old else 1, evidence['quantity']),
            'ordered_at': evidence['observed_at'] if status == 'Ordered' else None,
            'shipped_at': evidence['observed_at'] if status == 'Shipped' else None,
            'delivered_at': evidence['observed_at'] if status == 'Delivered' else None,
            'estimated_delivery': old['estimated_delivery'] if old else None,
            'delivery_status': status, 'attention': old['attention'] if old else '', 'tracking': [],
        }
        result = ebay.apply_items(db, [item], source='Today: eBay email', auto_match=False)
        for field in totals:
            totals[field] += result[field]
        if db.execute('SELECT 1 FROM ebay_order_items WHERE line_key=?', (key,)).fetchone():
            db.execute('INSERT INTO ebay_mail_receipts (message_id,line_key,status,evidence,received_at) VALUES (?,?,?,?,?)',
                       (evidence['message_id'], key, status, evidence['evidence'], evidence['observed_at']))
    # A note may have been added since the last email arrived.
    result = ebay.apply_items(db, [], source='Today: eBay email')
    totals['matched'] += result['matched']
    totals['updated'] += result['updated']
    return totals


def register(app, get_db):
    bp = Blueprint('ebay_mail', __name__)

    @bp.post('/ebay/today')
    def receive():
        secret = os.environ.get('STUFFAPP_TODAY_TOKEN', '')
        supplied = request.headers.get('Authorization', '')
        if not configured() or not hmac.compare_digest(supplied.encode(), ('Bearer ' + secret).encode()):
            abort(401)
        if request.content_length is None or request.content_length > 256 * 1024:
            abort(413)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict) or not isinstance(payload.get('events'), list) or len(payload['events']) > 100:
            abort(400)
        try:
            events = [validate_event(event) for event in payload['events']]
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO ebay_mail_connection (id) VALUES (1)')
        state = db.execute('SELECT * FROM ebay_mail_connection WHERE id=1').fetchone()
        if not state['enabled']:
            db.rollback()
            return jsonify(error='Email updates are paused in StuffApp'), 409
        result = apply_events(db, events)
        now = ebay.now_iso()
        db.execute('UPDATE ebay_mail_connection SET last_received=? WHERE id=1', (now,))
        if events:
            db.execute('INSERT INTO ebay_sync_runs (id,started_at,finished_at,status,items_seen,matched,updated) '
                       'VALUES (?,?,?,?,?,?,?)', ('mail:' + uuid.uuid4().hex, now, now, 'done',
                                                result['items_seen'], result['matched'], result['updated']))
        db.commit()
        return jsonify(ok=True, **result)

    app.register_blueprint(bp)
