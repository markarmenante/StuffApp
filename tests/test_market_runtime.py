"""Deterministic concurrency and request-budget contracts; no network or model."""
import os
import sys
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import market_scan as market


class RuntimeTests(unittest.TestCase):
    def test_progressive_delivery_precedes_slow_source(self):
        ctx = market.ScanContext(seconds=2, discovery_seconds=1)
        slow_done = threading.Event()
        observed = []
        def slow():
            time.sleep(.25)
            slow_done.set()
            return [{'id': 'slow'}], None, ''
        def publish(items):
            observed.append((items[0]['id'], slow_done.is_set()))
        errors, raw = market.ScanService(ctx).run([
            market.Source('fast', lambda: ([{'id': 'fast'}], None, '')),
            market.Source('slow', slow)], lambda x: x, publish, lambda *a: None)
        self.assertEqual(errors, [])
        self.assertEqual(raw, 2)
        self.assertEqual(observed, [('fast', False), ('slow', True)])
        self.assertEqual(ctx.metrics['fast']['retained'], 1)

    def test_retry_releases_worker(self):
        ctx = market.ScanContext(seconds=2, discovery_seconds=1)
        sequence = []
        def retry():
            sequence.append('retry')
            if sequence.count('retry') == 1:
                raise market.RetryLater('429', delay=.05)
            return [], None, ''
        def other():
            sequence.append('other')
            return [], None, ''
        market.ScanService(ctx, workers=1).run([market.Source('retry', retry), market.Source('other', other)],
                                              lambda x: x, lambda x: None, lambda *a: None)
        self.assertEqual(sequence, ['retry', 'other', 'retry'])
        self.assertEqual(ctx.metrics['retry']['retries'], 1)

    def test_deadline_cancels_queue_and_ignores_late_results(self):
        ctx = market.ScanContext(seconds=1, discovery_seconds=.03)
        calls, published = [], []
        released = threading.Event()
        def slow():
            calls.append('slow')
            released.wait(.8)
            return [{'id': 'late'}], None, ''
        def queued():
            calls.append('queued')
            return [], None, ''
        try:
            started = time.monotonic()
            errors, _ = market.ScanService(ctx, workers=1).run([
                market.Source('slow', slow), market.Source('queued', queued)],
                lambda x: x, published.extend, lambda *a: None)
            self.assertLess(time.monotonic() - started, .6)
            self.assertEqual(calls, ['slow'])
            self.assertEqual(published, [])
            self.assertEqual(len(errors), 2)
        finally:
            released.set()

    def test_output_search_and_request_budgets_before_transmission(self):
        ctx = market.ScanContext(max_requests=2, max_searches=10, max_output_tokens=150)
        calls = []
        def create(**kw):
            calls.append(kw)
            return SimpleNamespace(usage=SimpleNamespace(input_tokens=20, output_tokens=30))
        client = SimpleNamespace(messages=SimpleNamespace(create=create))
        with market.scope(ctx, 'test'):
            market.model_call(client, max_tokens=100, tools=[{'max_uses': 5}], messages=[])
            with self.assertRaises(market.ScanStopped):
                market.model_call(client, max_tokens=100, tools=[{'max_uses': 5}], messages=[])
        self.assertEqual(len(calls), 1)
        self.assertEqual(ctx.totals['requests'], 1)
        self.assertEqual(ctx.metrics['test']['input_tokens'], 20)
        self.assertLessEqual(calls[0]['timeout'], 240)

    def test_page_singleflight_identity_and_cache_expiry(self):
        ctx = market.ScanContext()
        now = [0.0]
        calls = []
        def transport(url, limit, timeout):
            calls.append(url)
            time.sleep(.02)
            return market.PageResult(200, 'Add to cart', url)
        fetcher = market.FetchService(ctx, transport, clock=lambda: now[0], ttl=5, pace=0)
        url = 'https://www.cngcoins.com/Coin.aspx?CoinID=123'
        with ThreadPoolExecutor(max_workers=6) as pool:
            pages = list(pool.map(lambda _: fetcher.fetch(url + '&utm_source=x'), range(6)))
        self.assertEqual(len(calls), 1)
        self.assertTrue(all(p.text == 'Add to cart' for p in pages))
        fetcher.fetch(url.replace('123', '124'))
        self.assertEqual(len(calls), 2)
        now[0] = 6
        fetcher.fetch(url)
        self.assertEqual(len(calls), 3)
        # Independent scan/owner never inherits another scan's cache.
        market.FetchService(market.ScanContext(), transport, pace=0).fetch(url)
        self.assertEqual(len(calls), 4)

    def test_challenge_cooldown_and_page_budget(self):
        ctx = market.ScanContext(max_page_requests=1)
        calls = []
        def transport(url, limit, timeout):
            calls.append(url)
            return market.PageResult(403, 'captcha', url, True)
        fetcher = market.FetchService(ctx, transport, pace=0)
        fetcher.fetch('https://dealer.example/a')
        self.assertTrue(fetcher.fetch('https://dealer.example/b').challenged)
        self.assertEqual(len(calls), 1)
        with self.assertRaises(market.ScanStopped):
            fetcher.fetch('https://another.example/a')
        self.assertEqual(len(calls), 1)

    def test_discovery_scope_prevents_late_http_requests(self):
        ctx = market.ScanContext(seconds=10, discovery_seconds=.01)
        calls = []
        fetcher = market.FetchService(ctx, lambda *a: calls.append(a), pace=0)
        time.sleep(.02)
        with market.scope(ctx, 'late-source', discovery=True):
            with self.assertRaises(market.ScanStopped):
                fetcher.fetch('https://dealer.example/a')
        self.assertEqual(calls, [])

    def test_cache_memory_is_bounded(self):
        ctx = market.ScanContext()
        fetcher = market.FetchService(ctx, lambda url, *a: market.PageResult(200, 'x' * 100, url),
                                      pace=0, max_cache_bytes=160)
        fetcher.fetch('https://dealer.example/a')
        fetcher.fetch('https://dealer.example/b')
        self.assertLessEqual(fetcher.cache_bytes, 160)
        self.assertEqual(len(fetcher.cache), 1)

    def test_catalogue_gets_capacity_before_second_theme(self):
        ctx = market.ScanContext(seconds=2, discovery_seconds=1)
        order = []
        def source(name):
            def run():
                order.append(name)
                if name == 'catalogue': time.sleep(.02)
                return [], None, ''
            return run
        market.ScanService(ctx).run([
            market.Source('first', source('first')), market.Source('second', source('second')),
            market.CatalogueSource('catalogue', source('catalogue'))], lambda x: x, lambda x: None, lambda *a: None)
        self.assertLess(order.index('catalogue'), order.index('second'))

    def test_canonical_url_preserves_listing_identity(self):
        self.assertEqual(market.canonical_url('https://www.ebay.co.uk/itm/title/123456?mkcid=1'),
                         market.canonical_url('https://ebay.com/itm/123456'))
        self.assertNotEqual(market.canonical_url('https://cngcoins.com/Coin.aspx?CoinID=1'),
                            market.canonical_url('https://cngcoins.com/Coin.aspx?CoinID=2'))
        self.assertEqual(market.canonical_url('https://dealer.test/item?sku=3&utm_medium=email#photos'),
                         'https://dealer.test/item?sku=3')


if __name__ == '__main__':
    unittest.main()
