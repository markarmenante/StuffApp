"""Provenance & Pedigree and Rarity & Population (Mark, 2026-09-16).

Covers: the schema lands on both tables; the detail pages render both
panels; hand-entered provenance events add / delete and move the
earliest-documented marker; a research job (model mocked) stores the
found chain, replaces only the research rows on a rerun, and reports
through the poll URL; the rarity job stores the census; the overview
pages render and sort; the model output cleaners are tolerant.

Run: python tests/test_pedigree.py
"""
import os, sys, json, time, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-pedigree-')
os.environ['ANTHROPIC_API_KEY'] = 'test-key'

import app as stuffapp

client = stuffapp.app.test_client()

# ── schema ────────────────────────────────────────────────────────────
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    for table in ('coins', 'banknotes'):
        cols = stuffapp._table_cols(db, table)
        for c in ('provenance_summary', 'provenance_earliest', 'provenance_restriction',
                  'provenance_searched_at', 'rarity_known', 'rarity_same', 'rarity_finer',
                  'rarity_rank', 'rarity_die', 'rarity_summary', 'rarity_searched_at'):
            assert c in cols, (table, c)
    assert 'provenance_events' in {
        r['name'] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    db.execute(
        "INSERT INTO coins (id, coin_id, region, authority, denomination, mint, date_1, "
        "date_1_text, weight, coin_references, description, vendor, purchase_date, price, "
        "status) VALUES ('c1', 'C 1', 'Aegina', 'Aegina civic', 'Stater', '', -480, "
        "'480 BC - 440 BC', 12.24, 'Milbank IIIa; HGC 435', "
        "'Turtle. Ex CNG 87 (2011), lot 245.', 'Kirk Davis', '2026-02-22', 4800, 'Own')")
    db.execute(
        "INSERT INTO banknotes (id, banknote_id, country, denomination, series, pick_number, "
        "serial_number, grade, grade_numeric, grading_authority, slab_number, date_1, "
        "vendor, purchase_date, price, status) VALUES ('b1', 'P 001', 'French Indochina', "
        "'5 Piastres', 'ND (1946)', 'P-55b', 'A.1234 567', '65 EPQ', 65, 'PMG', "
        "'8078166-001', 1946, 'Heritage', '2026-09-11', 900, 'Own')")
    db.commit()
print('schema OK')

# ── cleaners ──────────────────────────────────────────────────────────
cd = stuffapp._pedigree_clean_date
assert cd('2015-01-07') == '2015-01-07'
assert cd('2015-1-7') == '2015-01-07'
assert cd('7 January 2015') == '2015-01-07'
assert cd('January 2015') == '2015-01'
assert cd('c. 1978') == '1978'
assert cd('1978') == '1978'
assert cd('') == '' and cd(None) == ''
assert stuffapp._pedigree_clean_confidence(85) == 0.85
assert stuffapp._pedigree_clean_confidence(0.4) == 0.4
assert stuffapp._pedigree_clean_confidence('x') is None
assert stuffapp._pedigree_clean_int('1,234 graded') == 1234
assert stuffapp._pedigree_clean_int(None) is None
assert stuffapp._pedigree_clean_int(True) is None
assert stuffapp._normalise_provenance_event({'kind': 'nonsense', 'house': 'CNG', 'url': 'javascript:x'})['kind'] == 'other'
assert stuffapp._normalise_provenance_event({'kind': 'auction', 'house': 'CNG', 'url': 'javascript:x'})['url'] == ''
assert stuffapp._normalise_provenance_event({'kind': 'auction'}) is None
parsed = stuffapp._pedigree_parse_json('Here you go:\n```json\n{"events": [], "summary": "s"}\n```')
assert parsed == {'events': [], 'summary': 's'}
try:
    stuffapp._pedigree_parse_json('no json here')
    raise AssertionError('expected RuntimeError')
except RuntimeError:
    pass
label = stuffapp._pedigree_label('coins', {'region': 'Aegina', 'authority': 'Aegina civic',
                                           'denomination': 'Stater', 'date_1_text': '480 BC - 440 BC'})
assert label == 'Aegina, Aegina civic, Stater — 480 BC - 440 BC', label
prompt = stuffapp._provenance_prompt('coins', {'id': 'c1', 'weight': 12.24, 'mint': 'Aegina',
                                              'denomination': 'Stater', 'coin_references': 'Milbank IIIa'}, [])
assert '12.24' in prompt and 'Greece' in prompt and 'THIS specimen' in prompt
rprompt = stuffapp._rarity_prompt('banknotes', {'id': 'b1', 'pick_number': 'P-55b', 'grade': '65 EPQ',
                                               'slab_number': '8078166-001', 'grading_authority': 'PMG'})
assert 'pmgnotes.com' in rprompt and '8078166-001' in rprompt
print('cleaners OK')

# ── panels render ─────────────────────────────────────────────────────
r = client.get('/coins/c1')
assert r.status_code == 200, r.status_code
html = r.get_data(as_text=True)
assert 'Provenance &amp; Pedigree' in html and 'Rarity &amp; Population' in html
assert 'pdgData' in html and 'Bought by the owner' in html
assert '/coins/c1/pedigree/provenance/events' in html
r = client.get('/banknotes/b1')
assert r.status_code == 200, r.status_code
html = r.get_data(as_text=True)
assert 'Census &amp; rarity' in html and 'pdgRarResearch' in html
# A new record has no panels (nothing to research yet).
r = client.get('/coins/new')
assert r.status_code == 200 and 'pdgData' not in r.get_data(as_text=True)
# The list toolbar links to both overviews.
r = client.get('/coins')
assert '/coins/pedigree/provenance' in r.get_data(as_text=True)
assert '/coins/pedigree/rarity' in r.get_data(as_text=True)
r = client.get('/watches')
assert '/watches/pedigree/' not in r.get_data(as_text=True)
print('panels render OK')

# ── hand-entered events ───────────────────────────────────────────────
r = client.post('/coins/c1/pedigree/provenance/events', json={
    'date': '7 January 2015', 'kind': 'auction', 'house': 'CNG', 'sale': 'Triton XVIII',
    'lot': '245', 'price': '$4,000', 'url': 'https://cngcoins.com/x', 'notes': 'ticket'})
assert r.status_code == 200, r.get_data(as_text=True)
data = r.get_json()
assert len(data['events']) == 1 and data['events'][0]['source'] == 'manual'
assert data['events'][0]['sort_date'] == '2015-01-07'
assert data['earliest'] == '2015-01-07', data
assert data['purchase']['house'] == 'Kirk Davis' and data['purchase']['price'] == '$4,800'
manual_id = data['events'][0]['id']
# An earlier hand-entered event moves the marker back.
r = client.post('/coins/c1/pedigree/provenance/events', json={
    'date': '1978', 'kind': 'collection', 'house': 'Hunt collection'})
assert r.get_json()['earliest'] == '1978'
hunt_id = [e for e in r.get_json()['events'] if e['house'] == 'Hunt collection'][0]['id']
# Empty event refused.
r = client.post('/coins/c1/pedigree/provenance/events', json={'date': '2020'})
assert r.status_code == 400
# Delete recomputes the marker.
r = client.delete(f'/coins/c1/pedigree/provenance/events/{hunt_id}')
assert r.status_code == 200 and r.get_json()['earliest'] == '2015-01-07', r.get_json()
# Unknown record / category 404.
assert client.get('/coins/nope/pedigree/provenance/events').status_code == 404
assert client.get('/watches/c1/pedigree/provenance/events').status_code == 404
print('manual events OK')

# ── research job (model mocked) ───────────────────────────────────────
calls = []


def fake_model_call(kind, category, prompt, images):
    calls.append((kind, category))
    if kind == 'provenance':
        # The hand-entered CNG event must have been shown to the model.
        assert 'Triton XVIII' in prompt
        return {
            'events': [
                {'date': '2011-05-18', 'date_text': '18 May 2011', 'kind': 'auction',
                 'house': 'CNG', 'sale': 'CNG 87', 'lot': '245', 'price': '$3,250',
                 'url': 'https://cngcoins.com/Coin.aspx?CoinID=1', 'basis': 'weight 12.24 g + Milbank IIIa',
                 'confidence': 0.9},
                {'date': '1994', 'kind': 'collection', 'house': 'Ex Leu 1994', 'confidence': 0.5},
                {'kind': 'auction'},  # dropped: nothing identifies it
            ],
            'summary': 'Traced to CNG 87 in 2011 by weight and die; earlier Leu appearance inferred.',
            'earliest': '1994', 'restriction': 'Greece — coins designated 2011-12-01; the May 2011 CNG appearance predates it.',
            'confidence': 0.8, 'notes': 'acsearch, CNG archive', '_searches': 5,
        }
    return {
        'known': '23', 'same_grade': 4, 'finer': 1, 'rank': 'Below finest', 'rating': 'R2 (HGC)',
        'die': 'Milbank Group IIIa, O-14/R-22, 6 of the pair recorded', 'regrade': '',
        'summary': 'Scarce type; a solid mid-range example.', 'source': 'acsearch.info (23 records), HGC 6, 435',
        'source_url': 'https://www.acsearch.info/search.html?term=aegina', 'confidence': 0.7, '_searches': 4,
    }


stuffapp._pedigree_model_call = fake_model_call


def run_job(category, record_id, kind):
    r = client.post(f'/{category}/{record_id}/pedigree/{kind}/research')
    assert r.status_code == 202, r.get_data(as_text=True)
    poll = r.get_json()['poll_url']
    for _ in range(100):
        r = client.get(poll)
        if r.status_code != 202:
            return r
        time.sleep(0.05)
    raise AssertionError('job never finished')


r = run_job('coins', 'c1', 'provenance')
assert r.status_code == 200, r.get_data(as_text=True)
res = r.get_json()
assert res['status'] == 'done'
houses = [e['house'] for e in res['events']]
assert houses == ['Ex Leu 1994', 'CNG', 'CNG'], houses  # sorted oldest first; manual kept
assert [e['source'] for e in res['events']] == ['research', 'research', 'manual']
assert res['earliest'] == '1994' and 'Greece' in res['restriction']
assert res['confidence'] == 0.8
with stuffapp.app.app_context():
    row = stuffapp.get_db().execute("SELECT * FROM coins WHERE id = 'c1'").fetchone()
    assert row['provenance_earliest'] == '1994' and row['provenance_searched_at']
    assert 'CNG 87' in row['provenance_summary']
# Rerun replaces the research rows, keeps the hand-entered one, no duplicates.
r = run_job('coins', 'c1', 'provenance')
res = r.get_json()
assert len(res['events']) == 3 and sum(1 for e in res['events'] if e['source'] == 'manual') == 1
assert [e['id'] for e in res['events'] if e['source'] == 'manual'] == [manual_id]

r = run_job('coins', 'c1', 'rarity')
res = r.get_json()
assert res['status'] == 'done' and res['known'] == 23 and res['finer'] == 1
assert res['rank'] == 'Below finest' and res['rating'] == 'R2 (HGC)'
with stuffapp.app.app_context():
    row = stuffapp.get_db().execute("SELECT * FROM coins WHERE id = 'c1'").fetchone()
    assert row['rarity_known'] == 23 and row['rarity_same'] == 4 and row['rarity_searched_at']
    assert row['rarity_source_url'].startswith('https://')

# The panel now renders the stored figures and summary.
html = client.get('/coins/c1').get_data(as_text=True)
assert 'R2 (HGC)' in html and 'Milbank Group IIIa' in html and 'Traced to CNG 87' in html
# Unknown kind / lost job.
assert client.post('/coins/c1/pedigree/nonsense/research').status_code == 404
assert client.get('/coins/c1/pedigree/provenance/job/nope').status_code == 404
# Summary edits save.
r = client.post('/coins/c1/pedigree/rarity/summary', json={'summary': 'My own note.'})
assert r.status_code == 200
with stuffapp.app.app_context():
    assert stuffapp.get_db().execute("SELECT rarity_summary FROM coins WHERE id='c1'").fetchone()[0] == 'My own note.'
print('research jobs OK')

# ── a failing model surfaces as an error, not a 500 ───────────────────
def boom(kind, category, prompt, images):
    raise RuntimeError('Provenance research temporarily unavailable (HTTP 529). Please try again.')


stuffapp._pedigree_model_call = boom
r = run_job('banknotes', 'b1', 'provenance')
assert r.status_code == 503 and 'HTTP 529' in r.get_json()['error'], r.get_json()
stuffapp._pedigree_model_call = fake_model_call
print('error path OK')

# ── overview pages + bulk run ─────────────────────────────────────────
r = client.get('/coins/pedigree/provenance')
assert r.status_code == 200, r.status_code
html = r.get_data(as_text=True)
assert 'Provenance &amp; Pedigree' in html and 'C 1' in html and '1994' in html
assert 'Research missing (0)' in html
r = client.get('/coins/pedigree/rarity?sort=number')
assert r.status_code == 200 and 'Below finest' in r.get_data(as_text=True)
r = client.get('/banknotes/pedigree/rarity')
assert r.status_code == 200
html = r.get_data(as_text=True)
assert 'Research missing (1)' in html and 'P 001' in html
assert client.get('/watches/pedigree/rarity').status_code == 404
assert client.get('/coins/pedigree/nonsense').status_code == 404

# Bulk run: only the missing note is researched; status reports done.
r = client.post('/banknotes/pedigree/rarity/run', json={'only_missing': True})
assert r.status_code in (200, 202), r.get_data(as_text=True)
for _ in range(100):
    st = client.get('/banknotes/pedigree/rarity/run/status').get_json()['state']
    if st['status'] == 'done':
        break
    time.sleep(0.05)
assert st['status'] == 'done' and st['done'] == 1 and st['failed'] == 0, st
with stuffapp.app.app_context():
    row = stuffapp.get_db().execute("SELECT * FROM banknotes WHERE id = 'b1'").fetchone()
    assert row['rarity_known'] == 23 and row['rarity_searched_at']
assert 'Research missing (0)' in client.get('/banknotes/pedigree/rarity').get_data(as_text=True)
# Nothing missing → a run finishes immediately.
r = client.post('/banknotes/pedigree/rarity/run', json={'only_missing': True})
assert r.status_code == 200 and r.get_json()['state']['total'] == 0
print('overview + bulk run OK')

print('ALL PEDIGREE TESTS PASSED')
