"""Market Scan: a candidate bought outside the Buy button can still be
filed. Superseded candidates are kept (not deleted) when a new scan
lands, the market page lists them under Earlier candidates, and the
Bought button files any candidate — current, superseded or dismissed —
as an Ordered record without opening the listing.

Run: .venv/bin/python tests/test_market_bought.py
"""
import os, sys, json, tempfile
from datetime import datetime, timedelta

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-mbought-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuffapp

client = stuffapp.app.test_client()
stuffapp._market_store_images = lambda item: {}  # no network in tests

def seed_item(db, item_id, status, title, created_at, scan_id='scan-1'):
    payload = {'title': title, 'listing_url': f'https://example.test/{item_id}',
               'venue': 'eBay', 'seller': 'dealer', 'price': '$900', 'price_usd': 900,
               'country': 'French Indochina', 'denomination': '5 Piastres',
               'pick_number': 'P-55b', 'grade': 'Gem Unc', 'grade_numeric': 65,
               'grading_authority': 'PMG', 'designation': 'EPQ', 'date_1': 1936,
               'why': 'fills the Indochina gap', 'score': 90, 'image_urls': []}
    db.execute(
        "INSERT INTO market_scan_items (id, scan_id, category, rank, score, status, title, "
        "listing_url, venue, price, price_usd, grade_numeric, designation, closes, theme, payload, created_at) "
        "VALUES (?, ?, 'banknotes', 1, 90, ?, ?, ?, 'eBay', '$900', 900, 65, 'EPQ', NULL, 'colonial', ?, ?)",
        [item_id, scan_id, status, title, payload['listing_url'], json.dumps(payload), created_at])

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    now = datetime.utcnow()
    db.execute("INSERT INTO market_scans (id, category, started_at, finished_at, status, summary, item_count) "
               "VALUES ('scan-1', 'banknotes', ?, ?, 'done', '3 candidates', 3)",
               [now.isoformat(), now.isoformat()])
    db.execute("INSERT INTO properties (id, name) VALUES ('p1', 'Carpinteria')")
    seed_item(db, 'cur-1', 'new', 'Current candidate', now.isoformat())
    seed_item(db, 'old-1', 'superseded', 'Indochina 5 Piastres PMG 65 EPQ', (now - timedelta(days=1)).isoformat())
    seed_item(db, 'dis-1', 'dismissed', 'Dismissed one', (now - timedelta(days=2)).isoformat())
    db.commit()

    cur = stuffapp._market_items(db, 'banknotes')
    assert [i['id'] for i in cur] == ['cur-1'], cur
    earlier = stuffapp._market_items(db, 'banknotes', earlier=True)
    assert [i['id'] for i in earlier] == ['old-1', 'dis-1'], [i['id'] for i in earlier]
    assert earlier[0]['scanned_at'] == (now - timedelta(days=1)).isoformat()[:10]
    print('ITEMS OK')

# Current view: Buy + Bought + dismiss, and the Earlier candidates link.
r = client.get('/banknotes/market')
assert r.status_code == 200, r.status_code
html = r.get_data(as_text=True)
assert 'market-bought' in html and 'data-bought="1"' in html
assert 'Earlier candidates' in html and 'earlier=1' in html
assert html.count('class="market-btn market-buy" data-id="cur-1"') == 1
assert 'old-1' not in html
print('CURRENT VIEW OK')

# Earlier view: superseded and dismissed rows with Bought only, no autoscan.
r = client.get('/banknotes/market?earlier=1')
assert r.status_code == 200
html = r.get_data(as_text=True)
assert 'old-1' in html and 'dis-1' in html and 'cur-1' not in html
assert 'data-id="old-1" data-bought="1"' in html
assert 'class="market-btn market-buy" data-id="old-1"' not in html   # no plain Buy there
assert 'Scan of' in html and 'Dismissed' in html
assert 'Current scan' in html
print('EARLIER VIEW OK')

# Bought on a superseded candidate files an Ordered record.
r = client.post('/banknotes/market/old-1/buy', json={'location': 'Carpinteria'})
d = r.get_json()
assert r.status_code == 200 and d['ok'] and d['record_id'], d
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    row = db.execute("SELECT status, country, denomination, pick_number, grading_authority, grade_modifier, property_name "
                     "FROM banknotes WHERE id = ?", [d['record_id']]).fetchone()
    assert row['status'] == 'Ordered' and row['country'] == 'French Indochina', dict(row)
    assert row['pick_number'] == 'P-55b' and row['grading_authority'] == 'PMG' and row['grade_modifier'] == 'EPQ', dict(row)
    assert row['property_name'] == 'Carpinteria'
    it = db.execute("SELECT status, record_id FROM market_scan_items WHERE id = 'old-1'").fetchone()
    assert it['status'] == 'ordered' and it['record_id'] == d['record_id'], dict(it)
# Filing it again is idempotent (same record).
r2 = client.post('/banknotes/market/old-1/buy', json={'location': 'Carpinteria'})
assert r2.get_json()['record_id'] == d['record_id']
# The filed note is on the list (default All view).
r = client.get('/banknotes')
assert d['record_id'] in r.get_data(as_text=True)
print('BOUGHT FILES OK')
print('ALL MARKET-BOUGHT ASSERTIONS PASSED')
