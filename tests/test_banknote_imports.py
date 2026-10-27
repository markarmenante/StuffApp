"""Exact checkout drafts remain separate and revision-safe until explicit release."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlencode, urlsplit

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='stuff-import-tests-')
for key in ('BANKNOTE_IMPORT_WORKER','ORIGINAL_LISTING_WORKER','EBAY_SYNC_WORKER'):
    os.environ[key]='0'
os.environ['STUFFAPP_TODAY_TOKEN']='x'*40
os.environ.pop('ANTHROPIC_API_KEY',None)
import app as stuff
import banknote_imports as imports
import ebay_orders
from PIL import Image

HEADERS={'Authorization':'Bearer '+'x'*40}
ORDERS=['24-15335-90977','24-15335-90978','24-15335-90979']
IDS=['158075629160','336824466148','236156645678']

class DraftTests(unittest.TestCase):
    def setUp(self):
        self.ctx=stuff.app.app_context();self.ctx.push()
        self.db=stuff.get_db();self.client=stuff.app.test_client()
        self.db.execute('PRAGMA foreign_keys=OFF')
        for table in ('banknote_import_image_edits','trimmed_image_sources','banknote_import_evidence','banknote_import_assets','banknote_import_items','banknote_import_batches',
                      'banknote_ebay_links','ebay_purchase_prices','ebay_order_items','ebay_purchase_request_sessions',
                      'ebay_purchase_requests','ebay_purchase_observations','ebay_listing_captures','banknotes','record_documents',
                      'original_listing_sources','banknote_original_listings','original_listing_image_sources','original_image_assets','record_source_documents'):
            if self.db.execute("SELECT 1 FROM sqlite_master WHERE name=?",(table,)).fetchone():self.db.execute('DELETE FROM '+table)
        self.db.execute("INSERT OR REPLACE INTO ebay_purchase_account VALUES(1,'buyer')")
        self.db.execute('INSERT OR REPLACE INTO ebay_mail_connection(id,enabled) VALUES(1,1)')
        self.db.commit()
        self.fills=dict(country='Netherlands Antilles',denomination='1 Gulden',pick_number='P14a')
    def tearDown(self):
        self.db.rollback();self.ctx.pop()
    def batch(self,number=ORDERS[1]):
        response=self.client.post('/banknotes/imports',json={'order_number':number})
        self.assertEqual(response.status_code,200,response.get_json());return response.json
    def payload(self,request):
        items=[dict(order_id=o,item_id=i,title=f'Netherlands Antilles {n+1} Gulden PMG 67 EPQ',seller='dealer'+str(n),quantity=1,status_text='Order processing',delivery_text='',ordered_date='Oct 26, 2026') for n,(o,i) in enumerate(zip(ORDERS,IDS))]
        receipts=[dict(order_id=o,item_id=i,quantity=1,url='https://order.ebay.com/ord/show?orderId='+o,currency='USD',unit_amount=a,observed_at=ebay_orders.now_iso(),evidence=f'Order number: {o}\nItem info\nUnit price USD {a}\nItem number: {i}\nShipping USD 5.00\nOrder total USD 999.99') for o,i,a in zip(ORDERS,IDS,['599.89','125.37','30.00'])]
        listings=[dict(item_id=i,url='https://www.ebay.com/itm/'+i,title=item['title'],text=item['title']+'; exact purchased listing.',images=['https://i.ebayimg.com/images/g/'+i+side+'/s-l1600.jpg' for side in ('front','back')]) for i,item in zip(IDS,items)]
        checkout=dict(requested_order_id=request['order_id'],purchase_order_id='24-1533-590976',orders=[dict(order_id=o,details_url=f'https://order.ebay.com/ord/show?orderId={o}&purchaseOrderId=24-1533-590976',item_ids=[i]) for o,i in zip(ORDERS,IDS)])
        return dict(action='complete',id=request['id'],account='buyer',observed_at=ebay_orders.now_iso(),checkout=checkout,items=items,receipts=receipts,listings=listings)
    def imported(self,mutate=None):
        batch=self.batch();claim=self.client.post('/ebay/today/requests',json={'action':'claim'},headers=HEADERS).json['request']
        self.assertTrue(claim['import_checkout'])
        payload=self.payload(claim)
        if mutate:mutate(payload)
        response=self.client.post('/ebay/today/requests',json=payload,headers=HEADERS)
        self.assertEqual(response.status_code,200,response.json)
        return self.client.get(batch['status_url']).json
    def release(self,batch,items=None):
        return self.client.post(batch['url']+'/release',json={'items':[dict(id=i['id'],revision=i['revision']) for i in (items or batch['items'])]})
    def download(self,url,folder):
        filename=hashlib.sha256(url.encode()).hexdigest()+'.jpg';path=Path(folder)/filename
        Image.new('RGB',(160,80),'red' if 'front' in url else 'blue').save(path)
        return dict(url=url,filename=filename,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),width=160,height=80)
    def classify(self,photos):
        return dict(photos=[dict(id=p['id'],side='front' if n==0 else 'back',confidence='high',complete_note=True,same_note=True,reason='different complete designs') for n,p in enumerate(photos)],front=photos[0]['id'],back=photos[1]['id'],pair_verified=True,pair_reason='Opposite sides of same note')
    def check(self,batch,item,evaluate=None):
        token=imports.claim_check(self.db,batch['id'],item['id'],item['revision'])
        with patch.object(imports.listing_images,'download',side_effect=self.download):
            imports.run_check(stuff.open_db_connection,batch['id'],item['id'],item['revision'],token,stuff.UPLOAD_FOLDER,self.classify,evaluate or (lambda *_:dict(filled=self.fills)))
        return self.client.get(batch['status_url']).json
    def test_complete_checkout_is_staged_with_exact_cents_and_actual_seller_orders(self):
        b=self.imported();self.assertEqual(len(b['items']),3)
        self.assertEqual({i['order_number'] for i in b['items']},set(ORDERS))
        self.assertEqual({i['fields']['price'] for i in b['items']},{'$599.89','$125.37','$30'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0],0)
        with stuff.app.test_request_context('/banknotes'):
            stuff.app.preprocess_request();self.assertEqual(stuff.get_counts()['banknotes'],0)
    def test_repeat_entered_and_sibling_orders_resume_same_batch_with_edits(self):
        b=self.imported();item=b['items'][0]
        r=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{'country':'Saved choice','price':'$599.89'}})
        self.assertEqual(r.status_code,200)
        for order in ORDERS:self.assertEqual(self.batch(order)['id'],b['id'])
        self.assertEqual(self.batch()['items'][0]['fields']['country'],'Saved choice')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_import_batches').fetchone()[0],1)
    def test_explicit_release_is_atomic_and_idempotent_and_preserves_actual_orders(self):
        b=self.imported();first=b['items'][0]
        result=self.release(b,[first]);self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['next_url'],b['url'])
        again=self.release(b,[first]);self.assertEqual(again.json['released'],result.json['released'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],1)
        latest=self.client.get(b['status_url']).json;result=self.release(latest,[i for i in latest['items'] if i['state']=='draft'])
        self.assertEqual(result.status_code,200,result.json);self.assertEqual(result.json['next_url'],'/banknotes')
        self.assertEqual({r[0] for r in self.db.execute('SELECT order_number FROM banknotes')},set(ORDERS))
        self.assertEqual({r[0] for r in self.db.execute('SELECT price FROM banknotes')},{'$599.89','$125.37','$30'})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0],3)
    def test_revision_conflict_and_source_identity_are_not_rewritten(self):
        b=self.imported();item=b['items'][0]
        for updates in ({'order_number':'11-11111-11111'},{'image_1':'other.jpg'}):
            self.assertEqual(self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':updates}).status_code,409)
        r=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{'notes':'keep me'}});self.assertEqual(r.status_code,200)
        self.assertEqual(self.release(b).status_code,409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)
    def test_checkout_membership_mismatch_rejects_entire_snapshot(self):
        b=self.batch();q=self.client.post('/ebay/today/requests',json={'action':'claim'},headers=HEADERS).json['request'];payload=self.payload(q)
        payload['checkout']['orders'][0]['item_ids']=['999999999999']
        response=self.client.post('/ebay/today/requests',json=payload,headers=HEADERS)
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_import_items').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0],0)
    def test_old_reader_without_membership_proof_cannot_import_partial_checkout(self):
        b=self.batch();q=self.client.post('/ebay/today/requests',json={'action':'claim'},headers=HEADERS).json['request'];payload=self.payload(q)
        payload.pop('checkout');payload['items']=payload['items'][1:2];payload['receipts']=[];payload['listings']=[]
        self.assertEqual(self.client.post('/ebay/today/requests',json=payload,headers=HEADERS).status_code,409)
        self.assertEqual(self.client.get(b['status_url']).json['state'],'failed')
        self.assertNotEqual(self.batch()['id'],'')
    def test_session_outcome_cannot_smuggle_checkout_or_capture_data(self):
        self.batch();q=self.client.post('/ebay/today/requests',json={'action':'claim'},headers=HEADERS).json['request']
        result=self.client.post('/ebay/today/requests',json=dict(action='complete',id=q['id'],session={'state':'sign_in_required'},checkout={}),headers=HEADERS)
        self.assertEqual(result.status_code,409)
    def test_source_membership_loss_and_account_change_block_release(self):
        b=self.imported()
        self.db.execute("UPDATE banknote_import_batches SET snapshot_json='[]' WHERE id=?",(b['id'],));self.db.commit()
        self.assertEqual(self.release(b).status_code,409)
        self.db.execute("UPDATE ebay_purchase_account SET account_name='other'");self.db.commit()
        self.assertEqual(self.client.get(b['status_url']).status_code,404)
        self.assertEqual(self.release(b).status_code,409)
    def test_check_saves_original_photos_and_missing_fields_without_live_insert(self):
        b=self.imported();item=b['items'][0];b=self.check(b,item);item=next(i for i in b['items'] if i['id']==item['id'])
        self.assertEqual(item['check_state'],'done',item['warnings']);self.assertEqual(item['fields']['pick_number'],'P14a')
        self.assertEqual(len(item['photos']),2)
        response=self.client.get(item['photos'][0]['url']);self.assertEqual(response.status_code,200);response.close()
        self.assertIn(item['photos'][0]['url'].split('/')[-1],stuff._collect_referenced_uploads(self.db))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)
        self.assertEqual(self.client.get(item['detail_url']).status_code,200)
        self.assertEqual(self.release(b,[item]).status_code,200)
        live=self.db.execute('SELECT * FROM banknotes').fetchone()
        self.assertTrue(live['image_1']);self.assertNotEqual(live['image_1'],item['fields']['image_1'])
        self.assertEqual((Path(stuff.UPLOAD_FOLDER)/live['image_1']).read_bytes(),(Path(stuff.UPLOAD_FOLDER)/item['fields']['image_1']).read_bytes())
    def test_failed_check_retains_original_assets_and_can_retry(self):
        b=self.imported();item=b['items'][0]
        def fail(*_):raise RuntimeError('private provider token')
        b=self.check(b,item,fail);item=next(i for i in b['items'] if i['id']==item['id'])
        self.assertEqual(item['check_state'],'failed');self.assertNotIn('private',item['check_message']);self.assertEqual(len(item['photos']),2)
        b=self.check(b,item);self.assertEqual(next(i for i in b['items'] if i['id']==item['id'])['check_state'],'done')
    def test_late_check_cannot_overwrite_user_changes(self):
        b=self.imported();item=b['items'][0]
        def during(*_):
            db=stuff.open_db_connection()
            imports.save(db,b['id'],item['id'],item['revision'],{'country':'User choice'},lambda x:x);db.close()
            return dict(filled={'country':'Model country','pick_number':'P99'})
        b=self.check(b,item,during);item=next(i for i in b['items'] if i['id']==item['id'])
        self.assertEqual(item['fields']['country'],'User choice');self.assertNotIn('pick_number',item['fields']);self.assertEqual(item['check_state'],'failed')
    def test_non_discovery_titles_still_have_saved_review_drafts(self):
        b=self.imported(lambda p:p['items'][0].update(title='Lot reference 2026A unusual collectible'))
        self.assertEqual(len(b['items']),3);self.assertEqual(b['items'][0]['state'],'draft')
    def test_quantity_and_bundles_are_visible_but_never_released_as_one_note(self):
        def mutate(p):
            p['items'][0]['quantity']=2;p['receipts']=p['receipts'][1:];p['listings']=p['listings'][1:]
        b=self.imported(mutate);blocked=next(i for i in b['items'] if i['state']=='blocked')
        self.assertEqual(self.release(b,[blocked]).status_code,409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)
    def test_read_only_status_does_not_start_checks_or_create_records(self):
        b=self.imported()
        with patch.object(stuff,'_start_import_checks') as start,patch.object(stuff,'_queue_import_check') as check:
            for _ in range(3):self.assertEqual(self.client.get(b['status_url']).status_code,200)
        self.assertFalse(start.called);self.assertFalse(check.called)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)
    def test_all_drafts_saved_before_automatic_workers_are_dispatched(self):
        b=self.imported();seen=[]
        def worker(batch_id,item_id,revision,token):
            seen.append(self.db.execute('SELECT COUNT(*) FROM banknote_import_items WHERE batch_id=?',(batch_id,)).fetchone()[0])
            stuff.banknote_imports._CHECK_SLOTS.release()
        class Inline:
            def __init__(self,target,args=(),**kwargs):self.target,self.args=target,args
            def start(self):self.target(*self.args)
        with patch.dict(os.environ,{'BANKNOTE_IMPORT_WORKER':'1'}),patch.object(stuff.threading,'Thread',Inline),patch.object(stuff,'_run_import_check',side_effect=worker):
            stuff._start_import_checks(b['id'])
        self.assertEqual(seen,[3,3,3])
    def test_expired_check_is_readable_and_explicitly_retryable(self):
        b=self.imported();item=b['items'][0]
        imports.claim_check(self.db,b['id'],item['id'],item['revision'])
        self.db.execute('UPDATE banknote_import_items SET check_expires=0 WHERE id=?',(item['id'],));self.db.commit()
        latest=self.client.get(b['status_url']).json
        self.assertEqual(next(i for i in latest['items'] if i['id']==item['id'])['check_state'],'failed')
        self.assertTrue(imports.claim_check(self.db,b['id'],item['id'],item['revision']))
    def test_refresh_preserves_edits_and_rechecks_complete_membership(self):
        b=self.imported();item=b['items'][0]
        self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{'notes':'keep typed note','price':'$599.89'}})
        response=self.client.post('/banknotes/imports',json={'order_number':ORDERS[1],'refresh':True})
        self.assertEqual(response.json['id'],b['id']);self.assertEqual(response.json['state'],'queued')
        self.assertEqual(self.release(response.json).status_code,409)
        q=self.client.post('/ebay/today/requests',json={'action':'claim'},headers=HEADERS).json['request']
        self.assertEqual(self.client.post('/ebay/today/requests',json=self.payload(q),headers=HEADERS).status_code,200)
        latest=self.client.get(b['status_url']).json
        self.assertEqual(next(i for i in latest['items'] if i['id']==item['id'])['fields']['notes'],'keep typed note')
        self.assertEqual(len(latest['items']),3)
    def partial_record(self):
        for filename,color in (('saved-front.jpg','green'),('saved-back.jpg','yellow')):
            Image.new('RGB',(160,80),color).save(Path(stuff.UPLOAD_FOLDER)/filename)
        self.db.execute("INSERT INTO banknotes(id,order_number,marketplace,image_1,image_2,notes) VALUES('failed-form',?,'eBay','saved-front.jpg','saved-back.jpg','Keep user text')",(ORDERS[1],))
        stuff.original_listings.add_source(self.db,'banknotes','failed-form','https://www.ebay.com/itm/'+IDS[1]);self.db.commit()
    def test_partial_existing_form_recovers_only_exact_item_and_preserves_photos(self):
        self.partial_record();b=self.imported();item=next(i for i in b['items'] if i.get('existing_record_id'))
        self.assertEqual(item['existing_record_id'],'failed-form');self.assertEqual(item['order_number'],ORDERS[1])
        self.assertEqual(item['fields']['image_1'],'saved-front.jpg');self.assertEqual(item['fields']['notes'],'Keep user text')
        b=self.check(b,item);item=next(i for i in b['items'] if i['id']==item['id'])
        self.assertEqual(self.release(b,[item]).json['released'][0]['record_id'],'failed-form')
        live=self.db.execute("SELECT * FROM banknotes WHERE id='failed-form'").fetchone()
        self.assertEqual(live['image_1'],'saved-front.jpg');self.assertEqual(live['image_2'],'saved-back.jpg')
        self.assertEqual(live['notes'],'Keep user text');self.assertEqual(live['price'],'$125.37')
        self.assertEqual(live['country'],'Netherlands Antilles');self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],1)
    def test_recovery_occupied_values_are_read_only_in_draft(self):
        self.partial_record();b=self.imported();item=next(i for i in b['items'] if i.get('existing_record_id'))
        self.assertIn('notes',item['preserved_fields'])
        response=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{'notes':'would be ignored'}})
        self.assertEqual(response.status_code,409)
        self.assertEqual(self.db.execute("SELECT notes FROM banknotes WHERE id='failed-form'").fetchone()[0],'Keep user text')

    def test_partial_existing_form_concurrent_changes_block_release(self):
        self.partial_record();b=self.imported();item=next(i for i in b['items'] if i.get('existing_record_id'))
        self.db.execute("UPDATE banknotes SET notes='Newer edit' WHERE id='failed-form'");self.db.commit()
        self.assertEqual(self.release(b,[item]).status_code,409)
        self.assertEqual(self.db.execute("SELECT notes FROM banknotes WHERE id='failed-form'").fetchone()[0],'Newer edit')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0],0)

    def refresh_existing(self,item):
        return self.client.post(item['detail_url']+'/refresh-existing',json={
            'revision':item['revision'],'existing_record_version':item['existing_record_version']})

    def recovered_item(self):
        self.partial_record();batch=self.imported()
        return batch,next(item for item in batch['items'] if item.get('existing_record_id'))

    def current_item(self,batch,item):
        return next(value for value in self.client.get(batch['status_url']).json['items'] if value['id']==item['id'])

    def test_existing_photo_change_is_reviewable_and_refresh_preserves_current_photo(self):
        batch,item=self.recovered_item()
        edited=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{
            'country':'Netherlands Antilles','denomination':'2.5 Gulden','printer':'My draft research'}})
        item=edited.json['item']
        replacement=Path(stuff.UPLOAD_FOLDER)/'newer-back.jpg'
        Image.new('RGB',(160,80),'purple').save(replacement)
        self.db.execute("UPDATE banknotes SET image_2='newer-back.jpg',banknote_id='P 099',updated_at='later' WHERE id='failed-form'")
        self.db.commit()
        before=dict(self.db.execute("SELECT * FROM banknotes WHERE id='failed-form'").fetchone())
        failed=self.release(batch,[item])
        self.assertEqual(failed.status_code,409,failed.json)
        self.assertEqual(failed.json['code'],'existing_record_changed')
        changed=failed.json['item']
        self.assertEqual(changed['existing_record_changes'],[{'field':'image_2','before':'saved-back.jpg','current':'newer-back.jpg'}])
        self.assertEqual(changed['existing_record_url'],'/banknotes/failed-form')
        self.assertEqual(self.current_item(batch,item)['existing_record_changes'],changed['existing_record_changes'])
        self.assertEqual(self.client.get(item['detail_url']).status_code,200)
        request_count=self.db.execute('SELECT COUNT(*) FROM ebay_purchase_requests').fetchone()[0]
        response=self.refresh_existing(changed)
        self.assertEqual(response.status_code,200,response.json)
        refreshed=response.json['item']
        self.assertEqual(refreshed['revision'],item['revision']+1)
        self.assertFalse(refreshed['existing_record_changes'])
        self.assertEqual(refreshed['fields']['image_2'],'newer-back.jpg')
        self.assertIn('image_2',refreshed['preserved_fields'])
        self.assertEqual(refreshed['fields']['printer'],'My draft research')
        self.assertEqual(refreshed['check_state'],item['check_state'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_purchase_requests').fetchone()[0],request_count)
        self.assertEqual(dict(self.db.execute("SELECT * FROM banknotes WHERE id='failed-form'").fetchone()),before)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0],0)
        result=self.release(batch,[refreshed]);self.assertEqual(result.status_code,200,result.json)
        self.assertEqual(result.json['released'][0]['record_id'],'failed-form')
        live=self.db.execute("SELECT * FROM banknotes WHERE id='failed-form'").fetchone()
        self.assertEqual(live['image_2'],'newer-back.jpg');self.assertEqual(live['printer'],'My draft research')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],1)

    def test_refresh_existing_requires_review_of_newest_collection_values(self):
        batch,item=self.recovered_item()
        self.db.execute("UPDATE banknotes SET notes='First change' WHERE id='failed-form'");self.db.commit()
        first=self.current_item(batch,item)
        self.db.execute("UPDATE banknotes SET notes='Second change' WHERE id='failed-form'");self.db.commit()
        response=self.refresh_existing(first)
        self.assertEqual(response.status_code,409,response.json)
        self.assertEqual(response.json['code'],'existing_record_changed')
        latest=response.json['item']
        self.assertEqual(latest['existing_record_changes'],[{'field':'notes','before':'Keep user text','current':'Second change'}])
        self.assertEqual(latest['revision'],item['revision'])
        refreshed=self.refresh_existing(latest).json['item']
        self.assertEqual(refreshed['fields']['notes'],'Second change')
        self.db.execute("UPDATE banknotes SET notes='Third change' WHERE id='failed-form'");self.db.commit()
        failed=self.release(batch,[refreshed])
        self.assertEqual(failed.status_code,409);self.assertEqual(failed.json['code'],'existing_record_changed')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0],0)

    def test_refresh_existing_keeps_blank_draft_edits_and_deliberate_collection_clears(self):
        batch,item=self.recovered_item()
        item=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{
            'country':'Draft country','printer':'Draft printer'}}).json['item']
        self.db.execute("UPDATE banknotes SET notes=NULL,issuer='Current issuer' WHERE id='failed-form'");self.db.commit()
        refreshed=self.refresh_existing(self.current_item(batch,item)).json['item']
        self.assertFalse(refreshed['fields'].get('notes'))
        self.assertEqual(refreshed['fields']['issuer'],'Current issuer')
        self.assertEqual(refreshed['fields']['country'],'Draft country')
        self.assertEqual(refreshed['fields']['printer'],'Draft printer')
        self.assertNotIn('notes',refreshed['preserved_fields']);self.assertIn('issuer',refreshed['preserved_fields'])
        self.assertEqual(self.release(batch,[refreshed]).status_code,200)
        self.assertIsNone(self.db.execute("SELECT notes FROM banknotes WHERE id='failed-form'").fetchone()[0])

    def test_refresh_existing_keeps_manually_selected_draft_photo(self):
        self.partial_record();self.db.execute("UPDATE banknotes SET image_2=NULL WHERE id='failed-form'");self.db.commit()
        batch=self.imported();item=next(value for value in batch['items'] if value.get('existing_record_id'))
        batch,item=self.ambiguous_photos(batch,item)
        photo=next(value for value in item['photos'] if value['selectable'])
        item=self.choose(item,'image_2',photo['filename']).json['item']
        self.db.execute("UPDATE banknotes SET notes='Current notes' WHERE id='failed-form'");self.db.commit()
        refreshed=self.refresh_existing(self.current_item(batch,item)).json['item']
        self.assertEqual(refreshed['fields']['image_2'],photo['filename'])
        self.assertEqual(refreshed['manual_photos'],item['manual_photos'])
        self.assertEqual(refreshed['fields']['notes'],'Current notes')
        self.assertIsNone(self.db.execute("SELECT image_2 FROM banknotes WHERE id='failed-form'").fetchone()[0])

    def test_refresh_existing_revision_conflict_and_active_check_do_not_rebase(self):
        batch,item=self.recovered_item()
        self.db.execute("UPDATE banknotes SET notes='Current notes' WHERE id='failed-form'");self.db.commit()
        old=self.current_item(batch,item)
        item=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{'printer':'Newest draft'}}).json['item']
        stale=self.refresh_existing(old)
        self.assertEqual(stale.status_code,409);self.assertEqual(stale.json['code'],'draft_changed')
        imports.claim_check(self.db,batch['id'],item['id'],item['revision'])
        active=self.refresh_existing(self.current_item(batch,item));self.assertEqual(active.status_code,409)
        self.assertIn('Check',active.json['error'])
        saved=self.current_item(batch,item)
        self.assertEqual(saved['fields']['notes'],'Keep user text');self.assertEqual(saved['fields']['printer'],'Newest draft')

    def test_refresh_existing_refuses_changed_account_or_purchase_source(self):
        batch,item=self.recovered_item()
        self.db.execute("UPDATE banknotes SET notes='Current notes' WHERE id='failed-form'");self.db.commit()
        item=self.current_item(batch,item)
        self.db.execute("UPDATE ebay_purchase_account SET account_name='other'");self.db.commit()
        self.assertEqual(self.refresh_existing(item).status_code,409)
        self.db.execute("UPDATE ebay_purchase_account SET account_name='buyer'")
        self.db.execute("UPDATE ebay_order_items SET title='Changed purchased item' WHERE order_id=?",(ORDERS[1],));self.db.commit()
        self.assertEqual(self.refresh_existing(item).status_code,409)
        self.assertEqual(self.db.execute('SELECT revision FROM banknote_import_items WHERE id=?',(item['id'],)).fetchone()[0],item['revision'])

    def test_refresh_existing_never_switches_targets_or_accepts_ambiguous_matches(self):
        batch,item=self.recovered_item()
        self.db.execute("UPDATE banknotes SET notes='Current notes' WHERE id='failed-form'");self.db.commit()
        item=self.current_item(batch,item)
        self.db.execute("INSERT INTO banknotes(id,order_number,marketplace) VALUES('other-target',?,'eBay')",(ORDERS[1],))
        stuff.original_listings.add_source(self.db,'banknotes','other-target','https://www.ebay.com/itm/'+IDS[1]);self.db.commit()
        self.assertEqual(self.refresh_existing(item).status_code,409)
        self.db.execute("DELETE FROM banknote_original_listings WHERE banknote_id='failed-form'");self.db.commit()
        self.assertEqual(self.refresh_existing(item).status_code,409)
        stored=self.db.execute('SELECT existing_record_id,revision FROM banknote_import_items WHERE id=?',(item['id'],)).fetchone()
        self.assertEqual(stored['existing_record_id'],'failed-form');self.assertEqual(stored['revision'],item['revision'])

    def test_refresh_existing_refuses_item_or_record_linked_elsewhere(self):
        batch,item=self.recovered_item()
        self.db.execute("UPDATE banknotes SET notes='Current notes' WHERE id='failed-form'");self.db.commit()
        item=self.current_item(batch,item)
        other=next(value for value in batch['items'] if not value.get('existing_record_id'))
        line=self.db.execute('SELECT line_key FROM banknote_import_items WHERE id=?',(other['id'],)).fetchone()[0]
        self.db.execute("INSERT INTO banknote_ebay_links(banknote_id,line_key,matched_by,matched_at) VALUES('failed-form',?,'manual','now')",(line,));self.db.commit()
        self.assertEqual(self.refresh_existing(item).status_code,409)
        self.db.execute('DELETE FROM banknote_ebay_links')
        self.db.execute("INSERT INTO banknotes(id) VALUES('linked-other')")
        line=self.db.execute('SELECT line_key FROM banknote_import_items WHERE id=?',(item['id'],)).fetchone()[0]
        self.db.execute("INSERT INTO banknote_ebay_links(banknote_id,line_key,matched_by,matched_at) VALUES('linked-other',?,'manual','now')",(line,));self.db.commit()
        self.assertEqual(self.refresh_existing(item).status_code,409)
        self.assertEqual(self.db.execute('SELECT revision FROM banknote_import_items WHERE id=?',(item['id'],)).fetchone()[0],item['revision'])

    def test_display_renumber_does_not_require_collection_recovery(self):
        batch,item=self.recovered_item()
        self.db.execute("UPDATE banknotes SET banknote_id='P 110',updated_at='later',specs_searched_at='later' WHERE id='failed-form'");self.db.commit()
        latest=self.current_item(batch,item)
        self.assertFalse(latest['existing_record_changes'])
        self.assertEqual(latest['existing_record_version'],item['existing_record_version'])
        self.assertEqual(self.release(batch,[latest]).status_code,200)
    def refresh(self,b):
        response=self.client.post('/banknotes/imports',json={'order_number':b['order_number'],'refresh':True})
        self.assertEqual(response.status_code,200,response.json)
        q=self.client.post('/ebay/today/requests',json={'action':'claim'},headers=HEADERS).json['request']
        result=self.client.post('/ebay/today/requests',json=self.payload(q),headers=HEADERS)
        self.assertEqual(result.status_code,200,result.json)
        return self.client.get(b['status_url']).json
    def test_refresh_rebases_same_recovery_record_after_concurrent_edit(self):
        self.partial_record();b=self.imported();item=next(i for i in b['items'] if i.get('existing_record_id'))
        self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{'country':'Draft country','denomination':'2.5 Gulden'}})
        self.db.execute("UPDATE banknotes SET notes='Newer actual notes' WHERE id='failed-form'");self.db.commit()
        self.assertEqual(self.release(b,[item]).status_code,409)
        b=self.refresh(b);item=next(i for i in b['items'] if i.get('existing_record_id'))
        self.assertEqual(item['fields']['notes'],'Newer actual notes');self.assertIn('notes',item['preserved_fields'])
        self.assertEqual(item['fields']['country'],'Draft country')
        result=self.release(b,[item]);self.assertEqual(result.status_code,200,result.json)
        live=self.db.execute("SELECT * FROM banknotes WHERE id='failed-form'").fetchone()
        self.assertEqual(live['notes'],'Newer actual notes');self.assertEqual(live['country'],'Draft country')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],1)
    def test_refresh_does_not_restore_deliberately_cleared_existing_value(self):
        self.partial_record();b=self.imported()
        self.db.execute("UPDATE banknotes SET notes=NULL WHERE id='failed-form'");self.db.commit()
        b=self.refresh(b);item=next(i for i in b['items'] if i.get('existing_record_id'))
        self.assertFalse(item['fields'].get('notes'))
        self.assertEqual(self.release(b,[item]).status_code,200)
        self.assertIsNone(self.db.execute("SELECT notes FROM banknotes WHERE id='failed-form'").fetchone()[0])

    def test_populated_existing_record_stays_blocked_through_refresh(self):
        self.partial_record();self.db.execute("UPDATE banknotes SET country='Populated country' WHERE id='failed-form'");self.db.commit()
        b=self.imported();b=self.refresh(b);item=next(i for i in b['items'] if i['order_number']==ORDERS[1])
        self.assertEqual(item['state'],'blocked');self.assertEqual(self.release(b,[item]).status_code,409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],1)
    def test_record_created_after_staging_blocks_new_record_release(self):
        b=self.imported();self.partial_record();item=next(i for i in b['items'] if i['order_number']==ORDERS[1])
        self.assertEqual(self.release(b,[item]).status_code,409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],1)
    def test_recovery_refresh_never_switches_to_another_record(self):
        self.partial_record();b=self.imported()
        self.db.execute("UPDATE banknotes SET order_number='11-11111-11111' WHERE id='failed-form'");self.db.commit()
        b=self.refresh(b);item=next(i for i in b['items'] if i.get('existing_record_id'))
        self.assertEqual(item['state'],'blocked');self.assertEqual(item['existing_record_id'],'failed-form')
        self.assertEqual(self.release(b,[item]).status_code,409)
    def test_refresh_retains_target_id_when_item_linked_elsewhere(self):
        b=self.imported();self.partial_record()
        line=self.db.execute('SELECT line_key FROM ebay_order_items WHERE item_id=?',(IDS[1],)).fetchone()[0]
        self.db.execute("INSERT INTO banknote_ebay_links(banknote_id,line_key,matched_by,matched_at) VALUES('failed-form',?,'manual','now')",(line,));self.db.commit()
        b=self.refresh(b);item=next(i for i in b['items'] if i['order_number']==ORDERS[1])
        self.assertEqual(item['state'],'released');self.assertEqual(item['released_record_id'],'failed-form')
        self.assertEqual(self.release(b,[item]).json['released'][0]['record_id'],'failed-form')

    def test_populated_exact_existing_record_is_not_cloned(self):
        self.partial_record();self.db.execute("UPDATE banknotes SET country='User identified country' WHERE id='failed-form'");self.db.commit()
        b=self.imported();item=next(i for i in b['items'] if i['order_number']==ORDERS[1])
        self.assertEqual(item['state'],'blocked');self.assertEqual(self.release(b,[item]).status_code,409)
    def test_accepted_catalogue_proof_survives_release_and_reload(self):
        b=self.imported();item=b['items'][0]
        proof=dict(value='Bradbury Wilkinson',scope='type',source_url='https://en.numista.com/catalogue/note123.html',quote='Synthetic catalogue printer evidence')
        b=self.check(b,item,lambda *_:dict(filled={**self.fills,'printer':proof['value']},catalogue={'fields':{'printer':proof}}))
        item=next(i for i in b['items'] if i['id']==item['id']);self.assertEqual(len(item['evidence']),1)
        result=self.release(b,[item]);self.assertEqual(result.status_code,200,result.json)
        row=self.db.execute('SELECT f.* FROM banknote_catalog_proposal_fields f JOIN banknote_catalog_proposals p ON p.id=f.proposal_id WHERE p.record_id=?',(result.json['released'][0]['record_id'],)).fetchone()
        self.assertIsNotNone(row['accepted_at']);self.assertEqual(row['source_url'],proof['source_url'])
    def test_source_only_purchase_header_is_not_changed_by_draft_price_edit(self):
        b=self.imported();item=b['items'][0];original=item['purchase']['price']
        response=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{'price':'$1.23'}})
        self.assertEqual(response.json['item']['purchase']['price'],original)
        self.assertEqual(response.json['item']['fields']['price'],'$1.23')

    def test_draft_review_uses_existing_detail_template_without_live_record_side_effects(self):
        b=self.imported();item=b['items'][0]
        before=[tuple(row) for row in self.db.execute('SELECT * FROM banknote_import_items ORDER BY id')]
        with patch.object(stuff,'render_template',wraps=stuff.render_template) as render, \
                patch.object(stuff,'ensure_country_history') as history, \
                patch.object(stuff,'_start_import_checks') as start, \
                patch.object(stuff,'_queue_import_check') as check:
            response=self.client.get(item['detail_url'])
        self.assertEqual(response.status_code,200)
        self.assertEqual(render.call_args.args[0],'detail.html')
        context=render.call_args.kwargs
        self.assertTrue(context['import_draft']);self.assertFalse(context['is_new'])
        self.assertEqual(context['back_href'],b['url'])
        self.assertEqual(context['record']['id'],item['id'])
        self.assertIsNone(context['record']['cat_id']);self.assertIsNone(context['record']['banknote_id'])
        self.assertEqual(context['record']['order_number'],item['order_number'])
        self.assertEqual(context['record']['marketplace'],'eBay')
        self.assertEqual(context['record']['price'],item['fields']['price'])
        self.assertNotIn('order_number',context['import_editable_fields'])
        self.assertNotIn('image_1',context['import_editable_fields'])
        self.assertEqual(context['record_documents_by_set'],{})
        self.assertIsNone(context['banknote_origin'])
        html=response.get_data(as_text=True)
        self.assertIn('id="mainForm"',html)
        self.assertIn('class="coin-imgs coin-imgs-large banknote-imgs"',html)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertFalse(history.called);self.assertFalse(start.called);self.assertFalse(check.called)
        self.assertEqual(before,[tuple(row) for row in self.db.execute('SELECT * FROM banknote_import_items ORDER BY id')])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)

    def test_released_review_opens_real_detail_with_normal_controls_and_review_return(self):
        batch=self.imported();item=batch['items'][0]
        batch=self.check(batch,item);item=self.current_item(batch,item)
        released=self.release(batch,[item]);self.assertEqual(released.status_code,200,released.json)
        record_id=released.json['released'][0]['record_id']
        self.db.execute('UPDATE banknotes SET notes=? WHERE id=?',('Current collection edit',record_id));self.db.commit()
        before=[tuple(row) for row in self.db.execute('SELECT * FROM banknote_import_items ORDER BY id')]
        live_before=dict(self.db.execute('SELECT * FROM banknotes WHERE id=?',(record_id,)).fetchone())
        redirect=self.client.get(item['detail_url'])
        self.assertEqual(redirect.status_code,302)
        self.assertEqual(redirect.headers['Cache-Control'],'no-store')
        destination=urlsplit(redirect.headers['Location'])
        self.assertEqual(destination.path,'/banknotes/'+record_id)
        self.assertEqual(parse_qs(destination.query),{'report_back':[batch['url']]})
        with patch.object(stuff,'render_template',wraps=stuff.render_template) as render:
            response=self.client.get(redirect.headers['Location'])
        self.assertEqual(response.status_code,200)
        context=render.call_args.kwargs
        self.assertEqual(render.call_args.args[0],'detail.html')
        self.assertFalse(context.get('import_draft',False))
        self.assertEqual(context['record']['id'],record_id)
        self.assertEqual(context['back_href'],batch['url'])
        self.assertEqual(context['detail_report_back'],batch['url'])
        html=response.get_data(as_text=True)
        self.assertIn('Current collection edit',html)
        self.assertIn('class="serial-scan-btn"',html)
        self.assertIn('class="coin-img-panel drop-zone"',html)
        self.assertIn('aria-label="Adjust front crop"',html)
        self.assertNotIn('id="banknote-import-data"',html)
        self.assertEqual(before,[tuple(row) for row in self.db.execute('SELECT * FROM banknote_import_items ORDER BY id')])
        self.assertEqual(live_before,dict(self.db.execute('SELECT * FROM banknotes WHERE id=?',(record_id,)).fetchone()))

    def test_released_review_status_uses_live_fields_without_rewriting_draft_or_purchase(self):
        batch=self.imported();item=batch['items'][0]
        self.assertIsNone(item['collection_url'])
        result=self.release(batch,[item]);record_id=result.json['released'][0]['record_id']
        frozen=dict(self.db.execute('SELECT * FROM banknote_import_items WHERE id=?',(item['id'],)).fetchone())
        self.db.execute('UPDATE banknotes SET country=?,notes=?,image_1=?,price=? WHERE id=?',
                        ('Current country','Saved after review','new-collection-crop.jpg','$615.25',record_id));self.db.commit()
        current=self.current_item(batch,item)
        self.assertEqual(current['fields']['country'],'Current country')
        self.assertEqual(current['fields']['notes'],'Saved after review')
        self.assertEqual(current['fields']['image_1'],'new-collection-crop.jpg')
        self.assertEqual(current['fields']['price'],'$615.25')
        self.assertEqual(current['purchase'],item['purchase'])
        self.assertEqual(current['detail_url'],item['detail_url'])
        self.assertEqual(urlsplit(current['collection_url']).path,'/banknotes/'+record_id)
        self.assertEqual(parse_qs(urlsplit(current['collection_url']).query),{'report_back':[batch['url']]})
        self.assertEqual(frozen,dict(self.db.execute('SELECT * FROM banknote_import_items WHERE id=?',(item['id'],)).fetchone()))
        self.db.execute('UPDATE banknotes SET country=NULL,notes=NULL,image_1=NULL WHERE id=?',(record_id,));self.db.commit()
        cleared=self.current_item(batch,item)
        for field in ('country','notes','image_1'):self.assertIsNone(cleared['fields'][field])

    def test_released_review_original_write_urls_still_reject_draft_mutation(self):
        batch=self.imported();item=batch['items'][0]
        self.assertEqual(self.release(batch,[item]).status_code,200)
        current=self.current_item(batch,item)
        before=[tuple(row) for row in self.db.execute('SELECT * FROM banknote_import_items ORDER BY id')]
        live_before=[tuple(row) for row in self.db.execute('SELECT * FROM banknotes ORDER BY id')]
        for method in (self.client.post,self.client.patch):
            response=method(item['detail_url'],json={'revision':current['revision'],'updates':{'notes':'Must not save'}})
            self.assertEqual(response.status_code,409)
            self.assertEqual(response.json['code'],'draft_changed')
        self.assertEqual(before,[tuple(row) for row in self.db.execute('SELECT * FROM banknote_import_items ORDER BY id')])
        self.assertEqual(live_before,[tuple(row) for row in self.db.execute('SELECT * FROM banknotes ORDER BY id')])

    def test_deleted_released_record_does_not_reopen_snapshot_or_create_a_replacement(self):
        batch=self.imported();item=batch['items'][0]
        result=self.release(batch,[item]);record_id=result.json['released'][0]['record_id']
        frozen=dict(self.db.execute('SELECT * FROM banknote_import_items WHERE id=?',(item['id'],)).fetchone())
        self.db.execute('DELETE FROM banknotes WHERE id=?',(record_id,));self.db.commit()
        current=self.current_item(batch,item)
        self.assertEqual(current['state'],'released');self.assertIsNone(current['collection_url'])
        response=self.client.get(item['detail_url'])
        self.assertEqual(response.status_code,404);self.assertNotIn('Location',response.headers)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)
        self.assertEqual(frozen,dict(self.db.execute('SELECT * FROM banknote_import_items WHERE id=?',(item['id'],)).fetchone()))

    def test_released_review_redirect_requires_owner_and_matching_purchase_account(self):
        batch=self.imported();item=batch['items'][0]
        self.assertEqual(self.release(batch,[item]).status_code,200)
        self.db.execute("INSERT OR REPLACE INTO users(id,email,display_name,role,categories) VALUES('review-member','review-member@example.test','Review member','member','banknotes')")
        self.db.commit()
        response=self.client.get(item['detail_url'],headers={'Cf-Access-Authenticated-User-Email':'review-member@example.test'})
        self.assertEqual(response.status_code,403);self.assertNotIn('Location',response.headers)
        self.db.execute("UPDATE ebay_purchase_account SET account_name='other'");self.db.commit()
        response=self.client.get(item['detail_url'])
        self.assertEqual(response.status_code,409);self.assertNotIn('Location',response.headers)

    def test_normal_detail_full_form_save_keeps_safe_review_return_destination(self):
        batch=self.imported();item=batch['items'][0]
        self.assertEqual(self.release(batch,[item]).status_code,200)
        current=self.current_item(batch,item)
        form_action=urlsplit(current['collection_url']).path
        response=self.client.post(form_action,data={'notes':'Saved with normal form','_detail_report_back':batch['url']})
        self.assertEqual(response.status_code,302,response.get_data(as_text=True))
        self.assertEqual(parse_qs(urlsplit(response.headers['Location']).query),{'report_back':[batch['url']]})
        self.assertEqual(self.db.execute('SELECT notes FROM banknotes WHERE id=?',(current['released_record_id'],)).fetchone()[0],'Saved with normal form')
        with patch.object(stuff,'render_template',wraps=stuff.render_template) as render:
            self.assertEqual(self.client.get(response.headers['Location']).status_code,200)
        self.assertEqual(render.call_args.kwargs['back_href'],batch['url'])
        # Older callers may still submit the return path on the request URL.
        fallback=self.client.post(current['collection_url'],data={'notes':'Query fallback'})
        self.assertEqual(fallback.status_code,302)
        self.assertEqual(parse_qs(urlsplit(fallback.headers['Location']).query),{'report_back':[batch['url']]})
        for unsafe in ('https://example.invalid/','//example.invalid/','/\\example.invalid/','/\x01example.invalid/'):
            with self.subTest(unsafe=unsafe):
                url='/banknotes/'+current['released_record_id']+'?'+urlencode({'report_back':unsafe})
                with patch.object(stuff,'render_template',wraps=stuff.render_template) as render:
                    self.assertEqual(self.client.get(url).status_code,200)
                self.assertIsNone(render.call_args.kwargs['detail_report_back'])
                response=self.client.post(url,data={'notes':'Still ordinary form'})
                self.assertEqual(response.status_code,302)
                self.assertNotIn('report_back',parse_qs(urlsplit(response.headers['Location']).query))
                for target in (form_action,current['collection_url']):
                    response=self.client.post(target,data={'notes':'Safe hidden field handling','_detail_report_back':unsafe})
                    self.assertEqual(response.status_code,302)
                    self.assertNotIn('report_back',parse_qs(urlsplit(response.headers['Location']).query))

    def test_recovery_detail_renders_saved_draft_snapshot_not_existing_live_identity(self):
        self.partial_record();b=self.imported();item=next(i for i in b['items'] if i.get('existing_record_id'))
        with patch.object(stuff,'render_template',wraps=stuff.render_template) as render:
            self.assertEqual(self.client.get(item['detail_url']).status_code,200)
        context=render.call_args.kwargs
        self.assertEqual(context['record']['id'],item['id'])
        self.assertNotEqual(context['record']['id'],'failed-form')
        self.assertEqual(context['record']['image_1'],'saved-front.jpg')
        self.assertEqual(context['record']['notes'],'Keep user text')
        self.assertIn('notes',context['import_item']['preserved_fields'])
        self.assertIn('image_1',context['import_item']['preserved_fields'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],1)
        self.assertIsNone(self.db.execute("SELECT country FROM banknotes WHERE id='failed-form'").fetchone()[0])

    def test_shared_detail_display_values_normalize_without_losing_paid_cents(self):
        b=self.imported();item=b['items'][0]
        response=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{
            'size_width':'155 mm','size_height':'66.5 mm','date_1':'450 BC','price':'$599.89'}})
        self.assertEqual(response.status_code,200,response.json)
        fields=response.json['item']['fields']
        self.assertEqual(fields['size_width'],'155');self.assertEqual(fields['size_height'],'66.5')
        self.assertEqual(fields['date_1'],'-450');self.assertEqual(fields['price'],'$599.89')
        item=response.json['item']
        rejected=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{'size_width':'6 inches'}})
        self.assertEqual(rejected.status_code,409)
        current=self.client.get(b['status_url']).json
        self.assertEqual(next(i for i in current['items'] if i['id']==item['id'])['fields']['size_width'],'155')

    def ambiguous_photos(self,b=None,item=None):
        b=b or self.imported();item=item or b['items'][0]
        with patch.object(self,'classify',return_value={'photos':[]}):
            b=self.check(b,item)
        return b,next(i for i in b['items'] if i['id']==item['id'])
    def choose(self,item,field,filename,revision=None):
        return self.client.post(item['detail_url']+'/photos',json=dict(revision=item['revision'] if revision is None else revision,field=field,filename=filename))
    def test_manual_front_back_resolves_ambiguity_and_release_keeps_original_bytes(self):
        b,item=self.ambiguous_photos();self.assertEqual(item['check_state'],'partial')
        self.assertFalse(item['fields'].get('image_1'));self.assertEqual(len(item['photos']),2)
        first=self.choose(item,'image_1',item['photos'][0]['filename']);self.assertEqual(first.status_code,200,first.json)
        item=first.json['item'];self.assertEqual(item['check_state'],'partial')
        second=self.choose(item,'image_2',item['photos'][1]['filename']);self.assertEqual(second.status_code,200,second.json)
        item=second.json['item'];self.assertEqual(item['check_state'],'done');self.assertFalse(item['warnings'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)
        result=self.release(b,[item]);self.assertEqual(result.status_code,200,result.json)
        row=self.db.execute('SELECT * FROM banknotes WHERE id=?',(result.json['released'][0]['record_id'],)).fetchone()
        for field in ('image_1','image_2'):
            self.assertEqual((Path(stuff.UPLOAD_FOLDER)/row[field]).read_bytes(),(Path(stuff.UPLOAD_FOLDER)/item['fields'][field]).read_bytes())
        self.assertEqual(self.choose(item,'image_1',item['photos'][0]['filename']).status_code,409)
    def test_manual_photo_rejects_foreign_asset_stale_revision_and_missing_file(self):
        b,item=self.ambiguous_photos();other=next(i for i in b['items'] if i['id']!=item['id'])
        b,other=self.ambiguous_photos(b,other)
        self.assertEqual(self.choose(item,'image_1',other['photos'][0]['filename']).status_code,409)
        self.assertEqual(self.choose(item,'image_1','../outside.jpg').status_code,409)
        self.assertEqual(self.choose(item,'price',item['photos'][0]['filename']).status_code,409)
        first=self.choose(item,'image_1',item['photos'][0]['filename']);self.assertEqual(first.status_code,200)
        self.assertEqual(self.choose(item,'image_2',item['photos'][1]['filename']).status_code,409)
        item=first.json['item'];(Path(stuff.UPLOAD_FOLDER)/item['photos'][1]['filename']).unlink()
        self.assertEqual(self.choose(item,'image_2',item['photos'][1]['filename']).status_code,409)
    def test_manual_photo_rejects_same_content_for_both_sides(self):
        b,item=self.ambiguous_photos();name=item['photos'][0]['filename']
        item=self.choose(item,'image_1',name).json['item']
        self.assertEqual(self.choose(item,'image_2',name).status_code,409)
        duplicate='duplicate-'+name;(Path(stuff.UPLOAD_FOLDER)/duplicate).write_bytes((Path(stuff.UPLOAD_FOLDER)/name).read_bytes())
        asset=self.db.execute('SELECT * FROM banknote_import_assets WHERE item_id=? AND filename=?',(item['id'],name)).fetchone()
        self.db.execute('INSERT INTO banknote_import_assets VALUES(?,?,?,?,?,?,?)',(item['id'],'https://i.ebayimg.com/images/g/duplicate/s-l1600.jpg',duplicate,asset['sha256'],asset['width'],asset['height'],2));self.db.commit()
        self.assertEqual(self.choose(item,'image_2',duplicate).status_code,409)
    def test_manual_photo_keeps_other_warnings_and_draft_fields(self):
        b,item=self.ambiguous_photos();extra='The exact paid item amount is unavailable.'
        self.db.execute('UPDATE banknote_import_items SET check_message=check_message || ? WHERE id=?',(' '+extra,item['id']));self.db.commit()
        before=dict(item['fields']);item=self.choose(item,'image_1',item['photos'][0]['filename']).json['item']
        item=self.choose(item,'image_2',item['photos'][1]['filename']).json['item']
        self.assertEqual(item['check_state'],'partial');self.assertEqual(item['check_message'],extra)
        self.assertTrue(all(item['fields'][key]==value for key,value in before.items()))
    def test_manual_photo_cannot_replace_existing_record_slots_or_active_check(self):
        self.partial_record();b=self.imported();item=next(i for i in b['items'] if i.get('existing_record_id'))
        b,item=self.ambiguous_photos(b,item)
        candidate=next(photo for photo in item['photos'] if photo['selectable'])
        self.assertEqual(self.choose(item,'image_1',candidate['filename']).status_code,409)
        self.assertEqual(self.db.execute("SELECT image_1 FROM banknotes WHERE id='failed-form'").fetchone()[0],'saved-front.jpg')
        other=next(i for i in b['items'] if not i.get('existing_record_id'));b,other=self.ambiguous_photos(b,other)
        imports.claim_check(self.db,b['id'],other['id'],other['revision'])
        self.assertEqual(self.choose(other,'image_1',other['photos'][0]['filename']).status_code,409)
    def test_manual_photo_requires_connected_account_and_can_replace_draft_only_slot(self):
        b,item=self.ambiguous_photos();item=self.choose(item,'image_1',item['photos'][0]['filename']).json['item']
        item=self.choose(item,'image_1',item['photos'][1]['filename']).json['item']
        self.assertEqual(item['fields']['image_1'],item['photos'][1]['filename'])
        self.db.execute("UPDATE ebay_purchase_account SET account_name='different'");self.db.commit()
        self.assertEqual(self.choose(item,'image_2',item['photos'][0]['filename']).status_code,409)


    def crop_info(self,item,field='image_1'):
        return self.client.get(item['detail_url']+'/trim-quad/'+field)

    def crop(self,item,field='image_1',info=None,quad=None):
        info=info or self.crop_info(item,field).json
        return self.client.post(item['detail_url']+'/trim-quad/'+field,json={
            'revision':info['revision'],'trimmed':info['trimmed'],
            'quad':quad if quad is not None else [[10,10],[150,10],[150,70],[10,70]]})

    def checked_item(self):
        batch=self.imported();item=batch['items'][0]
        batch=self.check(batch,item)
        return batch,self.current_item(batch,item)

    def test_crop_read_and_cancel_do_not_mutate_draft_or_collection(self):
        batch,item=self.checked_item()
        before=[tuple(row) for row in self.db.execute('SELECT * FROM banknote_import_items ORDER BY id')]
        info=self.crop_info(item);self.assertEqual(info.status_code,200,info.json)
        self.assertEqual(info.json['revision'],item['revision'])
        response=self.client.get(info.json['source_url']);self.assertEqual(response.status_code,200);response.close()
        self.assertEqual(before,[tuple(row) for row in self.db.execute('SELECT * FROM banknote_import_items ORDER BY id')])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_import_image_edits').fetchone()[0],0)

    def test_crop_both_sides_preserves_originals_and_remains_reeditable(self):
        batch,item=self.checked_item();originals={field:item['fields'][field] for field in ('image_1','image_2')}
        before={name:(Path(stuff.UPLOAD_FOLDER)/name).read_bytes() for name in originals.values()}
        for field in originals:
            response=self.crop(item,field);self.assertEqual(response.status_code,200,response.json)
            item=response.json['item'];name=item['fields'][field]
            self.assertNotEqual(name,originals[field]);self.assertEqual(item['manual_photos'][field],name)
            self.assertEqual(item['image_sources'][field],originals[field])
            image=self.client.get(response.json['url']);self.assertEqual(image.status_code,200);image.close()
            self.assertEqual(stuff._banknote_vision_source(name,self.db),originals[field])
            info=self.crop_info(item,field).json
            self.assertEqual(info['quad'][0],[10,10]);self.assertEqual((info['width'],info['height']),(160,80))
        for name,raw in before.items():self.assertEqual((Path(stuff.UPLOAD_FOLDER)/name).read_bytes(),raw)
        self.assertEqual(self.current_item(batch,item)['fields'],item['fields'])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],0)
        first=item['fields']['image_1'];item=self.crop(item).json['item']
        self.assertEqual(stuff._banknote_vision_source(item['fields']['image_1'],self.db),originals['image_1'])
        referenced=stuff._collect_referenced_uploads(self.db)
        self.assertTrue(set(originals.values())|{first,item['fields']['image_1'],item['fields']['image_2']} <= referenced)

    def test_check_keeps_manual_crop_and_uses_original_holder(self):
        batch,item=self.checked_item();original=item['fields']['image_1'];item=self.crop(item).json['item'];cropped=item['fields']['image_1']
        seen=[]
        def evaluate(note,prepared):
            seen.append(stuff._banknote_vision_source(note['image_1'],self.db))
            return dict(filled={'image_1':'other-file.jpg','notes':'additional verified details'})
        batch=self.check(batch,item,evaluate);item=self.current_item(batch,item)
        self.assertEqual(seen,[original]);self.assertEqual(item['fields']['image_1'],cropped)
        self.assertEqual(item['fields']['notes'],'additional verified details')

    def test_release_copies_crop_and_original_mapping(self):
        batch,item=self.checked_item();original=item['fields']['image_1'];item=self.crop(item).json['item']
        cropped=item['fields']['image_1'];raw=(Path(stuff.UPLOAD_FOLDER)/cropped).read_bytes()
        response=self.release(batch,[item]);self.assertEqual(response.status_code,200,response.json)
        live=self.db.execute('SELECT * FROM banknotes').fetchone();self.assertNotEqual(live['image_1'],cropped)
        self.assertEqual((Path(stuff.UPLOAD_FOLDER)/live['image_1']).read_bytes(),raw)
        self.assertEqual(stuff._banknote_vision_source(live['image_1'],self.db),original)
        info=self.client.get('/banknotes/'+live['id']+'/trim-quad/image_1').json
        self.assertEqual(info['quad'][0],[10,10]);self.assertEqual((info['width'],info['height']),(160,80))
        self.assertEqual(self.crop_info(item).status_code,409)
        self.assertEqual(self.crop(item,info={'revision':item['revision'],'trimmed':cropped}).status_code,409)

    def test_recovery_crop_changes_only_explicit_image_on_release(self):
        batch,item=self.recovered_item();before=dict(self.db.execute("SELECT * FROM banknotes WHERE id='failed-form'").fetchone())
        item=self.crop(item,'image_2').json['item']
        self.assertEqual(dict(self.db.execute("SELECT * FROM banknotes WHERE id='failed-form'").fetchone()),before)
        self.assertEqual(item['fields']['image_1'],before['image_1']);self.assertNotEqual(item['fields']['image_2'],before['image_2'])
        self.assertEqual(self.release(batch,[item]).status_code,200)
        live=dict(self.db.execute("SELECT * FROM banknotes WHERE id='failed-form'").fetchone())
        self.assertNotEqual(live['image_2'],before['image_2']);self.assertEqual(live['image_1'],before['image_1'])
        self.assertEqual(live['notes'],before['notes']);self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0],1)
        self.assertEqual(stuff._banknote_vision_source(live['image_2'],self.db),before['image_2'])

    def test_recovery_crop_binding_rejects_concurrent_collection_photo_change(self):
        batch,item=self.recovered_item();info=self.crop_info(item).json
        Image.new('RGB',(160,80),'purple').save(Path(stuff.UPLOAD_FOLDER)/'replacement.jpg')
        self.db.execute("UPDATE banknotes SET image_1='replacement.jpg' WHERE id='failed-form'");self.db.commit()
        result=self.crop(item,info=info);self.assertEqual(result.status_code,409,result.json)
        self.assertEqual(result.json['code'],'existing_record_changed')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_import_image_edits').fetchone()[0],0)
        self.assertEqual(self.crop_info(item).status_code,409)

    def test_refresh_existing_keeps_crop_unless_review_accepts_changed_original(self):
        batch,item=self.recovered_item();item=self.crop(item).json['item'];crop=item['fields']['image_1']
        self.db.execute("UPDATE banknotes SET notes='New collection notes' WHERE id='failed-form'");self.db.commit()
        item=self.refresh_existing(self.current_item(batch,item)).json['item']
        self.assertEqual(item['fields']['image_1'],crop)
        batch=self.refresh(batch);item=self.current_item(batch,item);self.assertEqual(item['fields']['image_1'],crop)
        Image.new('RGB',(160,80),'purple').save(Path(stuff.UPLOAD_FOLDER)/'replacement.jpg')
        self.db.execute("UPDATE banknotes SET image_1='replacement.jpg' WHERE id='failed-form'");self.db.commit()
        item=self.refresh_existing(self.current_item(batch,item)).json['item']
        self.assertEqual(item['fields']['image_1'],'replacement.jpg')
        self.assertIn(crop,stuff._collect_referenced_uploads(self.db))
        self.assertEqual(self.release(batch,[item]).status_code,200)
        self.assertEqual(self.db.execute("SELECT image_1 FROM banknotes WHERE id='failed-form'").fetchone()[0],'replacement.jpg')

    def test_refresh_existing_does_not_resurrect_manually_cropped_photo_after_live_clear(self):
        batch,item=self.recovered_item();item=self.crop(item).json['item'];cropped=item['fields']['image_1']
        self.db.execute("UPDATE banknotes SET image_1=NULL WHERE id='failed-form'");self.db.commit()
        item=self.refresh_existing(self.current_item(batch,item)).json['item']
        self.assertFalse(item['fields'].get('image_1'));self.assertIn(cropped,stuff._collect_referenced_uploads(self.db))
        self.assertEqual(self.release(batch,[item]).status_code,200)
        self.assertIsNone(self.db.execute("SELECT image_1 FROM banknotes WHERE id='failed-form'").fetchone()[0])

    def test_order_refresh_does_not_resurrect_cropped_photo_after_live_clear(self):
        batch,item=self.recovered_item();item=self.crop(item).json['item']
        self.db.execute("UPDATE banknotes SET image_1=NULL WHERE id='failed-form'");self.db.commit()
        batch=self.refresh(batch);item=self.current_item(batch,item)
        self.assertFalse(item['fields'].get('image_1'))

    def test_crop_guards_stale_revision_filename_and_active_check(self):
        batch,item=self.checked_item();info=self.crop_info(item).json
        item=self.client.post(item['detail_url'],json={'revision':item['revision'],'updates':{'notes':'Keep my edit'}}).json['item']
        stale=self.crop(item,info=info);self.assertEqual(stale.status_code,409);self.assertEqual(stale.json['code'],'draft_changed')
        self.assertEqual(self.client.get(info['source_url']).status_code,409)
        invalid=dict(info,revision=item['revision'],trimmed='../other.jpg')
        self.assertEqual(self.crop(item,info=invalid).status_code,409)
        info=self.crop_info(item).json;imports.claim_check(self.db,batch['id'],item['id'],item['revision'])
        self.assertEqual(self.crop(item,info=info).status_code,409);self.assertEqual(self.crop_info(item).status_code,409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_import_image_edits').fetchone()[0],0)

    def test_crop_rejects_foreign_draft_asset_account_and_malformed_quad(self):
        batch,item=self.checked_item();other=next(value for value in batch['items'] if value['id']!=item['id'])
        info=self.crop_info(item).json
        for quad in ([],[[1,2]],'bad',[[False,1],[150,1],[150,70],[1,70]],[[float('nan'),1],[150,1],[150,70],[1,70]],[[1,1],[2,1],[2,2],[1,2]]):
            self.assertEqual(self.crop(item,info=info,quad=quad).status_code,409)
        self.assertEqual(self.crop_info(item,'notes').status_code,409)
        response=self.client.post(other['detail_url']+'/trim-quad/image_1',json=dict(revision=other['revision'],trimmed=info['trimmed'],quad=info['quad']))
        self.assertEqual(response.status_code,409)
        item=self.crop(item).json['item'];url='/uploads/'+item['fields']['image_1']
        self.db.execute("UPDATE ebay_purchase_account SET account_name='other'");self.db.commit()
        self.assertEqual(self.crop_info(item).status_code,409);self.assertEqual(self.client.get(url).status_code,404)

    def test_cropped_front_cannot_be_selected_as_back_via_its_original(self):
        batch,item=self.ambiguous_photos();original=item['photos'][0]['filename']
        item=self.choose(item,'image_1',original).json['item'];item=self.crop(item).json['item']
        response=self.choose(item,'image_2',original)
        self.assertEqual(response.status_code,409);self.assertIn('different',response.json['error'])

    def test_crop_failed_render_leaves_no_file_or_draft_changes(self):
        batch,item=self.checked_item();info=self.crop_info(item).json
        files={path.name for path in Path(stuff.UPLOAD_FOLDER).iterdir()};before=self.current_item(batch,item)
        with patch.object(stuff,'_rectify_note_quad',return_value=None):
            self.assertEqual(self.crop(item,info=info).status_code,409)
        self.assertEqual(files,{path.name for path in Path(stuff.UPLOAD_FOLDER).iterdir()})
        self.assertEqual(before,self.current_item(batch,item))

if __name__=='__main__':unittest.main()
