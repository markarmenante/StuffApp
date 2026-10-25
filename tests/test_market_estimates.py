"""Bounded estimate research, durable cache and source preservation; no network."""
import copy
import importlib
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import threading
import time
import types
import unittest
from datetime import date
from unittest.mock import patch, Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_estimates as estimates
import market_scan

SOURCE = 'https://currency.ha.com/itm/fixture/90001'


def item(number=0, **changes):
    out = dict(title='India 1937 10 Rupees P-18 PMG 64 EPQ', country='India',
               issuer='Government of India', date_1=1937, denomination='10 Rupees',
               pick_number='P-18', grade='PMG 64 EPQ', grade_numeric=64,
               price='$199.89', listing_url=f'https://www.ebay.com/itm/{123456789012 + number}')
    out.update(changes)
    return out


def researched(wanted, **changes):
    out = dict(key=wanted['key'], listing_url=wanted['listing_url'],
        _observed_source_urls=[SOURCE], valuation=dict(low=150, high=200, currency='USD',
        as_of=date.today().isoformat(), confidence='medium', grade='PMG 64 EPQ',
        sources=[dict(kind='sold', url=SOURCE, title='Synthetic comparable auction lot',
                      date='2026-04-12', amount=178.50, currency='USD', grade='PMG 64 EPQ')]))
    out.update(changes)
    return out


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='market-estimates-')
        self.path = str(Path(self.temp.name) / 'fixture.sqlite')
        self.db = self.connect()
        self.db.execute('CREATE TABLE market_dismissals(category TEXT,canonical_url TEXT,dismissed_at TEXT)')
        estimates.init_schema(self.db)

    def connect(self):
        db = sqlite3.connect(self.path); db.row_factory = sqlite3.Row
        return db

    def tearDown(self):
        self.db.close(); self.temp.cleanup()

    def test_batch_limit_join_negative_cooldown_and_next_unattempted(self):
        rows = [item(n) for n in range(17)]
        state, targets = estimates.claim(self.db, rows + [rows[0]])
        self.assertEqual((state['total'], state['remaining']), (12, 5))
        again, none = estimates.claim(self.db, rows)
        self.assertEqual(again['job_id'], state['job_id']); self.assertEqual(none, [])
        for index, wanted in enumerate(targets):
            estimates.store(self.db, state['job_id'], wanted,
                            researched(wanted) if index % 2 else researched(wanted, valuation=None))
        estimates.finish(self.db, state['job_id'])
        second, targets2 = estimates.claim(self.db, rows)
        self.assertEqual((second['total'], second['skipped'], second['remaining']), (5, 12, 0))
        self.assertEqual([r['listing_url'] for r in targets2], [market_scan.canonical_url(r['listing_url']) for r in rows[12:]])

    def test_identity_cache_survives_price_change_but_not_grade_change(self):
        original = item(discovery_sources=['watched']); before = copy.deepcopy(original)
        wanted = estimates.target(original)
        self.assertEqual(wanted['key'], estimates.target(dict(original, price='$299.89', sources=['sponsored']))['key'])
        self.assertNotEqual(wanted['key'], estimates.target(dict(original, grade_numeric=65))['key'])
        state, _ = estimates.claim(self.db, [original])
        raw = researched(wanted, _observed_listing_text=dict(url=wanted['listing_url'], text='Buy It Now'),
                         listing_basis=dict(url=wanted['listing_url'], sale_type='fixed', evidence='Buy It Now'))
        estimates.store(self.db, state['job_id'], wanted, raw)
        shown = estimates.overlay(self.db, original)
        self.assertEqual(shown['valuation']['low'], 150); self.assertEqual(shown['sale_type'], 'fixed')
        self.assertEqual(shown['price'], '$199.89'); self.assertEqual(original, before)
        changed = estimates.overlay(self.db, dict(original, price='$299.89'))
        self.assertIn('valuation', changed); self.assertNotIn('sale_type', changed)
        self.assertNotIn('valuation', estimates.overlay(self.db, dict(original, grade_numeric=65)))
        self.assertNotIn('sale_type', estimates.overlay(self.db, original, now=time.time() + 86401))

    def test_only_observed_source_urls_and_valid_source_arrays_can_support_estimates(self):
        wanted = estimates.target(item())
        self.assertIsNotNone(estimates.result(wanted, researched(wanted))[0])
        for seen in ([], ['https://currency.ha.com/itm/different/90002'], None):
            self.assertIsNone(estimates.result(wanted, researched(wanted, _observed_source_urls=seen))[0])
        for sources in (None, {}, 'fake', 2):
            raw = researched(wanted); raw['valuation']['sources'] = sources
            self.assertEqual(estimates.result(wanted, raw), (None, None))
        self.assertEqual(estimates.result(wanted, researched(wanted, key='other')), (None, None))
        self.assertEqual(estimates.result(wanted, researched(wanted, listing_url=[])), (None, None))

    def test_sale_type_needs_exact_listing_evidence_not_title_or_other_listing(self):
        wanted = estimates.target(item(title='Buy It Now banknote'))
        basis = dict(url=wanted['listing_url'], sale_type='fixed', evidence='Buy It Now')
        raw = researched(wanted, listing_basis=basis)
        self.assertIsNone(estimates.result(wanted, raw)[1])
        raw['_observed_source_urls'].append(item(1)['listing_url'])
        self.assertIsNone(estimates.result(wanted, raw)[1])
        raw['_observed_source_urls'].append(wanted['listing_url'])
        self.assertIsNone(estimates.result(wanted, raw)[1], 'search URL alone is not exact-page proof')
        fresh = dict(wanted, live_state='live', listing_checked_at=time.time(), listing_text='Exact note. Buy It Now')
        self.assertEqual(estimates.result(fresh, raw)[1]['sale_type'], 'fixed')
        for updates in (dict(live_state='unknown'), dict(listing_checked_at=time.time()-601),
                        dict(listing_text='This was an active listing')):
            self.assertIsNone(estimates.result(dict(fresh, **updates), raw)[1])

    def test_dismissal_mid_job_cannot_publish_or_resurrect(self):
        original = item(); state, targets = estimates.claim(self.db, [original])
        self.db.execute('INSERT INTO market_dismissals VALUES(?,?,?)', ('banknotes', targets[0]['listing_url'], 'now'))
        self.db.commit()
        estimates.store(self.db, state['job_id'], targets[0], researched(targets[0]))
        self.assertEqual(self.db.execute('SELECT count(*) FROM market_estimate_cache').fetchone()[0], 0)
        self.assertEqual(estimates.status(self.db)['estimated'], 0)
        self.assertEqual(estimates.overlay(self.db, original), original)

    def test_removed_or_changed_target_and_late_response_cannot_publish(self):
        state, targets = estimates.claim(self.db, [item()])
        estimates.store(self.db, state['job_id'], targets[0], researched(targets[0]), eligible=False)
        self.assertEqual(self.db.execute('SELECT count(*) FROM market_estimate_cache').fetchone()[0], 0)
        estimates.finish(self.db, state['job_id'])
        self.assertFalse(estimates.store(self.db, state['job_id'], targets[0], researched(targets[0])))

    def test_eligibility_rechecked_inside_publication_lock_and_retry_order_is_oldest_first(self):
        now = time.time()
        rows = [item(n) for n in range(14)]
        state, targets = estimates.claim(self.db, rows, now=now)
        checked = []
        def eligibility(db, wanted):
            checked.append(db.in_transaction)
            return False
        estimates.store(self.db, state['job_id'], targets[0], researched(targets[0]), eligible=eligibility, now=now)
        self.assertEqual(checked, [True])
        for wanted in targets[1:]:
            estimates.store(self.db, state['job_id'], wanted, researched(wanted, valuation=None), now=now)
        estimates.finish(self.db, state['job_id'], now=now)
        second, remaining = estimates.claim(self.db, rows, now=now+1)
        for wanted in remaining:
            estimates.store(self.db, second['job_id'], wanted, researched(wanted, valuation=None), now=now+1)
        estimates.finish(self.db, second['job_id'], now=now+1)
        # Simulate the first twelve having been retried more recently. A later
        # daily click must prioritize the two older tail attempts.
        self.db.execute('UPDATE market_estimate_cache SET checked_at=?,retry_after=?', (now+100, now-1))
        for row in rows[12:]:
            self.db.execute('UPDATE market_estimate_cache SET checked_at=? WHERE cache_key=?',
                            (now, estimates.target(row)['key']))
        self.db.commit()
        _, again = estimates.claim(self.db, rows, now=now+101)
        self.assertEqual([r['key'] for r in again[:2]], [estimates.target(r)['key'] for r in rows[12:]])

    def test_deadline_leaves_unattempted_items_uncached_and_available_next_batch(self):
        state, targets = estimates.claim(self.db, [item(n) for n in range(4)])
        context = market_scan.ScanContext(seconds=0)
        call = Mock(side_effect=AssertionError('deadline should prevent research'))
        estimates.run(self.connect, state['job_id'], targets, call, lambda *_: True, context)
        call.assert_not_called()
        done = estimates.status(self.db)
        self.assertEqual((done['status'], done['completed'], done['remaining']), ('failed', 0, 4))
        self.assertEqual(self.db.execute('SELECT count(*) FROM market_estimate_cache').fetchone()[0], 0)
        self.assertEqual(len(estimates.claim(self.db, [item(n) for n in range(4)])[1]), 4)

    def test_two_workers_bound_progress_and_provider_failures_cool_down(self):
        state, targets = estimates.claim(self.db, [item(n) for n in range(5)])
        lock = threading.Lock(); counts = dict(active=0, high=0)
        def research(wanted, context):
            with lock:
                counts['active'] += 1; counts['high'] = max(counts['high'], counts['active'])
            try:
                time.sleep(.01)
                if wanted == targets[0]:
                    raise RuntimeError('synthetic provider unavailable')
                return researched(wanted)
            finally:
                with lock: counts['active'] -= 1
        estimates.run(self.connect, state['job_id'], targets, research, lambda *_: True,
                      market_scan.ScanContext(seconds=5))
        done = estimates.status(self.db)
        self.assertEqual((done['status'], done['completed'], done['estimated'], done['unavailable']), ('failed', 5, 4, 1))
        self.assertIn('could not complete', done['error'])
        self.assertLessEqual(counts['high'], 2)
        self.assertEqual(estimates.claim(self.db, [item(n) for n in range(5)])[1], [])


class AppTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='market-estimates-app-')
        with patch.dict(os.environ, DATA_DIR=cls.temp.name, ANTHROPIC_API_KEY=''), \
                patch.dict(sys.modules, dotenv=types.SimpleNamespace(load_dotenv=lambda **_: None)), \
                patch.object(threading.Thread, 'start', lambda *_: None):
            cls.stuff = importlib.import_module('app')
        cls.stuff.app.config['TESTING'] = True

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def setUp(self):
        self.ctx = self.stuff.app.app_context(); self.ctx.push()
        self.db = self.stuff.get_db(); self.client = self.stuff.app.test_client()
        self.db.execute('DELETE FROM market_estimate_cache'); self.db.execute('DELETE FROM market_estimate_jobs'); self.db.commit()
        self.stuff._MARKET_ESTIMATE_ACTIVE.clear()

    def tearDown(self):
        self.ctx.pop()

    def test_init_db_creates_cache_for_existing_database_and_status_get_is_read_only(self):
        self.db.execute('DROP TABLE market_estimate_cache'); self.db.execute('DROP TABLE market_estimate_jobs'); self.db.commit()
        self.stuff.init_db()
        self.db.execute('PRAGMA query_only=ON')
        try:
            with patch.object(self.stuff, '_market_estimate_research', side_effect=AssertionError('GET cannot research')):
                response = self.client.get('/banknotes/market/estimates/status')
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json['status'], 'none')
                self.assertIn('no-store', response.headers['Cache-Control'])
                self.assertEqual(estimates.overlay(self.db, item()), item())
        finally:
            self.db.execute('PRAGMA query_only=OFF')

    def test_owner_only_and_missing_provider_return_without_starting(self):
        with patch.object(self.stuff, 'g', dict(current_user=dict(role='viewer'))):
            for route in (self.stuff.market_estimates_status, self.stuff.market_estimates_start):
                with self.assertRaises(Exception) as caught: route()
                self.assertEqual(caught.exception.code, 403)
        with patch.dict(os.environ, ANTHROPIC_API_KEY=''):
            response = self.client.post('/banknotes/market/estimates')
            self.assertEqual(response.status_code, 503); self.assertFalse(response.json['ok'])
        self.assertEqual(estimates.status(self.db)['status'], 'none')

    def test_post_bounds_both_sources_and_duplicate_click_joins(self):
        with patch.dict(os.environ, ANTHROPIC_API_KEY='synthetic'), \
                patch.object(self.stuff, '_market_estimate_rows', return_value=[item(n) for n in range(17)]), \
                patch.object(threading.Thread, 'start') as start:
            first = self.client.post('/banknotes/market/estimates').json
            second = self.client.post('/banknotes/market/estimates').json
            self.assertEqual((first['status'], first['total'], first['remaining']), ('running', 12, 5))
            self.assertEqual(first['job_id'], second['job_id']); self.assertEqual(start.call_count, 1)
            self.assertEqual(self.client.get('/banknotes/market/estimates/status').json['status'], 'running')

    def test_adapter_overwrites_fabricated_urls_with_structured_tool_results(self):
        wanted = estimates.target(item())
        raw = researched(wanted, _observed_source_urls=['https://fake.example/lot/1'])
        raw['valuation']['sources'][0]['url'] = 'https://fake.example/lot/1'
        response = types.SimpleNamespace(stop_reason='end_turn', content=[
            types.SimpleNamespace(type='text', text=json.dumps(raw)),
            {'type':'web_search_tool_result', 'content':[{'type':'web_search_result','url':SOURCE}]}])
        fake = Mock(); fake.close = Mock()
        context = market_scan.ScanContext(seconds=5, max_requests=1, max_searches=6)
        with patch.dict(os.environ, ANTHROPIC_API_KEY='synthetic'), \
                patch.dict(sys.modules, anthropic=types.SimpleNamespace(Anthropic=Mock(return_value=fake))), \
                patch.object(self.stuff, '_market_resolve_model', return_value='synthetic-model'), \
                patch.object(self.stuff.market_runtime, 'model_call', return_value=response) as call:
            got = self.stuff._market_estimate_research(wanted, context)
            self.assertEqual(got['_observed_source_urls'], [SOURCE])
            self.assertIsNone(estimates.result(wanted, got)[0])
            self.assertEqual(call.call_count, 1)
            self.assertEqual(call.call_args.kwargs['tools'][0]['max_uses'], 6)
            fake.close.assert_called_once()

    def test_exact_page_proof_requires_same_identity_nonchallenge_and_visible_literal_text(self):
        wanted = estimates.target(item())
        raw = researched(wanted, listing_basis=dict(url=wanted['listing_url'], sale_type='fixed', evidence='Buy It Now'),
                         _observed_listing_text=dict(url=wanted['listing_url'], text='Buy It Now'))
        response = types.SimpleNamespace(stop_reason='end_turn', content=[types.SimpleNamespace(type='text', text=json.dumps(raw))])
        context = market_scan.ScanContext(seconds=5)
        context.fetcher = Mock()
        cases = [(200, '<button>Buy It Now</button>', wanted['listing_url'], False, True),
                 (200, '<button>Buy It Now</button>', item(1)['listing_url'], False, False),
                 (200, '<button>Buy It Now</button>', wanted['listing_url'], True, False),
                 (403, '<button>Buy It Now</button>', wanted['listing_url'], False, False),
                 (200, '<p>This listing has ended.</p><h2>Similar items</h2><button>Buy It Now</button>', wanted['listing_url'], False, False),
                 (200, '<h1>India note</h1><h2>Similar items</h2><button>Buy It Now</button>', wanted['listing_url'], False, False),
                 (200, '<script>Buy It Now</script><p>Unknown</p>', wanted['listing_url'], False, False)]
        with patch.dict(os.environ, ANTHROPIC_API_KEY='synthetic'), \
                patch.dict(sys.modules, anthropic=types.SimpleNamespace(Anthropic=Mock(return_value=Mock()))), \
                patch.object(self.stuff, '_market_resolve_model', return_value='synthetic-model'), \
                patch.object(self.stuff.market_runtime, 'model_call', return_value=response):
            for status, text, final, challenged, expected in cases:
                context.fetcher.fetch.reset_mock()
                context.fetcher.fetch.return_value = market_scan.PageResult(status, text, final, challenged)
                got = self.stuff._market_estimate_research(wanted, context)
                self.assertEqual(bool(estimates.result(wanted, got)[1]), expected)
                context.fetcher.fetch.assert_called_once_with(wanted['listing_url'])

    def test_actual_candidate_and_watched_overlay_preserve_source_rows_and_actions(self):
        stuff = self.stuff
        candidate = item(verified=True, sale_type='fixed')
        observed = item(1)
        now = time.time()
        self.db.execute("INSERT INTO market_scans(id,category,started_at,status) VALUES('fixture','banknotes','2026-10-25','done')")
        self.db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,created_at,payload,title,listing_url,price) VALUES('candidate','fixture','banknotes','new','2026-10-25',?,?,?,?)",
                        (json.dumps(candidate), candidate['title'], candidate['listing_url'], candidate['price']))
        self.db.execute("INSERT INTO ebay_market_requests(id,requested_at,expires_at,status,observed_at) VALUES('feed',?,?,'done',?)", (now, now+600, now))
        self.db.execute("INSERT INTO ebay_market_cards VALUES('feed','123456789013',?,?,?,?,?,?,?,?)",
                        (observed['title'], observed['listing_url'], observed['price'], '', 'Watched', 'Buy It Now', 'live', now))
        self.db.execute("INSERT INTO ebay_market_card_sources VALUES('feed','123456789013','watched')")
        self.db.commit()
        snapshot = lambda: ([tuple(r) for r in self.db.execute('SELECT * FROM market_scan_items')],
                            [tuple(r) for r in self.db.execute('SELECT * FROM ebay_market_cards')])
        with patch.object(stuff.market_ebay_feed, 'enabled', return_value=True):
            rows = stuff._market_estimate_rows(self.db)
            before = snapshot()
            state, targets = estimates.claim(self.db, rows)
            self.assertEqual(len(targets), 2)
            for wanted in targets:
                estimates.store(self.db, state['job_id'], wanted, researched(wanted), eligible=stuff._market_estimate_eligible)
            self.db.execute('PRAGMA query_only=ON')
            try:
                after = stuff._market_estimate_rows(self.db)
                self.assertTrue(all(row['valuation']['low'] == 150 for row in after))
                self.assertEqual(after[0]['id'], 'candidate')
                self.assertEqual(after[1]['item_id'], '123456789013')
                self.assertEqual(after[1]['sources'], ['watched'])
                self.assertEqual([r['price'] for r in after], ['$199.89', '$199.89'])
            finally:
                self.db.execute('PRAGMA query_only=OFF')
            self.assertEqual(snapshot(), before)


if __name__ == '__main__':
    unittest.main()
