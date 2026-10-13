"""Session recovery must wait without model calls or fabricated source success."""
import os, sys, tempfile, time, types, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='market-session-tests-')
os.environ.pop('ANTHROPIC_API_KEY',None)
sys.modules['dotenv']=types.SimpleNamespace(load_dotenv=lambda **kw:None)
import app as stuff
import market_ebay_feed as feed
TOKEN='synthetic-session-token-'+'x'*40

class SessionTests(unittest.TestCase):
    def setUp(self):
        self.env=patch.dict(os.environ,STUFFAPP_TODAY_TOKEN=TOKEN,RAILWAY_SERVICE_NAME='web');self.env.start()
        self.ctx=stuff.app.app_context();self.ctx.push();self.db=stuff.get_db();self.client=stuff.app.test_client()
        for table in ('ebay_market_card_sources','ebay_market_cards','ebay_market_sessions','ebay_market_requests','market_scan_items','market_scans','ebay_purchase_account','ebay_connection'):
            self.db.execute('DELETE FROM '+table)
        self.db.execute("INSERT INTO ebay_purchase_account VALUES(1,'fixture-owner')");self.db.commit()
        stuff._MARKET_SCAN_INFLIGHT.clear();stuff._MARKET_SCAN_ACTIVE_IDS.clear()
        self.headers={'Authorization':'Bearer '+TOKEN}
        self.thread=patch.object(stuff.threading,'Thread');self.start=self.thread.start()
    def tearDown(self):
        self.thread.stop();self.ctx.pop();self.env.stop();stuff._MARKET_SCAN_INFLIGHT.clear()
    def prepare(self):
        response=self.client.post('/banknotes/market/scan',json={})
        self.assertEqual(response.status_code,202,response.json)
        self.assertTrue(response.json['waiting_for_ebay']);self.start.assert_not_called()
        return response.json['session']['request_id']
    def claim(self):return self.client.get('/banknotes/market/ebay-feed',headers=self.headers).json['request']
    def deliver(self,ident,state='ready',account='fixture-owner',reason=None):
        return self.client.post('/banknotes/market/ebay-feed',headers=self.headers,json=dict(
            request_id=ident,account=account if state=='ready' else '',observed_at=feed.utc(time.time()),items=[],
            sources={k:dict(status='ok' if state=='ready' else 'unavailable',message='Fixture only') for k in feed.KINDS},
            session=dict(state=state,reason=reason)))
    def test_missing_session_opens_once_retries_and_resumes_one_scan(self):
        ident=self.prepare();self.assertEqual(self.prepare(),ident)
        self.assertTrue(self.claim()['session_recovery']['open_browser'])
        result=self.deliver(ident,'sign_in_required');self.assertEqual(result.status_code,200,result.json);self.assertTrue(result.json['pending'])
        self.assertIsNone(feed.get_result(self.db,ident));self.assertIsNone(self.claim());self.start.assert_not_called()
        state=self.client.get('/banknotes/market/ebay-session',query_string={'request_id':ident}).json['session']
        self.assertTrue(state['active']);self.assertEqual(state['state'],'sign_in_required')
        self.db.execute('UPDATE ebay_market_sessions SET retry_after=0');self.db.commit()
        self.assertFalse(self.claim()['session_recovery']['open_browser'])
        self.assertEqual(self.deliver(ident).status_code,200)
        result=self.client.post('/banknotes/market/scan',json={'ebay_request_id':ident})
        self.assertEqual(result.status_code,200,result.json);self.start.assert_called_once()
        self.assertEqual(self.start.call_args.kwargs['args'][2],ident)
        again=self.client.post('/banknotes/market/scan',json={'ebay_request_id':ident})
        self.assertEqual(again.json['scan_id'],result.json['scan_id']);self.start.assert_called_once()
    def test_cancel_stops_recovery_and_retry_gets_new_request(self):
        ident=self.prepare();self.claim()
        self.assertEqual(self.client.post('/banknotes/market/ebay-session/cancel',json={'request_id':ident}).status_code,200)
        self.assertEqual(self.deliver(ident).status_code,409)
        self.assertEqual(self.client.post('/banknotes/market/scan',json={'ebay_request_id':ident}).status_code,409)
        self.assertNotEqual(self.prepare(),ident)
    def test_cancel_after_ready_cannot_resume_on_reload(self):
        ident=self.prepare();self.claim();self.deliver(ident)
        self.client.post('/banknotes/market/ebay-session/cancel',json={'request_id':ident})
        self.assertEqual(feed.session_status(self.db,ident)['state'],'unavailable')
        self.assertEqual(self.client.post('/banknotes/market/scan',json={'ebay_request_id':ident}).status_code,409)
        self.start.assert_not_called()
    def test_expiry_and_wrong_account_never_resume(self):
        ident=self.prepare();self.claim()
        self.assertEqual(self.deliver(ident,account='another-account').status_code,409)
        self.db.execute('UPDATE ebay_market_requests SET expires_at=?',(time.time()-1,));self.db.commit()
        self.assertFalse(feed.session_status(self.db,ident)['active'])
        self.assertEqual(self.client.post('/banknotes/market/scan',json={'ebay_request_id':ident}).status_code,409)
        self.start.assert_not_called()
    def test_changed_binding_invalidates_ready_request(self):
        ident=self.prepare();self.claim();self.assertEqual(self.deliver(ident).status_code,200)
        self.db.execute("UPDATE ebay_purchase_account SET account_name='new-owner'");self.db.commit()
        self.assertEqual(feed.session_status(self.db,ident)['state'],'unavailable')
        self.assertEqual(self.client.post('/banknotes/market/scan',json={'ebay_request_id':ident}).status_code,409)
    def test_unsupported_browser_is_explicit_and_not_retried(self):
        ident=self.prepare();self.claim();self.assertEqual(self.deliver(ident,'unavailable',reason='unsupported_browser').status_code,200)
        state=feed.session_status(self.db,ident)
        self.assertFalse(state['active']);self.assertIn('supports Chrome',state['message']);self.assertIsNone(self.claim())
    def test_challenge_waits_without_treating_it_as_empty_feed(self):
        ident=self.prepare();self.claim();self.assertEqual(self.deliver(ident,'challenge_required').status_code,200)
        self.assertEqual(feed.session_status(self.db,ident)['state'],'challenge_required');self.assertIsNone(feed.get_result(self.db,ident))
        self.assertEqual(self.client.post('/banknotes/market/scan',json={'ebay_request_id':ident}).status_code,409)
    def test_owner_only_and_web_only_session_controls(self):
        with patch.object(stuff,'_market_require_owner',side_effect=lambda:stuff.abort(403)):
            self.assertEqual(self.client.get('/banknotes/market/ebay-session').status_code,403)
            self.assertEqual(self.client.post('/banknotes/market/ebay-session/cancel',json={}).status_code,403)
        with patch.dict(os.environ,RAILWAY_SERVICE_NAME='gerri'):
            self.assertEqual(self.client.get('/banknotes/market/ebay-session').status_code,404)
    def test_explicit_skip_and_coin_scan_do_not_require_personalized_banknote_feed(self):
        self.assertEqual(self.client.post('/banknotes/market/scan',json={'skip_ebay':True}).status_code,200)
        self.assertTrue(self.start.call_args.kwargs['args'][3])
        self.assertEqual(self.client.post('/coins/market/scan',json={}).status_code,200)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_market_requests').fetchone()[0],0)
    def test_prepared_snapshot_is_used_without_another_browser_read(self):
        ident=self.prepare();self.claim();self.deliver(ident)
        ctx=types.SimpleNamespace(ebay_request_id=ident,skip_ebay=False,check=lambda *a:None)
        with patch.object(stuff.market_runtime,'current',return_value=ctx),patch.object(feed,'queue',side_effect=AssertionError('duplicate read')):
            rows,error,notes=stuff._market_ebay_source('unused',())
        self.assertEqual(rows,[]);self.assertIsNone(error);self.assertIn('0 observed',notes)
    def test_worker_restart_reclaims_timed_out_lease_without_reopening_browser(self):
        ident=self.prepare();self.assertTrue(self.claim()['session_recovery']['open_browser'])
        self.db.execute('UPDATE ebay_market_sessions SET claimed_at=?',(time.time()-121,));self.db.commit()
        next_claim=self.claim();self.assertEqual(next_claim['id'],ident);self.assertFalse(next_claim['session_recovery']['open_browser'])

if __name__=='__main__':unittest.main()
