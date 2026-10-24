"""Explicit personal-card purchases share exact identity and Ordered filing."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='market-card-buy-')
os.environ.pop('ANTHROPIC_API_KEY', None)
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff
import market_ebay_feed as feed

ITEM = '123456789012'
URL = 'https://www.ebay.com/itm/' + ITEM
ROUTE = '/banknotes/market/ebay-feed/' + ITEM + '/buy'
TITLE = 'Canada 1937 $20 Bank of Canada PMG 64 EPQ'


class PersonalBuyTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, STUFFAPP_TODAY_TOKEN='fixture-' + 'x' * 40, RAILWAY_SERVICE_NAME='web')
        self.env.start()
        self.ctx = stuff.app.app_context(); self.ctx.push()
        self.db = stuff.get_db(); self.client = stuff.app.test_client()
        for table in ('ebay_market_card_sources', 'ebay_market_cards', 'ebay_market_sessions', 'ebay_market_requests',
                      'market_scan_items', 'market_scans', 'market_dismissals', 'banknotes',
                      'ebay_purchase_account', 'ebay_connection'):
            self.db.execute('DELETE FROM ' + table)
        self.db.execute("INSERT INTO ebay_purchase_account VALUES(1,'fixture-owner')")
        self.db.commit()
        self.patches = [patch.object(stuff, '_market_store_images', return_value={}),
                        patch.object(stuff, '_market_vendor_name', return_value='Fixture seller (eBay)'),
                        patch.object(stuff, 'property_choices_for_category', return_value=['Home']),
                        patch.object(stuff, 'ensure_country_history')]
        for p in self.patches: p.start()

    def tearDown(self):
        for p in reversed(self.patches): p.stop()
        self.ctx.pop(); self.env.stop()

    def snapshot(self, title=TITLE, account='fixture-owner', age=0, state='unknown'):
        observed=time.time()-age
        self.db.execute("INSERT INTO ebay_market_requests(id,requested_at,expires_at,status,expected_account,observed_at,source_status) VALUES('snapshot',?,?,'done',?,?,?)",
                        (observed, observed+600, account, observed, json.dumps({k:dict(status='ok',message='') for k in feed.KINDS})))
        self.db.execute('INSERT INTO ebay_market_cards VALUES(?,?,?,?,?,?,?,?,?,?)',
                        ('snapshot',ITEM,title,URL,'$599.99','','Watchlist',title,state,observed if state=='live' else None))
        self.db.execute("INSERT INTO ebay_market_card_sources VALUES('snapshot',?,'watched')", (ITEM,))
        self.db.commit()

    def bought(self):
        return self.client.post(ROUTE, json=dict(location='Home',bought=True))

    def test_observed_unverified_card_bought_preserves_price_and_exact_purchase_source(self):
        self.snapshot()
        with patch.object(stuff, '_market_listing_probe', side_effect=AssertionError('Bought must not require liveness')):
            response=self.bought()
        self.assertEqual(response.status_code,200,response.json)
        note=dict(self.db.execute('SELECT * FROM banknotes').fetchone())
        self.assertEqual(note['status'],'Ordered')
        self.assertEqual(note['price'],'$599.99')
        self.assertEqual(note['property_name'],'Home')
        self.assertFalse(note['country']); self.assertFalse(note['pick_number'])
        self.assertIn(URL,note['description'])
        self.assertEqual(stuff.ebay_orders.listing_candidates(self.db)[ITEM],{note['id']})
        self.assertEqual(stuff._market_personal_feed(self.db,[])['cards'],[])
        self.assertEqual(self.bought().json['record_id'],note['id'])
        self.db.execute('DELETE FROM ebay_market_card_sources'); self.db.execute('DELETE FROM ebay_market_cards')
        self.db.execute('DELETE FROM ebay_market_requests'); self.db.commit()
        self.assertEqual(self.bought().json['record_id'],note['id'])
        self.db.execute("UPDATE ebay_purchase_account SET account_name='different'"); self.db.commit()
        self.assertEqual(self.bought().status_code,404)

    def test_buy_rechecks_live_then_files_and_unknown_does_not_create_record(self):
        self.snapshot()
        with patch.object(stuff, '_market_listing_probe', return_value=dict(state='unknown',why='unreadable')):
            response=self.client.post(ROUTE,json=dict(location='Home'))
        self.assertEqual(response.status_code,409,response.json)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0],0)
        with patch.object(stuff, '_market_listing_probe', return_value=dict(state='live',title=TITLE,why='live')):
            response=self.client.post(ROUTE,json=dict(location='Home'))
        self.assertEqual(response.status_code,200,response.json)

    def test_ended_bought_works_but_ended_buy_does_not(self):
        self.snapshot(state='ended')
        with patch.object(stuff, '_market_listing_probe', side_effect=AssertionError('Bought bypasses ended check')):
            self.assertEqual(self.bought().status_code,200)

    def test_bought_recovers_personal_listing_that_buy_found_ended(self):
        self.snapshot()
        with patch.object(stuff,'_market_listing_probe',return_value=dict(state='ended',why='Listing ended')):
            response=self.client.post(ROUTE,json=dict(location='Home'))
        self.assertEqual(response.status_code,409,response.json)
        with patch.object(stuff,'_market_listing_probe',side_effect=AssertionError('Already paid')):
            response=self.bought()
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0],1)

    def test_bought_does_not_bypass_prior_identity_failure(self):
        self.snapshot()
        probe=dict(state='live',title='Canada 1938 $50 Bank of Canada PMG 64 EPQ',why='live')
        with patch.object(stuff,'_market_listing_probe',return_value=probe):
            response=self.client.post(ROUTE,json=dict(location='Home'))
        self.assertEqual(response.status_code,409,response.json)
        self.assertEqual(self.bought().status_code,409)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0],0)

    def test_ended_recovery_still_rejects_prohibited_personal_card(self):
        self.snapshot()
        with patch.object(stuff,'_market_listing_probe',return_value=dict(state='ended',why='Listing ended')):
            self.assertEqual(self.client.post(ROUTE,json=dict(location='Home')).status_code,409)
        self.db.execute("UPDATE ebay_market_cards SET title=?",[TITLE+' Specimen']);self.db.commit()
        self.assertEqual(self.bought().status_code,409)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0],0)

    def test_buy_and_bought_require_valid_location_and_owner(self):
        self.snapshot()
        self.assertEqual(self.client.post(ROUTE,json=dict(bought=True)).status_code,400)
        self.assertEqual(self.client.post(ROUTE,json=dict(bought=True,location='Other')).status_code,400)
        with patch.object(stuff, '_resolve_user_email', return_value='unknown@example.test'):
            self.assertEqual(self.bought().status_code,403)
        self.assertEqual(self.client.post(ROUTE,json=dict(bought=True,location='Home'),headers={'Origin':'https://evil.example'}).status_code,403)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0],0)

    def test_account_tenant_expiry_and_arbitrary_client_url_are_guarded(self):
        self.assertEqual(self.bought().status_code,404)
        self.snapshot(age=86401)
        self.assertEqual(self.bought().status_code,404)
        self.db.execute('UPDATE ebay_market_requests SET observed_at=?,expected_account=?',(time.time(),'different')); self.db.commit()
        self.assertEqual(self.bought().status_code,404)
        self.db.execute("UPDATE ebay_market_requests SET expected_account='fixture-owner'"); self.db.commit()
        with patch.dict(os.environ,RAILWAY_SERVICE_NAME='gerri'):
            self.assertEqual(self.bought().status_code,404)
        response=self.client.post(ROUTE,json=dict(location='Home',bought=True,listing_url='https://evil.example'))
        self.assertEqual(response.json['listing_url'],URL)

    def test_exclusions_apply_to_both_actions(self):
        self.snapshot()
        for label in ('Specimen','Proof','Remainder','PMG 64 NET'):
            self.db.execute('UPDATE ebay_market_cards SET title=?',(TITLE+' '+label,)); self.db.commit()
            for bought in (True,False):
                response=self.client.post(ROUTE,json=dict(location='Home',bought=bought))
                self.assertEqual(response.status_code,409,(label,response.json))
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0],0)

    def seed_scan(self):
        self.db.execute("INSERT INTO market_scans(id,category,status,started_at) VALUES('scan','banknotes','done',datetime('now'))")
        item=dict(title=TITLE,listing_url=URL,venue='eBay',price='$599.99',country='Canada',verified=True)
        self.db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,title,listing_url,payload,created_at) VALUES('candidate','scan','banknotes','new',?,?,?,datetime('now'))",(TITLE,URL,json.dumps(item)))
        self.db.commit()

    def test_feed_and_scan_buy_share_one_record_in_either_direction(self):
        self.snapshot(); self.seed_scan()
        first=self.bought()
        second=self.client.post('/banknotes/market/candidate/buy',json=dict(location='Home',bought=True))
        self.assertEqual(first.json['record_id'],second.json['record_id'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0],1)

    def test_scan_then_feed_and_retry_after_expiry_share_one_record(self):
        self.snapshot(); self.seed_scan()
        first=self.client.post('/banknotes/market/candidate/buy',json=dict(location='Home',bought=True))
        second=self.bought()
        self.assertEqual(first.json['record_id'],second.json['record_id'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0],1)
        self.db.execute('UPDATE ebay_market_requests SET observed_at=?',(time.time()-86401,)); self.db.commit()
        self.assertEqual(self.bought().json['record_id'],first.json['record_id'])

    def test_simultaneous_feed_and_scan_requests_create_one_record_without_network_write_lock(self):
        self.snapshot(); self.seed_scan()
        barrier=threading.Barrier(2)
        def images(item,category=None):
            conn=stuff.open_db_connection()
            try:
                conn.execute('BEGIN IMMEDIATE'); conn.rollback()
            finally: conn.close()
            barrier.wait(timeout=10)
            return {}
        results=[]
        def purchase(route):
            with stuff.app.test_client() as client:
                results.append(client.post(route,json=dict(location='Home',bought=True)))
        with patch.object(stuff,'_market_store_images',side_effect=images):
            threads=[threading.Thread(target=purchase,args=(route,)) for route in (ROUTE,'/banknotes/market/candidate/buy')]
            for thread in threads: thread.start()
            for thread in threads: thread.join(timeout=20)
        self.assertEqual([r.status_code for r in results],[200,200],[r.json for r in results])
        self.assertEqual(len({r.json['record_id'] for r in results}),1)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0],1)


if __name__ == '__main__': unittest.main()
