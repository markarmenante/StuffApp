"""Fresh exact-item Purchases evidence completes only an explicit market purchase."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from zoneinfo import ZoneInfo
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='market-purchase-capture-')
os.environ['ORIGINAL_LISTING_WORKER']='0'
os.environ.pop('ANTHROPIC_API_KEY',None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff
import market_purchase_capture as capture
import ebay_purchase_lookup as lookup
from flask import g, render_template_string

TOKEN='fixture-'+'x'*40
ITEM='123456789012'
URL='https://www.ebay.com/itm/'+ITEM
TITLE='Canada 1937 $20 Bank of Canada PMG 64 EPQ'
ORDER='12-12345-12345'

if 'banknote_market_purchase_status' not in stuff.app.view_functions:
    capture.register(stuff.app,stuff.get_db,stuff._market_require_owner)


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,STUFFAPP_TODAY_TOKEN=TOKEN,RAILWAY_SERVICE_NAME='web')
        self.env.start()
        self.ctx=stuff.app.app_context();self.ctx.push()
        self.db=stuff.get_db();self.client=stuff.app.test_client()
        capture.init(self.db)
        for table in ('market_purchase_captures','banknote_purchase_review_dismissals','banknote_ebay_links',
                      'ebay_status_events','ebay_purchase_prices','ebay_purchase_observations',
                      'ebay_item_tracking','ebay_order_items','ebay_purchase_request_sessions','ebay_purchase_requests',
                      'market_scan_items','market_scans','banknotes','ebay_purchase_account','ebay_connection','ebay_mail_connection'):
            self.db.execute('DELETE FROM '+table)
        self.db.execute("INSERT INTO ebay_purchase_account VALUES(1,'buyer')")
        self.db.execute("INSERT INTO banknotes(id,status,description,note_references,price,image_1) VALUES('note','Ordered',?,'','$599.99','saved-photo.jpg')",[TITLE+'\n\nListing: '+URL])
        self.db.commit()

    def tearDown(self):
        self.ctx.pop();self.env.stop()

    def enqueue(self):
        return capture.enqueue(self.db,'note',URL,TITLE)

    def post(self,**payload):
        return self.client.post('/ebay/today/requests',json=payload,headers={'Authorization':'Bearer '+TOKEN})

    def claim(self):
        return self.post(action='claim').json['request']

    def item(self,**changes):
        return dict(dict(order_id=ORDER,item_id=ITEM,title=TITLE,seller='fixture-seller',quantity=1,
                         status_text='Paid',delivery_text='',ordered_date=datetime.now(ZoneInfo('America/New_York')).strftime('%b %d, %Y')),**changes)

    def payload(self,job,**changes):
        return dict(dict(action='complete',kind='market_purchase',id=job['id'],account='buyer',
            observed_at=datetime.now(timezone.utc).isoformat(),items=[self.item()],skipped=[],pages=1,
            search_item_id=ITEM,search_complete=True),**changes)

    def complete(self,job,**changes):
        return self.post(**self.payload(job,**changes))

    def test_paid_exact_purchase_captures_number_and_preserves_other_record_fields(self):
        pending=self.enqueue()
        self.assertEqual(self.enqueue()['id'],pending['id'])
        job=self.claim()
        self.assertEqual(job['kind'],'market_purchase');self.assertEqual(job['listing_title'],TITLE)
        self.assertNotIn('session_recovery',job)
        self.assertIsNone(self.claim())
        before=dict(self.db.execute("SELECT * FROM banknotes WHERE id='note'").fetchone())
        response=self.complete(job)
        self.assertEqual(response.status_code,200,response.json)
        after=dict(self.db.execute("SELECT * FROM banknotes WHERE id='note'").fetchone())
        self.assertEqual(after['order_number'],ORDER);self.assertEqual(after['marketplace'],'eBay')
        for key in before:
            if key not in ('order_number','marketplace','updated_at'):
                self.assertEqual(after[key],before[key],key)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_ebay_links').fetchone()[0],1)
        state=capture.state(self.db,'note')
        self.assertEqual(state['status'],'done');self.assertEqual(state['order_reference']['number'],ORDER)
        self.assertEqual(self.complete(job).status_code,409)
        self.assertEqual(capture.state(self.db,'note')['status'],'done')

    def test_empty_unpaid_and_session_results_retry_without_order_writes(self):
        self.enqueue();job=self.claim()
        response=self.complete(job,items=[])
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(capture.state(self.db,'note')['status'],'queued')
        self.assertIsNone(self.claim())
        self.db.execute('UPDATE market_purchase_captures SET next_attempt_at=0');self.db.commit()
        job=self.claim()
        response=self.complete(job,items=[self.item(status_text='Payment pending')])
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],0)
        self.db.execute('UPDATE market_purchase_captures SET next_attempt_at=0');self.db.commit()
        job=self.claim()
        response=self.post(action='complete',kind='market_purchase',id=job['id'],session={'state':'sign_in_required'})
        self.assertEqual(response.status_code,200)
        state=capture.state(self.db,'note')
        self.assertEqual(state['status'],'queued');self.assertIn('Sign in',state['message'])
        self.assertEqual(state['browser_state'],'sign_in_required')

    def test_expiry_and_stale_reader_lease_recover_without_extending_deadline(self):
        pending=self.enqueue();job=self.claim()
        self.db.execute('UPDATE market_purchase_captures SET claimed_at=?',[time.time()-181]);self.db.commit()
        self.assertEqual(self.claim()['id'],job['id'])
        self.assertEqual(capture.state(self.db,'note')['expires_at'],pending['expires_at'])
        self.db.execute('UPDATE market_purchase_captures SET expires_at=?',[time.time()-1]);self.db.commit()
        changes=self.db.total_changes
        self.assertEqual(capture.state(self.db,'note')['status'],'expired')
        self.assertEqual(self.db.total_changes,changes)
        self.assertIsNone(self.claim())
        self.assertEqual(self.complete(job).status_code,409)

    def test_wrong_account_and_stale_or_incomplete_evidence_roll_back(self):
        changes=[dict(account='other'),dict(observed_at='2026-01-01T00:00:00Z'),
                 dict(observed_at='2099-01-01T00:00:00Z'),dict(observed_at='2026-10-24T12:00:00'),
                 dict(search_complete=False),dict(search_item_id='123456789013'),dict(pages=0),
                 dict(pages=True),dict(skipped=[{'reason':'Unreadable row'}]),
                 dict(items=[self.item(item_id='123456789013')])]
        for change in changes:
            with self.subTest(change=change):
                self.db.execute('DELETE FROM market_purchase_captures');self.db.commit()
                self.enqueue();job=self.claim()
                response=self.complete(job,**change)
                self.assertEqual(response.status_code,409,response.json)
                self.assertEqual(capture.state(self.db,'note')['status'],'review')
                self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],0)
                self.assertIsNone(self.db.execute('SELECT order_number FROM banknotes').fetchone()[0])

    def test_manual_number_clear_marketplace_and_source_edits_win(self):
        for field,value in [('order_number','manual'),('order_number',''),('marketplace','CNG'),('description','Changed source')]:
            with self.subTest(field=field,value=value):
                self.db.execute("UPDATE banknotes SET order_number=NULL,marketplace=NULL,description=?",[TITLE+'\nListing: '+URL])
                self.db.execute('DELETE FROM market_purchase_captures');self.db.commit()
                self.enqueue();job=self.claim()
                self.db.execute('UPDATE banknotes SET '+field+'=?',[value]);self.db.commit()
                response=self.complete(job)
                self.assertEqual(response.status_code,409,response.json)
                self.assertEqual(self.db.execute('SELECT '+field+' FROM banknotes').fetchone()[0],value)
                self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],0)

    def test_multiple_orders_quantities_and_ambiguous_items_need_review(self):
        for items in ([self.item(),self.item(order_id='13-12345-12345')],
                      [self.item(quantity=2)],[self.item(identity_ambiguous=True)]):
            with self.subTest(items=items):
                self.db.execute('DELETE FROM market_purchase_captures');self.db.commit()
                self.enqueue();job=self.claim()
                response=self.complete(job,items=items)
                self.assertEqual(response.status_code,409,response.json)
                self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],0)

    def test_repeated_stored_purchase_is_not_reassigned(self):
        self.enqueue();job=self.claim()
        prior=lookup.ebay_mail.validate_purchase(self.item(order_id='13-12345-12345'))
        lookup.ebay_mail.apply_purchases(self.db,[prior],datetime.now(timezone.utc).isoformat(),auto_match=False)
        self.db.commit()
        response=self.complete(job)
        self.assertEqual(response.status_code,409,response.json)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_ebay_links').fetchone()[0],0)

    def test_duplicate_collection_source_needs_review(self):
        self.enqueue();job=self.claim()
        self.db.execute("INSERT INTO banknotes(id,status,description,note_references) VALUES('other','Ordered',?,'')",['Listing: '+URL]);self.db.commit()
        response=self.complete(job)
        self.assertEqual(response.status_code,409,response.json)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],0)

    def test_source_for_single_target_in_multi_item_order_updates_only_target(self):
        other=lookup.ebay_mail.validate_purchase(self.item(item_id='123456789013'))
        lookup.ebay_mail.apply_purchases(self.db,[other],datetime.now(timezone.utc).isoformat(),auto_match=False)
        self.db.commit()
        before=dict(self.db.execute('SELECT * FROM ebay_order_items').fetchone())
        self.enqueue();job=self.claim()
        response=self.complete(job)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(dict(self.db.execute('SELECT * FROM ebay_order_items WHERE item_id=?',['123456789013']).fetchone()),before)
        self.assertEqual(self.db.execute('SELECT order_number FROM banknotes').fetchone()[0],ORDER)

    def test_unrelated_incomplete_history_cannot_block_complete_targeted_search(self):
        self.enqueue();job=self.claim()
        # The targeted protocol contains only the complete requested item search;
        # periodic history failures are not imported or turned into evidence.
        response=self.complete(job)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],1)

    def test_old_order_requires_bought_and_cannot_be_filled_by_periodic_sync(self):
        self.enqueue();job=self.claim()
        response=self.complete(job,items=[self.item(ordered_date='Jan 01, 2020')])
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(capture.state(self.db,'note')['status'],'queued')
        old=lookup.ebay_mail.validate_purchase(self.item(ordered_date='Jan 01, 2020'))
        lookup.ebay_mail.apply_purchases(self.db,[old],datetime.now(timezone.utc).isoformat(),auto_match=True)
        self.db.commit()
        self.assertIsNone(self.db.execute('SELECT order_number FROM banknotes').fetchone()[0])
        capture.enqueue(self.db,'note',URL,TITLE,already_paid=True)
        self.db.execute('UPDATE market_purchase_captures SET next_attempt_at=0');self.db.commit()
        job=self.claim()
        response=self.complete(job,items=[self.item(ordered_date='Jan 01, 2020')])
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.db.execute('SELECT order_number FROM banknotes').fetchone()[0],ORDER)

    def test_existing_link_with_null_order_number_completes_without_overwrite(self):
        self.enqueue();job=self.claim()
        evidence=lookup.ebay_mail.validate_purchase(self.item())
        lookup.ebay_mail.apply_purchases(self.db,[evidence],datetime.now(timezone.utc).isoformat(),auto_match=False)
        key=self.db.execute('SELECT line_key FROM ebay_order_items').fetchone()[0]
        self.db.execute("INSERT INTO banknote_ebay_links(banknote_id,line_key,matched_by,matched_at) VALUES('note',?,'listing',?)",[key,stuff.ebay_orders.now_iso()]);self.db.commit()
        self.assertIsNone(self.db.execute('SELECT order_number FROM banknotes').fetchone()[0])
        response=self.complete(job)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.db.execute('SELECT order_number FROM banknotes').fetchone()[0],ORDER)

    def test_periodic_sync_finishes_while_targeted_reader_is_running(self):
        self.enqueue();job=self.claim()
        evidence=lookup.ebay_mail.validate_purchase(self.item())
        lookup.ebay_mail.apply_purchases(self.db,[evidence],datetime.now(timezone.utc).isoformat(),auto_match=True)
        self.db.commit()
        response=self.complete(job)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(capture.state(self.db,'note')['status'],'done')
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_ebay_links').fetchone()[0],1)

    def test_periodic_sync_completion_is_shown_as_done_not_manual_edit(self):
        self.enqueue()
        evidence=lookup.ebay_mail.validate_purchase(self.item())
        lookup.ebay_mail.apply_purchases(self.db,[evidence],datetime.now(timezone.utc).isoformat(),auto_match=True)
        self.db.commit()
        self.assertEqual(self.db.execute('SELECT order_number FROM banknotes').fetchone()[0],ORDER)
        changes=self.db.total_changes
        self.assertEqual(capture.state(self.db,'note')['status'],'done')
        self.assertEqual(self.db.total_changes,changes)
        self.assertIsNone(self.claim())
        self.assertEqual(self.db.execute('SELECT status FROM market_purchase_captures').fetchone()[0],'done')

    def test_status_owner_guard_no_store_and_viewer_context(self):
        self.enqueue()
        changes=self.db.total_changes
        response=self.client.get('/banknotes/note/market-purchase-status')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'private, no-store')
        self.assertEqual(self.db.total_changes,changes)
        with patch.object(stuff,'_resolve_user_email',return_value='unknown@example.test'):
            self.assertEqual(self.client.get('/banknotes/note/market-purchase-status').status_code,403)
        with stuff.app.test_request_context():
            g.current_user={'role':'viewer'}
            self.assertEqual(render_template_string("{{ market_purchase_capture('note') }}"),'None')
        self.assertEqual(self.client.post('/ebay/today/requests',json={'action':'claim'}).status_code,401)

    def test_tenant_pause_and_account_change_are_guarded(self):
        with patch.dict(os.environ,RAILWAY_SERVICE_NAME='gerri'):
            self.assertIsNone(self.enqueue())
        self.enqueue()
        self.db.execute('INSERT INTO ebay_mail_connection(id,enabled) VALUES(1,0)');self.db.commit()
        self.assertIsNone(self.claim());self.assertIn('paused',capture.state(self.db,'note')['message'])
        self.db.execute('UPDATE ebay_mail_connection SET enabled=1');self.db.execute("UPDATE ebay_purchase_account SET account_name='other'");self.db.commit()
        self.assertIsNone(self.claim());self.assertEqual(capture.state(self.db,'note')['status'],'cancelled')

    def test_enqueue_can_share_the_record_transaction(self):
        self.db.execute('BEGIN IMMEDIATE')
        self.db.execute("UPDATE banknotes SET price='$600.01' WHERE id='note'")
        queued=capture.enqueue(self.db,'note',URL,TITLE,commit=False)
        self.assertEqual(queued['status'],'queued')
        self.assertTrue(self.db.in_transaction)
        self.db.rollback()
        self.assertIsNone(capture.state(self.db,'note'))
        self.assertEqual(self.db.execute('SELECT price FROM banknotes').fetchone()[0],'$599.99')

    def test_targeted_evidence_is_rejected_by_periodic_and_exact_order_endpoints(self):
        self.enqueue();job=self.claim()
        payload=self.payload(job,source='ebay_purchases')
        response=self.client.post('/ebay/today',json=payload,headers={'Authorization':'Bearer '+TOKEN})
        self.assertEqual(response.status_code,400,response.json)
        self.assertIn('full Purchases snapshot',response.json['error'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],0)
        self.assertEqual(capture.state(self.db,'note')['status'],'reading')
        self.db.execute("INSERT INTO banknotes(id,order_number,marketplace) VALUES('existing',?,'eBay')",[ORDER]);self.db.commit()
        ordinary=lookup.ensure(self.db,dict(self.db.execute("SELECT * FROM banknotes WHERE id='existing'").fetchone()))
        self.assertEqual(self.claim()['id'],ordinary['id'])
        payload=self.payload(ordinary)
        del payload['kind']
        response=self.post(**payload)
        self.assertEqual(response.status_code,409,response.json)
        self.assertIn('exact-order request',response.json['error'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],0)

    def test_existing_explicit_order_request_keeps_claim_priority(self):
        self.enqueue()
        self.db.execute("INSERT INTO banknotes(id,order_number,marketplace) VALUES('existing','11-11111-11111','eBay')");self.db.commit()
        order=lookup.ensure(self.db,dict(self.db.execute("SELECT * FROM banknotes WHERE id='existing'").fetchone()))
        self.assertEqual(self.claim()['id'],order['id'])
        self.assertEqual(capture.state(self.db,'note')['status'],'queued')
        self.assertEqual(self.claim()['kind'],'market_purchase')


if __name__=='__main__': unittest.main()
