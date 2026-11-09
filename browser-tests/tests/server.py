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
    BANKNOTE_ECONOMICS_REFRESH='0', COIN_ECONOMICS_REFRESH='0',
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
import ebay_orders
import ebay_purchase_prices
from PIL import Image

preview_crop_calls = 0
metadata_check_calls = 0
checkable_fixture_sequence = 0

def fixture_listing_image(url,folder):
    if not url.startswith('https://i.ebayimg.com/images/g/fixture-'):
        raise RuntimeError('Fixture does not permit provider access')
    filename=uuid.uuid4().hex+'.jpg';path=Path(folder)/filename
    colour=(0,160,0) if 'alternate-front' in url else 'green' if 'front' in url else 'red'
    Image.new('RGB',(160,80),colour).save(path)
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
    if not row or not row['batch_id'].startswith('fixture-checkable-photo-review-'):
        raise RuntimeError('Fixture Check is restricted to the synthetic inspection draft')
    metadata_check_calls+=1
    if 'Pick # 46c' in (note.get('description') or ''):
        return dict(filled=dict(country='Belize',denomination='1 Dollar',pick_number='P-46c',series='1987',
                               grading_authority='PMG',grade='67',grade_modifier='EPQ'),catalogue=dict(fields={}))
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


@stuff.app.route('/__fixture/timor',methods=['GET','POST'])
def fixture_timor():
    db=stuff.get_db()
    if request.method=='POST':
        db.execute('''INSERT OR REPLACE INTO country_eras(country_key,title,eras,spellings)
            VALUES(?,?,?,?)''',('timor','Portuguese Timor',
            json.dumps([[1959,1975,'Portuguese Timorese escudo','Synthetic history fixture.']]),
            json.dumps(['timor','portuguese timor'])))
        for ident,country,year,denomination,status in (
                ('fixture-timor-500','Portuguese Timor',1963,'500 Escudos','Delivered'),
                ('fixture-timor-20','Timor',1967,'20 Escudos','Own'),
                ('fixture-timor-50','Portuguese Timor',1967,'50 Escudos','Shipped'),
                ('fixture-timor-modern','Timor-Leste',2002,'1 Dollar','Own')):
            filename=ident+'.jpg'
            Image.new('RGB',(160,80),'green').save(Path(stuff.UPLOAD_FOLDER)/filename)
            db.execute('''INSERT OR REPLACE INTO banknotes
                (id,country,date_1,denomination,status,issuer,series,image_1,image_2,price)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',(ident,country,year,denomination,status,
                'Banco Nacional Ultramarino' if year<1975 else 'Banco Central de Timor-Leste',
                '1963-68 Issue' if year<1975 else '',filename,filename,'$82.13'))
        db.commit();stuff._generated_country_eras(force=True)
        stuff._renumber_banknotes(db);db.commit()
    return jsonify(rows=[dict(row) for row in db.execute("SELECT * FROM banknotes WHERE id LIKE 'fixture-timor-%' ORDER BY id")],
        sections=[dict(title=title,ids=[row['id'] for row in rows]) for title,key,rows in
            stuff._banknote_report_sections(db,{'q':'Portuguese Timor','filter':'heritage_portuguese'})])


@stuff.app.route('/__fixture/economics',methods=['GET','POST'])
def fixture_economics():
    db=stuff.get_db()
    if request.method=='POST':
        for ident,country,denom,year,series,issue,issuer in (
                ('fixture-economics-gbp','England','10 Shillings',1935,'','',''),
                ('fixture-economics-usd','United States of America','5 Dollars',1896,'Series of 1896','1897',''),
                ('fixture-economics-brl','Brazil','10 Mil Reis',1925,'Estampa 17A','',''),
                ('fixture-economics-connecticut','Connecticut Colony','1 Shilling',1776,'','','Colony of Connecticut'),
                ('fixture-economics-usd-1917','United States of America','2 Dollars',1917,'Series of 1917','','United States Treasury'),
                ('fixture-economics-hkd','Hong Kong','1 Dollar',1940,'','','Government of Hong Kong')):
            db.execute('''INSERT OR REPLACE INTO banknotes
                (id,country,denomination,date_1,series,issue_date,issuer,status,price,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',
                (ident,country,denom,year,series,issue,issuer,'Own','$12.34','Synthetic collector notes'))
        db.commit()
    return jsonify(rows=[dict(r) for r in db.execute("SELECT * FROM banknotes WHERE id LIKE 'fixture-economics-%' ORDER BY id")])


@stuff.app.route('/__fixture/coin-economics', methods=['GET', 'POST'])
def fixture_coin_economics():
    db = stuff.get_db()
    if request.method == 'POST':
        for ident, metal in (('fixture-coin-silver', 'AR Silver'), ('fixture-coin-gold', 'AV Gold')):
            db.execute('''INSERT OR REPLACE INTO coins
                (id,region,mint,authority,denomination,date_1,date_1_text,date_2,date_2_text,metal,weight,status,price,notes)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (ident,'Attica','Athens','Athens','Tetradrachm',-454,'454 BC',-404,'404 BC',metal,17.15,'Own',123.45,'Synthetic collector notes'))
        db.commit()
        Path(stuff.DATA_DIR, 'precious-metals.json').write_text(json.dumps(dict(version=1, quotes={
            'XAU':dict(price=4000,updated_at='2026-11-01T12:00:00Z'),
            'XAG':dict(price=50,updated_at='2026-11-01T12:00:00Z')})))
    return jsonify(rows=[dict(row) for row in db.execute("SELECT * FROM coins WHERE id LIKE 'fixture-coin-%' ORDER BY id")])


original_coin_spec_lookup = stuff.fetch_coin_specs
def fixture_coin_spec_lookup(coin, provider='anthropic'):
    if str(coin['id']).startswith('fixture-coin-'):
        return dict(sources='Synthetic fixture: no provider calls')
    return original_coin_spec_lookup(coin, provider=provider)
stuff.fetch_coin_specs = fixture_coin_spec_lookup


@stuff.app.post('/__fixture/import-photos')
def fixture_import_photos():
    """Saved synthetic siblings; no purchase reader, Check or network activity."""
    return make_import_photo_fixture('fixture-photo-review','90-00000-00001',
        ('199999999991','199999999992'),
        'Synthetic purchase status needs review <strong>before release</strong>.')


@stuff.app.post('/__fixture/import-checkable-photos')
def fixture_import_checkable_photos():
    return make_checkable_photo_fixture()


@stuff.app.post('/__fixture/import-priced-photos')
def fixture_import_priced_photos():
    return make_checkable_photo_fixture(receipt_amount='72.63')


@stuff.app.post('/__fixture/import-catalogue-suffix')
def fixture_import_catalogue_suffix():
    return make_checkable_photo_fixture(receipt_amount='82.00',
        title='Belize 1 Dollar 1987 PMG 67 EPQ UNC Pick # 46c Queen Elizabeth II, Series A/15')


@stuff.app.post('/__fixture/import-ambiguous-identity')
def fixture_import_ambiguous_identity():
    return make_checkable_photo_fixture(receipt_amount='82.00',
        title='Belize 1 Dollar / 5 Dollars PMG 67 EPQ Pick # 46c')


def make_checkable_photo_fixture(receipt_amount=None,title=None):
    global checkable_fixture_sequence
    checkable_fixture_sequence+=1
    number=checkable_fixture_sequence
    return make_import_photo_fixture('fixture-checkable-photo-review-'+str(number),f'90-00001-{number:05d}',
        (str(199999990000+2*number),str(199999990001+2*number)),
        'Multiple items; shipment or delivery not confirmed',extra_front=True,receipt_amount=receipt_amount,blocked_title=title)


def make_import_photo_fixture(batch_id,order,identifiers,blocked_attention,extra_front=False,receipt_amount=None,blocked_title=None):
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
            if index==0 and blocked_title:title=blocked_title
            attention = blocked_attention if index == 0 else ''
            db.execute('''INSERT INTO ebay_order_items
                (line_key,order_id,item_id,title,seller,quantity,delivery_status,attention,last_seen)
                VALUES(?,?,?,?,?,1,'Ordered',?,?)''',
                ('fixture-photo-' + ident, order, ident, title, 'fixture-seller', attention, '2026-11-01T00:00:00Z'))
            items.append(dict(order_id=order, item_id=ident))
            urls = ['https://i.ebayimg.com/images/g/fixture-' + ident + '-' + side + '/s-l1600.png'
                    for side in ('front', 'back')]
            if extra_front and index==0:
                urls.append('https://i.ebayimg.com/images/g/fixture-'+ident+'-alternate-front/s-l1600.png')
            db.execute('INSERT INTO ebay_listing_captures VALUES(?,?,?,?,?)',
                ('https://www.ebay.com/itm/' + ident, title, 'Synthetic exact listing evidence for browser verification.', json.dumps(urls), now))
        if receipt_amount is not None:
            source=dict(db.execute('SELECT * FROM ebay_order_items WHERE order_id=? AND item_id=?',
                                   (order,identifiers[0])).fetchone())
            # Exercise the real exact-item receipt parser and stored authority,
            # including cents and distracting shipping/order totals.
            receipt=dict(order_id=order,item_id=identifiers[0],quantity=1,
                url='https://order.ebay.com/ord/show?orderId='+order,currency='USD',
                unit_amount=receipt_amount,observed_at=ebay_orders.now_iso(),
                evidence=f'Order number: {order}\nItem info\nUnit price USD {receipt_amount}\n'
                         f'Item number: {identifiers[0]}\nShipping USD 9.00\nOrder total USD 999.99')
            ebay_purchase_prices.save(db,receipt,[source],now-10)
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


@stuff.app.post('/__fixture/expire-import-capture')
def fixture_expire_import_capture():
    batch_id=(request.get_json(silent=True) or {}).get('batch_id','')
    if not batch_id.startswith('fixture-checkable-photo-review-'):
        return jsonify(error='Not a synthetic editable review fixture'),400
    db=stuff.get_db()
    for row in db.execute('SELECT item_id FROM banknote_import_items WHERE batch_id=?',(batch_id,)).fetchall():
        db.execute('UPDATE ebay_listing_captures SET captured_at=? WHERE url=?',
                   (time.time()-banknote_imports.ebay_listing_captures.MAX_AGE-1,
                    'https://www.ebay.com/itm/'+row['item_id']))
    db.commit()
    return jsonify(banknote_imports.status(db,batch_id))


@stuff.app.get('/__fixture/import-photo-state')
def fixture_import_photo_state():
    db = stuff.get_db()
    batch_id=request.args.get('batch','fixture-photo-review')
    return jsonify(
        collection_count=db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],
        link_count=db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0],
        preview_crop_calls=preview_crop_calls,
        metadata_check_calls=metadata_check_calls,
        records=[dict(row) for row in db.execute('''SELECT id,country,denomination,pick_number,
            price,vendor,status,order_number,image_1,image_2 FROM banknotes WHERE id IN
            (SELECT released_record_id FROM banknote_import_items WHERE batch_id=?)''',(batch_id,))],
        source_items=[dict(row) for row in db.execute('''SELECT line_key,item_id,attention FROM ebay_order_items
            WHERE line_key IN (SELECT line_key FROM banknote_import_items WHERE batch_id=?) ORDER BY item_id''',(batch_id,))],
        items=[dict(row) for row in db.execute('''SELECT id,state,check_state,revision,fields_json,
            warning,source_json,source_digest,manual_photos_json,released_record_id
            FROM banknote_import_items WHERE batch_id=? ORDER BY id''',(batch_id,))])

if __name__ == '__main__':
    with make_server('127.0.0.1', 4182, stuff.app, threaded=True) as server:
        server.serve_forever()
