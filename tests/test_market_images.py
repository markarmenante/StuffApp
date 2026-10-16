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
    Image.new('RGB', (400, 200), color).save(buf, format='JPEG')
    return buf.getvalue()

FRONT = jpeg_bytes('red'); BACK = jpeg_bytes('blue'); OTHER = jpeg_bytes('green')
IMAGES = {
    'https://i.ebayimg.com/images/g/AAA/s-l1600.jpg': FRONT,
    'https://i.ebayimg.com/images/g/BBB/s-l1600.jpg': BACK,
    # CCC is another of the seller's items, shown in the listing page's
    # "similar items" carousel (the /thumbs/ path) — never this note.
    'https://i.ebayimg.com/images/g/CCC/s-l1600.jpg': OTHER,
    'https://dealer.example/photos/front.jpg': FRONT,
    'https://dealer.example/photos/back.jpg': BACK,
}
FETCHED = []
def fake_fetch_image(url, limit=15_000_000):
    FETCHED.append(url)
    data = IMAGES.get(url)
    return (data, 'jpg') if data else (None, None)
stuffapp._market_fetch_image = fake_fetch_image

def classify(photos):
    readings=[];selected={}
    for photo in photos:
        with Image.open(os.path.join(stuffapp.UPLOAD_FOLDER,photo['filename'])) as image:
            red,green,blue=image.convert('RGB').getpixel((0,0))
        side='front' if red>blue else 'back'
        readings.append(dict(id=photo['id'],side=side,confidence='high',complete_note=True,same_note=True,reason='Synthetic design'))
        if photo['gallery']:
            selected.setdefault(side,photo['id'])
    return dict(photos=readings,front=selected.get('front'),back=selected.get('back'),pair_verified=True,pair_reason='Synthetic distinct sides')
stuffapp._classify_banknote_listing_photos=classify

# A real eBay item page: JSON-LD lists every listing photo (front, back);
# the rest of the page carries carousels of other items (CCC in the
# /thumbs/ path, DDD in a script blob) and the site logo.
EBAY_PAGE = ('<html><head><meta property="og:image" content="https://i.ebayimg.com/images/g/AAA/s-l500.jpg"/>'
             '<script type="application/ld+json">{"@type":"Product","image":["https://i.ebayimg.com/images/g/AAA/s-l1600.jpg","https://i.ebayimg.com/images/g/BBB/s-l1600.jpg"]}</script>'
             '</head><body><img src="https://i.ebayimg.com/images/g/AAA/s-l64.jpg"><img src="https://i.ebayimg.com/images/g/BBB/s-l225.jpg">'
             '<div class="similar-items"><img src="https://i.ebayimg.com/thumbs/images/g/CCC/s-l300.jpg"></div>'
             '<script>{"items":[{"image":{"URL":"https://i.ebayimg.com/images/g/DDD/s-l140.jpg"}}]}</script>'
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
assert stuffapp._market_full_size_url('https://i.ebayimg.com/thumbs/images/g/CCC/s-l300.jpg') == 'https://i.ebayimg.com/images/g/CCC/s-l1600.jpg'
assert stuffapp._market_image_key('https://i.ebayimg.com/thumbs/images/g/CCC/s-l300.jpg') == stuffapp._market_image_key('https://i.ebayimg.com/images/g/CCC/s-l1600.jpg')
urls = stuffapp._market_page_image_urls('https://www.ebay.com/itm/1')
assert urls == ['https://i.ebayimg.com/images/g/AAA/s-l1600.jpg', 'https://i.ebayimg.com/images/g/BBB/s-l1600.jpg'], urls
assert all('logo' not in u for u in urls)
# Only the listing's own photos: the carousel's CCC and the script blob's DDD stay out.
assert not any('CCC' in u or 'DDD' in u for u in urls), urls
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
# The scan handed over a carousel photo as the reverse (New Hebrides
# 1000 Fr, 2026-09-19): the listing's own back photo is stored instead.
del FETCHED[:]
stored = stuffapp._market_store_images({'title': 'New Hebrides 1000 Francs', 'listing_url': 'https://www.ebay.com/itm/1',
                                        'image_urls': ['https://i.ebayimg.com/images/g/AAA/s-l225.jpg',
                                                       'https://i.ebayimg.com/thumbs/images/g/CCC/s-l300.jpg']})
assert set(stored) == {'image_1', 'image_2'}, stored
assert FETCHED == ['https://i.ebayimg.com/images/g/AAA/s-l1600.jpg', 'https://i.ebayimg.com/images/g/BBB/s-l1600.jpg'], FETCHED
# Scan photos in the model's order stand when they are the listing's own (back listed first).
del FETCHED[:]
stuffapp._market_store_images({'title': 'x', 'listing_url': 'https://www.ebay.com/itm/1',
                               'image_urls': ['https://i.ebayimg.com/images/g/BBB/s-l225.jpg', 'https://i.ebayimg.com/images/g/AAA/s-l225.jpg']})
assert FETCHED == ['https://i.ebayimg.com/images/g/BBB/s-l1600.jpg', 'https://i.ebayimg.com/images/g/AAA/s-l1600.jpg'], FETCHED
# Unreadable eBay page: nothing to check against, the scan's photos stand.
del FETCHED[:]
stuffapp._market_store_images({'title': 'x', 'listing_url': 'https://www.ebay.com/itm/3',
                               'image_urls': ['https://i.ebayimg.com/images/g/AAA/s-l225.jpg', 'https://i.ebayimg.com/images/g/CCC/s-l225.jpg']})
assert FETCHED == ['https://i.ebayimg.com/images/g/AAA/s-l1600.jpg', 'https://i.ebayimg.com/images/g/CCC/s-l1600.jpg'], FETCHED
print('STORE OK')

# The probe hands photos to a candidate the model gave none for.
items = [{'title': 'a', 'listing_url': 'https://www.ebay.com/itm/1', 'live_evidence': ''},
         {'title': 'b', 'listing_url': 'https://dealer.example/notes/2', 'live_evidence': '',
          'image_urls': ['https://dealer.example/photos/back.jpg'], 'image_url': 'https://dealer.example/photos/back.jpg'}]
kept = stuffapp._market_verify_live(items)
assert kept[0]['image_urls'] == ['https://i.ebayimg.com/images/g/AAA/s-l1600.jpg', 'https://i.ebayimg.com/images/g/BBB/s-l1600.jpg'], kept[0].get('image_urls')
assert kept[0]['image_url'].endswith('/AAA/s-l1600.jpg')
assert kept[1]['image_urls'] == ['https://dealer.example/photos/back.jpg'], 'a model-given image is kept as is'
# An eBay candidate whose model-given reverse is a carousel photo is corrected by the probe.
kept = stuffapp._market_verify_live([{'title': 'c', 'listing_url': 'https://www.ebay.com/itm/1', 'live_evidence': '',
                                      'image_urls': ['https://i.ebayimg.com/images/g/AAA/s-l225.jpg', 'https://i.ebayimg.com/thumbs/images/g/CCC/s-l300.jpg'],
                                      'image_url': 'https://i.ebayimg.com/images/g/AAA/s-l225.jpg'}])
assert kept[0]['image_urls'] == ['https://i.ebayimg.com/images/g/AAA/s-l1600.jpg', 'https://i.ebayimg.com/images/g/BBB/s-l1600.jpg'], kept[0].get('image_urls')
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
# Banknote acquisition examines the full gallery, including later reverse views.
from unittest.mock import patch
import hashlib
four_url='https://www.ebay.com/itm/123456789012'
four_urls=['https://i.ebayimg.com/images/g/'+key+'/s-l1600.jpg' for key in ('AAA','FRONT2','BBB','BACK2')]
IMAGES[four_urls[1]]=jpeg_bytes((230,20,10));IMAGES[four_urls[3]]=jpeg_bytes((10,20,230))
four_html='<h1>Exact four-photo banknote listing</h1><script type="application/ld+json">'+json.dumps({'@type':'Product','url':four_url,'image':four_urls})+'</script>'
PAGES[four_url]=(200,four_html)
with stuffapp.app.app_context():
    candidate={'title':'Exact note','listing_url':four_url,'image_urls':[four_urls[0],four_urls[1]]}
    seen=[]
    def all_views(photos):
        seen.append(len(photos));return classify(photos)
    with patch.object(stuffapp,'_classify_banknote_listing_photos',side_effect=all_views):
        stored=stuffapp._market_store_images(candidate,category='banknotes')
    assert seen==[4],seen
    assert len(candidate['_listing_photo_assets'])==4
    assert open(os.path.join(stuffapp.UPLOAD_FOLDER,stored['image_2']),'rb').read()==BACK
    db=stuffapp.get_db()
    record_id=stuffapp._market_create_record(db,'banknotes',dict(candidate,country='Test',denomination='1'),images=stored)
    db.commit()
    assert db.execute('SELECT COUNT(*) FROM record_documents WHERE record_id=?',(record_id,)).fetchone()[0]==4
    # The exact signed-in browser capture works when a server page fetch is blocked.
    stuffapp.banknote_check_sources.ebay_listing_captures.save(db,
        {'url':four_url,'title':'Exact four-photo banknote listing','text':'This is the exact purchased banknote listing with four photographs.','images':four_urls},
        [{'item_id':'123456789012','quantity':1}])
    db.commit()
    with patch.object(stuffapp,'_market_fetch_page',side_effect=AssertionError('Should use exact capture')):
        captured=stuffapp._market_store_images(dict(candidate),category='banknotes')
    assert set(captured)=={'image_1','image_2'},captured
    regional=dict(candidate,listing_url='https://www.ebay.co.uk/itm/a-note/123456789012?hash=tracking')
    with patch.object(stuffapp,'_market_fetch_page',side_effect=AssertionError('Should use canonical capture')):
        regional_images=stuffapp._market_store_images(regional,category='banknotes')
    regional_id=stuffapp._market_create_record(db,'banknotes',dict(regional,country='Test',denomination='1'),images=regional_images)
    db.commit()
    assert db.execute('SELECT url FROM banknote_original_listings WHERE banknote_id=?',(regional_id,)).fetchone()[0]==four_url
    assert db.execute('SELECT COUNT(*) FROM record_documents WHERE record_id=?',(regional_id,)).fetchone()[0]==4
    # Cached originals also work without a readable/captured page.
    db.execute('DELETE FROM ebay_listing_captures WHERE url=?',(four_url,));db.commit()
    with patch.object(stuffapp,'_market_fetch_page',return_value=(None,'')):
        cached=stuffapp._market_store_images(dict(candidate),category='banknotes')
    assert set(cached)=={'image_1','image_2'},cached
    with patch.object(stuffapp,'_classify_banknote_listing_photos',side_effect=RuntimeError('Unavailable')):
        failed=stuffapp._market_store_images(dict(candidate),category='banknotes')
    assert failed=={},failed
    assert len(candidate['_listing_photo_assets'])==4
with stuffapp.app.app_context(),patch.object(stuffapp,'_market_fetch_page',return_value=(None,'')):
    unverified=stuffapp._market_store_images({'listing_url':'https://www.ebay.com/itm/111111111111','image_urls':[four_urls[0],four_urls[1]]},category='banknotes')
    assert unverified=={},unverified
# Exact-item redirects are not gallery evidence for the requested item.
def wrong_item(url,limit=0):
    stuffapp._MARKET_LAST_URL.final='https://www.ebay.com/itm/999999999999'
    return 200,EBAY_PAGE
with patch.object(stuffapp,'_market_fetch_page',side_effect=wrong_item):
    assert stuffapp._market_page_image_urls(four_url)==[]
print('VERIFIED BANKNOTE GALLERY OK')
print('ALL MARKET-IMAGES ASSERTIONS PASSED')
