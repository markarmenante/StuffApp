"""Real Flask/SQLite fixture; never runs against a collection or provider account."""
import atexit
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import uuid
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
from flask import jsonify, request
import banknote_imports
from PIL import Image

preview_crop_calls = 0
metadata_check_calls = 0

def fixture_listing_image(url,folder):
    if not url.startswith('https://i.ebayimg.com/images/g/fixture-'):
        raise RuntimeError('Fixture does not permit provider access')
    filename=uuid.uuid4().hex+'.jpg';path=Path(folder)/filename
    Image.new('RGB',(160,80),'green' if 'front' in url else 'red').save(path)
    return dict(filename=filename,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),width=160,height=80)

def fixture_preview_crop(raw,note):
    global preview_crop_calls
    preview_crop_calls += 1
    output=io.BytesIO()
    Image.open(io.BytesIO(raw)).crop((5,5,155,75)).save(output,format='JPEG')
    return dict(data=output.getvalue(),quad=[[5,5],[155,5],[155,75],[5,75]])

banknote_imports.listing_images.download = fixture_listing_image
stuff._prepare_import_photo = fixture_preview_crop

def fixture_photo_sides(photos):
    """Synthetic colour encodes the side; no model or provider is contacted."""
    readings=[]; selected={}
    for photo in photos:
        with Image.open(Path(stuff.UPLOAD_FOLDER)/photo['filename']) as image:
            red,green,_=image.convert('RGB').getpixel((10,10))
        side='front' if green>red else 'back'
        readings.append(dict(id=photo['id'],side=side,confidence='high',complete_note=True,same_note=True,
                             reason='Synthetic '+side+' colour fixture.'))
        if photo['gallery']:selected[side]=photo['id']
    return dict(photos=readings,front=selected.get('front'),back=selected.get('back'),
                pair_verified=True,pair_reason='Different synthetic front/back colour fixtures.')

def fixture_metadata_check(note,prepared):
    global metadata_check_calls
    row=stuff.get_db().execute('SELECT batch_id FROM banknote_import_items WHERE id=?',(note['id'],)).fetchone()
    if not row or row['batch_id']!='fixture-checkable-photo-review':
        raise RuntimeError('Fixture Check is restricted to the synthetic inspection draft')
    metadata_check_calls+=1
    return dict(filled=dict(country='Peru',denomination='5 Soles de Oro',pick_number='P-66A',
                           grading_authority='PMG',grade='67',grade_modifier='EPQ',
                           price='9999.99',vendor='Unverified provider seller',status='Own'),
                catalogue=dict(fields={}))

stuff._classify_banknote_listing_photos=fixture_photo_sides
stuff._evaluate_import_check=fixture_metadata_check

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
    return make_import_photo_fixture('fixture-photo-review','90-00000-00001',
        ('199999999991','199999999992'),
        'Synthetic purchase status needs review <strong>before release</strong>.')


@stuff.app.post('/__fixture/import-checkable-photos')
def fixture_import_checkable_photos():
    return make_import_photo_fixture('fixture-checkable-photo-review','90-00000-00002',
        ('199999999993','199999999994'),'Multiple items; shipment or delivery not confirmed')


def make_import_photo_fixture(batch_id,order,identifiers,blocked_attention):
    db = stuff.get_db()
    for table in ('banknote_import_preview_jobs','banknote_import_photo_previews'):
        db.execute('DELETE FROM '+table+' WHERE item_id IN (SELECT id FROM banknote_import_items WHERE batch_id=?)',(batch_id,))
    if not db.execute('SELECT 1 FROM banknote_import_batches WHERE id=?', (batch_id,)).fetchone():
        now = time.time()
        db.execute('''INSERT INTO banknote_import_batches
            (id,account_name,order_id,request_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?)''', (batch_id, 'fixture-buyer', order, 'fixture-photo-request', now, now))
        items = []
        for index, ident in enumerate(identifiers):
            title = 'Synthetic banknote ' + ('blocked' if index == 0 else 'clean')
            attention = blocked_attention if index == 0 else ''
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
                (clean['id'], 'https://i.ebayimg.com/images/g/fixture-' + identifiers[1] + '-' + side + '/s-l1600.png',
                 filename, hashlib.sha256(png).hexdigest(), 1, 1, position))
        db.execute('UPDATE banknote_import_items SET fields_json=?,manual_photos_json=? WHERE id=?',
                   (json.dumps(fields),json.dumps({key:fields[key] for key in ('image_1','image_2')}),clean['id']))
        db.commit()
    db.commit()
    return jsonify(banknote_imports.status(db, batch_id))


@stuff.app.get('/__fixture/import-photo-state')
def fixture_import_photo_state():
    db = stuff.get_db()
    batch_id=request.args.get('batch','fixture-photo-review')
    return jsonify(
        collection_count=db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],
        link_count=db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0],
        preview_crop_calls=preview_crop_calls,
        metadata_check_calls=metadata_check_calls,
        items=[dict(row) for row in db.execute('''SELECT id,state,check_state,revision,fields_json,
            warning,source_json,source_digest,manual_photos_json,released_record_id
            FROM banknote_import_items WHERE batch_id=? ORDER BY id''',(batch_id,))])

if __name__ == '__main__':
    with make_server('127.0.0.1', 4182, stuff.app, threaded=True) as server:
        server.serve_forever()
