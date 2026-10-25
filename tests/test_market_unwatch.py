"""Only explicit Delete queues an account-bound, exact-item unwatch command."""
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
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-unwatch-')
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **_: None)
import app as stuff
import market_unwatch as unwatch
import market_ebay_feed as feed

URL = 'https://www.ebay.com/itm/123456789012'
TOKEN = 'synthetic-only-token-' + 'x' * 32


class UnwatchTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, STUFFAPP_TODAY_TOKEN=TOKEN, RAILWAY_SERVICE_NAME='web')
        self.env.start()
        self.authorized = patch.object(stuff, '_market_unwatch_authorized', return_value=True)
        self.authorized.start()
        self.ctx = stuff.app.app_context(); self.ctx.push()
        self.db = stuff.get_db(); self.client = stuff.app.test_client()
        for table in ('ebay_unwatch_commands', 'ebay_market_card_sources', 'ebay_market_cards',
                      'ebay_market_requests', 'market_scan_items', 'market_scans', 'market_dismissals',
                      'ebay_purchase_account', 'ebay_connection'):
            self.db.execute('DELETE FROM ' + table)
        self.db.execute("INSERT INTO ebay_purchase_account VALUES(1,'fixture-owner')")
        self.db.execute("INSERT INTO market_scans(id,category,started_at,status) VALUES('scan','banknotes','2026-10-25','done')")
        self.db.commit()
        self.headers = {'Authorization': 'Bearer ' + TOKEN}

    def tearDown(self):
        self.ctx.pop(); self.env.stop(); self.authorized.stop()

    def candidate(self, url=URL):
        self.db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,title,listing_url,payload,created_at) "
                        "VALUES('candidate','scan','banknotes','new','Fixture note',?,?,'2026-10-25')",
                        (url, json.dumps(dict(title='Fixture note', listing_url=url))))
        self.db.commit()

    def delete(self):
        response = self.client.post('/banknotes/market/candidate/dismiss')
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def claim(self):
        response = self.client.get('/banknotes/market/ebay-unwatch', headers=self.headers)
        self.assertEqual(response.status_code, 200, response.json)
        return response.json['request']

    def result(self, command, **changes):
        result = dict(request_id=command['id'], action='unwatch', claim_token=command['claim_token'],
                      item_id=command['item_id'], listing_url=command['listing_url'], account='fixture-owner',
                      observed_at=feed.utc(time.time()), state='removed', watch_state='not_watching')
        result.update(changes)
        return result

    def finish(self, result):
        return self.client.post('/banknotes/market/ebay-unwatch', headers=self.headers, json=result)

    def test_delete_suppresses_and_queues_exact_id_once_without_claiming_success(self):
        self.candidate('https://m.ebay.com/itm/a-note/123456789012?tracking=one')
        first = self.delete()
        self.assertTrue(stuff.market_runtime.is_dismissed(self.db, 'banknotes', URL))
        self.assertEqual(first['unwatch']['state'], 'queued')
        self.assertIn('pending', first['unwatch']['message'])
        self.assertNotIn('removed from', first['unwatch']['message'])
        self.assertEqual(self.delete()['unwatch']['id'], first['unwatch']['id'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 1)
        command = self.claim()
        self.assertFalse(command['verify_only'])
        self.assertEqual(command['listing_url'], URL)
        self.assertIsNone(self.claim())
        self.assertEqual(self.finish(self.result(command)).json['unwatch']['state'], 'removed')
        self.assertEqual(self.finish(self.result(command)).status_code, 409)
        self.assertEqual(self.delete()['unwatch']['state'], 'removed')
        self.assertIsNone(self.claim())

    def test_observed_sponsored_delete_checks_watch_state_without_source_inference(self):
        now = time.time()
        self.db.execute("INSERT INTO ebay_market_requests(id,requested_at,expires_at,status,expected_account,observed_at) VALUES('feed',?,?,'done','fixture-owner',?)", (now, now+180, now))
        self.db.execute("INSERT INTO ebay_market_cards VALUES('feed','123456789012','Fixture',?,'$10','','Sponsored','','unknown',NULL)", (URL,))
        self.db.execute("INSERT INTO ebay_market_card_sources VALUES('feed','123456789012','sponsored')")
        self.db.commit()
        response = self.client.post('/banknotes/market/ebay-feed/123456789012/dismiss')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['unwatch']['state'], 'queued')
        command = self.claim()
        self.assertEqual(self.finish(self.result(command, state='already_unwatched')).status_code, 200)

    def test_restart_reclaim_is_verify_only_and_fences_old_acknowledgment(self):
        self.candidate(); self.delete(); original = self.claim()
        self.db.execute('UPDATE ebay_unwatch_commands SET claimed_at=?', (time.time()-121,)); self.db.commit()
        recovered = self.claim()
        self.assertTrue(recovered['verify_only'])
        self.assertNotEqual(original['claim_token'], recovered['claim_token'])
        self.assertEqual(self.finish(self.result(original)).status_code, 409)
        self.assertEqual(self.finish(self.result(recovered)).status_code, 409)
        self.assertEqual(self.finish(self.result(recovered, state='already_unwatched')).status_code, 200)

    def test_uncertain_result_is_terminal_without_a_second_action(self):
        self.candidate(); self.delete(); command = self.claim()
        response = self.finish(self.result(command, state='uncertain', watch_state='watching'))
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('removed from', response.json['unwatch']['message'])
        self.assertIsNone(self.claim())

    def test_expiry_and_account_change_never_dispatch_old_intent(self):
        self.candidate(); self.delete(); command = self.claim()
        self.db.execute('UPDATE ebay_unwatch_commands SET expires_at=?', (time.time()-1,)); self.db.commit()
        before = self.db.total_changes
        status = self.client.get('/banknotes/market/ebay-unwatch/status').json
        self.assertEqual(status['requests'][0]['state'], 'expired')
        self.assertEqual(before, self.db.total_changes)
        self.assertEqual(self.finish(self.result(command)).status_code, 409)
        self.assertIsNone(self.claim())
        self.db.execute('DELETE FROM ebay_unwatch_commands'); self.db.commit()
        self.delete()
        self.db.execute("UPDATE ebay_purchase_account SET account_name='other-owner'"); self.db.commit()
        self.assertIsNone(self.claim())
        self.assertEqual(self.db.execute('SELECT state FROM ebay_unwatch_commands').fetchone()[0], 'failed')
        self.assertEqual(self.client.get('/banknotes/market/ebay-unwatch/status').json['requests'], [])

    def test_success_requires_matching_fresh_account_item_and_watch_evidence(self):
        self.candidate(); self.delete(); command = self.claim()
        for changes in (dict(account='other-owner'), dict(account=''), dict(watch_state='watching'),
                        dict(item_id='123456789013'), dict(listing_url='https://ebay.com.evil.test/itm/123456789012'),
                        dict(observed_at=feed.utc(time.time()-1000)), dict(claim_token='stale'),
                        dict(state='invented'), dict(request_id=[])):
            self.assertEqual(self.finish(self.result(command, **changes)).status_code, 409, changes)
        self.assertEqual(self.finish(self.result(command)).status_code, 200)

    def test_bridge_auth_owner_and_tenant_boundaries(self):
        self.candidate()
        self.assertEqual(self.client.get('/banknotes/market/ebay-unwatch').status_code, 401)
        with patch.object(stuff, '_resolve_user_email', return_value='unknown@example.test'):
            self.assertEqual(self.client.post('/banknotes/market/candidate/dismiss').status_code, 403)
            self.assertEqual(self.client.get('/banknotes/market/ebay-unwatch/status').status_code, 403)
            self.assertEqual(self.client.get('/banknotes/market/ebay-unwatch', headers=self.headers).status_code, 200)
            self.assertEqual(self.client.get('/banknotes/market/ebay-unwatch').status_code, 401)
        with patch.dict(os.environ, RAILWAY_SERVICE_NAME='gerri'):
            self.assertEqual(self.delete()['unwatch']['state'], 'unavailable')
            self.assertEqual(self.client.get('/banknotes/market/ebay-unwatch', headers=self.headers).status_code, 404)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 0)

    def test_no_account_or_disagreement_never_creates_unbound_command(self):
        self.candidate()
        self.db.execute('DELETE FROM ebay_purchase_account'); self.db.commit()
        self.assertEqual(self.delete()['unwatch']['state'], 'unavailable')
        self.db.execute("INSERT INTO ebay_purchase_account VALUES(1,'one')")
        self.db.execute("INSERT INTO ebay_connection(id,account_key,account_name,owner_email,connected_at) VALUES(1,'fixture-key','two','fixture@example.test','2026-10-25')"); self.db.commit()
        self.assertEqual(self.delete()['unwatch']['state'], 'unavailable')
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 0)

    def test_non_ebay_and_misleading_hosts_never_enqueue(self):
        for url in ('https://dealer.example/item/123456789012', 'https://ebay.com.evil.test/itm/123456789012',
                    'http://www.ebay.com/itm/123456789012', 'https://name:password@ebay.com/itm/123456789012'):
            self.db.execute('DELETE FROM market_scan_items'); self.db.commit()
            self.candidate(url)
            self.assertIsNone(self.delete()['unwatch'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 0)

    def test_canonical_only_legacy_record_cannot_authorize_an_ebay_mutation(self):
        self.candidate('')
        self.db.execute('UPDATE market_scan_items SET canonical_url=?', (URL,)); self.db.commit()
        self.assertIsNone(self.delete()['unwatch'])
        self.assertTrue(stuff.market_runtime.is_dismissed(self.db, 'banknotes', URL))
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 0)

    def test_unverified_origin_preserves_suppression_without_authorizing_external_write(self):
        self.candidate()
        self.authorized.stop()
        try:
            response = self.client.post('/banknotes/market/candidate/dismiss',
                        headers={'Cf-Access-Authenticated-User-Email': stuff.OWNER_EMAIL})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['unwatch']['state'], 'unavailable')
            self.assertTrue(stuff.market_runtime.is_dismissed(self.db, 'banknotes', URL))
            self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 0)
            status = self.client.get('/banknotes/market/ebay-unwatch/status').json
            self.assertIs(status['unwatch_authorized'], False)
        finally:
            self.authorized.start()

    def test_signed_owner_capability_is_read_only_and_authorizes_only_new_delete(self):
        import jwt
        from cryptography.hazmat.primitives.asymmetric import rsa
        private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        key = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
        key.update(kid='fixture', alg='RS256', use='sig')
        issuer, audience = 'https://fixture.cloudflareaccess.com', 'a' * 64
        claims = dict(iss=issuer, aud=[audience], email=stuff.OWNER_EMAIL, sub='fixture-user',
                      type='app', iat=int(time.time())-5, exp=int(time.time())+300)
        token = jwt.encode(claims, private, algorithm='RS256', headers={'kid':'fixture'})
        self.candidate(); self.authorized.stop()
        try:
            with patch.dict(os.environ, STUFFAPP_CF_ACCESS_TEAM_DOMAIN=issuer, STUFFAPP_CF_ACCESS_AUD=audience), \
                    patch.object(stuff.cloudflare_access, '_keys', return_value=[key]):
                headers = {'Cf-Access-Jwt-Assertion':token}
                before = self.db.total_changes
                status = self.client.get('/banknotes/market/ebay-unwatch/status', headers=headers).json
                self.assertIs(status['unwatch_authorized'], True)
                self.assertEqual(self.db.total_changes, before)
                self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 0)
                for extra in ({}, {'Origin':'null'}, {'Origin':'null','Sec-Fetch-Site':'cross-site'}):
                    response = self.client.post('/banknotes/market/candidate/dismiss', headers=dict(headers, **extra))
                    self.assertEqual(response.json['unwatch']['state'], 'unavailable')
                    self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 0)
                response = self.client.post('/banknotes/market/candidate/dismiss',
                           headers=dict(headers, Origin='https://localhost', **{'Sec-Fetch-Site':'same-origin'}))
                self.assertEqual(response.json['unwatch']['state'], 'queued')
        finally:
            self.authorized.start()

    def test_status_and_schema_initialization_do_not_retroactively_queue(self):
        self.candidate()
        stuff.market_runtime.dismiss_listing(self.db, 'banknotes', URL)
        unwatch.init_schema(self.db)
        self.db.execute('PRAGMA query_only=ON')
        try:
            self.assertEqual(self.client.get('/banknotes/market/ebay-unwatch/status').json['requests'], [])
        finally:
            self.db.execute('PRAGMA query_only=OFF')
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 0)

    def test_coin_delete_queues_ebay_and_other_marketplaces_stay_durably_suppressed(self):
        self.candidate()
        self.db.execute("UPDATE market_scan_items SET category='coins'")
        self.db.execute("UPDATE market_scans SET category='coins'"); self.db.commit()
        response = self.client.post('/coins/market/candidate/dismiss')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['unwatch']['state'], 'queued')
        self.assertTrue(stuff.market_runtime.is_dismissed(self.db, 'coins', URL))
        self.assertFalse(stuff.market_runtime.is_dismissed(self.db, 'banknotes', URL))
        self.db.execute('DELETE FROM market_scan_items'); self.db.commit()
        other = 'https://dealer.example/coin/12'
        self.candidate(other)
        self.db.execute("UPDATE market_scan_items SET category='coins'"); self.db.commit()
        response = self.client.post('/coins/market/candidate/dismiss')
        self.assertIsNone(response.json['unwatch'])
        self.assertTrue(stuff.market_runtime.is_dismissed(self.db, 'coins', other))
        self.assertIn(stuff.market_runtime.canonical_url(other), stuff.market_runtime.dismissed_keys(self.db, 'coins'))
        self.assertEqual(stuff._market_items(self.db, 'coins'), [])
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_unwatch_commands').fetchone()[0], 1)
        self.db.execute('DELETE FROM market_scan_items')
        self.db.execute("UPDATE market_scans SET status='running'"); self.db.commit()
        repository = stuff.market_runtime.MarketRepository(stuff.open_db_connection, 'coins', 'scan')
        self.assertEqual(repository.publish([dict(title='Coin', listing_url=other), dict(title='Coin', listing_url=URL)]), [])
        self.assertEqual(self.db.execute('SELECT count(*) FROM market_scan_items').fetchone()[0], 0)

    def test_queue_failure_rolls_back_suppression_together(self):
        self.candidate()
        with patch.object(unwatch, 'enqueue', side_effect=RuntimeError('synthetic failure')):
            with self.assertRaises(RuntimeError):
                unwatch.dismiss(self.db, URL)
        self.assertFalse(stuff.market_runtime.is_dismissed(self.db, 'banknotes', URL))
        self.assertEqual(self.db.execute("SELECT status FROM market_scan_items WHERE id='candidate'").fetchone()[0], 'new')


if __name__ == '__main__':
    unittest.main()
