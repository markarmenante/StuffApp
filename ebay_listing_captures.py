"""Public listing evidence read by the owner's signed-in browser, not invoices."""
from html import escape
import json
import re
import time

MAX_AGE = 7 * 86400


def save(db, capture, items):
    if capture is None:
        return
    if len(items) != 1 or items[0]['quantity'] != 1 or items[0].get('identity_ambiguous'):
        raise ValueError('A listing capture requires one uniquely identified purchased item')
    url = 'https://www.ebay.com/itm/' + items[0]['item_id']
    if not isinstance(capture, dict) or capture.get('url') != url:
        raise ValueError('Listing capture does not match the purchased item')
    title, text, images = (capture.get(k) for k in ('title', 'text', 'images'))
    if not isinstance(title, str) or not 12 <= len(title) <= 500 or not isinstance(text, str) or not 40 <= len(text) <= 60000:
        raise ValueError('Listing capture is incomplete')
    if not isinstance(images, list) or len(images) > 24 or any(not isinstance(u, str) or not re.fullmatch(
            r'https://i\.ebayimg\.com/images/g/[\w~-]+/s-l\d+\.(?:jpg|jpeg|png|webp)', u) for u in images):
        raise ValueError('Listing capture contains an unsupported image URL')
    db.execute('INSERT INTO ebay_listing_captures VALUES (?,?,?,?,?) ON CONFLICT(url) DO UPDATE SET '
               'title=excluded.title,text=excluded.text,images_json=excluded.images_json,captured_at=excluded.captured_at',
               (url, title, text, json.dumps(list(dict.fromkeys(images))), time.time()))


def html(db, url):
    row = db.execute('SELECT * FROM ebay_listing_captures WHERE url=? AND captured_at>?',
                     (url, time.time() - MAX_AGE)).fetchone()
    if not row:
        return None
    images = json.loads(row['images_json'])
    product = json.dumps({'@type': 'Product', 'url': url, 'image': images}).replace('<', '\\u003c')
    image = '<meta property="og:image" content="' + escape(images[0], quote=True) + '">' if images else ''
    return ('<html><head><title>' + escape(row['title']) + '</title>' + image + '</head><body><h1>' +
            escape(row['title']) + '</h1>' + ''.join('<p>' + escape(line) + '</p>' for line in row['text'].splitlines()) +
            '<script type="application/ld+json">' + product + '</script></body></html>')
