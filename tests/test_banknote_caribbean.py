"""Regional filing keeps authority, territory, catalogue variety and saved facts."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-caribbean-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import banknote_catalog as catalog
import app as stuff


class CaribbeanTests(unittest.TestCase):
    def setUp(self):
        self.context = stuff.app.app_context()
        self.context.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknotes')
        self.db.commit()

    def tearDown(self):
        self.context.pop()

    def add(self, ident, country, issuer, denom, pick, year=1965, series=None, municipality=None):
        self.db.execute('''INSERT INTO banknotes
            (id,country,issuer,denomination,pick_number,date_1,series,municipality,status,
             cat_id,price,image_1,image_2,serial_number,slab_number,notes)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
            (ident, country, issuer, denom, pick, year, series, municipality, 'Ordered',
             'B' + ident, '$599.89', 'front.jpg', 'reverse.jpg', 'G123456', '777777-001', 'Preserve me'))
        self.db.commit()

    def rows(self):
        return self.db.execute('SELECT * FROM banknotes ORDER BY ' + stuff.CATEGORY_ORDER_BY['banknotes']).fetchall()

    def fixture(self):
        self.add('authority20', 'East Caribbean States', 'East Caribbean Currency Authority', '20 Dollars', 'P-15j')
        self.add('board10', 'British Caribbean Territories', 'British Caribbean Territories Currency Board', '10 Dollars', 'P-9c', 1964, '1953-1964 Currency Board issue')
        self.add('grenada5', 'East Caribbean States - Grenada', 'East Caribbean Currency Authority', 'Five Dollars', 'P-14h', municipality='Grenada')
        self.add('authority1', None, 'East Caribbean Currency Authority', '1 Dollar', 'P-13g')
        self.add('authority5', 'East Caribbean States', 'East Caribbean Currency Authority', '$5', 'P-14j', series='ND (1965)')
        self.add('board1', 'British Caribbean Territories', 'British Caribbean Currency Board (The British Caribbean Territories, Eastern Group)', '1 Dollar', 'P-7c', 1958, '1953–1964 Elizabeth II issue')
        self.add('central10', 'East Caribbean States', 'Eastern Caribbean Central Bank', '10 Dollars', 'P-18a', 1984)
        self.add('central5', 'Eastern Caribbean Central Bank', '', '5 Dollars', 'P-17a', 1984)

    def test_exact_regional_names_and_explicit_blank_country_issuer(self):
        for country in ('East Caribbean States', 'East Caribbean States - Grenada',
                        'Eastern Caribbean States (Grenada)', 'East Caribbean Currency Authority', None):
            with self.subTest(country=country):
                resolved = catalog.eastern_caribbean_issue(country, 1965, 'East Caribbean Currency Authority')
                self.assertEqual((resolved['key'], resolved['entity_country']), ('ecca', 'East Caribbean States'))
                self.assertEqual(catalog.classify(country, 1965, 'East Caribbean Currency Authority')['key'], 'british')
                self.assertEqual(catalog.canonical_country(country), country)
        self.assertEqual(catalog.eastern_caribbean_issue('Saint Kitts', 1988, 'Eastern Caribbean Central Bank')['key'], 'eccb')

    def test_no_standalone_territory_or_date_guess_or_foreign_bank_merge(self):
        for country, issuer in (('Grenada', ''), ('Grenada', 'National Bank of Grenada'),
                                ('Canada', 'Eastern Caribbean Central Bank'),
                                (None, 'National Bank of Grenada'),
                                ('East Caribbean States - Atlantis', 'East Caribbean Currency Authority')):
            self.assertIsNone(catalog.eastern_caribbean_issue(country, 1965, issuer))
        for issuer in ('', 'National Bank of Grenada'):
            value = catalog.eastern_caribbean_issue('East Caribbean States', 1965, issuer)
            self.assertEqual(value['key'], 'unresolved')
            self.assertIsNone(value['entity_country'])
            self.assertNotIn('first issued notes on', value['history'])
        self.assertEqual(catalog.eastern_caribbean_issue('British Caribbean Territories', 1965, 'East Caribbean Currency Authority')['key'], 'ecca')

    def test_shared_family_orders_authority_then_series_numeric_value_full_reference(self):
        self.fixture()
        self.assertEqual([r['id'] for r in self.rows()], [
            'board1', 'board10', 'authority1', 'grenada5', 'authority5', 'authority20', 'central5', 'central10'])
        self.add('earlier100', 'East Caribbean States', 'Eastern Caribbean Central Bank', '100 Dollars', 'P-20a', 1984)
        self.add('later1', 'East Caribbean States', 'Eastern Caribbean Central Bank', '1 Dollar', 'P-21a', 1986)
        ids = [r['id'] for r in self.rows()]
        self.assertLess(ids.index('earlier100'), ids.index('later1'))
        self.assertIn('pick_number', stuff.BANKNOTE_SORT_FIELDS)
        self.assertIn('other_catalog', stuff.BANKNOTE_SORT_FIELDS)

    def test_full_reference_natural_order_preserves_suffix_namespace_and_original(self):
        values = ['P-14j', 'Pick 14h', 'P-15a', 'P-9z', '14g', 'P-14h2', 'P-14h10']
        original = values[:]
        self.assertEqual(sorted(values, key=catalog.catalogue_reference_sort),
                         ['P-9z', '14g', 'Pick 14h', 'P-14h2', 'P-14h10', 'P-14j', 'P-15a'])
        self.assertEqual(values, original)
        for spelling in ('Pick#14a', 'Pick #14a', 'P-14a', '14a'):
            self.assertEqual(catalog.catalogue_reference_sort(spelling), catalog.catalogue_reference_sort('P14a'))
        self.assertNotEqual(catalog.catalogue_reference_sort('P-14h'), catalog.catalogue_reference_sort('B-14h'))

    def test_series_range_does_not_erase_distinct_design_identity(self):
        key = lambda label: catalog.eastern_caribbean_series('East Caribbean States', 1974, 'East Caribbean Currency Authority', label)
        self.assertNotEqual(key('1974–1978 portrait issue'), key('1974–1978 map issue'))
        self.assertNotEqual(key('1974–1976–1978 issue'), key('1974–1977–1978 issue'))
        self.add('portrait1', 'East Caribbean States', 'East Caribbean Currency Authority', '1 Dollar', 'P-13a', 1974, '1974–1978 portrait issue')
        self.add('map20', 'East Caribbean States', 'East Caribbean Currency Authority', '20 Dollars', 'P-15a', 1974, '1974–1978 map issue')
        self.add('portrait20', 'East Caribbean States', 'East Caribbean Currency Authority', '20 Dollars', 'P-15b', 1974, '1974–1978 portrait issue')
        self.assertEqual([r['id'] for r in self.rows()], ['map20', 'portrait1', 'portrait20'])
        bccb = lambda label: catalog.eastern_caribbean_series('British Caribbean Territories', 1958, 'BCCB', label)
        self.assertEqual(bccb('1953–1964 Elizabeth II issue'), bccb('1953-1964 Currency Board issue'))

    def test_history_panels_have_three_issuers_and_no_1965_variety_date_claim(self):
        self.fixture()
        panels = [v['panel'] for v in stuff.series_panels(self.rows()).values() if 'panel' in v]
        self.assertEqual([p['regional_issuer'] for p in panels], ['bccb', 'ecca', 'eccb'])
        authority = panels[1]
        self.assertIn('6 October 1965', authority['era']['body'])
        self.assertIn('Grenada joined the currency arrangement in 1968', authority['era']['body'])
        self.assertIn('not the issue date of every', authority['era']['body'])
        self.assertEqual(authority['series_list'], ['Catalogue family ND (1965)'])
        self.assertIn('15 November 1984', panels[2]['era']['body'])

    def test_history_on_and_off_keep_family_issuer_headers_and_raw_territory(self):
        self.fixture()
        for history in ('0', '1'):
            response = stuff.app.test_client().get('/banknotes', query_string={'history': history})
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertEqual(html.count('data-banknote-family="eastern-caribbean"'), 1)
            for key in ('bccb', 'ecca', 'eccb'):
                self.assertEqual(html.count('data-banknote-issuer="' + key + '"'), 1)
            # These are issued sets, not the denominations held in this fixture.
            for issued in ('$1, $2, $5, $10, $20, $100', '$1, $5, $20, $100',
                           '$1, $2, $5, $10, $20, $50, $100'):
                self.assertIn('>Issued: ' + issued + '</span>', html)
            self.assertIn('withdrawn $1 and the $2 circulation commemorative', html)
            self.assertIn('East Caribbean States - Grenada', html)
            self.assertIn('P-14h', html)
            self.assertIn('P-14j', html)

    def test_unresolved_authority_does_not_borrow_issued_denominations(self):
        self.add('unclear', 'East Caribbean States', '', '5 Dollars', 'P-14', 1965)
        self.add('other-issuer', 'East Caribbean States', 'Unidentified local bank', '1 Dollar', '', 1955)
        for history in ('0', '1'):
            response = stuff.app.test_client().get('/banknotes', query_string={'history': history})
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertNotIn('class="usp-denoms"', html)
            self.assertNotIn('>Issued: ', html)

    def test_family_closes_before_following_country_in_both_history_modes(self):
        from html.parser import HTMLParser
        class ScopeParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack, self.scopes, self.parents = [], [], {}
            def handle_starttag(self, tag, attributes):
                attrs = dict(attributes)
                if tag == 'section':
                    scope = {'rows': [], 'boundary': None} if attrs.get('data-banknote-family-scope') else None
                    self.stack.append(scope)
                    if scope is not None:
                        self.scopes.append(scope)
                scope = next((value for value in reversed(self.stack) if value is not None), None)
                if 'item-row' in attrs.get('class', '').split():
                    self.parents[attrs['id']] = scope
                    if scope is not None:
                        scope['rows'].append(attrs['id'])
                if attrs.get('data-banknote-family-end'):
                    scope['boundary'] = attrs
            def handle_endtag(self, tag):
                if tag == 'section':
                    self.stack.pop()
        self.fixture()
        self.add('jamaica', 'Jamaica', 'Government of Jamaica', '1 Pound', 'P-37', 1957)
        self.add('canada', 'Canada', 'Bank of Canada', '1 Dollar', 'P-84a', 1967)
        placements = stuff.banknote_grouping(self.rows())
        self.assertTrue(placements['central10']['regional_end'])
        self.assertNotIn('regional_end', placements['jamaica'])
        by_id = {row['id']: row for row in self.rows()}
        # Purchase-date views can interrupt and later reopen the regional run.
        interrupted = stuff.banknote_grouping([by_id['authority1'], by_id['jamaica'], by_id['central10']])
        self.assertTrue(interrupted['authority1']['regional_end'])
        self.assertTrue(interrupted['central10']['regional_heading'])
        self.assertTrue(interrupted['central10']['regional_end'])
        for history in ('0', '1'):
            html = stuff.app.test_client().get('/banknotes', query_string={'history': history}).get_data(as_text=True)
            parsed = ScopeParser()
            parsed.feed(html)
            self.assertEqual(len(parsed.scopes), 1)
            scope = parsed.scopes[0]
            self.assertEqual(len(scope['rows']), 8)
            self.assertIsNone(parsed.parents['item-jamaica'])
            self.assertIsNone(parsed.parents['item-canada'])
            boundary = scope['boundary']
            self.assertEqual(boundary['role'], 'separator')
            self.assertIn('us-series-divider', boundary['class'])
            self.assertEqual(parsed.stack, [])

        # A filtered regional-only list must also close its section at the end.
        self.db.execute("DELETE FROM banknotes WHERE id IN ('jamaica','canada')")
        self.db.commit()
        self.assertTrue(stuff.banknote_grouping(self.rows())['central10']['regional_end'])

    def test_report_has_same_issuer_sections_and_keeps_territorial_attribution(self):
        self.fixture()
        sections = stuff._banknote_report_sections(self.db)
        self.assertEqual([key for _, key, _ in sections], ['eastern-caribbean-bccb', 'eastern-caribbean-ecca', 'eastern-caribbean-eccb'])
        self.assertEqual([len(rows) for _, _, rows in sections], [2, 4, 2])
        for title, key, rows in sections:
            history = stuff._banknote_report_history(title, key, rows)
            self.assertEqual(history[0], title)
            self.assertIn('Regional currency history', history[2][0])
        row = self.db.execute("SELECT * FROM banknotes WHERE id='grenada5'").fetchone()
        line = stuff._banknote_report_lines(row)[0]
        self.assertIn('East Caribbean States - Grenada', line)
        self.assertIn('P-14h', line)
        unresolved = dict(row, issuer='')
        self.assertIn('East Caribbean States - Grenada', stuff._banknote_report_lines(unresolved)[0])

    def test_v32_migration_changes_only_display_position_and_runs_once(self):
        self.fixture()
        self.db.execute("UPDATE banknotes SET banknote_id='P 999'")
        self.db.execute("DELETE FROM migration_state WHERE key='banknote_display_number_v33'")
        self.db.commit()
        before = {r['id']: dict(r) for r in self.rows()}
        stuff.init_db()
        rows = self.rows()
        self.assertEqual([r['banknote_id'] for r in rows], [f'P {i:03}' for i in range(1, 9)])
        for row in rows:
            self.assertEqual({k: v for k, v in dict(row).items() if k != 'banknote_id'},
                             {k: v for k, v in before[row['id']].items() if k != 'banknote_id'})
        with patch.object(stuff, '_renumber_banknotes', wraps=stuff._renumber_banknotes) as renumber:
            stuff.init_db()
        renumber.assert_not_called()


if __name__ == '__main__':
    unittest.main()
