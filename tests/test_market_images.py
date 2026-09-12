"""Market Scan photos: Buy brings the listing's note photos over. The
scan's own image URL is fetched at full size where the CDN allows
(eBay s-l1600); when the scan stored none, or the fetch fails, the
listing page is read for its photos (JSON-LD / og:image / eBay
gallery). The liveness probe harvests the same photos for a candidate
the model gave no image for, so the list shows a thumbnail.

Run: .venv/bin/python tests/test_market_images.py
"""
import os, sys, io, json, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-mimg-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuffapp
from PIL import Image

def jpeg_bytes(color):
    buf = io.BytesIO()
    Image.new('RGB', (64, 32), color).save(buf, format='JPEG')
    return buf.getvalue()

FRONT = jpeg_bytes('red'); BACK = jpeg_bytes('blue')
IMAGES = {
    'https://i.ebayimg.com/images/g/AAA/s-l1600.jpg': FRONT,
    'https://i.ebayimg.com/images/g/BBB/s-l1600.jpg': BACK,
    'https://dealer.example/photos/front.jpg': FRONT,
    'https://dealer.example/photos/back.jpg': BACK,
}
def fake_fetch_image(url, limit=15_000_000):
    data = IMAGES.get(url)
    return (data, 'jpg') if data else (None, None)
stuffapp._market_fetch_image = fake_fetch_image

EBAY_PAGE = ('<html><head><meta property="og:image" content="https://i.ebayimg.com/images/g/AAA/s-l500.jpg"/>'
             '<script type="application/ld+json">{"@type":"Product","image":["https://i.ebayimg.com/images/g/AAA/s-l1600.jpg"]}</script>'
             '</head><body><img src="https://i.ebayimg.com/images/g/AAA/s-l64.jpg"><img src="https://i.ebayimg.com/images/g/BBB/s-l225.jpg">'
             '<img src="https://ir.ebaystatic.com/logo.png"><button>Buy It Now</button></body></html>')
DEALER_PAGE = ('<html><head><meta property="og:image" content="https://dealer.example/photos/front.jpg"></head>'
               '<body><img src="https://dealer.example/photos/back.jpg"><img src="https://dealer.example/icons/sprite.png">Add to cart</body></html>')
PAGES = {'https://www.ebay.com/itm/1': (200, EBAY_PAGE), 'https://dealer.example/notes/2': (200, DEALER_PAGE),
         'https://www.ebay.com/itm/3': (None, '')}
def fake_fetch_page(url, limit=400_000):
    stuffapp._MARKET_LAST_URL.final = url
    return PAGES.get(url, (None, ''))
stuffapp._market_fetch_page = fake_fetch_page
stuffapp.time.sleep = lambda s: None

# Size upgrade + page extraction.
assert stuffapp._market_full_size_url('https://i.ebayimg.com/images/g/AAA/s-l225.jpg') == 'https://i.ebayimg.com/images/g/AAA/s-l1600.jpg'
assert stuffapp._market_full_size_url('https://dealer.example/photos/front.jpg') == 'https://dealer.example/photos/front.jpg'
urls = stuffapp._market_page_image_urls('https://www.ebay.com/itm/1')
assert urls[:2] == ['https://i.ebayimg.com/images/g/AAA/s-l1600.jpg', 'https://i.ebayimg.com/images/g/BBB/s-l1600.jpg'], urls
assert all('logo' not in u for u in urls)
urls = stuffapp._market_page_image_urls('https://dealer.example/notes/2')
assert urls == ['https://dealer.example/photos/front.jpg'], urls  # a bare <img> on a non-eBay page is not trusted
print('PAGE IMAGES OK')

# Buy: scan URL (thumbnail size) upgraded and stored; second photo from the page.
item = {'title': 'French Indochina 5 Piastres', 'listing_url': 'https://www.ebay.com/itm/1',
        'image_urls': ['https://i.ebayimg.com/images/g/AAA/s-l225.jpg']}
stored = stuffapp._market_store_images(item)
assert set(stored) == {'image_1', 'image_2'}, stored
assert all(os.path.exists(os.path.join(stuffapp.UPLOAD_FOLDER, n)) for n in stored.values())
# No scan image at all: both from the page.
stored = stuffapp._market_store_images({'title': 'x', 'listing_url': 'https://www.ebay.com/itm/1', 'image_urls': []})
assert set(stored) == {'image_1', 'image_2'}, stored
# Unreadable page and no scan image: nothing, no exception.
stored = stuffapp._market_store_images({'title': 'x', 'listing_url': 'https://www.ebay.com/itm/3', 'image_urls': []})
assert stored == {}, stored
print('STORE OK')

# The probe hands photos to a candidate the model gave none for.
items = [{'title': 'a', 'listing_url': 'https://www.ebay.com/itm/1', 'live_evidence': ''},
         {'title': 'b', 'listing_url': 'https://dealer.example/notes/2', 'live_evidence': '',
          'image_urls': ['https://dealer.example/photos/back.jpg'], 'image_url': 'https://dealer.example/photos/back.jpg'}]
kept = stuffapp._market_verify_live(items)
assert kept[0]['image_urls'] == ['https://i.ebayimg.com/images/g/AAA/s-l1600.jpg', 'https://i.ebayimg.com/images/g/BBB/s-l1600.jpg'], kept[0].get('image_urls')
assert kept[0]['image_url'].endswith('/AAA/s-l1600.jpg')
assert kept[1]['image_urls'] == ['https://dealer.example/photos/back.jpg'], 'a model-given image is kept as is'
print('PROBE IMAGES OK')

# End to end: Buy on a candidate files the record with both photos, trimmed-or-not, and it renders.
client = stuffapp.app.test_client()
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute("INSERT INTO market_scans (id, category, started_at, finished_at, status, summary, item_count) VALUES ('s1','banknotes','2026-09-12T00:00:00','2026-09-12T00:10:00','done','',1)")
    db.execute("INSERT INTO properties (id, name) VALUES ('p1', 'Carpinteria')")
    payload = dict(item, price='$900', price_usd=900, country='French Indochina', denomination='5 Piastres', why='', score=90, venue='eBay')
    db.execute("INSERT INTO market_scan_items (id, scan_id, category, rank, score, status, title, listing_url, venue, price, price_usd, payload, created_at) "
               "VALUES ('it1','s1','banknotes',1,90,'new',?,?, 'eBay','$900',900,?, '2026-09-12T00:10:00')",
               [payload['title'], payload['listing_url'], json.dumps(payload)])
    db.commit()
r = client.post('/banknotes/market/it1/buy', json={'location': 'Carpinteria'})
d = r.get_json(); assert r.status_code == 200 and d['ok'], d
with stuffapp.app.app_context():
    row = stuffapp.get_db().execute("SELECT image_1, image_2, status FROM banknotes WHERE id = ?", [d['record_id']]).fetchone()
assert row['image_1'] and row['image_2'] and row['status'] == 'Ordered', dict(row)
assert all(os.path.exists(os.path.join(stuffapp.UPLOAD_FOLDER, row[f])) for f in ('image_1', 'image_2'))
r = client.get(f"/banknotes/{d['record_id']}"); assert r.status_code == 200
print('BUY END-TO-END OK')
print('ALL MARKET-IMAGES ASSERTIONS PASSED')
