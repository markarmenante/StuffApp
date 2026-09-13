"""Market Scan: a 'running' row left behind by a restart mid-scan is
marked interrupted (the page stops polling and says why); a scan really
in flight is left alone; the catalogue call falls back to a plain call
when the model rejects thinking=disabled."""
import os, sys, tempfile
from datetime import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-market-int-')
os.environ['ANTHROPIC_API_KEY'] = 'test-key'

import app as stuffapp

stuffapp.app.config['TESTING'] = True
with stuffapp.app.app_context():
    stuffapp.init_db()
client = stuffapp.app.test_client()


def seed_running(scan_id):
    with stuffapp.app.app_context():
        db = stuffapp.get_db()
        db.execute("INSERT INTO market_scans (id, category, started_at, status) "
                   "VALUES (?, 'coins', ?, 'running')", [scan_id, datetime.utcnow().isoformat()])
        db.commit()


# 1. A 'running' row with nothing in flight (the process restarted) is
#    reported interrupted, once, with the reason.
seed_running('orphan-1')
st = client.get('/coins/market/status').get_json()
assert st['status'] == 'interrupted', st
assert 'restarted' in st['error'] and 'Rescan' in st['error'], st
assert st['finished_at'], st
with stuffapp.app.app_context():
    row = stuffapp.get_db().execute("SELECT status FROM market_scans WHERE id = 'orphan-1'").fetchone()
    assert row['status'] == 'interrupted'

# 2. The page says so and does not spin.
html = client.get('/coins/market').get_data(as_text=True)
assert 'Interrupted' in html and 'the scan was interrupted' in html, html[:2000]
assert '<h3>Scanning the market…</h3>' not in html
# The page does not resume polling: the template's own resume line is
# gone (the same call inside startScan() is the Rescan button's).
assert "addEventListener('click', startScan);\n  polling = Date.now(); poll();" not in html

# 3. A scan genuinely in flight is left running.
seed_running('live-1')
with stuffapp._MARKET_SCAN_LOCK:
    stuffapp._MARKET_SCAN_INFLIGHT.add('coins')
try:
    st = client.get('/coins/market/status').get_json()
    assert st['status'] == 'running', st
    html = client.get('/coins/market').get_data(as_text=True)
    assert '<h3>Scanning the market…</h3>' in html
    assert "addEventListener('click', startScan);\n  polling = Date.now(); poll();" in html
finally:
    with stuffapp._MARKET_SCAN_LOCK:
        stuffapp._MARKET_SCAN_INFLIGHT.discard('coins')
# ...and becomes interrupted only once the process has forgotten it.
assert client.get('/coins/market/status').get_json()['status'] == 'interrupted'


# 4. The catalogue call: thinking is disabled when the model accepts it,
#    and the plain call is made when it does not.
class _Resp:
    def __init__(self, text):
        self.stop_reason = 'end_turn'
        self.content = [type('B', (), {'type': 'text', 'text': text})()]

class _Messages:
    def __init__(self, reject):
        self.reject, self.calls = reject, []
    def create(self, **kw):
        self.calls.append(kw)
        if self.reject and 'thinking' in kw:
            raise ValueError("Unexpected value(s) `disabled` for the `thinking.type` parameter")
        return _Resp('{"items": []}')

class _Client:
    def __init__(self, reject):
        self.messages = _Messages(reject)

c = _Client(reject=False)
stuffapp._market_catalogue_call(c, 'm', 'p', max_tokens=8000)
assert c.messages.calls == [{'model': 'm', 'max_tokens': 8000,
                             'messages': [{'role': 'user', 'content': 'p'}],
                             'thinking': {'type': 'disabled'}}], c.messages.calls
c = _Client(reject=True)
stuffapp._market_catalogue_call(c, 'm', 'p', max_tokens=8000)
assert len(c.messages.calls) == 2 and 'thinking' not in c.messages.calls[1], c.messages.calls

print('test_market_interrupted: ok')
