"""Personalized source evidence, account isolation, and collection warnings."""
import json
import os
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='market-ebay-feed-')
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff
import market_ebay_feed as feed

TOKEN = 'local-fixture-token-' + 'x' * 32
URL = 'https://www.ebay.com/itm/123456789012'
TITLE = 'Philippines 1944 5 Pesos Victory P-96 PMG 64 EPQ'


def observation(ident, **kw):
    now = feed.utc(time.time())
    card = dict(item_id='123456789012', listing_url=URL + '?_trksid=fixture',
                title=TITLE, price='$150', image_url='https://i.ebayimg.com/images/g/x/s-l500.jpg',
                sources=['watched', 'sponsored'], source_label="Similar to what you've watched",
                listing_text=TITLE + ' Buy It Now', live_state='live', listing_checked_at=now)
    return dict(request_id=ident, account='fixture-owner', observed_at=now,
                sources={k:dict(status='ok',message='') for k in feed.KINDS}, items=[card], **kw)


class FeedTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, STUFFAPP_TODAY_TOKEN=TOKEN, RAILWAY_SERVICE_NAME='web')
        self.env.start()
        self.ctx = stuff.app.app_context(); self.ctx.push()
        self.db = stuff.get_db(); self.client = stuff.app.test_client()
        for table in ('ebay_market_card_sources', 'ebay_market_cards', 'ebay_market_requests',
                      'banknote_original_listings', 'banknote_ebay_links', 'banknotes', 'market_scan_items', 'market_scans',
                      'ebay_purchase_account', 'ebay_connection'):
            self.db.execute('DELETE FROM ' + table)
        self.db.execute("INSERT INTO ebay_purchase_account VALUES(1,'fixture-owner')")
        self.db.commit()
        self.headers = {'Authorization': 'Bearer ' + TOKEN}

    def tearDown(self):
        self.ctx.pop(); self.env.stop()

    def claimed(self):
        ident = feed.queue(self.db)
        response = self.client.get('/banknotes/market/ebay-feed', headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['request']['id'],ident)
        self.assertEqual(response.json['expected_account'],'fixture-owner')
        self.assertIsNone(self.client.get('/banknotes/market/ebay-feed',headers=self.headers).json['request'])
        return ident

    def post(self, payload):
        return self.client.post('/banknotes/market/ebay-feed',headers=self.headers,json=payload)

    def test_auth_tenant_and_claimed_request_are_required(self):
        self.assertEqual(self.client.get('/banknotes/market/ebay-feed').status_code,401)
        with patch.object(stuff,'_resolve_user_email',return_value='not-registered@example.test'):
            self.assertEqual(self.client.get('/banknotes/market/ebay-feed',headers=self.headers).status_code,200)
            self.assertEqual(self.client.post('/banknotes/market/ebay-feed/request',headers=self.headers).status_code,202)
            self.db.execute('DELETE FROM ebay_market_requests');self.db.commit()
        with patch.dict(os.environ,RAILWAY_SERVICE_NAME='gerri'):
            self.assertIsNone(feed.queue(self.db))
            self.assertEqual(self.client.get('/banknotes/market/ebay-feed',headers=self.headers).status_code,404)
        ident=feed.queue(self.db)
        self.assertEqual(self.post(observation(ident)).status_code,409)

    def test_read_only_refresh_requires_token_deduplicates_and_expires(self):
        route='/banknotes/market/ebay-feed/request'
        self.assertEqual(self.client.post(route).status_code,401)
        with patch.dict(os.environ,RAILWAY_SERVICE_NAME='gerri'):
            self.assertEqual(self.client.post(route,headers=self.headers).status_code,404)
        with patch.object(stuff,'_run_market_scan',side_effect=AssertionError('no paid scan')):
            response=self.client.post(route,headers=self.headers)
            self.assertEqual(response.status_code,202)
            ident=response.json['request_id']
            self.assertEqual(self.client.post(route,headers=self.headers).json['request_id'],ident)
        self.assertEqual(self.client.get('/banknotes/market/ebay-feed',headers=self.headers).json['request']['id'],ident)
        self.db.execute('UPDATE ebay_market_requests SET expires_at=?',(time.time()-1,));self.db.commit()
        self.assertEqual(self.post(observation(ident)).status_code,409)
        self.assertIsNone(self.client.get('/banknotes/market/ebay-feed',headers=self.headers).json['request'])

    def test_insufficient_identity_and_source_failure_render_honestly(self):
        ident=self.claimed();payload=observation(ident)
        payload['items'][0].update(title='A collectible note',sources=['watched'],live_state='unknown',listing_text='',listing_checked_at=None)
        payload['sources']['sponsored']=dict(status='unavailable',message='Sponsored module unavailable')
        self.assertEqual(self.post(payload).status_code,200)
        observed=stuff._market_personal_feed(self.db,[])
        self.assertTrue(observed['cards'][0]['collection_check_incomplete'])
        with stuff.app.test_request_context():
            from flask import render_template
            html=render_template('partials/market_ebay_feed.html',market_personal_feed=observed)
        self.assertIn('Sponsored module unavailable',html)
        self.assertIn('Collection match incomplete',html)
        self.assertIn('eBay Watched',html)
        self.assertNotIn('market-buy',html)

    def test_observed_cards_dedup_and_no_orders_are_created(self):
        ident=self.claimed(); payload=observation(ident)
        payload['items'].append(dict(payload['items'][0],listing_url='https://www.ebay.co.uk/itm/123456789012',sources=['watched']))
        count=self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0]
        response=self.post(payload)
        self.assertEqual(response.status_code,200,response.json)
        self.assertEqual(response.json['items_accepted'],1)
        cards,states=feed.get_result(self.db,ident)
        self.assertEqual(cards[0]['sources'],['sponsored','watched'])
        self.assertEqual(cards[0]['listing_url'],URL)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0],count)
        self.assertEqual(feed.live_probe(self.db,URL)['state'],'live')
        self.assertEqual(feed.live_probe(self.db,URL)['title'],TITLE+' Buy It Now')
        self.assertEqual(self.post(payload).status_code,409)

    def test_wrong_account_spoofed_url_stale_and_unavailable_source_rejected(self):
        ident=self.claimed(); payload=observation(ident)
        payload['account']='different-owner'
        self.assertEqual(self.post(payload).status_code,409)
        payload['account']='fixture-owner';payload['items'][0]['listing_url']='https://www.ebay.com.evil.test/itm/123456789012'
        self.assertEqual(self.post(payload).status_code,409)
        payload['items'][0]['listing_url']=URL
        payload['items'][0]['listing_checked_at']=feed.utc(time.time()-3600)
        self.assertEqual(self.post(payload).status_code,409)
        payload=observation(ident);payload['sources']['sponsored']['status']='unavailable'
        self.assertEqual(self.post(payload).status_code,409)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_market_cards').fetchone()[0],0)

    def test_no_session_is_reported_without_claiming_empty_success(self):
        ident=self.claimed();payload=observation(ident)
        payload.update(account='',items=[],sources={k:dict(status='unavailable',message='Sign-in needed') for k in feed.KINDS})
        self.assertEqual(self.post(payload).status_code,200)
        cards,states=feed.get_result(self.db,ident)
        self.assertEqual(cards,[])
        self.assertEqual(states['watched']['status'],'unavailable')

    def test_actions_use_only_fresh_exact_browser_proof_after_server_challenge(self):
        ident=self.claimed();payload=observation(ident)
        payload['items'][0]['listing_text']=TITLE+'\nBuy It Now'
        self.assertEqual(self.post(payload).status_code,200)
        row=dict(category='banknotes',status='new',id='fixture-action')
        item=dict(title=TITLE,country='Philippines',issuer='United States Administration',series='Victory',pick_number='P-96',
                  date_1=1944,issue_year_start=1944,issue_year_end=1945,issue_date_source='https://catalogue.example/p96',listing_url=URL)
        with patch.object(stuff,'_market_listing_probe',return_value=dict(state='unknown',why='blocked')):
            self.assertFalse(stuff._market_action_problem(self.db,row,item))
        with patch.object(stuff,'_market_listing_probe',return_value=dict(state='ended',why='ended')):
            self.assertEqual(stuff._market_action_problem(self.db,row,item),'ended')
        self.db.execute('UPDATE ebay_market_cards SET listing_checked_at=?',(time.time()-700,));self.db.commit()
        with patch.object(stuff,'_market_listing_probe',return_value=dict(state='unknown',why='blocked')):
            self.assertIn('could not be verified',stuff._market_action_problem(self.db,row,item))

    def test_recommendation_text_never_proves_exact_identity(self):
        html='<h1>'+TITLE+'</h1><p>Buy It Now</p><h2>Sponsored items similar to what you’ve watched</h2><p>Certification number 999999</p>'
        with patch.object(stuff,'_market_fetch_page',return_value=(200,html)):
            probe=stuff._market_listing_probe(URL)
        self.assertEqual(probe['state'],'live')
        self.assertNotIn('999999',probe['identity_text'])

    def test_browser_proof_can_resolve_challenge_but_never_ended_page(self):
        ident=self.claimed();self.assertEqual(self.post(observation(ident)).status_code,200)
        unknown=dict(state='unknown',status=403,length=0,challenged=True,final=URL,why='challenge')
        with patch.object(stuff,'_market_listing_probe',return_value=unknown),patch.object(stuff,'_market_pause'):
            self.assertEqual(stuff._market_listing_state(URL),'live')
        ended=dict(unknown,state='ended',why='sold')
        with patch.object(stuff,'_market_listing_probe',return_value=ended):
            self.assertEqual(stuff._market_listing_state(URL),'ended')
        self.db.execute('UPDATE ebay_market_cards SET listing_checked_at=?',(time.time()-700,));self.db.commit()
        self.assertIsNone(feed.live_probe(self.db,URL))
        with patch.object(stuff,'_market_listing_probe',return_value=unknown),patch.object(stuff,'_market_pause'):
            self.assertEqual(stuff._market_listing_state(URL),'unknown')

    def note(self, ident, **kw):
        values=dict(id=ident,banknote_id='B '+ident,country='Philippines',denomination='5 Pesos',
                    pick_number='P-96',date_1=1944,grade='64 EPQ',grading_authority='PMG',status='Own')
        values.update(kw)
        self.db.execute('INSERT INTO banknotes('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',list(values.values()))
        self.db.commit()

    def test_all_sources_get_linked_exact_and_possible_matches_excluding_sold(self):
        self.note('exact',slab_number='123-456',serial_number='A99')
        self.note('type',status='Ordered')
        self.note('sold',status='Sold')
        self.note('other',country='Ceylon',pick_number='P-96')
        item=dict(country='Philippines',denomination='5 Pesos',pick_number='Pick 96',date_1=1944,
                  slab_number='123456',observed_identifiers=['slab_number','serial_number'],grading_authority='PMG',listing_url='https://dealer.example/item')
        for source in ('colonial-british','ebay-personalized','sources'):
            copy=dict(item,theme=source)
            stuff._market_owned_match(self.db,'banknotes',copy)
            self.assertEqual([(x['id'],x['kind']) for x in copy['collection_matches']],[('exact','exact'),('type','possible')])
            self.assertEqual(copy['collection_matches'][0]['url'],'/banknotes/exact')
        item.update(slab_number='',serial_number='A99')
        self.assertEqual(stuff._market_collection_matches(self.db,item)[0]['kind'],'exact')
        item.update(serial_number='',country='Unknown',pick_number='',listing_url=URL)
        self.db.execute('INSERT INTO original_listing_pages(url,vendor,item_key) VALUES(?,?,?)',(URL,'eBay','ebay:123456789012'))
        self.db.execute('INSERT INTO banknote_original_listings(banknote_id,url) VALUES(?,?)',('exact',URL));self.db.commit()
        self.assertEqual(stuff._market_collection_matches(self.db,item)[0]['kind'],'listing')

    def test_unverified_personal_cards_remain_visible_without_purchase_actions(self):
        ident=self.claimed(); payload=observation(ident)
        payload['items'][0].update(live_state='unknown',listing_text='',listing_checked_at=None)
        self.assertEqual(self.post(payload).status_code,200)
        self.note('existing')
        observed=stuff._market_personal_feed(self.db,[])
        self.assertEqual(len(observed['cards']),1)
        self.assertEqual(observed['cards'][0]['availability_label'],'Availability unverified')
        self.assertEqual(observed['cards'][0]['collection_matches'][0]['id'],'existing')
        with stuff.app.test_request_context():
            from flask import render_template
            html=render_template('partials/market_ebay_feed.html',market_personal_feed=observed)
        self.assertIn('Availability unverified',html)
        self.assertIn('/banknotes/existing',html)
        self.assertIn('Open eBay to check',html)
        self.assertIn('eBay Watched',html)
        self.assertIn('eBay Sponsored',html)
        self.assertNotIn('market-buy',html)
        self.assertNotIn('✓ live',html)
        self.assertEqual(stuff._market_personal_feed(self.db,[dict(listing_url=URL)])['cards'],[])

    def test_model_cannot_invent_personal_urls_or_prove_exact_identifiers(self):
        ident=self.claimed(); self.assertEqual(self.post(observation(ident)).status_code,200)
        observed=feed.get_result(self.db,ident)
        valid=dict(listing_url=URL,title=TITLE,slab_number='123456',serial_number='A99999')
        fake=dict(valid,listing_url='https://www.ebay.com/itm/999999999999')
        client=types.SimpleNamespace(close=lambda:None)
        with patch.object(feed,'queue',return_value=ident),patch.object(feed,'get_result',return_value=observed), \
             patch('anthropic.Anthropic',return_value=client),patch.object(stuff,'_market_resolve_model',return_value='fixture'), \
             patch.object(stuff.market_runtime,'model_call',return_value=None), \
             patch.object(stuff,'_market_model_json',return_value={'items':[valid,fake]}):
            items,error,note=stuff._market_ebay_source('fixture',('','','','',''))
        self.assertEqual([i['listing_url'] for i in items],[URL])
        self.assertEqual(items[0]['discovery_sources'],['sponsored','watched'])
        self.note('claimed-cert',slab_number='123456')
        item=dict(valid,country='Philippines',pick_number='P-96',denomination='5 Pesos',grading_authority='PMG')
        self.assertEqual(stuff._market_collection_matches(self.db,item)[0]['kind'],'possible')
        pr=dict(state='live',status=200,length=50,challenged=False,final=URL,why='Buy it now',identity_text=TITLE)
        with patch.object(stuff,'_market_listing_state',side_effect=lambda url: (setattr(stuff._MARKET_LAST_PROBE,'probe',pr) or 'live')):
            checked=stuff._market_verify_live([item])[0]
        self.assertEqual(checked['observed_identifiers'],[])
        pr['identity_text']=TITLE+' Certification number 123456; serial number A99999'
        with patch.object(stuff,'_market_listing_state',side_effect=lambda url: (setattr(stuff._MARKET_LAST_PROBE,'probe',pr) or 'live')):
            checked=stuff._market_verify_live([item])[0]
        self.assertEqual(set(checked['observed_identifiers']),{'slab_number','serial_number'})
        self.assertEqual(stuff._market_collection_matches(self.db,checked)[0]['kind'],'exact')

    def test_old_saved_candidates_refresh_warnings_and_render_links(self):
        self.note('existing')
        item=dict(title=TITLE,country='Philippines',denomination='5 Pesos',pick_number='P-96',date_1=1944,
                  listing_url='https://dealer.example/itm/fixture',price='$150',grade_numeric=64,grade='Choice UNC',
                  grading_authority='PMG',designation='EPQ',venue='Dealer',verified=True,
                  issue_year_start=1944,issue_year_end=1945,issue_date_source='https://catalogue.example/fixture',
                  discovery_sources=['watched','sponsored'])
        self.db.execute("INSERT INTO market_scans(id,category,started_at,finished_at,status) VALUES('scan','banknotes',?,?, 'done')",(feed.utc(time.time()).replace('+00:00',''),feed.utc(time.time()).replace('+00:00','')))
        self.db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,payload,created_at) VALUES('candidate','scan','banknotes','new',?,?)",(json.dumps(item),feed.utc(time.time())))
        self.db.commit()
        html=self.client.get('/banknotes/market').get_data(as_text=True)
        self.assertIn('Possible collection duplicate',html)
        self.assertIn('/banknotes/existing',html)
        self.assertIn('eBay Watched',html);self.assertIn('eBay Sponsored',html)
        self.db.execute("UPDATE banknotes SET status='Sold'");self.db.commit()
        self.assertEqual(stuff._market_items(self.db,'banknotes')[0]['collection_matches'],[])


if __name__=='__main__': unittest.main()
