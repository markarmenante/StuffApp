"""Route smoke test: every category list view, the home page, and a
detail view render without a 500 against a fresh schema.

Run: .venv/bin/python tests/test_smoke.py
"""
import os, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-smoke-')

import app as stuffapp

client = stuffapp.app.test_client()

failures = []


def check(path, allowed=(200, 302, 308)):
    r = client.get(path)
    if r.status_code not in allowed:
        failures.append((path, r.status_code))
    return r


check('/')
for cat in stuffapp.CATEGORIES:
    check(f'/{cat}')

# A seeded record renders its detail page.
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute(
        "INSERT INTO banknotes (id, country, denomination, date_1) "
        "VALUES (9001, 'Belize', '50 Dollars', 2021)")
    db.commit()
check('/banknotes/9001')

# Unknown category and record 404 rather than 500.
check('/no-such-category', allowed=(404,))
check('/banknotes/999999', allowed=(404,))

assert not failures, f'routes failed: {failures}'

# Security headers present on a normal response.
r = client.get('/banknotes')
assert r.headers.get('X-Content-Type-Options') == 'nosniff', r.headers
assert r.headers.get('X-Frame-Options') == 'DENY', r.headers

# CSRF guard: a cross-site Origin on a write is blocked; same-origin and
# header-less writes are allowed through to the route (not 403 by the guard).
r = client.post('/banknotes/9001/delete',
                headers={'Origin': 'https://evil.example'})
assert r.status_code == 403, ('cross-site write not blocked', r.status_code)
r = client.post('/banknotes/9001/delete', headers={'Sec-Fetch-Site': 'cross-site'})
assert r.status_code == 403, ('cross-site fetch not blocked', r.status_code)
# No Origin (native app / curl) must NOT be blocked by the CSRF guard.
r = client.post('/banknotes/999999/delete')
assert r.status_code != 403, ('header-less write wrongly blocked', r.status_code)

# Every table-driven bulk-UPDATE admin route is wired and returns the
# right shape (secret required; owner via the dev fallback; no Origin so
# the CSRF guard allows it).
secret = stuffapp.IMPORT_MISSING_SECRET
for rule, endpoint, sql, use_now, total_table in stuffapp._BULK_UPDATE_ROUTES:
    # Wrong secret → 403.
    assert client.post(rule, data={'secret': 'nope'}).status_code == 403, rule
    r = client.post(rule, data={'secret': secret})
    assert r.status_code == 200, (rule, r.status_code)
    body = r.get_json()
    assert 'updated' in body, (rule, body)
    assert ('total' in body) == (total_table is not None), (rule, body)
print(f'BULK-UPDATE ROUTES OK: {len(stuffapp._BULK_UPDATE_ROUTES)} routes')

# Banknote-history diagnostic: 403 without secret, JSON shape with it.
assert client.get('/admin/banknote-countries-without-history').status_code == 403
r = client.get('/admin/banknote-countries-without-history', query_string={'secret': secret})
assert r.status_code == 200, r.status_code
body = r.get_json()
assert 'without_history' in body and 'missing_count' in body, body
# The seeded Belize note is a covered country, so it must not be listed.
assert all(e['country'] != 'Belize' for e in body['without_history']), body
print('HISTORY DIAGNOSTIC OK')

print(f'SMOKE OK: / + {len(stuffapp.CATEGORIES)} categories + detail + 404s '
      '+ headers + csrf guard')
