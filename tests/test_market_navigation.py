"""Collection selections survive Market Scan navigation without shared tab state."""
from datetime import datetime
from html.parser import HTMLParser
import itertools
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from urllib.parse import parse_qs, urlencode, urlsplit

from flask import template_rendered

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-market-navigation-')
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff


class Links(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            self.current = dict(attrs, text='')
            self.links.append(self.current)

    def handle_endtag(self, tag):
        if tag == 'a':
            self.current = None

    def handle_data(self, value):
        if self.current is not None:
            self.current['text'] += value

    def href(self, label):
        return next(link['href'] for link in self.links if link['text'].strip() == label)


def query(url):
    return parse_qs(urlsplit(url).query, keep_blank_values=True)


class MarketNavigationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = stuff.app.app_context()
        cls.context.push()
        cls.db = stuff.get_db()
        cls.client = stuff.app.test_client()
        now = datetime.utcnow().isoformat()
        for category in ('coins', 'banknotes'):
            cls.db.execute('INSERT INTO market_scans(id,category,status,started_at,finished_at) VALUES (?,?,?,?,?)',
                           ('navigation-' + category, category, 'done', now, now))
            payload = dict(title='Unfiltered market candidate', country='United States of America',
                           region='Attica', pick_number='Fr.35', date_1=1880, verified=True,
                           listing_url='https://example.test/navigation-candidate-' + category)
            cls.db.execute('INSERT INTO market_scan_items(id,scan_id,category,status,payload,created_at) VALUES (?,?,?,?,?,?)',
                           ('navigation-candidate-' + category, 'navigation-' + category, category,
                            'new', json.dumps(payload), now))
            for number, status in enumerate(('Own', 'Ordered', 'Shipped', 'Delivered', 'Sold')):
                ident = category + '-navigation-' + str(number)
                if category == 'coins':
                    cls.db.execute('INSERT INTO coins(id,coin_id,denomination,status,property_name,date_1) VALUES (?,?,?,?,?,?)',
                                   (ident, ident, 'Fixture coin', status, 'Carp' if number % 2 else 'NYC', -100 if number % 2 else 1900))
                else:
                    cls.db.execute('INSERT INTO banknotes(id,banknote_id,country,denomination,status,date_1) VALUES (?,?,?,?,?,?)',
                                   (ident, ident, 'United States of America', 'Fixture $20', status, 1872))
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.context.pop()

    def page(self, path):
        contexts = []
        def rendered(sender, template, context, **kwargs):
            contexts.append(context)
        with template_rendered.connected_to(rendered, stuff.app):
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return Links(response.get_data(as_text=True)), contexts[-1]

    def assert_round_trip(self, category, params, expected_status):
        start = '/' + category + ('?' + urlencode(params) if params else '')
        links, before = self.page(start)
        self.assertEqual(before['status_current'], expected_status)
        if category == 'banknotes' and expected_status in ('own', 'ordered', 'shipped', 'delivered') and params.get('dot') != '1':
            self.assertTrue(before['rows'], params)
        market = links.href('Market Scan')
        self.assertEqual(urlsplit(market).path, '/' + category + '/market')
        self.assertEqual(query(market), {'collection_' + key: [value] for key, value in params.items()})
        links, market_context = self.page(market)
        self.assertEqual(market_context['q'], '')  # collection search does not filter market candidates
        self.assertEqual([row['id'] for row in market_context['rows']], ['navigation-candidate-' + category])
        self.assertFalse(market_context['market_autoscan'])
        earlier = links.href('Earlier candidates')
        links, _ = self.page(earlier)
        self.assertEqual(urlsplit(links.href('Collection')).path, '/' + category)
        self.assertEqual(query(links.href('Collection')), query(start))
        current = links.href('Current scan')
        self.assertEqual(current, market)
        links, _ = self.page(current)
        # Poll/Rescan refreshes this same URL, retaining this tab's context.
        refreshed, _ = self.page(current)
        self.assertEqual(refreshed.href('Collection'), links.href('Collection'))
        back = links.href('Collection')
        self.assertEqual(urlsplit(back).path, '/' + category)
        self.assertEqual(query(back), query(start))
        _, after = self.page(back)
        for key in ('status_current', 'coin_filter', 'q', 'show_history', 'dot', 'at_property',
                    'coin_home_current', 'coin_era_current'):
            self.assertEqual(after[key], before[key], (category, params, key))
        self.assertEqual([row['id'] for row in after['rows']], [row['id'] for row in before['rows']])

    def test_coins_preserve_all_status_home_and_era_combinations(self):
        for home, era, status in itertools.product((None, 'ca', 'ny'), (None, 'ancient', 'modern'), ('all', 'ordered', 'own')):
            scope = stuff._join_coin_filter(era, home, status)
            params = dict(q='Fixture')
            if scope:
                params['filter'] = scope
            with self.subTest(home=home, era=era, status=status):
                self.assert_round_trip('coins', params, status)

    def test_banknotes_preserve_lifecycle_statuses_and_explicit_all(self):
        for status in (None, '', 'all', 'ordered', 'shipped', 'delivered', 'own'):
            params = dict(q_banknotes='Fixture', history='0', dot='0')
            if status is not None:
                params['filter'] = status
            with self.subTest(status=status):
                self.assert_round_trip('banknotes', params, status or 'all')
        for scope in ('us', 'military', 'notgeld', 'heritage_british'):
            self.assert_round_trip('banknotes', dict(filter=scope, history='0'), 'all')

    def test_category_search_precedence_encoded_values_and_flagged_scope_survive(self):
        self.assert_round_trip('banknotes', dict(filter='own', q='Other & \"quoted\" / <tag>',
                                               q_banknotes='Fixture', history='0', dot='1'), 'own')
        self.assert_round_trip('coins', dict(filter='', q='Other & \"quoted\" / <tag>',
                                           q_coins='Fixture'), 'all')

    def test_separate_tabs_and_categories_do_not_change_each_others_context(self):
        starts = ('/coins?filter=ca_ancient_own', '/coins?filter=ny_modern_ordered',
                  '/banknotes?filter=delivered&history=0', '/banknotes?filter=own')
        market_urls = [self.page(start)[0].href('Market Scan') for start in starts]
        for start, market in reversed(list(zip(starts, market_urls))):
            self.assertEqual(self.page(market)[0].href('Collection'), start)
        for category in ('coins', 'banknotes'):
            for suffix in ('', '?earlier=1'):
                back = self.page('/' + category + '/market' + suffix)[0].href('Collection')
                self.assertEqual(back, '/' + category)
                self.assertEqual(self.page(back)[1]['status_current'], 'all')

    def test_context_only_contains_same_category_collection_query_fields(self):
        params = dict(collection_filter='ordered', collection_q='Fixture & "quoted" / <tag>',
                      collection_history='0', collection_dot='1', collection_at='New York',
                      collection_q_banknotes='other category', collection_category='banknotes',
                      collection_return_to='https://example.test/elsewhere', return_to='//example.test',
                      collection_earlier='1', collection_admin='1', filter='own')
        links, _ = self.page('/coins/market?' + urlencode(params))
        back = links.href('Collection')
        self.assertEqual(urlsplit(back).path, '/coins')
        self.assertFalse(urlsplit(back).scheme)
        self.assertFalse(urlsplit(back).netloc)
        self.assertEqual(query(back), {key: [params['collection_' + key]]
                                      for key in ('filter', 'q', 'history', 'dot', 'at')})
        earlier = links.href('Earlier candidates')
        self.assertEqual(query(earlier), dict(earlier=['1'], **{
            'collection_' + key: values for key, values in query(back).items()}))
        self.assertNotIn('example.test', back)

    def test_navigation_does_not_change_collection_statuses(self):
        before = {category: [tuple(row) for row in self.db.execute('SELECT id,status FROM ' + category + ' ORDER BY id')]
                  for category in ('coins', 'banknotes')}
        for category in ('coins', 'banknotes'):
            self.assert_round_trip(category, dict(filter='ordered'), 'ordered')
        after = {category: [tuple(row) for row in self.db.execute('SELECT id,status FROM ' + category + ' ORDER BY id')]
                 for category in ('coins', 'banknotes')}
        self.assertEqual(after, before)


if __name__ == '__main__':
    unittest.main()
