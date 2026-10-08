"""Preserve original listing photos as additive, unmodified document attachments."""
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
from io import BytesIO
import json
from pathlib import Path
import re
import time
from urllib.parse import urljoin, urlsplit
import uuid

from PIL import Image
import source_documents

MAX_IMAGES = 24
MAX_BYTES = 12000000
ZOOM = re.compile(r"\bSetImageZoom\(\s*['\"]([^'\"]+)['\"]\s*\)")
CNG_ZOOM = re.compile(r"\bShowImage\(\s*['\"]([^'\"]+)['\"]\s*\)")


def image_urls(html, listing_url, final_url=None):
    from original_listings import exact_listing, page_state
    if page_state(listing_url, 200, html, final_url or listing_url) != 'available':
        raise ValueError('Original listing is not readable')
    info = exact_listing(listing_url)

    class Gallery(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.zoom, self.meta, self.products = [], [], []
            self.script, self.script_type = None, ''

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'script':
                self.script, self.script_type = [], attrs.get('type', '')
            if tag == 'meta' and (attrs.get('property') or attrs.get('name')) in ('og:image', 'twitter:image'):
                self.meta.append(attrs.get('content', ''))
            if info[1] == 'VCoins':
                self.zoom.extend(ZOOM.findall(attrs.get('onclick', '')))
                if 'bigimage' in attrs.get('class', '').split():
                    self.zoom.append(attrs.get('href', ''))
            elif info[1] == 'CNG':
                self.zoom.extend(CNG_ZOOM.findall(attrs.get('onclick', '')))

        def handle_data(self, value):
            if self.script is not None:
                self.script.append(value)

        def handle_endtag(self, tag):
            if tag != 'script' or self.script is None:
                return
            text = ''.join(self.script)
            if info[1] == 'VCoins':
                self.zoom.extend(ZOOM.findall(text))
            if self.script_type == 'application/ld+json':
                try:
                    self.read_product(json.loads(text))
                except (ValueError, TypeError):
                    pass
            self.script = None

        def read_product(self, value):
            if isinstance(value, list):
                for entry in value:
                    self.read_product(entry)
            elif isinstance(value, dict):
                if '@graph' in value:
                    self.read_product(value['@graph'])
                if value.get('@type') == 'Product':
                    self.products.append(value)

    parser = Gallery()
    parser.feed(html)
    products = [p for p in parser.products if exact_listing(urljoin(listing_url, p.get('url') or ''))
                and exact_listing(urljoin(listing_url, p.get('url') or ''))[2] == info[2] and p.get('url')]
    if not products and len(parser.products) == 1 and not parser.products[0].get('url'):
        products = parser.products
    found = list(parser.zoom)
    for product in products[:1]:
        images = product.get('image', [])
        for value in images if isinstance(images, list) else [images]:
            if isinstance(value, str):
                found.append(value)
            elif isinstance(value, dict):
                found.append(value.get('contentUrl') or value.get('url') or '')
    found.extend(parser.meta)
    output, seen, sizes = [], {}, {}
    for value in found:
        if not isinstance(value, str) or not value:
            continue
        url = urljoin(listing_url, value)
        if (not source_documents.safe_remote(url, source_documents.IMAGE_HOSTS)
                or re.search(r'logo|icon|sprite|avatar|badge|placeholder|pixel|1x1|\.svg', url, re.I)):
            continue
        parts = urlsplit(url)
        # VCoins exposes thumbnail, preview and original paths for the same file.
        key = (parts.hostname, Path(parts.path).name) if parts.hostname == 'images.vcoins.com' else url
        ebay_image = re.fullmatch(r'/images/g/([^/]+)/s-l(\d+)\.[a-z]+', parts.path, re.I)
        size = int(ebay_image[2]) if parts.hostname == 'i.ebayimg.com' and ebay_image else 0
        if size:
            key = (parts.hostname, ebay_image[1])
        if key not in seen:
            seen[key], sizes[key] = len(output), size
            output.append(url)
        elif size > sizes[key]:
            output[seen[key]], sizes[key] = url, size
    return output[:MAX_IMAGES]


def download(url, folder):
    data, mime, final = source_documents.fetch_bytes(url, source_documents.IMAGE_HOSTS, MAX_BYTES)
    if not mime.startswith('image/'):
        raise ValueError('Source is not an image')
    with Image.open(BytesIO(data)) as photo:
        width, height = photo.size
        extension = {'JPEG': 'jpg', 'PNG': 'png', 'WEBP': 'webp', 'GIF': 'gif'}.get(photo.format)
        if not extension or min(width, height) < 120 or width * height > 50000000:
            raise ValueError('Unsupported image dimensions or format')
        photo.verify()
    digest = hashlib.sha256(data).hexdigest()
    filename = 'listing_image_' + digest + '.' + extension
    path = Path(folder) / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('xb') as file:
            file.write(data)
    except FileExistsError:
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Existing image archive differs')
    return dict(url=url, filename=filename, sha256=digest, width=width, height=height, saved_at=time.time())


def attach_saved(db, category, record_id, listing_url):
    if category not in source_documents.TABLES:
        return 0
    from original_listings import TABLES, exact_listing
    table, key, _ = TABLES[category]
    if not db.execute(f'SELECT 1 FROM {table} WHERE {key}=? AND url=?', (record_id, listing_url)).fetchone():
        return 0
    vendor = exact_listing(listing_url)[1]
    record = db.execute(f'SELECT cat_id FROM {category} WHERE id=?', (record_id,)).fetchone()
    attached = 0
    for row in db.execute('SELECT s.position,a.filename FROM original_listing_image_sources s '
                          'JOIN original_image_assets a ON a.url=s.image_url WHERE s.listing_url=? '
                          'ORDER BY s.position', (listing_url,)).fetchall():
        if db.execute('SELECT 1 FROM record_documents WHERE category=? AND record_id=? AND filename=?',
                      (category, record_id, row['filename'])).fetchone():
            continue
        position = db.execute("SELECT COALESCE(MAX(position),-1)+1 FROM record_documents WHERE category=? "
                              "AND record_id=? AND doc_set='main'", (category, record_id)).fetchone()[0]
        title = f"{vendor} Original Listing Image {row['position'] + 1}"
        if record['cat_id']:
            title += ' - ' + record['cat_id']
        db.execute("INSERT INTO record_documents (id,category,record_id,doc_set,position,title,filename) "
                   "VALUES (?,?,?,'main',?,?,?)",
                   (str(uuid.uuid4()), category, record_id, position, title, row['filename']))
        attached += 1
    if attached:
        db.execute(f'UPDATE {category} SET updated_at=? WHERE id=?',
                   (datetime.now(timezone.utc).isoformat(), record_id))
    return attached


def save(db, listing_url, assets):
    """Caller owns the transaction; downloads are finished before taking a write lock."""
    for position, asset in enumerate(assets):
        db.execute('INSERT INTO original_image_assets (url,filename,sha256,width,height,saved_at) '
                   'VALUES (:url,:filename,:sha256,:width,:height,:saved_at) ON CONFLICT(url) DO NOTHING', asset)
        db.execute('INSERT INTO original_listing_image_sources (listing_url,image_url,position) VALUES (?,?,?) '
                   'ON CONFLICT DO NOTHING', (listing_url, asset['url'], asset.get('position', position)))
    attached = 0
    for category, (table, key) in source_documents.TABLES.items():
        for row in db.execute(f'SELECT {key} FROM {table} WHERE url=?', (listing_url,)).fetchall():
            attached += attach_saved(db, category, row[key], listing_url)
    return attached


def run_once(connect, upload_folder):
    db = connect()
    try:
        now, lease = time.time(), time.time() + 600
        db.execute('BEGIN IMMEDIATE')
        db.execute("INSERT INTO original_listing_image_scans (url) SELECT a.url FROM purchase_source_archives a "
                   "JOIN original_listing_pages p ON p.url=a.url WHERE a.kind='listing' AND p.state='available' "
                   'ON CONFLICT DO NOTHING')
        row = db.execute('SELECT s.* FROM original_listing_image_scans s WHERE s.completed_at IS NULL '
                         'AND s.attempts<3 AND s.next_attempt<=? AND s.lease_until<? AND '
                         '(EXISTS(SELECT 1 FROM coin_source_archives a WHERE a.url=s.url) OR '
                         'EXISTS(SELECT 1 FROM banknote_source_archives a WHERE a.url=s.url)) '
                         'ORDER BY s.next_attempt,s.url LIMIT 1', (now, now)).fetchone()
        if not row:
            db.commit()
            return False
        db.execute('UPDATE original_listing_image_scans SET attempts=attempts+1,lease_until=? WHERE url=?',
                   (lease, row['url']))
        db.commit()
        assets, failures = [], []
        try:
            data, mime, final = source_documents.fetch_bytes(row['url'])
            if mime not in ('text/html', 'application/xhtml+xml'):
                raise ValueError('Not a listing page')
            urls = image_urls(data.decode('utf-8', errors='replace'), row['url'], final)
            if not urls:
                raise ValueError('No original listing photos found')
            for position, url in enumerate(urls):
                try:
                    assets.append(dict(download(url, upload_folder), position=position))
                except Exception:
                    failures.append(url)
            db.execute('BEGIN IMMEDIATE')
            if db.execute('SELECT 1 FROM original_listing_image_scans WHERE url=? AND lease_until=?',
                          (row['url'], lease)).fetchone():
                save(db, row['url'], assets)
                db.execute('UPDATE original_listing_image_scans SET lease_until=0,completed_at=?,next_attempt=? '
                           'WHERE url=? AND lease_until=?',
                           (None if failures else time.time(), time.time()+3600, row['url'], lease))
            db.commit()
        except Exception:
            db.rollback()
            with db:
                db.execute('UPDATE original_listing_image_scans SET lease_until=0,next_attempt=? '
                           'WHERE url=? AND lease_until=?', (time.time()+3600, row['url'], lease))
        return True
    finally:
        db.close()
