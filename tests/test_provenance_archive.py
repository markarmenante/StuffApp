"""Provenance research: the acsearch.info archive sweep — queries built
from the record, lots kept by weight, lot pages and photographs read,
candidates handed to the model with tags, the matched lot's text filling
the record's EMPTY fields only (never the purchase fields)."""
import os, sys, json, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-prov-')
os.environ['ANTHROPIC_API_KEY'] = 'test-key'

import app as stuffapp

stuffapp.app.config['TESTING'] = True
with stuffapp.app.app_context():
    stuffapp.init_db()
client = stuffapp.app.test_client()
hdr = {'Accept': 'application/json'}

# ── A fake acsearch: the real page shape (results JSON + lot page) ──
LOTS = [
    {"id": 14261144, "title": "Noble Numismatics, Auction 138, Lot 2867",
     "description": "Greek Silver &amp; Bronze Coins  \nAttica, Aegina, silver stater, (12.24 g), obv. sea turtle...",
     "image": "https://media.acsearch.info/archive/157/13808/14261144.s.jpg", "date": "18.03.2025", "price": "*", "last": True},
    {"id": 11904598, "title": "Auktionshaus H. D. Rauch, Auction 117, Lot 438",
     "description": "AIGINA. Stater (12,24 g), ca. 525-480 v. Chr. Av.: Wasserschildkröte.",
     "image": "https://media.acsearch.info/archive/17/11550/11904598.s.jpg", "date": "07.12.2023", "price": "*", "last": True},
    {"id": 999, "title": "Roma Numismatics Limited, E-Sale 113, Lot 128",
     "description": "Aegina AR Stater. 12.41g, 20mm, 6h. Sea turtle / skew incuse.",
     "image": "https://media.acsearch.info/archive/1/1/999.s.jpg", "date": "28.09.2023", "price": "*", "last": True},
    {"id": 777, "title": "Savoca Numismatik , Live Online Auction 6, Lot 194",
     "description": "Aegina stater, 20 mm, no weight given.",
     "image": "", "date": "27.12.2015", "price": "*", "last": True},
]
FULL = {
    14261144: ('<h2>Description</h2><div id="details-description">Attica, Aegina (Aigina), silver stater, (12.24 g), '
               'obv. sea turtle, rev. incuse (HGC 6, 428). Die axis 3h. 20 mm. Toned, good very fine.<br>'
               'Ex Sotheby Auction Sale, New York December 9, 1993 &quot;The Athena Fund Sale&quot; (Lot 392 part).</div>'),
}
FETCHED = []

def fake_fetch_page(url, limit=0):
    FETCHED.append(url)
    if 'search.html?id=' in url:
        lot_id = int(url.rsplit('=', 1)[1])
        return 200, FULL.get(lot_id, '<html>no description</html>')
    if 'search.html?term=' in url:
        return 200, ('<html><script>acsearch.initSearchResults = ' + json.dumps(LOTS)
                     + ';</script><div>results</div></html>')
    return 404, ''

PNG = bytes.fromhex('89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4890000000d49444154'
                    '789c63f8cfc0f01f0005000201f9b01b6e0000000049454e44ae426082')
IMAGES = []
def fake_fetch_image(url, limit=0):
    IMAGES.append(url)
    return (PNG, 'png') if 'media.acsearch.info' in url else (None, None)

stuffapp._market_fetch_page = fake_fetch_page
stuffapp._market_fetch_image = fake_fetch_image

# ── 1. Query building and the sweep ──────────────────────────────────
row = {'id': 'c1', 'region': 'Aegina', 'authority': 'Attica', 'mint': '', 'denomination': 'Stater',
       'weight': 12.24, 'coin_references': 'HGC 6, 435; Milbank pl. I, 15; Ex CNG 100, lot 12',
       'serial_number': None}
queries, key = stuffapp._provenance_archive_queries('coins', row)
assert key == ('weight', 12.24), key
assert queries == ['Aegina Stater 12.24', 'Attica Stater 12.24', 'HGC 6 435 12.24', 'Milbank pl. I 15 12.24'], queries

with stuffapp.app.app_context():
    sweep = stuffapp._provenance_archive_sweep('coins', row)
cands = sweep['candidates']
assert sweep['keyed'] is True
assert [c['id'] for c in cands] == [14261144, 11904598], [c['title'] for c in cands]   # 12.41 g and no-weight lots dropped
assert cands[0]['tag'] == 'C1' and cands[0]['weight'] == 12.24 and cands[1]['weight'] == 12.24   # "12,24 g" parsed
assert cands[0]['sort_date'] == '2025-03-18' and cands[0]['house'] == 'Noble Numismatics' and cands[0]['lot'] == '2867'
assert 'Athena Fund Sale' in cands[0]['full'], cands[0]['full']          # the lot page, not the snippet
assert cands[1]['full'].startswith('AIGINA. Stater (12,24 g)')          # no lot page → the snippet
assert cands[0].get('image_b64') and cands[0]['image_media'] == 'image/png'
assert any(u.endswith('14261144.m.jpg') for u in IMAGES)                # the 400 px photo, not the thumbnail
assert '4 queries, 4 lots, 2 at 12.24 g' in sweep['status'] and '2 photographs compared' in sweep['status'], sweep['status']

block = stuffapp._provenance_archive_block('coins', sweep)
assert '[C1] Noble Numismatics, Auction 138, Lot 2867 — 18.03.2025 — 12.24 g — https://www.acsearch.info/search.html?id=14261144' in block
assert 'Athena Fund Sale' in block and 'Roma Numismatics' not in block
prompt = stuffapp._provenance_prompt('coins', row, [], archive=sweep)
assert 'CANDIDATE LOTS FROM THE AUCTION ARCHIVE' in prompt and '"candidate"' in prompt
assert 'already been swept' in prompt

# The archive down: a status line, not an exception, and no candidates.
stuffapp._market_fetch_page = lambda url, limit=0: (403, 'Forbidden')
with stuffapp.app.app_context():
    down = stuffapp._provenance_archive_sweep('coins', row)
assert down['candidates'] == [] and 'unreachable' in down['status'] and 'HTTP 403' in down['status'], down
assert 'No candidate lots' in stuffapp._provenance_archive_block('coins', down)
stuffapp._market_fetch_page = fake_fetch_page

# No weight on the record: type matches, capped, flagged as leads.
q2, k2 = stuffapp._provenance_archive_queries('coins', dict(row, weight=None))
assert k2 == (None, None) and q2 == ['HGC 6 435 Stater', 'Milbank pl. I 15 Stater', 'Aegina Attica Stater'], q2
with stuffapp.app.app_context():
    typed = stuffapp._provenance_archive_sweep('coins', dict(row, weight=None))
assert typed['keyed'] is False and len(typed['candidates']) == 4 and 'type matches' in typed['status']

# A banknote: the serial number is the key.
q3, k3 = stuffapp._provenance_archive_queries('banknotes', {
    'serial_number': 'A 123456', 'country': 'Philippines', 'denomination': '20 Pesos', 'pick_number': 'P-98a'})
assert k3 == ('serial', 'A 123456') and q3 == ['A 123456', 'Philippines 20 Pesos A 123456'], q3

# ── 2. End to end through fetch_provenance / _store_provenance ───────
r = client.post('/coins/new', data={'region': 'Aegina', 'authority': 'Attica', 'denomination': 'Stater',
                                    'date_1': '-500', 'weight': '12.24', 'owner': 'Mark',
                                    'purchase_date': '2026-06-01', 'price': '4500', 'vendor': 'CNG',
                                    'coin_references': 'HGC 6, 435'}, headers=hdr)
coin_id = r.get_json()['id']

CALLS = {}
def fake_model_call(kind, category, prompt, images):
    CALLS['prompt'] = prompt
    CALLS['images'] = images
    return {'events': [
        {'date': '2025-03-18', 'date_text': '18 March 2025', 'kind': 'auction', 'house': 'Noble Numismatics',
         'sale': 'Auction 138', 'lot': '2867', 'price': '', 'url': '',
         'basis': 'weight 12.24 g + same obverse die, flan notch at 2h', 'confidence': 0.9, 'notes': '', 'candidate': 'c1'},
        {'date': '1993-12-09', 'date_text': '9 December 1993', 'kind': 'auction', 'house': "Sotheby's New York",
         'sale': 'The Athena Fund Sale', 'lot': '392 (part)', 'price': '', 'url': '',
         'basis': 'stated in the Noble 138 description', 'confidence': 0.8, 'notes': '', 'candidate': 'C1'},
        {'date': '2023-12-07', 'date_text': '7 December 2023', 'kind': 'auction', 'house': 'H. D. Rauch',
         'sale': 'Auction 117', 'lot': '438', 'price': '', 'url': '', 'basis': 'weight only; different obverse die',
         'confidence': 0.2, 'notes': 'rejected', 'candidate': 'C2'},
    ], 'summary': 'C1 is this coin; C2 shares the weight but not the dies.', 'earliest': '1993-12-09',
        'restriction': 'None applies', 'confidence': 0.85, 'notes': 'acsearch candidates', '_searches': 2}
stuffapp._pedigree_model_call = fake_model_call

SPEC_INPUT = {}
def fake_specs(coin_like, provider='anthropic'):
    SPEC_INPUT.update(coin_like)
    return {'die_axis': '3h', 'size': '20', 'weight': '12.99', 'coin_references': 'HGC 6, 428',
            'obv_rev': 'Sea turtle / skew incuse', 'vendor': "Sotheby's", 'price': '99999',
            'purchase_date': '1993-12-09', 'grade_condition': 'Toned, good very fine',
            'sources': 'auction lot text'}
stuffapp.fetch_coin_specs = fake_specs

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    coin_row = db.execute("SELECT * FROM coins WHERE id = ?", (coin_id,)).fetchone()
    result = stuffapp._run_pedigree_research('provenance', 'coins', coin_row)

assert 'AUCTION LOT MATCHED TO THIS COIN — Noble Numismatics, Auction 138, Lot 2867' in SPEC_INPUT['description']
assert 'Athena Fund Sale' in SPEC_INPUT['description']
# Candidate photographs rode along with their captions, after the coin's own (none on this record).
caps = [i.get('caption') for i in CALLS['images']]
assert caps and caps[0].startswith('Archive candidate [C1] — Noble Numismatics, Auction 138, Lot 2867'), caps
assert set(result['filled']) == {'die_axis', 'size', 'obv_rev', 'grade_condition'}, result['filled']
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    c = db.execute("SELECT * FROM coins WHERE id = ?", (coin_id,)).fetchone()
assert c['die_axis'] == '3h' and c['size'] == 20.0 and c['obv_rev'] == 'Sea turtle / skew incuse'
assert c['weight'] == 12.24, c['weight']                 # never overwritten
assert c['coin_references'] == 'HGC 6, 435', c['coin_references']  # filled field was not empty → kept
assert c['vendor'] == 'CNG' and c['price'] == 4500 and c['purchase_date'] == '2026-06-01'   # purchase fields untouched
assert 'Filled from Noble Numismatics, Auction 138, Lot 2867:' in result['summary'] and 'die axis' in result['summary']
assert 'Archive sweep — acsearch.info: 3 queries' in result['summary'], result['summary']
events = result['events']
assert [e['house'] for e in events][:2] == ["Sotheby's New York", 'Noble Numismatics'], [e['house'] for e in events]
noble = next(e for e in events if e['house'] == 'Noble Numismatics')
assert noble['url'] == 'https://www.acsearch.info/search.html?id=14261144'    # URL supplied from the candidate
assert result['earliest'] == '1993-12-09'

# The Check button's apply route still works through the shared helper.
r = client.post(f'/coins/{coin_id}/apply-lookup-specs', json={'updates': {'metal': 'AR Silver', 'weight': '12.24'}})
assert r.status_code == 200 and r.get_json()['fields'] == ['metal', 'weight'], r.get_json()

print('test_provenance_archive: ok')

# ── 3. The Dionysios case: the identified lot IS the purchase sale, so
#      it is absent from the events — the match field still carries it,
#      the record stores it with its URL, and the fill runs off it.
r = client.post('/coins/new', data={'region': 'Syracuse', 'authority': 'Dionysios I', 'denomination': 'Dekadrachm',
                                    'date_1': '-400', 'weight': '12.24', 'owner': 'Mark', 'vendor': 'CNG',
                                    'purchase_date': '2024-01-09'}, headers=hdr)
coin2 = r.get_json()['id']
def fake_model_call_match(kind, category, prompt, images):
    return {'events': [
        {'date': '1999-09-15', 'date_text': '15 September 1999', 'kind': 'auction', 'house': 'CNG',
         'sale': 'CNG 51', 'lot': '152', 'price': '', 'url': '', 'basis': "stated in the record's pedigree",
         'confidence': 0.55, 'notes': '', 'candidate': ''}],
        'match': {'candidate': 'C1', 'confidence': 0.9, 'basis': '34 mm, 43.16 g, 9h, same dies'},
        'summary': 'Only C1 matches; it is the purchase sale so it is not an event.', 'earliest': '1999-09-15',
        'restriction': 'None applies', 'confidence': 0.6, 'notes': '', '_searches': 3}
stuffapp._pedigree_model_call = fake_model_call_match
SPEC_INPUT.clear()
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    row2 = db.execute("SELECT * FROM coins WHERE id = ?", (coin2,)).fetchone()
    res2 = stuffapp._run_pedigree_research('provenance', 'coins', row2)
assert res2['match_title'] == 'Noble Numismatics, Auction 138, Lot 2867 (18.03.2025)', res2['match_title']
assert res2['match_url'] == 'https://www.acsearch.info/search.html?id=14261144'
assert res2['match_basis'] == '34 mm, 43.16 g, 9h, same dies'
assert 'AUCTION LOT MATCHED TO THIS COIN — Noble Numismatics' in SPEC_INPUT['description']   # the fill ran
assert set(res2['filled']) == {'die_axis', 'size', 'coin_references', 'obv_rev', 'grade_condition'}, res2['filled']
assert [e['house'] for e in res2['events']] == ['CNG']              # the purchase sale stays out of the chain
with stuffapp.app.app_context():
    c2 = stuffapp.get_db().execute("SELECT * FROM coins WHERE id = ?", (coin2,)).fetchone()
assert c2['provenance_match_title'].startswith('Noble Numismatics') and c2['provenance_match_url'].endswith('id=14261144')
assert c2['coin_references'] == 'HGC 6, 428' and c2['vendor'] == 'CNG' and c2['purchase_date'] == '2024-01-09'
html = client.get(f'/coins/{coin2}').get_data(as_text=True)
assert 'Identified in the archive:' in html and 'id=14261144' in html

# A low-confidence match (below 0.5) is neither stored nor filled from.
def fake_model_call_weak(kind, category, prompt, images):
    d = fake_model_call_match(kind, category, prompt, images)
    d['match'] = {'candidate': 'C2', 'confidence': 0.3, 'basis': 'weight only'}
    return d
stuffapp._pedigree_model_call = fake_model_call_weak
with stuffapp.app.app_context():
    res3 = stuffapp._run_pedigree_research('provenance', 'coins', row2)
assert res3['match_title'] == '' and res3['match_url'] == '' and res3['filled'] == [], res3
print('test_provenance_archive (match): ok')

# ── 4. Rarity: the type sweep counts the archive; the counts stand in
#      wherever the model leaves a null (the Chalcedon stater's dashes).
TYPE_LOTS = [
    {"id": 101, "title": "Numisfitz, Auction 3, Lot 10", "description": "KALCHEDON. Stater (15.18 g). HGC 7, 509. Good VF.", "image": "", "date": "18.03.2025", "price": "*"},
    {"id": 102, "title": "Naumann, Auction 119, Lot 55", "description": "Bithynia, Kalchedon stater, 15.2 g. Extremely fine.", "image": "", "date": "07.08.2022", "price": "*"},
    {"id": 103, "title": "CNG, Triton IV, Lot 232", "description": "Chalcedon stater 15.18g. EF, toned.", "image": "", "date": "05.12.2000", "price": "*"},
    {"id": 104, "title": "Tauler & Fau, Auction 100, Lot 7", "description": "Calcedonia. Estatera. 15,1 g. MBC+.", "image": "", "date": "01.02.2024", "price": "*"},
    {"id": 105, "title": "Leu, Web 30, Lot 300", "description": "Kalchedon. Stater. Ch AU.", "image": "", "date": "10.07.2024", "price": "*"},
    {"id": 106, "title": "Roma, E-Sale 90, Lot 12", "description": "Kalchedon stater, no grade words at all.", "image": "", "date": "10.07.2023", "price": "*"},
]
def fake_fetch_type(url, limit=0):
    if 'term=' in url:
        return 200, ('<h1>Results <b><span>1</span>-<span>6</span></b> of <b>1,234</b></h1><script>acsearch.initSearchResults = '
                     + json.dumps(TYPE_LOTS) + ';</script>')
    return 404, ''
stuffapp._market_fetch_page = fake_fetch_type
r = client.post('/coins/new', data={'region': 'Chalcedon', 'authority': 'Bithynia', 'denomination': 'Stater',
                                    'date_1': '-380', 'weight': '15.18', 'owner': 'Mark', 'grade': 'EF',
                                    'coin_references': 'HGC 7, 509; SNG BM 96'}, headers=hdr)
coin3 = r.get_json()['id']
RAR = {}
def fake_rarity_call(kind, category, prompt, images):
    RAR['prompt'] = prompt
    return {'known': None, 'die_pair_known': None, 'auction_10y': None, 'finer': None, 'census_graded': None,
            'same_grade': None, 'rank': 'Unknown', 'rating': 'R1 (HGC)', 'die': '', 'regrade': '',
            'summary': 'No die study exists for Chalcedon.', 'source': 'HGC 7, 509', 'source_url': '', '_searches': 4}
stuffapp._pedigree_model_call = fake_rarity_call
with stuffapp.app.app_context():
    row3 = stuffapp.get_db().execute("SELECT * FROM coins WHERE id = ?", (coin3,)).fetchone()
    rar = stuffapp._run_pedigree_research('rarity', 'coins', row3)
assert 'TYPE RECORD FROM THE AUCTION ARCHIVE' in RAR['prompt'] and "query 'HGC 7 509': 1234 records" in RAR['prompt'], RAR['prompt'][-1500:]
assert '6 distinct lots retrieved; 5 dated within the last ten years' in RAR['prompt']
assert 'this coin reads as EF — 1 lot grades finer, 2 the same' in RAR['prompt'], RAR['prompt'][-900:]
assert rar['known'] == 1234 and rar['market'] == 5 and rar['finer'] == 1, (rar['known'], rar['market'], rar['finer'])
assert rar['rank'] == 'Typical', rar['rank']       # 1 finer of 5 graded (20%) — the sweep's own standing, since the model said Unknown
assert rar['source_url'].startswith('https://www.acsearch.info/search.html?term=HGC+7+509')
assert 'acsearch.info (6 lots, retrieved' in rar['source'] and rar['source'].startswith('HGC 7, 509; ')
assert rar['summary'].endswith("grades stated on 5, 1 finer than this coin's EF, 2 the same."), rar['summary'][-200:]
with stuffapp.app.app_context():
    c3 = stuffapp.get_db().execute("SELECT * FROM coins WHERE id = ?", (coin3,)).fetchone()
assert c3['rarity_known'] == 1234 and c3['rarity_market'] == 5 and c3['rarity_finer'] == 1 and c3['rarity_rank'] == 'Typical'
print('test_provenance_archive (rarity): ok')

# ── 5. Market Scan: archive context on coin candidates ───────────────
MK_LOTS = TYPE_LOTS + [
    {"id": 201, "title": "Peus, Auction 433, Lot 1224", "description": "Kalchedon stater (15.18 g). EF. Ex MMAG 54.", "image": "", "date": "01.11.2022", "price": "*"},
]
def fake_fetch_market(url, limit=0):
    if 'term=' in url:
        return 200, ("<h1>Results <b>1</b>-<b>7</b> of <b>3'162</b></h1><script>acsearch.initSearchResults = "
                     + json.dumps(MK_LOTS) + ';</script>')
    return 404, ''
stuffapp._market_fetch_page = fake_fetch_market
items = [
    {'title': 'Kalchedon stater, EF', 'listing_url': 'https://www.vcoins.com/x/1', 'region': 'Chalcedon', 'authority': 'Bithynia',
     'mint': None, 'denomination': 'Stater', 'references': 'HGC 7, 509', 'grade': 'EF', 'weight': 15.18, 'score': 50},
    {'title': 'Some drachm, no weight', 'listing_url': 'https://www.vcoins.com/x/2', 'region': 'Kyme', 'authority': None,
     'mint': None, 'denomination': 'Drachm', 'references': '', 'grade': 'Good VF', 'weight': None, 'score': 50},
]
with stuffapp.app.app_context():
    note = stuffapp._market_archive_context(items, 'coins')
assert note == 'acsearch context on 2 candidates', note
a = items[0]['archive']
assert a['type_total'] == 3162 and a['ten_years'] == 6 and a['graded'] == 6 and a['finer'] == 1, a
assert [p['title'] for p in a['prior']] == ['Numisfitz, Auction 3, Lot 10', 'Peus, Auction 433, Lot 1224', 'CNG, Triton IV, Lot 232'], a['prior']   # the 15.18 g lots, newest first (15.2 g and 15,1 g excluded)
assert items[0]['archive_note'].startswith('Archive: type seldom offered (6 sales in 10 yrs) · EF is upper-quartile (1 of 6 finer)'), items[0]['archive_note']
assert "this coin's prior sales: Numisfitz, Auction 3, Lot 10 (18.03.2025); Peus, Auction 433, Lot 1224 (01.11.2022)" in items[0]['archive_note'], items[0]['archive_note']
assert items[0]['score'] == 57, items[0]['score']      # +4 seldom-offered type, +3 upper-quartile grade
assert items[1]['archive']['prior'] == [] and 'good VF is typical' in items[1]['archive_note'], items[1]['archive_note']
# Unreachable archive: nothing annotated, a status line, no exception.
stuffapp._market_fetch_page = lambda url, limit=0: (403, '')
fresh = [dict(items[0], score=50)]
fresh[0].pop('archive'); fresh[0].pop('archive_note')
with stuffapp.app.app_context():
    note = stuffapp._market_archive_context(fresh, 'coins')
assert 'unreachable' in note and 'archive' not in fresh[0] and fresh[0]['score'] == 50, (note, fresh[0].get('score'))
assert stuffapp._market_archive_context(items, 'banknotes') == ''
stuffapp._market_fetch_page = fake_fetch_market
# The market page renders the tag from the stored payload.
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute("INSERT INTO market_scans (id, category, started_at, finished_at, status, summary, item_count) VALUES ('s1','coins',?,?,'done','x',1)",
               ['2026-09-17T00:00:00', '2026-09-17T00:01:00'])
    it = dict(items[0], price='$1,000', price_usd=1000.0, venue='VCoins · Store', seller=None, sale_type='fixed', closes='',
              live_evidence='', verified=False, grade_numeric=45, grading_authority=None, designation='', rarity='', fills='',
              why='fills the Bithynia gap', fair='', theme='t', empire='', new_source=False, date_1=-380, date_1_text='380 BC',
              image_urls=[], image_url=None, metal='AR', owned=None)
    db.execute("INSERT INTO market_scan_items (id, scan_id, category, rank, score, status, title, listing_url, venue, price, price_usd, "
               "grade_numeric, designation, closes, theme, payload, created_at) VALUES ('i1','s1','coins',1,53,'new',?,?,?,?,?,?,?,?,?,?,?)",
               [it['title'], it['listing_url'], it['venue'], it['price'], it['price_usd'], 45, '', '', 't', json.dumps(it), '2026-09-17T00:01:00'])
    db.commit()
html = client.get('/coins/market').get_data(as_text=True)
assert 'market-tag-archive' in html and 'EF is upper-quartile' in html and 'term=HGC+7+509' in html, html[html.find('market-tags'):][:600]
print('test_provenance_archive (market): ok')
