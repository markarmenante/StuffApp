"""Read-only eBay buyer API; automatic, evidence-based banknote deliveries.

Only GetUser and GetOrders are permitted Trading calls. Never place orders,
mark items shipped on eBay, change collection metadata, or use search snippets.
"""
import base64
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import fcntl
import hashlib
import hmac
import html
import json
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, build_opener, HTTPRedirectHandler
import uuid
import xml.etree.ElementTree as ET

from cryptography.fernet import Fernet, InvalidToken
from defusedxml.ElementTree import fromstring
from flask import (Blueprint, abort, flash, g, jsonify, redirect,
                   render_template, request, session, url_for)

SCOPE = 'https://api.ebay.com/oauth/api_scope'
NS = 'urn:ebay:apis:eBLBaseComponents'
RANK = {'Ordered': 0, 'Shipped': 1, 'Delivered': 2}
NOTE_WORDS = re.compile(r'\b(banknotes?|paper money|currency|PMG|Pick[ -]?\d|piastres?|francs?|rupees?|shillings?)\b', re.I)
EBAY_HOST = re.compile(r'(?:[a-z0-9-]+\.)*ebay\.(?:com|ca|co\.uk|com\.au|de|fr|it|es|at|be|ch|ie|nl|pl|com\.sg|com\.hk)$', re.I)


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00', 'Z')


def timestamp(value, observed=False):
    """Normalize timestamps; future estimates must never prove delivery."""
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        if dt.tzinfo is None:
            return None
        dt = dt.astimezone(timezone.utc)
        if observed and dt > datetime.now(timezone.utc) + timedelta(minutes=5):
            return None
        return dt.isoformat(timespec='seconds').replace('+00:00', 'Z')
    except (ValueError, TypeError):
        return None


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def listing_id(url):
    try:
        p = urlparse(html.unescape(str(url)).strip())
        if p.scheme not in ('https', 'http') or not EBAY_HOST.fullmatch(p.hostname or ''):
            return None
        m = re.fullmatch(r'/(?:ulk/)?itm/(?:[^/]+/)?(\d{9,15})/?', p.path)
        return m.group(1) if m else None
    except ValueError:
        return None


class EbayError(Exception):
    """Only safe, curated messages may reach logs or the dashboard."""


class Reauthorize(EbayError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward OAuth credentials to a redirected host.


class EbayClient:
    def __init__(self, client_id=None, client_secret=None, runame=None):
        self.client_id = client_id or os.environ.get('EBAY_CLIENT_ID', '')
        self.client_secret = client_secret or os.environ.get('EBAY_CLIENT_SECRET', '')
        self.runame = runame or os.environ.get('EBAY_RUNAME', '')

    @property
    def configured(self):
        return bool(self.client_id and self.client_secret and self.runame)

    def authorize_url(self, state):
        return 'https://auth.ebay.com/oauth2/authorize?' + urlencode({
            'client_id': self.client_id, 'redirect_uri': self.runame,
            'response_type': 'code', 'scope': SCOPE, 'state': state,
        })

    def _request(self, url, data=None, headers=None):
        req = Request(url, data=data, headers=headers or {})
        try:
            with build_opener(NoRedirect()).open(req, timeout=25) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                if len(raw) > 8 * 1024 * 1024:
                    raise EbayError('eBay response too large; no updates were applied.')
                return raw
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise Reauthorize('eBay authorization needs attention. Reconnect your account.') from None
            if exc.code == 400 and '/oauth2/token' in url:
                raise Reauthorize('eBay could not renew authorization. Reconnect your account.') from None
            raise EbayError(f'eBay returned HTTP {exc.code}; no order updates were applied.') from None
        except (URLError, TimeoutError, OSError):
            raise EbayError('eBay could not be reached. The next scheduled check will retry.') from None

    def token(self, *, code=None, refresh_token=None):
        if not self.configured:
            raise EbayError('The eBay application needs one-time setup.')
        fields = ({'grant_type': 'authorization_code', 'code': code,
                   'redirect_uri': self.runame} if code else
                  {'grant_type': 'refresh_token', 'refresh_token': refresh_token,
                   'scope': SCOPE})
        raw = self._request('https://api.ebay.com/identity/v1/oauth2/token',
                            urlencode(fields).encode(), {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Basic ' + base64.b64encode(
                (self.client_id + ':' + self.client_secret).encode()).decode(),
        })
        try:
            data = json.loads(raw)
            if not data.get('access_token') or int(data.get('expires_in', 0)) < 1:
                raise ValueError()
            if code and not data.get('refresh_token'):
                raise ValueError()
            return data
        except (ValueError, TypeError):
            raise EbayError('eBay returned an incomplete authorization response.') from None

    def trading(self, call, access_token, fields=()):
        if call not in ('GetOrders', 'GetUser'):
            raise ValueError('Only read-only buyer API calls are permitted')
        root = ET.Element(call + 'Request', xmlns=NS)
        ET.SubElement(root, 'DetailLevel').text = 'ReturnAll'
        for name, value in fields:
            parent = root
            parts = name.split('/')
            for part in parts[:-1]:
                node = parent.find(part)
                parent = node if node is not None else ET.SubElement(parent, part)
            ET.SubElement(parent, parts[-1]).text = str(value)
        raw = self._request('https://api.ebay.com/ws/api.dll',
                            ET.tostring(root, encoding='utf-8', xml_declaration=True), {
            'Content-Type': 'text/xml; charset=utf-8',
            'X-EBAY-API-CALL-NAME': call,
            'X-EBAY-API-SITEID': '0',
            'X-EBAY-API-COMPATIBILITY-LEVEL': '1477',
            'X-EBAY-API-IAF-TOKEN': access_token,
        })
        return parse_response(raw, call)

    def identity(self, access_token):
        root = self.trading('GetUser', access_token)
        user = root.find('User')
        name = text_at(user, 'UserID')
        stable = text_at(user, 'EIASToken') or name
        if not stable or not name:
            raise EbayError('eBay did not identify the connected account.')
        return digest(stable), name

    def orders(self, access_token):
        # Fixed window across pages; exclude eBay's in-flight order consolidation.
        end = datetime.now(timezone.utc) - timedelta(minutes=2)
        start = end - timedelta(days=89)
        items, seen = [], set()
        for page in range(1, 51):
            root = self.trading('GetOrders', access_token, (
                ('OrderRole', 'Buyer'), ('OrderStatus', 'All'),
                ('CreateTimeFrom', start.isoformat()), ('CreateTimeTo', end.isoformat()),
                ('Pagination/EntriesPerPage', 100), ('Pagination/PageNumber', page),
            ))
            batch = parse_orders(root)
            keys = {item['line_key'] for item in batch}
            if keys & seen:
                raise EbayError('eBay repeated an order page; no updates were applied.')
            seen.update(keys)
            items.extend(batch)
            if text_at(root, 'HasMoreOrders').lower() != 'true':
                return items
        raise EbayError('eBay returned too many order pages; no updates were applied.')


def text_at(element, path):
    return (element.findtext(path) or '').strip() if element is not None else ''


def parse_response(raw, call='GetOrders'):
    try:
        root = fromstring(raw)
        for el in root.iter():
            el.tag = el.tag.rsplit('}', 1)[-1]
        if root.tag != call + 'Response':
            raise ValueError()
    except Exception:
        raise EbayError('eBay returned an invalid response; no updates were applied.') from None
    errors = [e for e in root.findall('Errors') if text_at(e, 'SeverityCode') == 'Error']
    if errors or text_at(root, 'Ack') not in ('Success', 'Warning'):
        codes = {text_at(e, 'ErrorCode') for e in errors}
        if codes & {'931', '932', '940', '941', '942', '16110'}:
            raise Reauthorize('eBay authorization has expired or was revoked. Reconnect your account.')
        raise EbayError('eBay rejected the order request; check application access and try again.')
    return root


def package_dates(node):
    packages = node.findall('ShippingServiceSelected/ShippingPackageInfo') if node is not None else []
    actual = [timestamp(text_at(p, 'ActualDeliveryTime'), observed=True) for p in packages]
    # Every package must be delivered. Estimates and tracking creation are not proof.
    delivered = max(actual) if actual and all(actual) else None
    estimates = [timestamp(text_at(p, 'ScheduledDeliveryTimeMax') or
                           text_at(p, 'EstimatedDeliveryTimeMax')) for p in packages]
    return delivered, max((d for d in estimates if d), default=None)


def parse_orders(root):
    items = []
    for order in root.findall('OrderArray/Order'):
        transactions = order.findall('TransactionArray/Transaction')
        for tx in transactions:
            item_id = text_at(tx, 'Item/ItemID')
            transaction_id = text_at(tx, 'TransactionID')
            if not item_id.isdigit() or not transaction_id.isdigit():
                raise EbayError('eBay omitted an order item identity; no updates were applied.')
            try:
                quantity = int(text_at(tx, 'QuantityPurchased'))
                if quantity < 1:
                    raise ValueError()
            except ValueError:
                raise EbayError('eBay omitted an order quantity; no updates were applied.') from None
            delivered, estimated = package_dates(tx)
            shipped = timestamp(text_at(tx, 'ShippedTime'), observed=True)
            # Never apply one combined order's package to unrelated line items.
            source_nodes = [tx]
            if len(transactions) == 1:
                if not tx.findall('ShippingServiceSelected/ShippingPackageInfo'):
                    delivered, estimated = package_dates(order)
                shipped = shipped or timestamp(text_at(order, 'ShippedTime'), observed=True)
                source_nodes.append(order)
            tracking = set()
            for node in source_nodes:
                for track in node.findall('ShippingDetails/ShipmentTrackingDetails'):
                    carrier = text_at(track, 'ShippingCarrierUsed')[:80]
                    number = text_at(track, 'ShipmentTrackingNumber')[:100]
                    if carrier and number:
                        tracking.add((carrier, number))
            attention = ''
            cancel = text_at(tx, 'Status/CancelStatus') or text_at(order, 'CancelStatus')
            if cancel not in ('', 'NotApplicable', 'Invalid', 'CancelRejected', 'CancelClosedNoRefund'):
                attention = 'Cancellation or refund reported by eBay — review required'
            if text_at(order, 'OrderStatus') in ('Cancelled', 'CancelPending', 'Inactive'):
                attention = 'Order is cancelled or inactive — review required'
            if text_at(order, 'OrderStatus') in ('Pending', 'Incomplete') and not text_at(order, 'PaidTime'):
                attention = attention or 'Payment is not confirmed by eBay — review required'
            items.append({
                'line_key': item_id + '-' + transaction_id,
                'order_id': text_at(order, 'OrderID'), 'item_id': item_id,
                'title': text_at(tx, 'Item/Title')[:500],
                'seller': text_at(order, 'SellerUserID')[:150],
                'seller_key': digest(text_at(order, 'SellerEIASToken')) if text_at(order, 'SellerEIASToken') else '',
                'quantity': quantity,
                'ordered_at': timestamp(text_at(tx, 'CreatedDate') or text_at(order, 'CreatedTime'), observed=True),
                'shipped_at': shipped, 'delivered_at': delivered,
                'estimated_delivery': estimated,
                'delivery_status': 'Delivered' if delivered else ('Shipped' if shipped else 'Ordered'),
                'attention': attention, 'tracking': sorted(tracking),
            })
    return items


def init_schema(db):
    db.executescript(Path(__file__).with_name('ebay_schema.sql').read_text())
    with db:
        db.execute('BEGIN IMMEDIATE')
        sql = db.execute("SELECT sql FROM sqlite_master WHERE name='banknote_ebay_links'").fetchone()[0]
        if "'details'" not in sql:
            # Rebuild only the link table to widen its CHECK, preserving every link/override.
            db.execute(sql.replace('banknote_ebay_links', 'banknote_ebay_links_v2', 1)
                       .replace("'listing','manual'", "'listing','manual','details'"))
            db.execute("ALTER TABLE banknote_ebay_links_v2 ADD COLUMN match_evidence TEXT NOT NULL DEFAULT ''")
            db.execute('INSERT INTO banknote_ebay_links_v2 '
                       '(banknote_id,line_key,matched_by,matched_at,manual_status) '
                       'SELECT banknote_id,line_key,matched_by,matched_at,manual_status FROM banknote_ebay_links')
            db.execute('DROP TABLE banknote_ebay_links')
            db.execute('ALTER TABLE banknote_ebay_links_v2 RENAME TO banknote_ebay_links')
    db.commit()


def detail_match_plan(db):
    from ebay_matching import plan_matches
    return plan_matches([dict(r) for r in db.execute('SELECT * FROM banknotes')],
                        [dict(r) for r in db.execute('SELECT * FROM ebay_order_items')],
                        [dict(r) for r in db.execute('SELECT * FROM banknote_ebay_links')],
                        listing_candidates(db))


def listing_candidates(db):
    """Only purchase-source links, never comparison or historical references."""
    candidates = defaultdict(set)
    notes = db.execute("SELECT id, description, note_references FROM banknotes "
                       "WHERE status IS NULL OR status IN ('','Own','Owned','Ordered')").fetchall()
    eligible = {r['id'] for r in notes}
    for row in notes:
        for line in (row['description'] or '').splitlines():
            if line.strip().startswith('Listing: '):
                item_id = listing_id(line.strip()[9:])
                if item_id:
                    candidates[item_id].add(row['id'])
        for line in (row['note_references'] or '').splitlines():
            if re.match(r'^Market Scan \d{4}-\d{2}-\d{2}:', line):
                for url in re.findall(r'https?://\S+', line):
                    item_id = listing_id(url)
                    if item_id:
                        candidates[item_id].add(row['id'])
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='market_scan_items'").fetchone():
        for row in db.execute("SELECT record_id, payload FROM market_scan_items "
                              "WHERE category='banknotes' AND status='ordered' AND record_id IS NOT NULL"):
            if row['record_id'] in eligible:
                try:
                    item_id = listing_id(json.loads(row['payload']).get('listing_url'))
                    if item_id:
                        candidates[item_id].add(row['record_id'])
                except (ValueError, TypeError, AttributeError):
                    pass
    return candidates


def event(db, banknote_id, previous, new, source, occurred=None):
    if previous != new:
        now = now_iso()
        db.execute('INSERT INTO ebay_status_events '
                   '(banknote_id,previous_status,new_status,source,occurred_at,observed_at) '
                   'VALUES (?,?,?,?,?,?)', (banknote_id, previous, new, source, occurred or now, now))
        return 1
    return 0


def apply_items(db, items, source='eBay', auto_match=True):
    """Caller owns the transaction; a partial network page never reaches here."""
    candidates = listing_candidates(db)
    linked = {r['line_key']: dict(r) for r in db.execute('SELECT * FROM banknote_ebay_links')}
    suppressed = {r[0] for r in db.execute('SELECT identity_hash FROM ebay_deleted_accounts')}
    relevant = [i for i in items if not ({i['seller_key'], digest(i['seller'].lower())} & suppressed)
                and (i['line_key'] in linked or i['item_id'] in candidates or NOTE_WORDS.search(i['title']))]
    now, updates, matches = now_iso(), 0, 0
    for item in relevant:
        old = db.execute('SELECT * FROM ebay_order_items WHERE line_key=?', (item['line_key'],)).fetchone()
        status = item['delivery_status']
        # Exceptions do not advance a shipment. Missing/older evidence never regresses it.
        if item['attention']:
            status = old['delivery_status'] if old else 'Ordered'
        elif old and RANK[old['delivery_status']] > RANK[status]:
            status = old['delivery_status']
        values = dict(item, delivery_status=status, last_seen=now)
        for field in ('ordered_at', 'shipped_at', 'delivered_at'):
            values[field] = (old[field] if old else None) or item[field]
        fields = [k for k in values if k != 'tracking']
        db.execute('INSERT INTO ebay_order_items (' + ','.join(fields) + ') VALUES (' +
                   ','.join('?' for _ in fields) + ') ON CONFLICT(line_key) DO UPDATE SET ' +
                   ','.join(k + '=excluded.' + k for k in fields if k != 'line_key'),
                   [values[k] for k in fields])
        for carrier, number in item['tracking']:
            db.execute('INSERT OR IGNORE INTO ebay_item_tracking VALUES (?,?,?)',
                       (item['line_key'], carrier, number))
        link = linked.get(item['line_key'])
        if link and link['manual_status'] is None:
            updates += event(db, link['banknote_id'], old['delivery_status'] if old else None,
                             status, source, values.get('delivered_at') or values.get('shipped_at') or values.get('ordered_at'))
    if not auto_match:
        return {'items_seen': len(relevant), 'matched': 0, 'updated': updates}
    # Count all stored orders too: repeat purchases of a multi-quantity listing
    # must never silently attach the latest purchase to an older physical note.
    counts = Counter(r['item_id'] for r in db.execute('SELECT item_id FROM ebay_order_items'))
    occupied = {r['banknote_id'] for r in db.execute('SELECT banknote_id FROM banknote_ebay_links')}
    reverse = Counter(note for ids in candidates.values() for note in ids)
    for item in db.execute('SELECT i.* FROM ebay_order_items i LEFT JOIN banknote_ebay_links l '
                           'ON l.line_key=i.line_key WHERE l.line_key IS NULL AND i.ignored=0').fetchall():
        ids = candidates.get(item['item_id'], set())
        if len(ids) != 1 or counts[item['item_id']] != 1 or item['quantity'] != 1 or item['attention']:
            continue
        note_id = next(iter(ids))
        if note_id in occupied or reverse[note_id] != 1:
            continue
        db.execute('INSERT INTO banknote_ebay_links (banknote_id,line_key,matched_by,matched_at) VALUES (?,?,?,?)',
                   (note_id, item['line_key'], 'listing', now))
        occupied.add(note_id)
        matches += 1
        updates += event(db, note_id, None, item['delivery_status'], source + ' · exact listing',
                         item['delivered_at'] or item['shipped_at'] or item['ordered_at'])
    automatic, _ = detail_match_plan(db)
    for key, match in automatic.items():
        item = db.execute('SELECT * FROM ebay_order_items WHERE line_key=?', (key,)).fetchone()
        db.execute('INSERT INTO banknote_ebay_links '
                   '(banknote_id,line_key,matched_by,matched_at,match_evidence) VALUES (?,?,?,?,?)',
                   (match['banknote_id'], key, 'details', now, ', '.join(match['evidence'])))
        matches += 1
        updates += event(db, match['banknote_id'], None, item['delivery_status'],
                         source + ' · identity match: ' + ', '.join(match['evidence']),
                         item['delivered_at'] or item['shipped_at'] or item['ordered_at'])
    return {'items_seen': len(relevant), 'matched': matches, 'updated': updates}


class OrderSync:
    def __init__(self, app, open_db, data_dir, client=None):
        self.app, self.open_db, self.data_dir = app, open_db, Path(data_dir)
        self.client = client or EbayClient()
        self.interval = max(900, int(os.environ.get('EBAY_SYNC_INTERVAL_SECONDS', '1800')))
        self.lock = threading.Lock()
        self.wake = threading.Event()
        self.worker_enabled = os.environ.get('EBAY_SYNC_WORKER') == '1'

    def cipher(self):
        key = os.environ.get('EBAY_TOKEN_ENCRYPTION_KEY')
        if not key:
            path = self.data_dir / '.ebay-token-key'
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(fd, 'wb') as out:
                    out.write(Fernet.generate_key())
            key = path.read_bytes()
        try:
            return Fernet(key)
        except (ValueError, TypeError):
            raise EbayError('The eBay token encryption key needs attention.') from None

    def encrypt(self, value):
        return self.cipher().encrypt(value.encode()).decode()

    def decrypt(self, value):
        try:
            return self.cipher().decrypt(value.encode()).decode()
        except (InvalidToken, AttributeError):
            raise Reauthorize('Saved eBay authorization cannot be opened. Reconnect your account.') from None

    @contextmanager
    def exclusive(self):
        if not self.lock.acquire(blocking=False):
            yield False
            return
        try:
            with open(self.data_dir / '.ebay-sync.lock', 'a') as handle:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    yield False
                    return
                try:
                    yield True
                finally:
                    fcntl.flock(handle, fcntl.LOCK_UN)
        finally:
            self.lock.release()

    def access_token(self, db, conn):
        if conn['access_token'] and conn['access_expires'] > time.time() + 90:
            return self.decrypt(conn['access_token'])
        token = self.client.token(refresh_token=self.decrypt(conn['refresh_token']))
        db.execute('UPDATE ebay_connection SET access_token=?, access_expires=?, refresh_token=? '
                   'WHERE id=1 AND generation=?',
                   (self.encrypt(token['access_token']), time.time() + int(token['expires_in']),
                    self.encrypt(token['refresh_token']) if token.get('refresh_token') else conn['refresh_token'],
                    conn['generation']))
        db.commit()
        return token['access_token']

    def run_once(self, force=False):
        with self.exclusive() as acquired:
            if not acquired:
                return {'status': 'busy'}
            db, run_id = self.open_db(), None
            try:
                conn = db.execute('SELECT * FROM ebay_connection WHERE id=1').fetchone()
                if not conn or not conn['enabled'] or not conn['refresh_token'] or not self.client.configured:
                    return {'status': 'not_connected_or_paused'}
                if conn['last_attempt'] and not force:
                    last = datetime.fromisoformat(conn['last_attempt'].replace('Z', '+00:00')).timestamp()
                    if time.time() - last < self.interval:
                        return {'status': 'not_due'}
                run_id, started = str(uuid.uuid4()), now_iso()
                db.execute("UPDATE ebay_sync_runs SET status='interrupted', finished_at=?, error=? WHERE status='running'",
                           (started, 'Interrupted by an application restart; the next check retries.'))
                db.execute("INSERT INTO ebay_sync_runs (id,started_at,status) VALUES (?,?,'running')", (run_id, started))
                db.execute('UPDATE ebay_connection SET last_attempt=? WHERE id=1', (started,))
                db.commit()
                token = self.access_token(db, conn)
                items = self.client.orders(token)
                db.execute('BEGIN IMMEDIATE')
                current = db.execute('SELECT generation,enabled,account_key,connected_at FROM ebay_connection WHERE id=1').fetchone()
                if (not current or current['generation'] != conn['generation'] or not current['enabled']
                        or current['account_key'] != conn['account_key'] or current['connected_at'] != conn['connected_at']):
                    raise EbayError('Connection changed while checking; no updates were applied.')
                result = apply_items(db, items)
                finished = now_iso()
                db.execute('UPDATE ebay_connection SET last_success=?, error=NULL WHERE id=1', (finished,))
                db.execute("UPDATE ebay_sync_runs SET status='done',finished_at=?,items_seen=?,matched=?,updated=? WHERE id=?",
                           (finished, result['items_seen'], result['matched'], result['updated'], run_id))
                db.commit()
                return dict(result, status='done')
            except Exception as exc:
                db.rollback()
                message = str(exc) if isinstance(exc, EbayError) else 'The eBay check failed safely; no order updates were applied.'
                if run_id:
                    db.execute("UPDATE ebay_sync_runs SET status='failed',finished_at=?,error=? WHERE id=?",
                               (now_iso(), message, run_id))
                    db.execute('UPDATE ebay_connection SET error=? WHERE id=1 AND generation=?', (message, conn['generation']))
                    if isinstance(exc, Reauthorize):
                        db.execute('UPDATE ebay_connection SET enabled=0 WHERE id=1 AND generation=?', (conn['generation'],))
                    db.commit()
                self.app.logger.warning('eBay order sync: %s', message)
                return {'status': 'failed', 'error': message}
            finally:
                db.close()

    def loop(self):
        while True:
            self.wake.wait(60)
            self.wake.clear()
            try:
                self.run_once()
            except Exception:
                self.app.logger.error('eBay order scheduler could not complete a check; will retry.')

    def start(self):
        if self.worker_enabled:
            threading.Thread(target=self.loop, name='ebay-order-sync', daemon=True).start()


def register(app, get_db, open_db, require_owner, data_dir):
    sync = OrderSync(app, open_db, data_dir)
    app.extensions['ebay_orders'] = sync
    bp = Blueprint('ebay', __name__)

    def csrf_token():
        if 'ebay_csrf' not in session:
            session['ebay_csrf'] = secrets.token_urlsafe(32)
        return session['ebay_csrf']

    @bp.before_request
    def authorize():
        require_owner()
        if 'banknotes' not in g.get('allowed_cats', set()):
            abort(403)
        if request.method == 'POST':
            expected = session.get('ebay_csrf', '')
            provided = request.form.get('csrf_token', '')
            if not expected or not hmac.compare_digest(expected, provided):
                abort(403, description='Reload the eBay Orders page and try again.')

    @bp.after_request
    def private_response(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        return response

    @bp.get('/banknotes/ebay')
    def dashboard():
        db = get_db()
        from ebay_mail import configured as mail_configured
        mail_connection = db.execute('SELECT * FROM ebay_mail_connection WHERE id=1').fetchone()
        conn = db.execute('SELECT account_name,enabled,connected_at,last_attempt,last_success,error,refresh_token IS NOT NULL AS connected FROM ebay_connection WHERE id=1').fetchone()
        items = db.execute('SELECT i.*,l.banknote_id,l.manual_status,l.matched_by,l.match_evidence,b.country,b.denomination,b.cat_id '
                           'FROM ebay_order_items i LEFT JOIN banknote_ebay_links l ON l.line_key=i.line_key '
                           'LEFT JOIN banknotes b ON b.id=l.banknote_id WHERE i.ignored=0 '
                           'ORDER BY i.ordered_at DESC').fetchall()
        tracking = defaultdict(list)
        for row in db.execute('SELECT * FROM ebay_item_tracking ORDER BY carrier,tracking_number'):
            tracking[row['line_key']].append(dict(row))
        notes = db.execute("SELECT id,cat_id,country,denomination,date_1,serial_number FROM banknotes "
                           "WHERE (status IS NULL OR status IN ('','Own','Owned','Ordered')) AND id NOT IN "
                           "(SELECT banknote_id FROM banknote_ebay_links) ORDER BY country,denomination").fetchall()
        events = db.execute('SELECT e.*,b.cat_id,b.country,b.denomination FROM ebay_status_events e '
                            'JOIN banknotes b ON b.id=e.banknote_id ORDER BY e.id DESC LIMIT 50').fetchall()
        runs = db.execute('SELECT * FROM ebay_sync_runs ORDER BY started_at DESC LIMIT 5').fetchall()
        _, suggestions = detail_match_plan(db)
        return render_template('ebay_orders.html', current_category='banknotes', connection=conn,
                               configured=sync.client.configured, worker_enabled=sync.worker_enabled,
                               interval_minutes=sync.interval // 60, items=items, notes=notes,
                               events=events, runs=runs, tracking=tracking, suggestions=suggestions,
                               csrf_token=csrf_token(),
                               mail_configured=mail_configured(), mail_connection=mail_connection)

    @bp.post('/banknotes/ebay/connect')
    def connect():
        if not sync.client.configured:
            flash('eBay needs one-time application setup before you can connect.', 'error')
            return redirect(url_for('ebay.dashboard'))
        state, browser = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
        session['ebay_oauth_browser'] = browser
        db = get_db()
        db.execute('DELETE FROM ebay_oauth_states WHERE expires < ?', (time.time(),))
        db.execute('INSERT INTO ebay_oauth_states VALUES (?,?,?,?)',
                   (digest(state), digest(browser), g.user_email, time.time() + 600))
        db.commit()
        return redirect(sync.client.authorize_url(state))

    @bp.get('/banknotes/ebay/callback')
    def callback():
        db = get_db()
        state = request.args.get('state', '')
        browser = session.pop('ebay_oauth_browser', '')
        row = db.execute('SELECT * FROM ebay_oauth_states WHERE state_hash=?', (digest(state),)).fetchone()
        if not row or not browser or row['expires'] < time.time() or row['owner_email'] != g.user_email or not hmac.compare_digest(row['browser_hash'], digest(browser)):
            abort(400, description='eBay connection expired or belongs to another browser. Start Connect eBay again.')
        # Atomic consumption before exchanging the code prevents replay.
        consumed = db.execute('DELETE FROM ebay_oauth_states WHERE state_hash=?', (digest(state),)).rowcount
        db.commit()
        if consumed != 1:
            abort(400)
        if request.args.get('error') or not request.args.get('code'):
            flash('eBay connection was cancelled. Your existing connection was not changed.', 'error')
            return redirect(url_for('ebay.dashboard'))
        try:
            tokens = sync.client.token(code=request.args['code'])
            account_key, account_name = sync.client.identity(tokens['access_token'])
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM ebay_deleted_accounts WHERE identity_hash IN (?,?)',
                          (account_key, digest(account_name.lower()))).fetchone():
                raise EbayError('eBay reported this account closed; it cannot be connected.')
            existing = db.execute('SELECT * FROM ebay_connection WHERE id=1').fetchone()
            if existing and existing['account_key'] != account_key:
                raise EbayError('This collection is linked to a different eBay account. Reconnect the original account.')
            refresh, access = sync.encrypt(tokens['refresh_token']), sync.encrypt(tokens['access_token'])
            db.execute('INSERT INTO ebay_connection (id,account_key,account_name,owner_email,refresh_token,access_token,access_expires,connected_at,generation) '
                       'VALUES (1,?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET account_name=excluded.account_name, '
                       'owner_email=excluded.owner_email,refresh_token=excluded.refresh_token,access_token=excluded.access_token, '
                       'access_expires=excluded.access_expires,enabled=1,generation=generation+1,connected_at=excluded.connected_at,last_attempt=NULL,error=NULL',
                       (account_key, account_name, g.user_email, refresh, access,
                        time.time() + int(tokens['expires_in']), now_iso(), secrets.randbits(62)))
            db.commit()
            sync.wake.set()
            # First check also works if the periodic worker was not configured.
            threading.Thread(target=sync.run_once, daemon=True).start()
            flash('eBay connected. Exact matches will update automatically.', 'success')
        except EbayError as exc:
            db.rollback()
            flash(str(exc), 'error')
        return redirect(url_for('ebay.dashboard'))

    @bp.post('/banknotes/ebay/sync')
    def sync_now():
        threading.Thread(target=sync.run_once, kwargs={'force': True}, daemon=True).start()
        flash('Checking eBay orders. Refresh this page shortly for the result.', 'success')
        return redirect(url_for('ebay.dashboard'))

    @bp.post('/banknotes/ebay/settings')
    def settings():
        db = get_db()
        action = request.form.get('action')
        if action in ('pause_mail', 'resume_mail'):
            db.execute('INSERT OR IGNORE INTO ebay_mail_connection (id) VALUES (1)')
            db.execute('UPDATE ebay_mail_connection SET enabled=? WHERE id=1', (int(action == 'resume_mail'),))
        elif action == 'pause':
            db.execute('UPDATE ebay_connection SET enabled=0,generation=generation+1 WHERE id=1')
        elif action == 'resume':
            db.execute('UPDATE ebay_connection SET enabled=1,generation=generation+1,last_attempt=NULL WHERE id=1 AND refresh_token IS NOT NULL')
        elif action == 'disconnect':
            db.execute('UPDATE ebay_connection SET enabled=0,refresh_token=NULL,access_token=NULL,access_expires=0,generation=generation+1 WHERE id=1')
            db.execute('DELETE FROM ebay_oauth_states')
        elif action == 'delete_data':
            db.execute('INSERT OR IGNORE INTO ebay_mail_connection (id) VALUES (1)')
            db.execute('UPDATE ebay_mail_connection SET enabled=0,last_received=NULL WHERE id=1')
            for table in ('ebay_status_events', 'ebay_order_items', 'ebay_connection', 'ebay_oauth_states', 'ebay_sync_runs'):
                db.execute('DELETE FROM ' + table)
        else:
            abort(400)
        db.commit()
        sync.wake.set()
        flash('eBay connection and shipping history deleted. Your banknotes and photos are unchanged.'
              if action == 'delete_data' else 'eBay connection settings updated.', 'success')
        return redirect(url_for('ebay.dashboard'))

    @bp.post('/banknotes/ebay/match')
    def match():
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        key, note_id = request.form.get('line_key', ''), request.form.get('banknote_id', '')
        item = db.execute('SELECT * FROM ebay_order_items WHERE line_key=?', (key,)).fetchone()
        if not item or item['quantity'] != 1:
            abort(400, description='Only a single-note order item can be matched.')
        note = db.execute("SELECT id FROM banknotes WHERE id=? AND (status IS NULL OR status IN ('','Own','Owned','Ordered'))", (note_id,)).fetchone()
        if not note or db.execute('SELECT 1 FROM banknote_ebay_links WHERE banknote_id=? OR line_key=?', (note_id, key)).fetchone():
            abort(409, description='That banknote or order is already matched. Refresh and review the matches.')
        db.execute('INSERT INTO banknote_ebay_links (banknote_id,line_key,matched_by,matched_at) VALUES (?,?,?,?)',
                   (note_id, key, 'manual', now_iso()))
        event(db, note_id, None, item['delivery_status'], 'Owner confirmed match')
        db.commit()
        flash('Order matched. Its shipping progress will update automatically.', 'success')
        return redirect(url_for('ebay.dashboard'))

    @bp.post('/banknotes/ebay/match-auto')
    def match_auto():
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        result = apply_items(db, [], source='Recovered eBay orders')
        db.commit()
        flash(f"{result['matched']} orders matched. Collection ownership is unchanged.", 'success')
        return redirect(url_for('ebay.dashboard'))

    @bp.post('/banknotes/ebay/override')
    def override():
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        note_id, status = request.form.get('banknote_id', ''), request.form.get('status', '')
        row = db.execute('SELECT l.*,i.delivery_status FROM banknote_ebay_links l JOIN ebay_order_items i ON i.line_key=l.line_key WHERE l.banknote_id=?', (note_id,)).fetchone()
        if not row or status not in ('automatic', *RANK):
            abort(400)
        manual = None if status == 'automatic' else status
        new = manual or row['delivery_status']
        event(db, note_id, row['manual_status'] or row['delivery_status'], new,
              'Automatic updates restored' if manual is None else 'Owner override')
        db.execute('UPDATE banknote_ebay_links SET manual_status=? WHERE banknote_id=?', (manual, note_id))
        db.commit()
        return redirect(url_for('ebay.dashboard'))

    @bp.post('/banknotes/ebay/ignore')
    def ignore():
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        key = request.form.get('line_key', '')
        # Undoing a mistaken link also excludes it from automatic re-matching.
        db.execute('DELETE FROM banknote_ebay_links WHERE line_key=?', (key,))
        db.execute('UPDATE ebay_order_items SET ignored=1 WHERE line_key=?', (key,))
        db.commit()
        flash('Order excluded from this banknote sync. Collection records are unchanged.', 'success')
        return redirect(url_for('ebay.dashboard'))

    def deliveries():
        if 'ebay_deliveries' not in g:
            rows = get_db().execute('SELECT l.banknote_id,l.manual_status,i.delivery_status,i.attention,i.last_seen '
                                    'FROM banknote_ebay_links l JOIN ebay_order_items i ON i.line_key=l.line_key').fetchall()
            g.ebay_deliveries = {r['banknote_id']: {'status': r['manual_status'] or r['delivery_status'],
                               'manual': bool(r['manual_status']), 'attention': bool(r['attention']),
                               'last_seen': r['last_seen']} for r in rows}
        return g.ebay_deliveries

    @app.context_processor
    def delivery_context():
        return {'banknote_delivery': lambda note_id: deliveries().get(note_id)}

    app.register_blueprint(bp)
    from ebay_notifications import register_notifications
    register_notifications(app, get_db, sync.client)
    from ebay_mail import register as register_mail
    register_mail(app, get_db)
    return sync
