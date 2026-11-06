"""Bahrain's first Currency Board family belongs to its protected-state period."""
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import banknote_catalog as catalog
import banknote_entities as entities


class BahrainFilingTests(unittest.TestCase):
    def test_first_currency_board_issues_use_administrative_control_wording(self):
        for year in (1965, 1967, 1969, '1965', 1967.0):
            for issuer in ('Bahrain Currency Board', 'Bahrain Currency Board (BCB)',
                           'The Bahrain Currency Board', 'Currency Board of Bahrain', 'BCB', ''):
                with self.subTest(year=year, issuer=issuer):
                    info = catalog.classify('Bahrain', year, issuer)
                    self.assertEqual(info['key'], 'british')
                    self.assertEqual(info['country'], 'Bahrain')
                    self.assertIn('administrative control', info['period'])
                    self.assertIn('protected state', info['period'])
                    self.assertNotIn('colonial', info['period'].lower())
                    self.assertFalse(info['uncertain'])

    def test_1964_authorization_is_supported_only_with_explicit_currency_board(self):
        for year in (1964, '1964', 1964.0):
            with self.subTest(year=year):
                info = catalog.classify('Bahrain', year, 'Bahrain Currency Board')
                self.assertEqual(info['key'], 'british')
                self.assertIn('1964 authorization', info['period'])
                self.assertIn('1965–67', info['period'])
                self.assertFalse(info['uncertain'])
        for issuer in ('', None, 'Government of Bahrain', 'Bahrain Monetary Agency'):
            self.assert_review(1964, issuer)

    def test_saved_first_issue_catalogue_shapes_all_receive_correct_computed_period(self):
        for denomination, reference in (('1 Dinar', 'P4a'), ('1/4 Dinar', 'P2a'),
                                        ('1/2 Dinar', 'P3'), ('100 Fils', 'P1a')):
            with self.subTest(reference=reference):
                row=dict(country='Bahrain', date_1=1964, issuer='Bahrain Currency Board',
                         series=None, denomination=denomination, pick_number=reference)
                before=dict(row)
                self.assertEqual(catalog.row_classification(row)['key'], 'british')
                self.assertEqual(entities.entity_for_row(row)['key'], 'british-bahrain')
                self.assertEqual(row,before)

    def test_independence_transition_stays_unresolved(self):
        for issuer in ('Bahrain Currency Board', 'Bahrain Monetary Agency', ''):
            info = catalog.classify('Bahrain', 1971, issuer)
            self.assertEqual(info['key'], 'other')
            self.assertTrue(info['uncertain'])
            self.assertIn('15 August 1971', info['period'])

    def test_later_issues_are_independent_even_when_an_old_series_is_mentioned(self):
        for year, issuer in ((1972, 'Bahrain Currency Board'), (1973, 'Bahrain Monetary Agency'),
                             (1993, 'Bahrain Monetary Agency'), (2008, 'Central Bank of Bahrain')):
            with self.subTest(year=year, issuer=issuer):
                info = catalog.classify('Bahrain', year, issuer, '1965 first series')
                self.assertEqual(info['key'], 'other')
                self.assertEqual(info['period'], 'Independent Bahrain issue')
                self.assertFalse(info['uncertain'])

    def assert_review(self, year, issuer='Bahrain Currency Board', series=''):
        info = catalog.classify('Bahrain', year, issuer, series)
        self.assertEqual(info['key'], 'other')
        self.assertTrue(info['uncertain'])
        self.assertIn('review', info['period'])
        self.assertNotIn('Independent', info['period'])

    def test_undated_ranges_and_malformed_dates_do_not_guess_from_series(self):
        for year in (None, '', 'ND', 'ND (1965)', '1964–1967', '1965-1973',
                     '6/1964', 1965.5, True, float('nan'), float('inf'), 1963):
            with self.subTest(year=year):
                self.assert_review(year, series='Bahrain Currency Board (1965-1967)')

    def test_later_conflicting_or_unrecognized_issuer_cannot_be_overruled_by_early_date(self):
        for year in (1964, 1965, 1967):
            for issuer in ('Bahrain Monetary Agency', 'BMA', 'Central Bank of Bahrain', 'CBB',
                           'Reserve Bank of India', 'Unknown issuing bank',
                           'Bahrain Currency Board / Bahrain Monetary Agency'):
                with self.subTest(year=year, issuer=issuer):
                    self.assert_review(year, issuer)
            self.assert_review(year, series='Bahrain Monetary Agency 1973 series')
            for series in ('1971 issue', '1972 issue', '1973 issue'):
                self.assert_review(year, series=series)
            self.assert_review(year, series='BMA')
            self.assert_review(year, series='Central Bank of Bahrain')

    def test_entity_coverage_uses_the_same_period_and_never_date_only_fallback(self):
        for year, issuer, expected in (
                (1964, 'Bahrain Currency Board', 'british-bahrain'),
                (1965, 'Bahrain Currency Board', 'british-bahrain'),
                (1967, '', 'british-bahrain'), (1964, '', None),
                (1965, 'Bahrain Monetary Agency', None), (1967, 'Unknown issuing bank', None),
                (1971, 'Bahrain Currency Board', None), (1973, 'Bahrain Monetary Agency', None),
                (None, 'Bahrain Currency Board', None), ('1965-1973', 'Bahrain Currency Board', None)):
            with self.subTest(year=year, issuer=issuer):
                row=dict(country='Bahrain', date_1=year, issuer=issuer)
                entity=entities.entity_for_row(row)
                self.assertEqual(entity['key'] if entity else None, expected)
        self.assertIsNone(entities.entity_for_row(
            dict(country='Bahrain', date_1=1967, issuer='Bahrain Monetary Agency'),
            dict(country='Bahrain', key='british')))

    def test_shared_helper_and_row_classification_preserve_saved_facts(self):
        note=dict(id='held-note', country='Bahrain', date_1=1964, issuer='Bahrain Currency Board',
                  pick_number='P-4a', series='First issue', price='$105.43', status='Own',
                  order_number='12-12345-12345', image_1='original-front.jpg')
        before=deepcopy(note)
        info=catalog.row_classification(note)
        shared=catalog.bahrain_issue(note['country'], note['date_1'], note['issuer'], note['series'])
        self.assertEqual(info['key'],shared['group'])
        self.assertEqual(info['period'],shared['period'])
        self.assertEqual(entities.entity_for_row(note)['key'],'british-bahrain')
        self.assertEqual(note,before)
        db=sqlite3.connect(':memory:'); db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE banknotes(country TEXT,date_1 INTEGER,issuer TEXT)')
        db.execute("INSERT INTO banknotes VALUES('Bahrain',1964,'Bahrain Currency Board')")
        self.assertEqual(catalog.row_classification(db.execute('SELECT * FROM banknotes').fetchone())['key'],'british')
        db.close()

    def test_non_bahrain_countries_do_not_gain_bahrain_filing(self):
        self.assertIsNone(catalog.bahrain_issue('Kuwait',1965,'Bahrain Currency Board'))
        self.assertIsNone(catalog.bahrain_issue(None,1965,'Bahrain Currency Board'))
        self.assertNotIn('Bahrain',catalog.classify('Qatar and Dubai',1967)['period'])


if __name__ == '__main__':
    unittest.main()
