"""Exact purchase listings, independent of review flags and sales availability."""
from html import unescape
from html.parser import HTMLParser
import json
import hmac
import os
from pathlib import Path
import re
import threading
import time
from urllib.error import HTTPError
from urllib.parse import parse_qs, urljoin, urlsplit, urlunsplit
from urllib.request import Request, build_opener, HTTPRedirectHandler

from flask import Blueprint, abort, jsonify, g, request, session, url_for

from ebay_orders import banknote_deliveries, csrf_token, listing_id, review_digest, safe_review_source_url, now_iso
import listing_checks
import source_documents
import purchase_orders

TABLES = {'coins': ('coin_original_listings', 'coin_id', 'coin_references'),
          'banknotes': ('banknote_original_listings', 'banknote_id', 'note_references')}
FRESH_SECONDS = 24 * 60 * 60
RETRY_SECONDS = 60 * 60
GONE_SECONDS = 7 * 24 * 60 * 60


def exact_listing(value):
    """Allow only recognizable item URLs; never searches, accounts or references."""
    if not isinstance(value, str) or re.search(r'[\x00-\x20\\]', value):
        return None
    try:
        p = urlsplit(unescape(value))
        if p.scheme not in ('https', 'http') or p.username or p.password or p.port not in (None, 80, 443):
            return None
        host = (p.hostname or '').lower()
        ebay_id = listing_id(value)
        if ebay_id:
            return ('https://www.ebay.com/itm/' + ebay_id, 'eBay', 'ebay:' + ebay_id)
        if host in ('vcoins.com', 'www.vcoins.com'):
            match = re.fullmatch(r'/[a-z]{2}/stores/[^/]+/\d+/product/[^/]+/(\d+)/Default\.aspx',
                                 p.path, re.I)
            if match:
                return (urlunsplit(('https', 'www.vcoins.com', p.path, '', '')),
                        'VCoins', 'vcoins:' + match[1])
        if host in ('cngcoins.com', 'www.cngcoins.com'):
            query = {k.lower(): v for k, v in parse_qs(p.query).items()}
            for path, key, canonical in (('/coin.aspx', 'coinid', 'CoinID'),
                                         ('/lot.aspx', 'lot_id', 'LOT_ID')):
                ids = query.get(key, [])
                if p.path.lower() == path and len(ids) == 1 and re.fullmatch(r'\d+', ids[0]):
                    return ('https://www.cngcoins.com/' + ('Coin.aspx' if key == 'coinid' else 'Lot.aspx') +
                            '?' + canonical + '=' + ids[0], 'CNG', 'cng:' + key + ':' + ids[0])
        if host in ('ma-shops.com', 'www.ma-shops.com'):
            ids = parse_qs(p.query).get('id', [])
            if re.fullmatch(r'/[a-zA-Z0-9_-]+/item\.php', p.path) and len(ids) == 1 and re.fullmatch(r'\d+', ids[0]):
                return ('https://www.ma-shops.com' + p.path + '?id=' + ids[0],
                        'MA-Shops', 'ma-shops:' + p.path + ':' + ids[0])
    except (ValueError, TypeError):
        pass
    return None


def init_schema(db):
    db.executescript(Path(__file__).with_suffix('.sql').read_text())


def add_source(db, category, record_id, url):
    info = exact_listing(url)
    if category not in TABLES or not info:
        return False
    table, key, _ = TABLES[category]
    db.execute('INSERT INTO original_listing_pages (url,vendor,item_key) VALUES (?,?,?) '
               'ON CONFLICT(url) DO NOTHING', info)
    db.execute(f'INSERT INTO {table} ({key},url) VALUES (?,?) ON CONFLICT({key}) DO NOTHING',
               (record_id, info[0]))
    return True


def candidate(db, category, record):
    record = dict(record)
    _, _, reference = TABLES[category]
    groups = []
    if category == 'banknotes':
        groups.append(['https://www.ebay.com/itm/' + r['item_id'] for r in db.execute(
            'SELECT i.item_id FROM banknote_ebay_links l JOIN ebay_order_items i ON i.line_key=l.line_key '
            'WHERE l.banknote_id=?', (record['id'],))])
    lines = []
    for field in ('description', reference):
        for line in (record.get(field) or '').splitlines():
            if re.match(r'^\s*Listing:\s+', line, re.I) or re.match(r'^Market Scan \d{4}-\d{2}-\d{2}:', line):
                lines.extend(re.findall(r'https?://[^\s<>"\']+', line))
    groups.append(lines)
    market_urls = []
    for row in db.execute("SELECT listing_url,payload FROM market_scan_items "
                          "WHERE category=? AND record_id=? AND status='ordered'",
                          (category, record['id'])):
        try:
            market_urls.append(row['listing_url'] or json.loads(row['payload'] or '{}').get('listing_url', ''))
        except (ValueError, TypeError, AttributeError):
            continue
    groups.append(market_urls)
    # Review sources can be comparisons or uncertain matches, not original purchases.
    for group in groups:
        unique = {}
        for value in group:
            info = exact_listing(value)
            if info:
                unique[info[2]] = info[0]
        if unique:
            return next(iter(unique.values())) if len(unique) == 1 else None
    return None


class PageText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.capture = None
        self.headings = []
        self.title = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.hidden += 1
        primary = tag == 'h1' or (tag == 'h3' and dict(attrs).get('id', '').endswith('_txtName'))
        if not self.hidden and (primary or tag == 'title'):
            self.capture = tag
            if tag != 'title':
                self.headings.append([])

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.hidden = max(0, self.hidden - 1)
        if tag == self.capture:
            self.capture = None

    def handle_data(self, data):
        if not self.hidden:
            self.text.append(data)
            if self.capture == 'title':
                self.title.append(data)
            elif self.capture:
                self.headings[-1].append(data)


def page_state(url, status, body, final_url):
    original, final = exact_listing(url), exact_listing(final_url)
    if status in (404, 410):
        return 'gone'
    if not original or not final or original[2] != final[2]:
        return 'unknown'
    if status != 200 or not body:
        return 'unknown'
    parser = PageText()
    parser.feed(body)
    title = ' '.join(parser.title).strip()
    text = ' '.join(parser.text).lower()
    if re.search(r'captcha|just a moment|access denied|forbidden|service unavailable|security measure|verify (?:you are|that you)|'
                 r'pardon our interruption|sign in to your account', title + ' ' + text[:5000], re.I):
        return 'unknown'
    if re.search(r'page (?:was )?not found|listing (?:has been|was) removed|'
                 r'item (?:is )?no longer available|could not find (?:this|the) (?:item|page)|'
                 r'this listing is no longer available', text):
        return 'gone'
    headings = [' '.join(' '.join(h).split()) for h in parser.headings]
    if original[1] == 'CNG' and re.match(r'^CNG: The Coin Shop\.\s+\S.{20}', title):
        headings.append(title)
    for heading in headings:
        if len(heading) >= 12 and not re.search(
                r'^search|^all products|^shop\b|^inventory\b|^you may|^similar |^related |'
                r'^recommended|^sign in|^error|classical numismatic group', heading, re.I):
            return 'available'  # Sold/ended archives still qualify if the item remains readable.
    return 'unknown'


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_listing(url):
    original = exact_listing(url)
    if not original:
        return 'unknown', ''
    current = original[0]
    opener = build_opener(NoRedirect())
    for _ in range(4):
        try:
            request = Request(current, headers={'User-Agent': 'Mozilla/5.0',
                                               'Accept': 'text/html,application/xhtml+xml'})
            with opener.open(request, timeout=8) as response:
                body = response.read(2_000_001)
                if len(body) > 2_000_000:
                    return 'unknown', ''
                html = body.decode(response.headers.get_content_charset() or 'utf-8', errors='replace')
                state = page_state(url, response.status, html, response.geturl())
                parser = PageText()
                parser.feed(html)
                return state, ' '.join(' '.join(parser.text).split())[:60000] if state == 'available' else ''
        except HTTPError as error:
            if error.code in (301, 302, 303, 307, 308):
                destination = urljoin(current, error.headers.get('Location', ''))
                info = exact_listing(destination)
                if not info or info[2] != original[2]:
                    return 'unknown', ''
                current = info[0]
            else:
                return ('gone' if error.code in (404, 410) else 'unknown'), ''
        except Exception:
            return 'unknown', ''
    return 'unknown', ''


def check_page(url):
    return fetch_listing(url)[0]


def manual_review(db, category, record_id):
    if category == 'banknotes':
        return banknote_deliveries(db, record_id).get(record_id, {}).get('review')
    if category != 'coins':
        return None
    row = db.execute('SELECT r.*,d.review_digest AS dismissed_digest FROM coin_purchase_reviews r '
                     'LEFT JOIN coin_purchase_review_dismissals d ON d.coin_id=r.coin_id '
                     'WHERE r.coin_id=?', (record_id,)).fetchone()
    if row:
        token = review_digest(row)
        sources = [dict(source) for source in db.execute(
            'SELECT label,url FROM coin_purchase_review_sources WHERE coin_id=? ORDER BY position,url',
            (record_id,)) if safe_review_source_url(source['url'])]
        return dict(reason=row['reason'], token=token, dismissed=row['dismissed_digest'] == token, sources=sources)


def purchase_links(db, category, record_id, listing):
    links = [listing] if listing else []
    if category == 'coins':
        # Preserve actual order/invoice evidence, not speculative search links.
        for row in db.execute('SELECT label,url FROM coin_purchase_review_sources WHERE coin_id=? '
                              'ORDER BY position,url', (record_id,)):
            if safe_review_source_url(row['url']) and re.search(r'invoice|receipt|\border\b', row['label'], re.I):
                links.append(dict(row))
    for row in db.execute('SELECT title,filename FROM record_documents WHERE category=? AND record_id=? '
                          'ORDER BY position', (category, record_id)):
        if row['filename'] and re.search(r'invoice|receipt', row['title'] or '', re.I):
            links.append(dict(label=row['title'], url=url_for('uploaded_file', filename=row['filename'])))
    table, key = source_documents.TABLES[category]
    for row in db.execute(f'SELECT a.title,a.filename FROM {table} l JOIN purchase_source_archives a ON a.url=l.url '
                          f'WHERE l.{key}=? AND l.attached=1 AND a.filename IS NOT NULL', (record_id,)):
        links.append(dict(label=row['title'] + ' PDF', url=url_for('uploaded_file', filename=row['filename'])))
    seen = set()
    return [link for link in links if not (link['url'] in seen or seen.add(link['url']))]


def ebay_purchase_orders(db, category, record_id):
    """Expose exact saved purchase associations, never infer from seller names."""
    if category not in TABLES or not record_id:
        return []
    numbers = set()
    if category == 'banknotes':
        numbers.update(row['order_id'] for row in db.execute(
            'SELECT i.order_id FROM banknote_ebay_links l JOIN ebay_order_items i '
            'ON i.line_key=l.line_key WHERE l.banknote_id=?', (record_id,)))
    table, key, _ = TABLES[category]
    listing = db.execute(f'SELECT url FROM {table} WHERE {key}=?', (record_id,)).fetchone()
    item_id = listing_id(listing['url']) if listing else None
    if item_id:
        numbers.update(row['order_id'] for row in db.execute(
            'SELECT order_id FROM ebay_order_items WHERE item_id=? AND ignored=0', (item_id,)))
    table, key = source_documents.TABLES[category]
    for row in db.execute(f'SELECT a.url FROM {table} l JOIN purchase_source_archives a ON a.url=l.url '
                          f'WHERE l.{key}=? AND a.kind IN (\'order\',\'invoice\')', (record_id,)):
        try:
            url = urlsplit(row['url'])
            if (url.scheme == 'https' and url.hostname == 'order.ebay.com'
                    and not url.username and not url.password and url.port in (None, 443)
                    and url.path == '/ord/show'):
                values = parse_qs(url.query).get('orderId', [])
                if len(values) == 1:
                    numbers.add(values[0])
        except ValueError:
            continue
    return [dict(number=number, url='https://order.ebay.com/ord/show?orderId=' + number)
            for number in sorted(n for n in numbers if isinstance(n, str)
                                 and re.fullmatch(r'\d{2}-\d{5}-\d{5}', n))]


class ListingService:
    def __init__(self, app, get_db, connect, analyze, upload_folder, fonts):
        self.app, self.get_db, self.connect = app, get_db, connect
        self.analyze = analyze
        self.upload_folder, self.fonts = upload_folder, fonts
        self.wake = threading.Event()

    def lookup(self, category, record):
        if category not in TABLES:
            return dict(link=None, pending=False)
        db = self.get_db()
        table, key, _ = TABLES[category]
        row = db.execute(f'SELECT p.* FROM {table} l JOIN original_listing_pages p ON p.url=l.url '
                         f'WHERE l.{key}=?', (record['id'],)).fetchone()
        if not row:
            url = candidate(db, category, record)
            if url:
                add_source(db, category, record['id'], url)
                db.commit()
                row = db.execute('SELECT * FROM original_listing_pages WHERE url=?', (url,)).fetchone()
        now = time.time()
        link = None
        if row and row['state'] == 'available' and row['checked_at'] >= now - FRESH_SECONDS:
            info = exact_listing(row['url'])
            if info:
                link = dict(url=info[0], vendor=info[1], label=info[1] + ' Original Listing')
                if os.environ.get('ORIGINAL_LISTING_AI_CHECKS') == '1':
                    listing_checks.ensure(db, category, record['id'], row['url'])
                    db.commit()
        check = listing_checks.report(db, category, record['id'])
        pending = bool(row and row['next_check_at'] <= now)
        if pending:
            self.wake.set()
        links = purchase_links(db, category, record['id'], link)
        delivery = banknote_deliveries(db, record['id']).get(record['id']) if category == 'banknotes' else None
        review = delivery['review'] if delivery else manual_review(db, category, record['id'])
        if category == 'banknotes' and review:
            links.extend(review['sources'])
        archive_pending = False
        if os.environ.get('ORIGINAL_LISTING_ARCHIVES') == '1':
            if link:
                source_documents.enqueue(db, category, record['id'], link['url'], link['label'], 'listing')
            for source in links:
                if re.search(r'invoice|receipt', source['label'], re.I):
                    source_documents.enqueue(db, category, record['id'], source['url'], source['label'], 'invoice')
            db.commit()
            archive_table, archive_key = source_documents.TABLES[category]
            archive_pending = bool(db.execute(
                f'SELECT 1 FROM {archive_table} l JOIN purchase_source_archives a ON a.url=l.url '
                f'WHERE l.{archive_key}=? AND l.attached=0 AND a.attempts<3 '
                'AND (a.filename IS NOT NULL OR a.next_attempt<=?) LIMIT 1', (record['id'], now)).fetchone())
            if archive_pending:
                self.wake.set()
        return dict(link=link, links=links, pending=pending, archive_pending=archive_pending,
                    check=check, review=review, delivery=delivery)

    def work_once(self):
        db = self.connect()
        try:
            now = time.time()
            lease = now + 90
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT p.url FROM original_listing_pages p WHERE next_check_at<=? '
                             'AND lease_until<? AND (EXISTS (SELECT 1 FROM coin_original_listings c WHERE c.url=p.url) '
                             'OR EXISTS (SELECT 1 FROM banknote_original_listings b WHERE b.url=p.url)) '
                             'ORDER BY next_check_at LIMIT 1', (now, now)).fetchone()
            if not row:
                db.rollback()
                return False
            url = row['url']
            db.execute('UPDATE original_listing_pages SET lease_until=? WHERE url=?', (lease, url))
            db.commit()
            state = check_page(url)
            delay = {'available': FRESH_SECONDS, 'gone': GONE_SECONDS}.get(state, RETRY_SECONDS)
            checked = time.time()
            with db:
                db.execute('UPDATE original_listing_pages SET state=?,checked_at=?,next_check_at=?,lease_until=0 '
                           'WHERE url=? AND lease_until=?', (state, checked, checked + delay, url, lease))
                if state == 'available':
                    for category, (table, key, _) in TABLES.items():
                        for item in db.execute(f'SELECT {key} FROM {table} WHERE url=?', (url,)).fetchall():
                            if os.environ.get('ORIGINAL_LISTING_AI_CHECKS') == '1':
                                listing_checks.ensure(db, category, item[key], url)
                            if os.environ.get('ORIGINAL_LISTING_ARCHIVES') == '1':
                                source_documents.enqueue(db, category, item[key], url, exact_listing(url)[1] + ' Original Listing', 'listing')
            return True
        finally:
            db.close()

    def start(self):
        if os.environ.get('ORIGINAL_LISTING_WORKER', '1') == '0':
            return
        def run():
            while True:
                try:
                    worked = self.work_once()
                    if os.environ.get('ORIGINAL_LISTING_AI_CHECKS') == '1':
                        worked = listing_checks.run_once(self.connect, fetch_listing, self.analyze) or worked
                    if os.environ.get('ORIGINAL_LISTING_ARCHIVES') == '1':
                        worked = source_documents.run_once(self.connect, self.upload_folder, self.fonts) or worked
                    if worked:
                        time.sleep(0.3)
                        continue
                except Exception:
                    self.app.logger.exception('Original listing availability check failed')
                self.wake.wait(30)
                self.wake.clear()
        threading.Thread(target=run, name='original-listing-checks', daemon=True).start()


def register(app, get_db, connect, can_see, require_owner, analyze, upload_folder, fonts):
    service = ListingService(app, get_db, connect, analyze, upload_folder, fonts)
    bp = Blueprint('original_listings', __name__)

    @bp.get('/<category>/<record_id>/original-listing')
    def status(category, record_id):
        if category not in TABLES:
            abort(404)
        if category not in g.get('allowed_cats', set()):
            abort(403)
        record = get_db().execute(f'SELECT * FROM {category} WHERE id=?', (record_id,)).fetchone()
        if not record or not can_see(category, record):
            abort(404)
        data = service.lookup(category, record)
        if (g.get('current_user') or {}).get('role') == 'owner':
            data['csrf_token'] = csrf_token()
        response = jsonify(data)
        response.headers['Cache-Control'] = 'no-store'
        return response

    @bp.post('/<category>/<record_id>/original-listing/review')
    def review(category, record_id):
        require_owner()
        if category not in TABLES or category not in g.get('allowed_cats', set()):
            abort(403)
        expected, provided = session.get('ebay_csrf', ''), request.form.get('csrf_token', '')
        if not expected or not hmac.compare_digest(expected.encode(), provided.encode()):
            response = jsonify(code='csrf_expired', error='The page session expired. Please try again.')
            response.status_code = 403
            response.headers['Cache-Control'] = 'no-store'
            return response
        action = request.form.get('action')
        if action not in ('dismiss', 'restore'):
            abort(400)
        db = get_db()
        db.execute('BEGIN IMMEDIATE')
        record = db.execute(f'SELECT * FROM {category} WHERE id=?', (record_id,)).fetchone()
        if not record or not can_see(category, record):
            db.rollback()
            abort(404)
        current = manual_review(db, category, record_id)
        check = listing_checks.report(db, category, record_id)
        for name, value in (('review_token', current), ('check_token', check)):
            if not hmac.compare_digest((value['token'] if value else '').encode(),
                                       request.form.get(name, '').encode()):
                db.rollback()
                return jsonify(error='The review changed. Reload the page before confirming it.'), 409
        if current:
            table = 'coin_purchase_review_dismissals' if category == 'coins' else 'banknote_purchase_review_dismissals'
            key = 'coin_id' if category == 'coins' else 'banknote_id'
            if action == 'dismiss':
                db.execute(f'INSERT INTO {table} ({key},review_digest,dismissed_at) VALUES (?,?,?) '
                           f'ON CONFLICT({key}) DO UPDATE SET review_digest=excluded.review_digest,dismissed_at=excluded.dismissed_at',
                           (record_id, current['token'], now_iso()))
            else:
                db.execute(f'DELETE FROM {table} WHERE {key}=?', (record_id,))
        if check and check['state'] == 'checked':
            key = 'coin_id' if category == 'coins' else 'banknote_id'
            db.execute(f'UPDATE original_listing_checks SET dismissed=? WHERE {key}=?',
                       (int(action == 'dismiss'), record_id))
        db.commit()
        response = jsonify(service.lookup(category, record))
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.context_processor
    def helpers():
        def review_reason(category, record_id):
            if 'listing_review_reasons' not in g:
                g.listing_review_reasons = {}
                for row in get_db().execute("SELECT coin_id,banknote_id,result FROM original_listing_checks "
                                             "WHERE state='checked' AND dismissed=0"):
                    reasons = [c['label'] + ': ' + (c['stored'] or 'Missing') + ' / listing: ' + c['listed']
                               for c in json.loads(row['result'] or '[]') if c['outcome'] != 'match']
                    g.listing_review_reasons[(('coins' if row['coin_id'] else 'banknotes'),
                                              row['coin_id'] or row['banknote_id'])] = '; '.join(reasons)
            return g.listing_review_reasons.get((category, record_id))
        return {'original_listing': service.lookup, 'listing_review_reason': review_reason,
                'purchase_orders': lambda category, record_id: purchase_orders.purchase_orders(get_db(), category, record_id)}

    app.register_blueprint(bp)
    return service
