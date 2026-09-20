"""Shared market integration: persisted decisions, isolation and short writes."""
import os
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import datetime
from unittest.mock import patch

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-progressive-')
os.environ['ANTHROPIC_API_KEY'] = 'test-key'
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as appmod
import market_scan as market
appmod.app.config['TESTING'] = True


def candidate(url='https://dealer.example/one', **kw):
    return dict(title='Athens tetradrachm', listing_url=url, venue='Dealer', price='$100',
                price_usd=100, grade_numeric=45, designation='', closes='', theme='catalogue',
                score=50, **kw)


def start(category='coins'):
    import uuid
    ident = str(uuid.uuid4())
    db = appmod.open_db_connection()
    db.execute("INSERT INTO market_scans(id,category,started_at,status) VALUES(?,?,?,'running')",
               [ident, category, datetime.utcnow().isoformat()])
    db.commit(); db.close()
    return market.MarketRepository(appmod.open_db_connection, category, ident)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        db = appmod.open_db_connection()
        db.execute('DELETE FROM market_scan_items'); db.execute('DELETE FROM market_scans')
        db.commit(); db.close()

    def rows(self):
        db = appmod.open_db_connection()
        try:
            return [dict(r) for r in db.execute('SELECT * FROM market_scan_items')]
        finally:
            db.close()

    def test_decisions_and_ids_survive_progress_and_enrichment(self):
        repo = start()
        repo.publish([candidate()])
        row = self.rows()[0]
        repo.publish([dict(candidate(), score=65, archive_note='Enriched')])
        self.assertEqual(self.rows()[0]['id'], row['id'])
        self.assertEqual(self.rows()[0]['score'], 65)
        db = appmod.open_db_connection()
        db.execute("UPDATE market_scan_items SET status='ordered',record_id='bought-record' WHERE id=?", [row['id']])
        db.commit(); db.close()
        repo.publish([dict(candidate(), score=99)])
        row = self.rows()[0]
        self.assertEqual((row['status'], row['record_id'], row['score']), ('ordered', 'bought-record', 65))
        repo.finish('Done', [], {})
        new = start(); new.publish([candidate()])
        self.assertEqual(len(self.rows()), 1)
        self.assertEqual(self.rows()[0]['status'], 'ordered')

    def test_dismissed_listing_never_resurrected(self):
        repo = start(); repo.publish([candidate()])
        row = self.rows()[0]
        client = appmod.app.test_client()
        self.assertTrue(client.post('/coins/market/' + row['id'] + '/dismiss').get_json()['ok'])
        repo.publish([dict(candidate(), score=99)])
        self.assertEqual(self.rows()[0]['status'], 'dismissed')
        repo.finish('done', [], {})
        start().publish([candidate()])
        self.assertEqual(self.rows()[0]['status'], 'dismissed')

    def test_partial_scan_keeps_previous_candidates_and_stale_generation_cannot_write(self):
        old = start(); old.publish([candidate()]); old.finish('done', [], {})
        new = start(); new.publish([candidate('https://dealer.example/two')])
        with self.assertRaises(market.ScanStopped):
            old.publish([candidate('https://dealer.example/late')])
        with self.assertRaises(market.ScanStopped):
            old.finish('late', [], {})
        new.finish('partial', ['one source failed'], {})
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual({r['status'] for r in self.rows()}, {'new'})
        complete = start(); complete.publish([candidate('https://dealer.example/three')])
        complete.finish('done', [], {})
        self.assertEqual(sum(r['status'] == 'new' for r in self.rows()), 1)

    def test_prior_live_id_reused_and_category_isolated(self):
        old = start(); old.publish([candidate()]); old.finish('done', [], {})
        ident = self.rows()[0]['id']
        new = start(); new.publish([candidate()])
        self.assertEqual(self.rows()[0]['id'], ident)
        self.assertEqual(self.rows()[0]['scan_id'], new.scan_id)
        paper = start('banknotes'); paper.publish([candidate()])
        self.assertEqual(len(self.rows()), 2)
        self.assertEqual({r['category'] for r in self.rows()}, {'coins', 'banknotes'})

    def test_fx_cache_never_leaves_scan_writer_open(self):
        db = appmod.open_db_connection()
        db.execute("DELETE FROM fx_rates WHERE currency='EUR'"); db.commit()
        ctx = market.ScanContext()
        with patch.object(appmod, '_fetch_usd_rate', return_value=1.2) as fetch:
            with market.scope(ctx):
                self.assertEqual(appmod._usd_rate(db, 'EUR', '2026-09-20'), 1.2)
                self.assertFalse(db.in_transaction)
                # Represents a user's save while the scan later awaits a page.
                other = appmod.open_db_connection()
                other.execute("INSERT OR REPLACE INTO fx_rates VALUES('GBP','2026-09-20',1.3,'now')")
                other.commit(); other.close()
                self.assertEqual(appmod._usd_rate(db, 'EUR', '2026-09-20'), 1.2)
            self.assertEqual(fetch.call_count, 1)
        db.close()

    def test_preloaded_banknote_matching_uses_original_rules(self):
        db = appmod.open_db_connection()
        db.execute("INSERT OR REPLACE INTO banknotes(id,country,pick_number,denomination,date_1,cat_id) VALUES('match-fixture','Philippines','P-98a','20 Pesos',1944,'Btest')")
        db.commit()
        ctx = market.ScanContext()
        appmod._MARKET_POLICIES['banknotes'].prepare(db, ctx)
        queries = []; db.set_trace_callback(queries.append)
        with market.scope(ctx):
            item = dict(country='Philippines', pick_number='P-98a', denomination='20 Pesos', date_1=1944, series='')
            for _ in range(3):
                self.assertIn('same catalogue', appmod._market_owned_match(db, 'banknotes', item))
        self.assertFalse(any('FROM banknotes' in q for q in queries))
        db.close()

    def test_rejected_candidates_do_no_network(self):
        with patch.object(appmod, '_market_price_from_page') as fetch:
            self.assertIsNone(appmod._market_normalize_item(None, 'banknotes',
                dict(listing_url='https://dealer.example/raw', grade_numeric=30)))
            self.assertIsNone(appmod._market_normalize_item(None, 'coins',
                dict(listing_url='https://dealer.example/closed', closes='2000-01-01', theme='vcoins-catalogue', fills='Athens')))
            fetch.assert_not_called()

    def test_json_repair_never_repeats_discovery(self):
        calls = []
        def create(**kw):
            calls.append(kw)
            return types.SimpleNamespace(content=[types.SimpleNamespace(type='text', text='{"items": [], "notes": "none"}')])
        client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
        bad = types.SimpleNamespace(content=[types.SimpleNamespace(type='text', text='malformed output')])
        with market.scope(market.ScanContext()):
            self.assertEqual(appmod._market_model_json(client, 'model', bad, 'original')['items'], [])
        self.assertEqual(len(calls), 1)
        self.assertNotIn('tools', calls[0])
        self.assertEqual(calls[0]['max_tokens'], 5000)

    def test_repair_rate_limit_does_not_requeue_discovery(self):
        with market.scope(market.ScanContext()), patch.object(appmod, '_market_call_theme_once',
                return_value=([], 'theme: JSON repair failed: rate limit exceeded')) as call:
            items, error = appmod._market_call_theme('key', 'coins', 'theme', 'prompt')
        self.assertEqual(call.call_count, 1)
        self.assertEqual(items, [])
        self.assertIn('JSON repair', error)

    def test_model_selection_shared_by_sources(self):
        from concurrent.futures import ThreadPoolExecutor
        ctx = market.ScanContext()
        with patch.object(appmod, 'anthropic_lookup_model', return_value='selected') as lookup:
            with market.scope(ctx), ThreadPoolExecutor(max_workers=3) as pool:
                futures = [market.submit(pool, appmod._market_resolve_model, 'test') for _ in range(3)]
                self.assertEqual([f.result() for f in futures], ['selected'] * 3)
            self.assertEqual(lookup.call_count, 1)

    def test_metadata_archive_skips_lot_description_requests(self):
        lot = dict(id=1, title='Auction 1', description='Athens tetradrachm 17.20 g', sort_date='2025-01-01', date_text='2025', url='https://archive/1')
        with patch.object(appmod, '_acsearch_search', return_value=(200, [lot])), \
             patch.object(appmod, '_acsearch_lot_text', side_effect=AssertionError('unnecessary full lot fetch')):
            result = appmod._provenance_archive_sweep('coins', dict(region='Athens', denomination='Tetradrachm', weight=17.20), metadata_only=True, max_images=0)
        self.assertEqual(len(result['candidates']), 1)

    def test_real_pipeline_publishes_before_slow_theme_and_keeps_action(self):
        slow = threading.Event(); entered = threading.Event()
        themes = [('fast', 'fast'), ('slow', 'slow')]
        raw = dict(country='Philippines', pick_number='P-98a', title='Philippines 20 Pesos',
                   denomination='20 Pesos', year=1944, grade_numeric=65, grade='PMG 65',
                   grading_authority='PMG', price='$100', listing_url='https://dealer.example/early')
        def source(api_key, category, key, prompt):
            if key == 'slow':
                entered.set(); slow.wait(3)
                return [], 'simulated source failure'
            return [dict(raw, theme=key)], None
        repo = start('banknotes')
        appmod._MARKET_SCAN_INFLIGHT.add('banknotes')
        thread = None
        with patch.object(appmod._MARKET_POLICIES['banknotes'], 'themes', return_value=themes), \
             patch.object(appmod, '_market_call_theme', side_effect=source), \
             patch.object(appmod, '_market_transport', side_effect=lambda url, limit, timeout: market.PageResult(200, '<html>Add to cart</html>', url)):
            try:
                thread = threading.Thread(target=appmod._run_market_scan, args=('banknotes', repo.scan_id))
                thread.start(); self.assertTrue(entered.wait(1))
                deadline = time.monotonic() + 2
                while not self.rows() and time.monotonic() < deadline:
                    time.sleep(.01)
                rows = self.rows(); self.assertEqual(len(rows), 1)
                self.assertTrue(thread.is_alive())
                client = appmod.app.test_client()
                status = client.get('/banknotes/market/status').get_json()
                self.assertEqual(status['status'], 'running')
                self.assertGreater(status['revision'], 0)
                self.assertEqual(status['item_count'], 1)
                html = client.get('/banknotes/market').get_data(as_text=True)
                self.assertIn('Philippines 20 Pesos', html)
                self.assertIn('marketResults', html)
                client.post('/banknotes/market/' + rows[0]['id'] + '/dismiss')
            finally:
                slow.set()
                if thread: thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(self.rows()[0]['status'], 'dismissed')


if __name__ == '__main__':
    unittest.main()
