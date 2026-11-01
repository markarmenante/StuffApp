"""Real Flask/SQLite fixture; never runs against a collection or provider account."""
import atexit
import os
from pathlib import Path
import sys
import tempfile
import types
from unittest.mock import patch

root = Path(__file__).resolve().parents[2]
os.chdir(root)
sys.path.insert(0, str(root))
temporary = tempfile.TemporaryDirectory(prefix='stuffapp-e2e-')
atexit.register(temporary.cleanup)
os.environ.update(DATA_DIR=temporary.name, EBAY_SYNC_WORKER='0', ORIGINAL_LISTING_WORKER='0',
    BANKNOTE_IMPORT_WORKER='0', STUFFAPP_OWNER_EMAIL='fixture-owner@example.invalid',
    STUFFAPP_DEV_USER='fixture-owner@example.invalid', STUFFAPP_OWNER_DISPLAY_NAME='Synthetic Owner',
    STUFFAPP_TODAY_TOKEN='synthetic-fixture-token-not-an-account-key-0000')
for key in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(key, None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
with patch('threading.Thread.start'):
    import app as stuff
stuff.ensure_country_history = lambda *args, **kwargs: None
from flask import jsonify
from werkzeug.serving import make_server

@stuff.app.get('/__fixture/batches')
def fixture_batches():
    rows = stuff.get_db().execute('SELECT order_number FROM banknote_import_batches').fetchall()
    return jsonify(batches=[dict(row) for row in rows])

if __name__ == '__main__':
    with make_server('127.0.0.1', 4182, stuff.app, threaded=True) as server:
        server.serve_forever()
