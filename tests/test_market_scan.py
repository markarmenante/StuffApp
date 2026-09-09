"""Market Scan: candidate normalisation and ranking, the scan pipeline
with the model stubbed, the market page, and Buy filing an Ordered record."""
import os, sys, json, tempfile, time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-market-')
os.environ['ANTHROPIC_API_KEY'] = 'test-key'

import app as stuffapp

stuffapp._fetch_usd_rate = lambda currency, date_str: 1.1 if currency == 'EUR' else None
PAGES = {
    'https://www.ebay.com/itm/ended': (200, '<html><body><h1>Note</h1><div>This listing has ended.</div></body></html>'),
    'https://www.ebay.com/itm/live': (200, '<html><body><h1>Note</h1><span>Buy It Now</span><span>2 available</span></body></html>'),
    'https://www.stacksbowers.com/lot/closed': (200, '<html><body>Lot 2101 <b>Sold for $1,200</b> Prices Realized</body></html>'),
    'https://www.noonans.co.uk/lot/blocked': (403, ''),
}
stuffapp._market_fetch_page = lambda url, limit=0: PAGES.get(url, (None, ''))
stuffapp.app.config['TESTING'] = True
with stuffapp.app.app_context():
    stuffapp.init_db()
client = stuffapp.app.test_client()
hdr = {'Accept': 'application/json'}

# Seed a collection: two Philippine notes and a coin.
r = client.post('/banknotes/new', data={
    'country': 'Philippines', 'denomination': '20 Pesos', 'series': 'Victory Series 66',
    'date_1': '1944', 'pick_number': 'P-98a', 'grade_numeric': '64', 'grade_modifier': 'EPQ',
    'grading_authority': 'PMG', 'owner': 'Mark', 'purchase_date': '2026-08-01', 'price': '$450'},
    headers=hdr)
note_a = r.get_json(); assert note_a['ok'], note_a
client.post('/banknotes/new', data={
    'country': 'Philippines', 'denomination': '100 Pesos', 'series': 'Victory Series 66',
    'date_1': '1944', 'pick_number': 'P-100c', 'owner': 'Mark', 'purchase_date': '2026-07-15'},
    headers=hdr)
client.post('/coins/new', data={'region': 'Athens', 'authority': 'Attica', 'denomination': 'Tetradrachm',
                                'date_1': '-440', 'owner': 'Mark', 'purchase_date': '2026-06-01',
                                'price': '4500'}, headers=hdr)

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    holdings = stuffapp._market_holdings_summary(db, 'banknotes')
    assert 'Philippines (2)' in holdings and 'P-98a (64 EPQ)' in holdings, holdings
    coverage = stuffapp._market_denomination_coverage(db, 'banknotes')
    assert 'Philippines · Victory Series 66: 100 Pesos, 20 Pesos held' in coverage, coverage
    recent = stuffapp._market_recent_purchases(db, 'banknotes')
    assert recent.startswith('- 2026-08: Philippines 20 Pesos'), recent
    assert 'Athens' in stuffapp._market_denomination_coverage(db, 'coins')
    prompt = stuffapp._market_scan_prompt('banknotes', 'denominations', 'theme text',
                                          'PROFILE', holdings, coverage, recent)
    assert 'DENOMINATION COVERAGE' in prompt and 'RECENT PURCHASES' in prompt
    assert 'REPLACES any "major auction houses only" rule' in prompt
    coin_prompt = stuffapp._market_scan_prompt('coins', 'ancients-gaps', 't', '', '', '', '')
    assert 'ANCIENT GREEK coins only' in coin_prompt
print('PROMPT INPUTS OK')

# --- normalisation and grade rules ---
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    norm = lambda raw: stuffapp._market_normalize_item(db, 'banknotes', raw)
    base = {'title': 'Philippines 5 Pesos Victory Series 66 PMG 64 EPQ', 'country': 'Philippines',
            'denomination': '5 Pesos', 'series': 'Victory Series 66', 'year': 1944,
            'pick_number': 'P-96', 'grading_authority': 'PMG', 'grade_numeric': 64,
            'grade': 'Choice UNC 64', 'designation': 'EPQ', 'price': '$185', 'venue': 'eBay',
            'seller': 'notesRus', 'sale_type': 'fixed', 'closes': '',
            'listing_url': 'https://www.ebay.com/itm/123', 'image_url': None,
            'rarity': '', 'fills': 'Victory Series 66 5 Pesos', 'why': 'fills the 5', 'fair': '$150-200',
            'empire': 'US', 'new_source': False}
    good = norm(dict(base))
    assert good and good['grade_numeric'] == 64 and good['designation'] == 'EPQ', good
    assert good['price'] == '$185' and good['price_usd'] == 185
    assert norm(dict(base, listing_url='not a url')) is None
    assert norm(dict(base, listing_url='https://www.google.com/search?q=x')) is None
    assert norm(dict(base, price='')) is None
    assert norm(dict(base, grade_numeric=58, grade='AU 58', rarity='')) is None, 'below 64 without rarity'
    rare = norm(dict(base, grade_numeric=55, grade='AU 55', rarity='PMG census: 3 graded, none above 58'))
    assert rare and rare['grade_numeric'] == 55
    assert norm(dict(base, grade_numeric=45, grade='XF 45', rarity='rare')) is None, 'below 50 never'
    assert norm(dict(base, closes='2020-01-01')) is None, 'closed lot'
    assert norm(dict(base, sale_type='auction', closes='')) is None, 'auction without a close date'
    assert norm(dict(base, sale_type='auction', closes='2099-01-01')), 'auction with a future close'
    assert norm(dict(base, listing_url='https://www.ebay.com/sch/i.html?_nkw=x&LH_Sold=1&LH_Complete=1')) is None, 'sold search'
    assert norm(dict(base, listing_url='https://currency.ha.com/prices-realized/lot-1')) is None, 'prices realized page'
    assert norm(dict(base, why='Sold for $900 at Heritage in May')) is None, 'past sale in the text'
    assert norm(dict(base, live_evidence='listing has ended')) is None
    lively = norm(dict(base, live_evidence='Buy It Now, 2 available'))
    assert lively['live_evidence'] == 'Buy It Now, 2 available' and lively['verified'] is False
    # Page check: the venue's own wording decides; a bot wall never drops.
    ls = stuffapp._market_listing_state
    assert ls('https://www.ebay.com/itm/ended') == 'ended'
    assert ls('https://www.ebay.com/itm/live') == 'live'
    assert ls('https://www.stacksbowers.com/lot/closed') == 'ended'
    assert ls('https://www.noonans.co.uk/lot/blocked') == 'unknown'
    assert ls('https://nowhere.example/x') == 'unknown'
    kept = stuffapp._market_verify_live([
        dict(lively, listing_url='https://www.ebay.com/itm/ended'),
        dict(lively, listing_url='https://www.ebay.com/itm/live'),
        dict(lively, listing_url='https://www.noonans.co.uk/lot/blocked')])
    assert [k['listing_url'].rsplit('/', 1)[1] for k in kept] == ['live', 'blocked'], kept
    assert kept[0]['verified'] is True and kept[1]['verified'] is False
    raw_unc = norm(dict(base, grade_numeric=None, grade='Gem UNC', grading_authority=None, designation=''))
    assert raw_unc and raw_unc['grade_numeric'] == 66 and raw_unc['grading_authority'] is None
    euro = norm(dict(base, price='€1.200,00'))
    assert euro['price'] == '€1,200' and euro['price_usd'] == 1320, euro
    # Coins: XF40 floor, rarity down to 30, adjectival grades read.
    cnorm = lambda raw: stuffapp._market_normalize_item(db, 'coins', raw)
    cbase = {'title': 'Naxos tetradrachm', 'region': 'Sicily', 'authority': 'Naxos',
             'denomination': 'Tetradrachm', 'year': -460, 'grade': 'EF', 'grade_numeric': None,
             'price': 'CHF 12,000', 'venue': 'Nomos', 'sale_type': 'auction', 'closes': '2099-01-01',
             'listing_url': 'https://nomosag.com/lot/1', 'rarity': '', 'fills': 'Naxos', 'why': 'gap'}
    c = cnorm(dict(cbase))
    assert c and c['grade_numeric'] == 45 and c['date_1_text'] == '460 BC' and c['region'] == 'Sicily', c
    assert cnorm(dict(cbase, grade='VF', rarity='')) is None
    assert cnorm(dict(cbase, grade='VF', rarity='unique type'))['grade_numeric'] == 30
    # Owned match and scoring.
    dup = norm(dict(base, pick_number='P-98a', denomination='20 Pesos', title='dup'))
    dup['owned'] = stuffapp._market_owned_match(db, 'banknotes', dup)
    assert dup['owned'].startswith('B') and 'same catalogue number' in dup['owned'], dup['owned']
    good['owned'] = stuffapp._market_owned_match(db, 'banknotes', good)
    assert good['owned'] == ''
    colonial = norm(dict(base, empire='British', title='Sarawak $1', country='Sarawak', pick_number='P-20',
                         listing_url='https://www.ebay.com/itm/456'))
    colonial['owned'] = ''
    for it in (good, dup, colonial):
        it['score'] = stuffapp._market_score('banknotes', it)
    assert colonial['score'] > good['score'] > dup['score'], (colonial['score'], good['score'], dup['score'])
    deduped = stuffapp._market_dedupe([good, dict(good, title='other'), colonial])
    assert len(deduped) == 2
print('NORMALISE + RANK OK')

# --- the pipeline with the model stubbed ---
CANNED = {
    'colonial-british': [dict(base, title='Sarawak 1 Dollar 1935 PMG 65 EPQ', country='Sarawak',
                              denomination='1 Dollar', year=1935, pick_number='P-20', grade_numeric=65,
                              empire='British', fills='Sarawak — none held',
                              listing_url='https://www.stacksbowers.com/lot/sarawak')],
    'denominations': [dict(base)],
    'sources': [dict(base, title='Ceylon 5 Rupees 1942 PMG 64 EPQ', country='Ceylon', denomination='5 Rupees',
                     year=1942, pick_number='P-36', empire='British', new_source=True, venue='Noonans',
                     listing_url='https://www.noonans.co.uk/lot/ceylon', price='£420')],
    'pattern': [dict(base, title='Philippines 20 Pesos P-98a (duplicate)', pick_number='P-98a',
                     denomination='20 Pesos', listing_url='https://www.ebay.com/itm/999')],
    'colonial-continental': [dict(base, title='Malaya 10 Dollars 1941 PMG 64 EPQ', country='Malaya',
                                  denomination='10 Dollars', year=1941, pick_number='P-13', empire='British',
                                  listing_url='https://www.ebay.com/itm/ended')],
}
calls = []


def fake_theme(api_key, category, theme_key, prompt):
    calls.append(theme_key)
    if theme_key == 'pattern':
        items = [dict(it, theme=theme_key) for it in CANNED.get(theme_key, [])]
        return items, 'pattern: simulated timeout on a second call'
    items = [dict(it, theme=theme_key) for it in CANNED.get(theme_key, [])]
    return items, None


stuffapp._market_call_theme = fake_theme
r = client.post('/banknotes/market/scan')
assert r.get_json()['ok'] and r.get_json()['running']
for _ in range(100):
    st = client.get('/banknotes/market/status').get_json()
    if st['status'] != 'running':
        break
    time.sleep(0.1)
assert st['status'] == 'done', st
assert sorted(calls) == sorted(k for k, _ in stuffapp._MARKET_THEMES['banknotes']), calls
assert st['item_count'] == 4 and 'simulated timeout' in st['summary'], st
assert '1 dropped as sold/ended on their own pages' in st['summary'], st
with stuffapp.app.app_context():
    items = stuffapp._market_items(stuffapp.get_db(), 'banknotes')
titles = [it['title'] for it in items]
assert {titles[0].split()[0], titles[1].split()[0]} == {'Sarawak', 'Ceylon'}, titles  # colonial first
assert titles[-1].endswith('(duplicate)'), titles       # owned duplicate last
assert not any(t.startswith('Malaya') for t in titles), 'ended on its own page'
ceylon = next(it for it in items if it['title'].startswith('Ceylon'))
assert ceylon['new_source'] and ceylon['price'] == '£420'
print('SCAN PIPELINE OK')

# --- the page ---
html = client.get('/banknotes/market').get_data(as_text=True)
assert 'Collection</a>' in html and 'pill active market-pill' in html and 'class="toolbar-btn add"' not in html
assert 'market-row' in html and 'Sarawak 1 Dollar 1935 PMG 65 EPQ' in html
assert 'Choice UNC 65</span>' in html and '65 65' not in html
assert 'British colonial' in html and 'New source' in html and 'You have B' in html
assert 'View listing' in html and 'class="market-btn market-buy"' in html
assert 'Scanned ' in html
list_html = client.get('/banknotes').get_data(as_text=True)
assert 'Market Scan</a>' in list_html and 'class="toolbar-btn add"' in list_html
assert list_html.index('market-pill') < list_html.index('toolbar-btn add'), 'pill sits left of +'
coins_html = client.get('/coins/market').get_data(as_text=True)
assert 'Scanning the market' in coins_html or 'Rescan' in coins_html
print('PAGE OK')

# --- buy files an Ordered record; dismiss hides ---
sarawak = next(it for it in items if it['title'].startswith('Sarawak'))
r = client.post(f"/banknotes/market/{sarawak['id']}/buy")
d = r.get_json(); assert d['ok'] and d['listing_url'].startswith('https://www.stacksbowers.com'), d
with stuffapp.app.app_context():
    rec = stuffapp.get_db().execute("SELECT * FROM banknotes WHERE id = ?", [d['record_id']]).fetchone()
assert rec['status'] == 'Ordered' and rec['country'] == 'Sarawak' and rec['pick_number'] == 'P-20'
assert rec['grade_modifier'] == 'EPQ' and rec['grading_authority'] == 'PMG' and rec['price'] == '$185'
assert rec['grade_numeric'] == 65 and '65' in (rec['grade'] or ''), (rec['grade'], rec['grade_numeric'])
assert rec['vendor'] == 'notesRus' and 'Listing: https://www.stacksbowers.com' in rec['description']
assert rec['note_references'].startswith('Market Scan') and rec['cat_id'].startswith('B')
assert rec['banknote_id'], 'display number assigned'
# A second Buy on the same item reuses the record.
assert client.post(f"/banknotes/market/{sarawak['id']}/buy").get_json()['record_id'] == d['record_id']
r = client.post(f"/banknotes/market/{ceylon['id']}/dismiss"); assert r.get_json()['ok']
with stuffapp.app.app_context():
    left = [it['title'] for it in stuffapp._market_items(stuffapp.get_db(), 'banknotes')]
assert not any(t.startswith(('Sarawak', 'Ceylon')) for t in left), left
# Euro price on a coin buy lands as the USD number, with the listing price kept.
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    coin_item = stuffapp._market_normalize_item(db, 'coins', dict(cbase, price='€2,000', grade='EF'))
    rid = stuffapp._market_create_record(db, 'coins', coin_item)
    db.commit()
    coin = db.execute("SELECT * FROM coins WHERE id = ?", [rid]).fetchone()
assert coin['status'] == 'Ordered' and coin['price'] == 2200 and 'Listed at €2,000' in coin['description'], dict(coin)
assert coin['coin_id'] and coin['cat_id'] and coin['region'] == 'Sicily' and coin['date_1'] == -460
print('BUY + DISMISS OK')
print('ALL MARKET-SCAN ASSERTIONS PASSED')
