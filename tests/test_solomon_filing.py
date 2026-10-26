"""The 1977 SIMA issue predates independence; later/unclear issues do not.

Sources: CBSI Currency Overview (first $2/$5/$10 notes in 1977), CBSI
RP-012014 (first issued 24 October 1977), and Solomon Islands Parliament's
Independence Order 1978 (effective 7 July 1978).
"""
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-solomon-filing-')
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import banknote_catalog as catalog
import market_colonial
with patch('threading.Thread.start'):
    import app as stuff


class SolomonFilingTests(unittest.TestCase):
    def test_sima_1977_is_a_protectorate_issue_without_changing_country(self):
        for issuer in ('Solomon Islands Monetary Authority',
                       'Solomon Islands Monetary Authority (SIMA)', 'SIMA', ''):
            with self.subTest(issuer=issuer):
                result = catalog.classify('Solomon Islands', 1977, issuer)
                self.assertEqual(result['key'], 'british')
                self.assertEqual(result['country'], 'Solomon Islands')
                self.assertIn('protectorate', result['period'])
                self.assertFalse(result['uncertain'])

    def test_independence_year_requires_an_exact_issue_date(self):
        result = catalog.classify('Solomon Islands', 1978,
                                  'Solomon Islands Monetary Authority')
        self.assertEqual(result['key'], 'other')
        self.assertTrue(result['uncertain'])
        self.assertIn('7 July 1978', result['period'])

    def test_sima_name_or_1977_series_does_not_make_later_notes_colonial(self):
        for year in (1979, 1980, 1982, 1984, 2020):
            with self.subTest(year=year):
                result = catalog.classify('Solomon Islands', year,
                                          'Solomon Islands Monetary Authority', '1977 series')
                self.assertEqual(result['key'], 'other')
                self.assertIn('Independent', result['period'])

    def test_unknown_ranges_and_series_only_do_not_supply_a_printed_year(self):
        for date in (None, '', 'ND', 'ND (1977)', '1977–1982',
                     '1977-1978', 1977.5, True):
            with self.subTest(date=date):
                result = catalog.classify('Solomon Islands', date,
                                          'Solomon Islands Monetary Authority', 'ND (1977)')
                self.assertEqual(result['key'], 'other')
                self.assertTrue(result['uncertain'])

    def test_later_or_conflicting_issuer_is_not_overridden_by_year(self):
        for issuer in ('Central Bank of Solomon Islands', 'CBSI',
                       'Reserve Bank of Australia', 'Unknown issuing bank'):
            with self.subTest(issuer=issuer):
                result = catalog.classify('Solomon Islands', 1977, issuer)
                self.assertEqual(result['key'], 'other')
                self.assertTrue(result['uncertain'])

    def test_new_rule_does_not_invent_earlier_modern_country_issues(self):
        for year in (1916, 1932, 1950, 1976):
            self.assertEqual(catalog.classify('Solomon Islands', year)['key'], 'other')

    def test_valid_1977_issue_survives_the_full_market_policy(self):
        base = dict(country='Solomon Islands', date_1=1977,
                    issuer='Solomon Islands Monetary Authority',
                    title='Solomon Islands 1977 5 Dollars P-6a', pick_number='P-6a',
                    entity_key='british-british-solomon-islands', theme='entity-gap-british')
        for theme in ('entity-gap-british', 'colonial-worldwide'):
            with self.subTest(theme=theme):
                self.assertEqual(market_colonial.problem(dict(base, theme=theme)), '')
        for change in (
            dict(date_1=1978), dict(date_1=1980), dict(date_1=None),
            dict(date_1=1976), dict(issuer='Central Bank of Solomon Islands'),
            dict(issuer='Unknown issuing bank'), dict(issuer=''),
            dict(series='1979 issue'), dict(series='ND (1977)'),
        ):
            with self.subTest(change=change):
                self.assertTrue(market_colonial.problem(dict(base, **change)))

    def test_actual_issue_dates_override_an_older_printed_date_in_market(self):
        base = dict(country='Solomon Islands', date_1=1977,
                    issuer='Solomon Islands Monetary Authority',
                    title='Solomon Islands ND 1977 5 Dollars P-6a', pick_number='P-6a',
                    theme='colonial-worldwide', issue_year_start=1977, issue_year_end=1977,
                    issue_date_source='https://catalogue.example/issue/solomon-1977')
        self.assertEqual(market_colonial.problem(base), '')
        for start, end in ((1977, 1978), (1978, 1978), (1980, 1980)):
            changed = dict(base, issue_year_start=start, issue_year_end=end)
            self.assertTrue(market_colonial.problem(changed))
            # Administration evidence must not broaden the independence cutoff.
            changed['administration'] = dict(
                kind='protectorate', name='British protectorate',
                territory='Solomon Islands', year_start=1976, year_end=1983,
                source='https://history.example/solomon', evidence='Synthetic test evidence')
            self.assertTrue(market_colonial.problem(changed))
        administration = dict(
            kind='protectorate', name='British protectorate', territory='Solomon Islands',
            year_start=1976, year_end=1978, source='https://history.example/solomon',
            evidence='Synthetic test evidence')
        self.assertEqual(market_colonial.problem(dict(base, administration=administration)), '')
        self.assertTrue(market_colonial.problem(dict(base, series='1979 issue',
                                                   administration=administration)))
        self.assertTrue(market_colonial.problem(dict(base, administration=dict(
            administration, year_end=1983))))

    def test_display_and_filters_preserve_the_saved_note(self):
        with stuff.app.app_context():
            db = stuff.get_db()
            notes = [
                dict(id='solomon-1977', cat_id='B426', banknote_id='P 426',
                     country='Solomon Islands', issuer='Solomon Islands Monetary Authority',
                     date_1=1977, denomination='5 Dollars', pick_number='P-6a',
                     status='Ordered', image_1='front.jpg', image_2='back.jpg',
                     price='$199.89', serial_number='A123456', slab_number='1234567-001',
                     grade_numeric=65, history_context='Original history preserved'),
                dict(id='solomon-later', country='Solomon Islands',
                     issuer='Solomon Islands Monetary Authority', date_1=1980,
                     denomination='20 Dollars', status='Own'),
            ]
            for row in notes:
                db.execute('INSERT INTO banknotes (' + ','.join(row) + ') VALUES ('
                           + ','.join('?' for _ in row) + ')', list(row.values()))
            db.commit()
            before = [dict(row) for row in db.execute('SELECT * FROM banknotes ORDER BY id')]
            db.execute('PRAGMA query_only=ON')
            client = stuff.app.test_client()
            for history in ('0', '1'):
                with patch.object(stuff, 'ensure_country_history'):
                    british = client.get('/banknotes', query_string={
                        'filter': 'heritage_british', 'history': history}).get_data(as_text=True)
                    other = client.get('/banknotes', query_string={
                        'filter': 'heritage_other', 'history': history}).get_data(as_text=True)
                self.assertIn('id="item-solomon-1977"', british)
                self.assertNotIn('id="item-solomon-later"', british)
                self.assertIn('P-6a', british)
                self.assertIn('id="item-solomon-later"', other)
                self.assertNotIn('id="item-solomon-1977"', other)
            self.assertEqual(before, [dict(row) for row in db.execute(
                'SELECT * FROM banknotes ORDER BY id')])


if __name__ == '__main__':
    unittest.main()
