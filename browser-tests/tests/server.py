"""Real Flask/SQLite fixture; never runs against a collection or provider account."""
import atexit
import base64
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
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
import banknote_imports

# Only this temporary fixture has a verified synthetic purchase-account binding.
with stuff.app.app_context():
    db = stuff.get_db()
    db.execute("INSERT OR REPLACE INTO ebay_purchase_account(id,account_name) VALUES(1,'fixture-buyer')")
    db.execute("INSERT OR REPLACE INTO ebay_mail_connection(id,enabled) VALUES(1,1)")
    db.commit()
from werkzeug.serving import make_server

@stuff.app.get('/__fixture/batches')
def fixture_batches():
    rows = stuff.get_db().execute('SELECT order_id AS order_number FROM banknote_import_batches').fetchall()
    return jsonify(batches=[dict(row) for row in rows])


@stuff.app.post('/__fixture/import-photos')
def fixture_import_photos():
    """Saved synthetic siblings; no purchase reader, Check or network activity."""
    db = stuff.get_db()
    batch_id = 'fixture-photo-review'
    if not db.execute('SELECT 1 FROM banknote_import_batches WHERE id=?', (batch_id,)).fetchone():
        now = time.time()
        order = '90-00000-00001'
        db.execute('''INSERT INTO banknote_import_batches
            (id,account_name,order_id,request_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?)''', (batch_id, 'fixture-buyer', order, 'fixture-photo-request', now, now))
        items = []
        for index, ident in enumerate(('199999999991', '199999999992')):
            title = 'Synthetic banknote ' + ('blocked' if index == 0 else 'clean')
            attention = 'Synthetic purchase status needs review <strong>before release</strong>.' if index == 0 else ''
            db.execute('''INSERT INTO ebay_order_items
                (line_key,order_id,item_id,title,seller,quantity,delivery_status,attention,last_seen)
                VALUES(?,?,?,?,?,1,'Ordered',?,?)''',
                ('fixture-photo-' + ident, order, ident, title, 'fixture-seller', attention, '2026-11-01T00:00:00Z'))
            items.append(dict(order_id=order, item_id=ident))
            urls = ['https://i.ebayimg.com/images/g/fixture-' + ident + '-' + side + '/s-l1600.png'
                    for side in ('front', 'back')]
            db.execute('INSERT INTO ebay_listing_captures VALUES(?,?,?,?,?)',
                ('https://www.ebay.com/itm/' + ident, title, 'Synthetic exact listing evidence for browser verification.', json.dumps(urls), now))
        banknote_imports.materialize(db, 'fixture-buyer', order, items, 'fixture-photo-request')
        db.execute("UPDATE banknote_import_items SET check_state='done' WHERE batch_id=?", (batch_id,))
        clean = db.execute("SELECT * FROM banknote_import_items WHERE batch_id=? AND state='draft'", (batch_id,)).fetchone()
        fields = json.loads(clean['fields_json'])
        # Real retained assets deliberately coexist with a cached remote gallery.
        # Their precedence is exercised through the ordinary public payload.
        png = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=')
        for position, side in enumerate(('front', 'back')):
            filename = 'fixture-retained-' + side + '.png'
            (Path(stuff.UPLOAD_FOLDER) / filename).write_bytes(png)
            fields['image_' + str(position + 1)] = filename
            db.execute('INSERT INTO banknote_import_assets VALUES(?,?,?,?,?,?,?)',
                (clean['id'], 'https://i.ebayimg.com/images/g/fixture-199999999992-' + side + '/s-l1600.png',
                 filename, hashlib.sha256(png).hexdigest(), 1, 1, position))
        db.execute('UPDATE banknote_import_items SET fields_json=? WHERE id=?', (json.dumps(fields), clean['id']))
        db.commit()
    return jsonify(banknote_imports.status(db, batch_id))


@stuff.app.get('/__fixture/import-photo-state')
def fixture_import_photo_state():
    db = stuff.get_db()
    return jsonify(
        collection_count=db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],
        link_count=db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0],
        items=[dict(row) for row in db.execute('''SELECT id,state,check_state,revision,fields_json
            FROM banknote_import_items WHERE batch_id='fixture-photo-review' ORDER BY id''')])

if __name__ == '__main__':
    with make_server('127.0.0.1', 4182, stuff.app, threaded=True) as server:
        server.serve_forever()
