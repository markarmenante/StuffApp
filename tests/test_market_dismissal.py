"""Permanent listing decisions across scans, browser snapshots and DB restarts."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime, timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='market-dismissal-')
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff
import market_scan as market
import market_ebay_feed as feed

URL = 'https://www.ebay.com/itm/123456789012'
REGIONAL = 'https://www.ebay.co.uk/itm/fixture/123456789012?utm_source=one&_trksid=two'
OTHER = 'https://www.ebay.de/itm/123456789013'
TOKEN = 'fixture-token-' + 'x' * 32


def item(url=URL):
    return dict(title='Philippines 1944 5 Pesos P-96 PMG 64 EPQ', listing_url=url,
                country='Philippines', pick_number='P-96', denomination='5 Pesos',
                date_1=1944, price='$150', price_usd=150, grade_numeric=64,
                designation='EPQ', verified=True, score=75, seller='Fixture', image_urls=[])


class DismissalTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, STUFFAPP_TODAY_TOKEN=TOKEN, RAILWAY_SERVICE_NAME='web')
        self.env.start()
        self.ctx = stuff.app.app_context(); self.ctx.push()
        self.db = stuff.get_db(); self.client = stuff.app.test_client()
        for table in ('ebay_market_card_sources', 'ebay_market_cards', 'ebay_market_requests',
                      'market_scan_items', 'market_scans', 'market_dismissals', 'banknotes',
                      'ebay_purchase_account', 'ebay_connection'):
            self.db.execute('DELETE FROM ' + table)
        self.db.execute("INSERT INTO ebay_purchase_account VALUES(1,'fixture-owner')")
        self.db.commit()
        self.repo = self.start()

    def tearDown(self):
        self.ctx.pop(); self.env.stop()

    def start(self):
        import uuid
        ident = str(uuid.uuid4())
        self.db.execute("INSERT INTO market_scans(id,category,started_at,status) VALUES(?,'banknotes',?,'running')", [ident, datetime.utcnow().isoformat()])
        self.db.commit()
        return market.MarketRepository(stuff.open_db_connection, 'banknotes', ident)

    def publish(self, candidate=None):
        self.repo.publish([candidate or item()])
        return self.db.execute('SELECT * FROM market_scan_items ORDER BY rowid DESC LIMIT 1').fetchone()

    def snapshot(self, urls=(URL,)):
        ident=feed.queue(self.db)
        headers={'Authorization':'Bearer '+TOKEN}
        self.assertEqual(self.client.get('/banknotes/market/ebay-feed',headers=headers).json['request']['id'],ident)
        now=feed.utc(time.time())
        cards=[dict(item_id=feed.item_id(url),listing_url=url,title=item()['title'],price='$150',
                    image_url='',sources=['watched','sponsored'],source_label="Similar to what you've watched",
                    listing_text='',live_state='unknown',listing_checked_at=None) for url in urls]
        result=self.client.post('/banknotes/market/ebay-feed',headers=headers,json=dict(request_id=ident,
            account='fixture-owner',observed_at=now,sources={k:dict(status='ok',message='') for k in feed.KINDS},items=cards))
        self.assertEqual(result.status_code,200,result.json)
        return ident

    def test_normal_delete_hides_both_sources_but_not_same_reference_other_listing(self):
        row=self.publish();self.snapshot((REGIONAL,OTHER))
        result=self.client.post('/banknotes/market/'+row['id']+'/dismiss')
        self.assertTrue(result.json['ok'])
        self.assertEqual(result.json['canonical_url'],market.canonical_url(URL))
        self.assertEqual(result.json['unwatch']['state'],'unavailable')
        self.assertEqual(stuff._market_items(self.db,'banknotes'),[])
        visible=stuff._market_personal_feed(self.db,[])['cards']
        self.assertEqual([c['item_id'] for c in visible],['123456789013'])
        self.repo.publish([dict(item(REGIONAL),title='Changed title',price='$99'),item(OTHER)])
        self.assertEqual([c['canonical_url'] for c in stuff._market_items(self.db,'banknotes')],[market.canonical_url(OTHER)])
        self.assertGreater(self.db.execute('SELECT revision FROM market_scans WHERE id=?',[self.repo.scan_id]).fetchone()[0],1)
        self.assertEqual(self.db.execute('SELECT item_count FROM market_scans WHERE id=?',[self.repo.scan_id]).fetchone()[0],1)
        self.repo.finish('done',[],{})
        self.assertEqual(self.db.execute('SELECT item_count FROM market_scans WHERE id=?',[self.repo.scan_id]).fetchone()[0],1)

    def test_raw_delete_requires_observed_identity_and_is_idempotent_after_snapshot_prune(self):
        route='/banknotes/market/ebay-feed/123456789012/dismiss'
        self.assertEqual(self.client.post(route).status_code,404)
        self.snapshot()
        self.assertEqual(self.client.post(route).status_code,200)
        for table in ('ebay_market_card_sources','ebay_market_cards','ebay_market_requests'):
            self.db.execute('DELETE FROM '+table)
        self.db.commit()
        self.assertEqual(self.client.post(route).status_code,200)
        self.assertEqual(self.client.post('/banknotes/market/ebay-feed/not-an-id/dismiss').status_code,404)
        self.snapshot((REGIONAL,))
        self.assertEqual(stuff._market_personal_feed(self.db,[])['cards'],[])
        self.assertEqual(self.repo.publish([item(REGIONAL)]),[])

    def test_owner_category_cross_site_and_tenant_guards(self):
        row=self.publish();self.snapshot()
        route='/banknotes/market/ebay-feed/123456789012/dismiss'
        with patch.object(stuff,'_resolve_user_email',return_value='unknown@example.test'):
            self.assertEqual(self.client.post(route).status_code,403)
        self.db.execute("INSERT OR REPLACE INTO users(id,email,display_name,role,categories) VALUES('viewer-fixture','viewer@example.test','Viewer','viewer','banknotes')")
        self.db.commit()
        with patch.object(stuff,'_resolve_user_email',return_value='viewer@example.test'):
            self.assertEqual(self.client.post(route).status_code,403)
            self.assertEqual(self.client.post('/banknotes/market/'+row['id']+'/dismiss').status_code,403)
        self.assertEqual(self.client.post(route,headers={'Origin':'https://other.example'}).status_code,403)
        self.assertEqual(self.client.post('/coins/market/'+row['id']+'/dismiss').status_code,404)
        with patch.dict(os.environ,RAILWAY_SERVICE_NAME='gerri'):
            self.assertEqual(self.client.post(route).status_code,404)
        self.assertEqual(market.dismissed_keys(self.db,'banknotes'),set())

    def test_collection_and_ordered_records_are_preserved_all_duplicate_rows_hidden(self):
        row=self.publish()
        self.db.execute("INSERT INTO banknotes(id,country,pick_number,status) VALUES('owned-fixture','Philippines','P-96','Own')")
        original=dict(row)
        for ident,status in [('earlier-copy','superseded'),('ordered-copy','ordered')]:
            data=dict(original,id=ident,status=status,record_id='owned-fixture' if status=='ordered' else None)
            self.db.execute('INSERT INTO market_scan_items('+','.join(data)+') VALUES('+','.join('?' for _ in data)+')',list(data.values()))
        self.db.commit()
        self.assertEqual(self.client.post('/banknotes/market/'+row['id']+'/dismiss').status_code,200)
        states={r['id']:(r['status'],r['record_id']) for r in self.db.execute('SELECT * FROM market_scan_items')}
        self.assertEqual(states['ordered-copy'],('ordered','owned-fixture'))
        self.assertEqual(states['earlier-copy'][0],'dismissed')
        self.assertEqual(states[row['id']][0],'dismissed')
        self.assertEqual(self.db.execute('SELECT status FROM banknotes').fetchone()[0],'Own')

    def test_tombstone_outlives_candidate_feed_cleanup_and_database_reopen(self):
        row=self.publish();self.snapshot()
        self.client.post('/banknotes/market/'+row['id']+'/dismiss')
        self.db.execute('UPDATE market_scan_items SET created_at=?',[(datetime.utcnow()-timedelta(days=61)).isoformat()])
        self.db.execute('UPDATE ebay_market_requests SET requested_at=?',[time.time()-90000]);self.db.commit()
        self.repo.finish('done',[],{})
        feed.queue(self.db)
        self.assertEqual(self.db.execute('SELECT count(*) FROM market_scan_items').fetchone()[0],0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_market_cards').fetchone()[0],0)
        conn=stuff.open_db_connection()
        try:
            self.assertTrue(market.is_dismissed(conn,'banknotes',REGIONAL))
        finally:conn.close()
        self.repo=self.start()
        self.assertEqual(self.repo.publish([item(REGIONAL)]),[])

    def test_migration_backfills_legacy_payload_only_dismissal_before_prune(self):
        row=self.publish()
        self.db.execute("UPDATE market_scan_items SET status='dismissed', listing_url=NULL, canonical_url=NULL, created_at=? WHERE id=?",[(datetime.utcnow()-timedelta(days=61)).isoformat(),row['id']]);self.db.commit()
        market.init_dismissals(self.db);market.init_dismissals(self.db);self.db.commit()
        self.assertEqual(len(market.dismissed_keys(self.db,'banknotes')),1)
        self.repo.finish('done',[],{})
        self.assertEqual(self.db.execute('SELECT count(*) FROM market_scan_items').fetchone()[0],0)
        self.repo=self.start()
        self.assertEqual(self.repo.publish([item(REGIONAL)]),[])

    def test_late_publication_in_both_orders_and_concurrent_writers_never_resurrect(self):
        # Batch already loaded before a delete must consult the latest decision.
        batch=[item()]
        market.dismiss_listing(self.db,'banknotes',REGIONAL)
        self.assertEqual(self.repo.publish(batch),[])
        for i in range(5):
            url='https://ebay.com/itm/'+str(123456789100+i)
            barrier=threading.Barrier(2);errors=[]
            def publish():
                try:barrier.wait();self.repo.publish([item(url)])
                except BaseException as e:errors.append(e)
            def delete():
                conn=stuff.open_db_connection()
                try:barrier.wait();market.dismiss_listing(conn,'banknotes',url)
                except BaseException as e:errors.append(e)
                finally:conn.close()
            workers=[threading.Thread(target=publish),threading.Thread(target=delete)]
            for worker in workers:worker.start()
            for worker in workers:worker.join(10);self.assertFalse(worker.is_alive())
            self.assertEqual(errors,[])
            self.assertEqual(self.db.execute("SELECT count(*) FROM market_scan_items WHERE canonical_url=? AND status='new'",[market.canonical_url(url)]).fetchone()[0],0)
            self.assertEqual(self.repo.publish([item(url)]),[])

    def test_deleted_items_do_no_network_and_no_paid_personal_shaping(self):
        self.snapshot();market.dismiss_listing(self.db,'banknotes',URL)
        with patch.object(stuff,'_market_listing_probe',side_effect=AssertionError('no network')):
            self.assertIsNone(stuff._market_normalize_item(self.db,'banknotes',item(REGIONAL)))
        cards=feed.cards(self.db,self.db.execute("SELECT id FROM ebay_market_requests WHERE status='done'").fetchone()[0])
        states={k:dict(status='ok',message='') for k in feed.KINDS}
        with patch.object(feed,'queue',return_value='fixture'),patch.object(feed,'get_result',return_value=(cards,states)),patch.object(stuff,'_market_resolve_model',side_effect=AssertionError('no model')):
            found,error,note=stuff._market_ebay_source('fixture',())
        self.assertEqual(found,[]);self.assertIsNone(error);self.assertIn('1 previously deleted',note)

    def test_dismissed_history_has_bought_only_and_purchase_retains_suppression(self):
        row=self.publish(item('https://dealer.example/exact-note'))
        self.client.post('/banknotes/market/'+row['id']+'/dismiss')
        earlier=stuff._market_items(self.db,'banknotes',earlier=True)
        self.assertEqual(earlier[0]['status'],'dismissed')
        html=self.client.get('/banknotes/market?earlier=1').get_data(as_text=True)
        self.assertIn('Dismissed',html)
        self.assertIn('data-id="'+row['id']+'" data-bought="1"',html)
        with patch.object(stuff,'_market_listing_probe',return_value={'state':'unknown','why':'unreadable'}):
            self.assertEqual(self.client.get('/banknotes/market/'+row['id']+'/listing').status_code,302)
        self.assertEqual(self.client.post('/banknotes/market/'+row['id']+'/buy',json={'location':'Fixture'}).status_code,409)
        with patch.object(stuff,'property_choices_for_category',return_value=['Fixture']),patch.object(stuff,'_market_store_images',return_value={}),patch.object(stuff,'ensure_country_history'):
            result=self.client.post('/banknotes/market/'+row['id']+'/buy',json={'location':'Fixture','bought':True})
        self.assertEqual(result.status_code,200,result.json)
        self.assertTrue(market.is_dismissed(self.db,'banknotes','https://dealer.example/exact-note'))
        self.assertEqual(self.db.execute('SELECT status FROM banknotes WHERE id=?',[result.json['record_id']]).fetchone()[0],'Ordered')

    def test_dealer_identity_parameters_are_not_catalogue_wide(self):
        first='https://cngcoins.com/Coin.aspx?CoinID=1&utm_source=fixture'
        second='https://cngcoins.com/Coin.aspx?CoinID=2'
        market.dismiss_listing(self.db,'banknotes',first)
        self.assertFalse(market.is_dismissed(self.db,'banknotes',second))
        self.assertEqual(self.repo.publish([item(first),item(second)]),[item(second)])


if __name__=='__main__':unittest.main()
