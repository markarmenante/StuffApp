"""Coin Home, Era and Status selections stay independent across list consumers."""
from html.parser import HTMLParser
import itertools
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

REPO = Path(__file__).resolve().parents[1]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-coin-axes-')
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff


class ToolbarLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = {}
        self.current = None
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'a' and attrs.get('id') in ('coinHomeFilter', 'coinEraFilter', 'coinStatusFilter'):
            self.current = attrs['id']
            self.links[self.current] = dict(attrs, text='')

    def handle_endtag(self, tag):
        if tag == 'a':
            self.current = None

    def handle_data(self, data):
        if self.current:
            self.links[self.current]['text'] += data


class CoinFilterAxesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = stuff.app.app_context()
        cls.context.push()
        cls.db = stuff.get_db()
        cls.fixtures = []
        for number, (home, year, status) in enumerate(itertools.product(
                ('Carp', 'Carpinteria', 'NYC', 'Elsewhere'),
                (-100, 1000, None),
                ('Own', 'Owned', '', None, 'Ordered', 'Shipped', 'Delivered', 'Sold'))):
            ident = 'coin-axis-' + str(number)
            cls.fixtures.append((ident, home, year, status))
            cls.db.execute('INSERT INTO coins (id,coin_id,denomination,property_name,date_1,status) '
                           'VALUES (?,?,?,?,?,?)',
                           (ident, 'C' + str(number), 'Fixture', home, year, status))
        cls.db.commit()
        cls.client = stuff.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.context.pop()

    def expected(self, home=None, era=None, status=None):
        return {ident for ident, property_name, year, raw_status in self.fixtures
                if (home is None or (home == 'ca' and property_name in ('Carp', 'Carpinteria'))
                    or (home == 'ny' and property_name == 'NYC'))
                and (era is None or (era == 'ancient' and year is not None and year < 500)
                     or (era == 'modern' and year is not None and year >= 500))
                and (status in (None, 'all')
                     or (status == 'own' and raw_status in ('Own', 'Owned', '', None))
                     or (status == 'ordered' and raw_status == 'Ordered'))}

    def route_context(self, path):
        with patch.object(stuff, 'render_template', return_value='fixture') as rendered:
            response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return rendered.call_args.kwargs

    def test_every_axis_combination_selects_exact_records(self):
        for home, era, status in itertools.product(
                (None, 'ca', 'ny'), (None, 'ancient', 'modern'), ('all', 'ordered', 'own')):
            key = stuff._join_coin_filter(era, home, status)
            with self.subTest(filter=key), stuff.app.test_request_context('/coins'):
                sql, params = stuff.build_search_query('coins', '', coin_filter=key)
                actual = {row['id'] for row in self.db.execute(sql, params)}
                self.assertEqual(actual, self.expected(home, era, status))

    def test_cycles_preserve_the_other_two_axes(self):
        for home, era, status in itertools.product(
                (None, 'ca', 'ny'), (None, 'ancient', 'modern'), ('all', 'ordered', 'own')):
            key = stuff._join_coin_filter(era, home, status)
            context = self.route_context('/coins' + ('?filter=' + key if key else ''))
            with self.subTest(filter=key):
                self.assertEqual(context['status_cycle'], ['all', 'ordered', 'own'])
                self.assertEqual(context['status_current'], status)
                self.assertEqual(context['coin_home_current'], home)
                self.assertEqual(context['coin_era_current'], era)
                for field, expected_home, expected_era, expected_status in (
                    ('coin_home_next_filter', {None:'ca', 'ca':'ny', 'ny':None}[home], era, status),
                    ('coin_era_next_filter', home, {None:'ancient', 'ancient':'modern', 'modern':None}[era], status),
                    ('coin_status_next_filter', home, era, {'all':'ordered', 'ordered':'own', 'own':'all'}[status]),
                ):
                    next_key = context[field]
                    sql, params = stuff.build_search_query('coins', '', coin_filter=next_key)
                    actual = {row['id'] for row in self.db.execute(sql, params)}
                    self.assertEqual(actual, self.expected(expected_home, expected_era, expected_status))

    def test_rendered_controls_preserve_search_and_other_axes(self):
        for home, era, status in itertools.product(
                (None, 'ca', 'ny'), (None, 'ancient', 'modern'), ('all', 'ordered', 'own')):
            key = stuff._join_coin_filter(era, home, status)
            response = self.client.get('/coins', query_string={'filter': key or '', 'q': 'Fixture'})
            self.assertEqual(response.status_code, 200)
            links = ToolbarLinks(response.get_data(as_text=True)).links
            for ident, label, new_home, new_era, new_status in (
                ('coinHomeFilter', 'Home: ' + (home.upper() if home else 'All'),
                 {None:'ca', 'ca':'ny', 'ny':None}[home], era, status),
                ('coinEraFilter', 'Era: ' + (era.title() if era else 'All'),
                 home, {None:'ancient', 'ancient':'modern', 'modern':None}[era], status),
                ('coinStatusFilter', 'Status: ' + ('Owned' if status == 'own' else status.title()),
                 home, era, {'all':'ordered', 'ordered':'own', 'own':'all'}[status]),
            ):
                with self.subTest(filter=key, control=ident):
                    link = links[ident]
                    self.assertEqual(link['text'], label)
                    self.assertIn('active', link['class'].split())
                    query = parse_qs(urlsplit(link['href']).query)
                    self.assertEqual(query['q'], ['Fixture'])
                    self.assertEqual(query.get('filter', [None])[0],
                                     stuff._join_coin_filter(new_era, new_home, new_status))

    def test_legacy_keys_and_owned_aliases_remain_valid(self):
        for key in ('ca_ancient', 'ny_modern', 'ancient', 'modern', 'ca', 'ny', 'own', 'ordered'):
            self.assertIn(key, stuff.CATEGORY_FILTERS['coins'])
        self.assertEqual(stuff._coin_filter_label('ca_ancient_own'), 'CA Ancient Owned')
        self.assertEqual(stuff._coin_filter_label('ordered'), 'Ordered')
        self.assertEqual(stuff._join_coin_filter('ancient', 'ca'), 'ca_ancient')

    def test_old_status_only_bookmarks_show_all_without_hidden_restrictions(self):
        for legacy_status in ('shipped', 'delivered', 'sold', 'loaned', 'gifted', 'consigned', 'lost'):
            context = self.route_context('/coins?filter=' + legacy_status)
            self.assertIsNone(context['coin_filter'])
            self.assertEqual(context['status_current'], 'all')
            self.assertEqual({row['id'] for row in context['rows']}, self.expected())

    def test_detail_navigation_keeps_the_combined_scope(self):
        sql, params = stuff.build_search_query('coins', '', coin_filter='ca_ancient_own')
        ids = [row['id'] for row in self.db.execute(sql, params)]
        context = self.route_context('/coins/' + ids[1] + '?filter=ca_ancient_own')
        self.assertEqual(context['prev_id'], ids[0])
        self.assertEqual(context['next_id'], ids[2])
        self.assertEqual(parse_qs(urlsplit(context['back_href']).query)['filter'], ['ca_ancient_own'])

    def test_map_and_cards_use_the_same_combined_scope(self):
        expected = self.expected('ca', 'ancient', 'own')
        context = self.route_context('/coins/map?filter=ca_ancient_own')
        self.assertEqual({row['id'] for row in context['coins']}, expected)
        self.assertEqual(context['filter_label'], 'CA Ancient Owned')
        printed = []
        with patch.object(stuff, '_recompute_coin_bins', side_effect=lambda db, rows, total: (rows, 0)), \
                patch.object(stuff, '_draw_coin_card', side_effect=lambda canvas, coin, *args: printed.append(coin['id'])):
            response = self.client.get('/coins/print-pdf?filter=ca_ancient_own')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, 'application/pdf')
        self.assertEqual(set(printed), expected)

    def test_other_category_cycles_remain_unchanged(self):
        for category, expected in (
            ('cameras', ['all', 'ordered', 'shipped', 'delivered', 'own']),
            ('art', ['own', 'ordered', 'shipped', 'delivered', 'all']),
            ('watches', ['all', 'own', 'ordered']),
        ):
            self.assertEqual(self.route_context('/' + category)['status_cycle'], expected)


if __name__ == '__main__':
    unittest.main()
