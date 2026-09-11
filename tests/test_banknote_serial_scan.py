"""Serial-number scan on the banknote detail page: the Scan button in
the Serial # cell posts to /banknotes/<id>/scan-serial, which reads the
serial off the note's photos (model call stubbed here) and stores it.

Run: .venv/bin/python tests/test_banknote_serial_scan.py
"""
import os, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-serial-')

import app as stuffapp

client = stuffapp.app.test_client()
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute("INSERT INTO banknotes (id, country, denomination, date_1, serial_number) "
               "VALUES (9001, 'Belize', '50 Dollars', 2021, 'OLD 1')")
    db.execute("INSERT INTO banknotes (id, country, denomination, date_1) "
               "VALUES (9002, 'Japan', '10 Yen', 1943)")
    db.commit()

# The detail page carries the Scan button for a saved note, and still
# exactly one serial_number input.
r = client.get('/banknotes/9001')
assert r.status_code == 200
html = r.get_data(as_text=True)
assert 'serial-scan-btn' in html and '/banknotes/9001/scan-serial' in html, 'Scan button missing'
assert html.count('<input type="text" name="serial_number"') == 1
print('PAGE OK')

# No photo on file -> a friendly 503, nothing stored.
r = client.post('/banknotes/9001/scan-serial')
d = r.get_json()
assert r.status_code == 503 and 'photo' in d['error'], d
print('NO-PHOTO OK')

# A clean read is normalised, overwrites, and reports the previous value.
stuffapp.scan_banknote_serial = lambda note: {
    'serial_number': ' A 12345678  B ',
    'readings': ['front upper right: A 12345678 B', 'front lower left: A 12345678 B'],
    'confidence': 'high', 'basis': 'both printings agree'}
r = client.post('/banknotes/9001/scan-serial')
d = r.get_json()
assert r.status_code == 200, d
assert d['serial_number'] == 'A 12345678 B' and d['previous'] == 'OLD 1' and d['stored'] is True, d
with stuffapp.app.app_context():
    v = stuffapp.get_db().execute(
        "SELECT serial_number FROM banknotes WHERE id = 9001").fetchone()[0]
assert v == 'A 12345678 B', v
# The same value again is reported as unchanged and not re-stored.
r = client.post('/banknotes/9001/scan-serial')
d = r.get_json()
assert d['stored'] is False and d['unchanged'] is True, d
print('STORE OK')

# A note with no serial number -> null, nothing written.
stuffapp.scan_banknote_serial = lambda note: {
    'serial_number': None, 'readings': [], 'confidence': 'high',
    'basis': 'issued without serial numbers'}
r = client.post('/banknotes/9002/scan-serial')
d = r.get_json()
assert d['serial_number'] is None and d['stored'] is False, d
with stuffapp.app.app_context():
    v = stuffapp.get_db().execute(
        "SELECT serial_number FROM banknotes WHERE id = 9002").fetchone()[0]
assert v in (None, ''), v

clean = stuffapp._clean_scanned_serial
assert clean('null') is None and clean('??') is None and clean('x' * 41) is None
assert clean(None) is None and clean('') is None
assert clean('AB 123?56') == 'AB 123?56'
print('NULL OK')

r = client.post('/banknotes/nope/scan-serial')
assert r.status_code == 404
print('ALL BANKNOTE-SERIAL-SCAN ASSERTIONS PASSED')
