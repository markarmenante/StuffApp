"""Similar-banknote check: fires on the country / catalogue number /
denomination saves, matching on a shared catalogue number or on
denomination plus year or series within one country."""
import os, sys, sqlite3, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-similar-')

import app as stuffapp

t = stuffapp._banknote_catalog_tokens
assert t('P-64') == {'64'}, t('P-64')
assert t('Pick 64a') == {'64a'}
assert t('P64a; Fr. 1234, TBB B123') == {'64a', '1234', 'b123'}, t('P64a; Fr. 1234, TBB B123')
assert t('') == set() and t(None) == set()
print('CATALOG TOKENS OK')

f = stuffapp._banknote_country_fold
assert f('United States') == f('USA') == f('United States of America')
assert f('Sarawak (Malaysia)') == f('sarawak')
assert f('') == ''
print('COUNTRY FOLD OK')


def _db(rows):
    db = sqlite3.connect(':memory:')
    db.row_factory = sqlite3.Row
    stuffapp._configure_db_connection(db)
    db.execute("""CREATE TABLE banknotes (
        id TEXT PRIMARY KEY, banknote_id TEXT, cat_id TEXT, country TEXT,
        denomination TEXT, series TEXT, pick_number TEXT, date_1 INTEGER,
        date_1_text TEXT, grade TEXT, grading_authority TEXT)""")
    for r in rows:
        cols = ', '.join(r)
        db.execute(f"INSERT INTO banknotes ({cols}) VALUES ({', '.join('?' for _ in r)})",
                   list(r.values()))
    return db


db = _db([
    {'id': 'a', 'banknote_id': 'B1', 'country': 'France', 'denomination': '5 Francs',
     'series': '1943', 'pick_number': 'P-98a', 'date_1': 1943, 'date_1_text': '1943',
     'grade': '65 EPQ', 'grading_authority': 'PMG'},
    {'id': 'b', 'banknote_id': 'B2', 'country': 'France', 'denomination': '10 Francs',
     'series': '1943', 'pick_number': 'P-99', 'date_1': 1943, 'date_1_text': '1943'},
    {'id': 'c', 'banknote_id': 'B3', 'country': 'Belgium', 'denomination': '5 Francs',
     'series': '1943', 'pick_number': 'P-98a', 'date_1': 1943, 'date_1_text': '1943'},
    {'id': 'd', 'banknote_id': 'B4', 'country': 'USA', 'denomination': '$1',
     'series': '1957 B', 'pick_number': 'Fr. 1621', 'date_1': 1957, 'date_1_text': '1957'},
])

with stuffapp.app.test_request_context():
    sim = stuffapp._similar_banknotes
    # Same country + shared Pick number: the France note, not Belgium's P-98a.
    got = sim(db, 'new', {'country': 'france', 'pick_number': 'Pick 98a',
                          'denomination': None, 'date_1': None, 'series': None})
    assert [m['id'] for m in got] == ['a'], got
    assert got[0]['reason'] == 'same catalogue number 98a', got[0]
    assert got[0]['label'] == 'B1 5 Francs 1943 (P-98a) PMG 65 EPQ', got[0]['label']
    assert got[0]['url'] == '/banknotes/a'

    # Same country + denomination + year, no catalogue number yet.
    got = sim(db, 'new', {'country': 'France', 'pick_number': '',
                          'denomination': '5 francs', 'date_1': 1943, 'series': None})
    assert [m['id'] for m in got] == ['a'] and got[0]['reason'] == 'same denomination and year', got

    # Same country + denomination + series (different year form).
    got = sim(db, 'new', {'country': 'France', 'pick_number': '',
                          'denomination': '10 Francs', 'date_1': None, 'series': '1943'})
    assert [m['id'] for m in got] == ['b'] and got[0]['reason'] == 'same denomination and series', got

    # Denomination alone is not similar.
    got = sim(db, 'new', {'country': 'France', 'pick_number': '',
                          'denomination': '5 Francs', 'date_1': 1950, 'series': '1950'})
    assert got == [], got

    # The record being edited never matches itself.
    got = sim(db, 'a', {'country': 'France', 'pick_number': 'P-98a',
                        'denomination': '5 Francs', 'date_1': 1943, 'series': '1943'})
    assert got == [], got

    # US spellings fold together; Friedberg numbers count as catalogue numbers.
    got = sim(db, 'new', {'country': 'United States of America', 'pick_number': 'Fr 1621',
                          'denomination': None, 'date_1': None, 'series': None})
    assert [m['id'] for m in got] == ['d'], got

    # No country: nothing to compare against.
    assert sim(db, 'new', {'country': '', 'pick_number': 'P-98a',
                           'denomination': None, 'date_1': None, 'series': None}) == []
print('SIMILAR BANKNOTES OK')
print('ALL BANKNOTE-SIMILAR ASSERTIONS PASSED')
