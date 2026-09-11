"""Country-history placeholder on the banknote list: a note whose country
has no era panel yet shows a placeholder at the head of its run — waiting
text while a generation is in flight, a retry offer when it is missing —
and the status / retry routes the placeholder's script polls.

Run: .venv/bin/python tests/test_country_history_placeholder.py
"""
import os, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-chist-')
os.environ.pop('ANTHROPIC_API_KEY', None)  # no generation in tests

import app as stuffapp

client = stuffapp.app.test_client()
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    # Two notes from a country with no history, one from a built-in one.
    db.execute("INSERT INTO banknotes (id, country, denomination, date_1) VALUES (9101, 'Atlantis', '5 Drachmae', 1950)")
    db.execute("INSERT INTO banknotes (id, country, denomination, date_1) VALUES (9102, 'Atlantis', '10 Drachmae', 1960)")
    db.execute("INSERT INTO banknotes (id, country, denomination, date_1) VALUES (9103, 'Djibouti', '100 Francs', 1952)")
    db.commit()

state = stuffapp._country_history_state
assert state('') is None and state(None) is None
assert state('Djibouti') == 'ready' and state('United States') == 'ready'
assert state('Atlantis') == 'missing'
with stuffapp._COUNTRY_HISTORY_INFLIGHT_LOCK:
    stuffapp._COUNTRY_HISTORY_INFLIGHT.add('atlantis')
assert state('Atlantis') == 'pending'
with stuffapp._COUNTRY_HISTORY_INFLIGHT_LOCK:
    stuffapp._COUNTRY_HISTORY_INFLIGHT.discard('atlantis')
print('STATE OK')

# Placement: one placeholder per run of the country, none for covered ones.
with stuffapp.app.app_context():
    rows = stuffapp.get_db().execute(
        "SELECT * FROM banknotes WHERE id IN (9101, 9102, 9103) ORDER BY id").fetchall()
placements = stuffapp.series_panels(rows)
assert placements.get('9101', {}).get('pending') == {'country': 'Atlantis', 'state': 'missing'}, placements.get(9101)
assert 'pending' not in placements.get('9102', {}), placements.get(9102)
assert placements.get('9103', {}).get('panel') and 'pending' not in placements['9103']
print('PLACEMENT OK')

# The list renders the placeholder with the retry offer (no API key -> missing).
r = client.get('/banknotes')
assert r.status_code == 200
html = r.get_data(as_text=True)
assert 'usp-pending' in html and 'data-country="Atlantis"' in html, 'placeholder missing'
assert html.count('data-country="Atlantis"') == 1
assert 'No history on file yet' in html and 'usp-retry-btn' in html
print('LIST OK')

# Status and retry routes.
r = client.get('/banknotes/country-history/status?country=Atlantis')
assert r.status_code == 200 and r.get_json()['state'] == 'missing', r.get_json()
r = client.get('/banknotes/country-history/status?country=Djibouti')
assert r.get_json()['state'] == 'ready'
r = client.get('/banknotes/country-history/status')
assert r.status_code == 400
r = client.post('/banknotes/country-history/retry', json={'country': 'Atlantis'})
assert r.status_code == 503 and 'ANTHROPIC_API_KEY' in r.get_json()['error'], r.get_json()
print('ROUTES OK')
print('ALL COUNTRY-HISTORY-PLACEHOLDER ASSERTIONS PASSED')
