"""Today bridge: eBay Purchases is authoritative; other sellers' mail is review-only."""
from datetime import datetime, timezone
import hmac
import os
import re
import uuid

from flask import Blueprint, abort, jsonify, request
import ebay_orders as ebay


def configured():
    return len(os.environ.get('STUFFAPP_TODAY_TOKEN', '')) >= 32


def text(raw, key, limit, pattern=None, empty=False):
    value = raw.get(key)
    if not isinstance(value, str) or len(value) > limit or (not empty and not value.strip()):
        raise ValueError('Missing or invalid ' + key)
    if pattern and not re.fullmatch(pattern, value):
        raise ValueError('Invalid ' + key)
    return value.strip()


def date_only(value, ordered=None):
    try:
        if ordered:
            value = re.sub(r'^[A-Za-z]{3},\s*', '', value)
            year = int(ordered[:4])
            dt = datetime.strptime(value + ' ' + str(year), '%b %d %Y').replace(tzinfo=timezone.utc)
            if dt.date() < datetime.fromisoformat(ordered.replace('Z', '+00:00')).date():
                dt = dt.replace(year=year + 1)
        else:
            dt = datetime.strptime(value, '%b %d, %Y').replace(tzinfo=timezone.utc)
        return ebay.timestamp(dt.isoformat(), observed=True)
    except (ValueError, TypeError):
        return None


def validate_purchase(raw):
    if not isinstance(raw, dict):
        raise ValueError('Invalid purchase')
    result = {k: text(raw, k, n, p) for k, n, p in [
        ('order_id', 14, r'\d{2}-\d{5}-\d{5}'), ('item_id', 15, r'\d{9,15}'),
        ('title', 500, None), ('seller', 150, r'[\w.%-]+'), ('status_text', 300, None)]}
    result['delivery_text'] = text(raw, 'delivery_text', 500, empty=True)
    result['ordered_at'] = date_only(text(raw, 'ordered_date', 40))
    if not result['ordered_at']:
        raise ValueError('Invalid order date')
    quantity = raw.get('quantity')
    if type(quantity) is not int or not 1 <= quantity <= 999:
        raise ValueError('Invalid quantity')
    result['quantity'] = quantity
    result.update(delivery_status='Ordered', shipped_at=None, delivered_at=None, attention='')
    status, delivery = result['status_text'].lower(), result['delivery_text']
    if re.search(r'cancel|refund|return|not delivered|failed', status, re.I):
        result['attention'] = result['status_text']
    elif status == 'delivered' and delivery.startswith('Delivered on '):
        delivered = date_only(delivery[len('Delivered on '):], result['ordered_at'])
        if not delivered:
            raise ValueError('Invalid confirmed delivery date')
        result.update(delivery_status='Delivered', delivered_at=delivered)
    elif status in ('shipped', 'in transit', 'out for delivery'):
        result['delivery_status'] = 'Shipped'
        # Observation time is not a shipping time. Leave the latter unknown.
    elif status not in ('awaiting shipment', 'paid', 'order placed', 'ordered'):
        result['attention'] = result['status_text'] + '; shipment or delivery not confirmed'
    if raw.get('identity_ambiguous') is True:
        result.update(delivery_status='Ordered', shipped_at=None, delivered_at=None,
                      attention='Multiple purchase rows share this identity; review required')
    return result


def validate_mail(raw):
    if not isinstance(raw, dict):
        raise ValueError('Invalid merchant notice')
    result = {k: text(raw, k, n, p) for k, n, p in [
        ('message_id', 64, r'[a-f0-9]{64}'), ('sender', 254, r'[^@\s]+@[^@\s]+\.[^@\s]+'),
        ('subject', 500, None), ('order_id', 50, r'[A-Za-z0-9][A-Za-z0-9-]{3,49}'),
        ('evidence', 300, None), ('status', 20, r'Ordered|Shipped|Delivered')]}
    if re.search(r'\bebay\b', ' '.join(result.values()), re.I):
        raise ValueError('eBay emails are not a shipment source')
    result['observed_at'] = ebay.timestamp(raw.get('observed_at'), observed=True)
    if not result['observed_at']:
        raise ValueError('Invalid notice timestamp')
    return result


def validate_purchases(raw):
    items, skipped, seen = [], {}, set()
    for index, item in enumerate(raw):
        order_id = item.get('order_id') if isinstance(item, dict) else None
        if not isinstance(order_id, str) or not re.fullmatch(r'\d{2}-\d{5}-\d{5}', order_id):
            order_id = None
        try:
            evidence = validate_purchase(item)
            key = (evidence['order_id'], evidence['item_id'])
            if key in seen:
                raise ValueError('Duplicate purchase identity')
            seen.add(key)
            items.append(evidence)
        except ValueError as exc:
            skipped.setdefault(order_id or 'row:' + str(index),
                               dict(order_id=order_id, reason=str(exc)))
    # A bad line holds the entire order, including valid sibling items.
    return [i for i in items if i['order_id'] not in skipped], list(skipped.values())


def apply_purchases(db, items, observed, auto_match=True):
    totals = dict(items_seen=0, matched=0, updated=0)
    existing, skipped = {}, {}
    for evidence in items:
        key = (evidence['order_id'], evidence['item_id'])
        rows = db.execute('SELECT * FROM ebay_order_items WHERE order_id=? AND item_id=?',
                          key).fetchall()
        if len(rows) > 1:
            skipped[evidence['order_id']] = dict(order_id=evidence['order_id'],
                reason='Ambiguous stored purchase identity; review required')
        existing[key] = rows[0] if rows else None
    for evidence in items:
        if evidence['order_id'] in skipped:
            continue
        old = existing[(evidence['order_id'], evidence['item_id'])]
        key = old['line_key'] if old else 'purchases:' + evidence['order_id'] + ':' + evidence['item_id']
        seen = db.execute('SELECT observed_at FROM ebay_purchase_observations WHERE line_key=?', (key,)).fetchone()
        if seen and seen['observed_at'] >= observed:
            continue
        item = {k: evidence[k] for k in ('order_id', 'item_id', 'title', 'seller', 'quantity',
                'ordered_at', 'shipped_at', 'delivered_at', 'delivery_status', 'attention')}
        item.update(line_key=key, seller_key=old['seller_key'] if old else '', estimated_delivery=None, tracking=[])
        result = ebay.apply_items(db, [item], source='Today: eBay Purchases', auto_match=False, authoritative=True)
        for k in totals:
            totals[k] += result[k]
        if result['items_seen']:
            db.execute('INSERT INTO ebay_purchase_observations VALUES (?,?,?,?) '
                       'ON CONFLICT(line_key) DO UPDATE SET observed_at=excluded.observed_at, '
                       'status_text=excluded.status_text,delivery_text=excluded.delivery_text',
                       (key, observed, evidence['status_text'], evidence['delivery_text']))
    # Missing orders could conceal repeat purchases. Update existing links, but
    # do not infer new collection matches from an incomplete order set.
    if auto_match and not skipped:
        result = ebay.apply_items(db, [], source='Today: eBay Purchases')
        totals['matched'] += result['matched']
        totals['updated'] += result['updated']
    return dict(totals, skipped=list(skipped.values()),
                items_accepted=sum(i['order_id'] not in skipped for i in items))


def register(app, get_db):
    bp = Blueprint('ebay_mail', __name__)

    @bp.post('/ebay/today')
    def receive():
        secret = os.environ.get('STUFFAPP_TODAY_TOKEN', '')
        supplied = request.headers.get('Authorization', '')
        if not configured() or not hmac.compare_digest(supplied.encode(), ('Bearer ' + secret).encode()):
            abort(401)
        if request.content_length is None or request.content_length > 2 * 1024 * 1024:
            abort(413)
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            abort(400)
        source = payload.get('source')
        if source not in ('ebay_purchases', 'merchant_email'):
            return jsonify(error='eBay email updates are retired. Use eBay Purchases.'), 410
        try:
            if source == 'ebay_purchases':
                account = text(payload, 'account', 100, r'[\w.%-]+').lower()
                observed = ebay.timestamp(payload.get('observed_at'), observed=True)
                raw = payload.get('items')
                if not observed or not isinstance(raw, list) or not 1 <= len(raw) <= 2000:
                    raise ValueError('Invalid Purchases snapshot')
                items, skipped = validate_purchases(raw)
            else:
                raw = payload.get('events')
                if not isinstance(raw, list) or len(raw) > 100:
                    raise ValueError('Invalid merchant notices')
                items = [validate_mail(i) for i in raw]
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('INSERT OR IGNORE INTO ebay_mail_connection (id) VALUES (1)')
            if not db.execute('SELECT enabled FROM ebay_mail_connection WHERE id=1').fetchone()[0]:
                db.rollback()
                return jsonify(error='Today purchase updates are paused in StuffApp'), 409
            if source == 'ebay_purchases':
                if db.execute('SELECT 1 FROM ebay_deleted_accounts WHERE identity_hash=?', (ebay.digest(account),)).fetchone():
                    db.rollback()
                    return jsonify(error='This eBay account was removed; updates are stopped'), 409
                owner = db.execute('SELECT account_name FROM ebay_purchase_account WHERE id=1').fetchone()
                api_owner = db.execute('SELECT account_name FROM ebay_connection WHERE id=1').fetchone()
                if any(r and r[0].lower() != account for r in (owner, api_owner)):
                    db.rollback()
                    return jsonify(error='eBay account does not match this connection'), 409
                db.execute('INSERT OR IGNORE INTO ebay_purchase_account VALUES (1,?)', (account,))
                result = apply_purchases(db, items, observed,
                    auto_match=not skipped and not payload.get('skipped'))
                result['skipped'] = skipped + result['skipped']
            else:
                added = 0
                for item in items:
                    added += db.execute('INSERT OR IGNORE INTO merchant_purchase_notices '
                        '(message_id,sender,subject,order_id,status,observed_at,evidence) VALUES (?,?,?,?,?,?,?)',
                        tuple(item[k] for k in ('message_id', 'sender', 'subject', 'order_id', 'status', 'observed_at', 'evidence'))).rowcount
                result = dict(items_seen=added, matched=0, updated=0)
            now = ebay.now_iso()
            if source == 'ebay_purchases':
                db.execute('UPDATE ebay_mail_connection SET last_received=? WHERE id=1', (now,))
                db.execute('INSERT INTO ebay_sync_runs (id,started_at,finished_at,status,items_seen,matched,updated) '
                           'VALUES (?,?,?,?,?,?,?)', ('purchases:' + uuid.uuid4().hex, now, now, 'done',
                            result['items_seen'], result['matched'], result['updated']))
            db.commit()
        except ValueError as exc:
            db.rollback()
            return jsonify(error=str(exc)), 409
        except Exception:
            db.rollback()
            raise
        return jsonify(ok=True, **result)

    app.register_blueprint(bp)
