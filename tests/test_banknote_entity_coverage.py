"""Pure regional coverage tests; no app, database or live collection access."""
import copy
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import banknote_catalog as catalog
import banknote_entities as entities
from banknote_entity_coverage import entities_for_row


BOARD = 'Board of Commissioners of Currency, Malaya and British Borneo'
REGION = 'british-malaya-and-british-borneo'
MALAYA = 'british-malaya'
SINGAPORE = 'british-singapore'
SARAWAK = 'british-sarawak'
NORTH_BORNEO = 'british-british-north-borneo'
BRUNEI = 'british-brunei'


class EntityCoverageTests(unittest.TestCase):
    def regional(self, year=1953, **changes):
        return dict(country='Malaya and British Borneo', date_1=year,
                    issuer=BOARD, **changes)

    def keys(self, row):
        return tuple(entity['key'] for entity in entities_for_row(row))

    def test_reported_1953_delivered_and_1959_ordered_notes_cover_north_borneo(self):
        for year, status, cat_id in ((1953, 'Delivered', 'B292'), (1959, 'Ordered', 'B321')):
            with self.subTest(year=year):
                row = self.regional(year, status=status, cat_id=cat_id)
                coverage = entities_for_row(row)
                self.assertEqual(coverage[0]['key'], REGION)
                self.assertEqual(coverage[0]['coverage_kind'], 'direct')
                north = next(entity for entity in coverage if entity['key'] == NORTH_BORNEO)
                self.assertEqual(north['coverage_kind'], 'regional')
                self.assertIn('shared Malaya and British Borneo', north['coverage_note'])
                self.assertIn('does not establish ownership of a separate territorial issue', north['coverage_note'])
                self.assertIs(north['issued'], True)
                # Primary identity remains regional, not a North Borneo Company note.
                self.assertEqual(entities.entity_for_row(row)['key'], REGION)

    def test_each_territory_stops_before_its_transition_year(self):
        expected = {
            1953: (REGION, MALAYA, SINGAPORE, SARAWAK, NORTH_BORNEO, BRUNEI),
            1956: (REGION, MALAYA, SINGAPORE, SARAWAK, NORTH_BORNEO, BRUNEI),
            1957: (REGION, SINGAPORE, SARAWAK, NORTH_BORNEO, BRUNEI),
            1959: (REGION, SINGAPORE, SARAWAK, NORTH_BORNEO, BRUNEI),
            1962: (REGION, SINGAPORE, SARAWAK, NORTH_BORNEO, BRUNEI),
            1963: (REGION, SINGAPORE, BRUNEI),
            1964: (REGION, SINGAPORE, BRUNEI),
            1965: (REGION, BRUNEI),
            1966: (REGION, BRUNEI),
            1967: (REGION,),
            1968: (REGION,),
        }
        for year, keys in expected.items():
            with self.subTest(year=year):
                self.assertEqual(self.keys(self.regional(year)), keys)

    def test_undated_earlier_or_inexact_dates_do_not_infer_regional_coverage(self):
        for value in (None, '', 1952, 1941, 'ND (1953)', '1953-1959', 1953.5, True):
            with self.subTest(value=value):
                self.assertEqual(self.keys(self.regional(value)), (REGION,))
        self.assertIn(NORTH_BORNEO, self.keys(self.regional('1959')))

    def test_date_ranges_must_fit_board_and_member_periods(self):
        self.assertNotIn(MALAYA, self.keys(self.regional(1953, date_2=1959)))
        self.assertIn(NORTH_BORNEO, self.keys(self.regional(1953, date_2=1959)))
        self.assertNotIn(NORTH_BORNEO, self.keys(self.regional(1959, date_2=1963)))
        for end in (1952, 1967, 'unknown'):
            with self.subTest(end=end):
                self.assertEqual(self.keys(self.regional(1953, date_2=end)), (REGION,))

    def test_named_board_issuer_accepts_only_exact_normalized_variants(self):
        for issuer in (BOARD, 'The Board of Commissioners of Currency',
                       'Board of Commissioners of Currency (Malaya & British Borneo)',
                       'Commissioners of Currency, Malaya and British Borneo',
                       'Malaya and British Borneo Board of Commissioners of Currency'):
            row = self.regional()
            row['issuer'] = issuer
            with self.subTest(issuer=issuer):
                self.assertIn(NORTH_BORNEO, self.keys(row))
        for issuer in ('', None, 'British North Borneo Company', 'British North Borneo Chartered Company',
                       'The Japanese Government', 'Bank Negara Malaysia', 'Brunei Currency Board',
                       'Board of Commissioners of Currency, Malaya',
                       'Board of Commissioners of Currency, Singapore',
                       'Replica of ' + BOARD, BOARD + '; Japanese occupation'):
            row = self.regional()
            row['issuer'] = issuer
            with self.subTest(issuer=issuer):
                self.assertEqual(self.keys(row), (REGION,))

    def test_other_country_names_do_not_fuzzily_expand_to_the_regional_board(self):
        for country in ('British North Borneo', 'North Borneo', 'Sarawak', 'Malaya',
                        'Brunei', 'Singapore', 'Malaysia', 'British Borneo',
                        'Malaya and British Borneo replica'):
            row = self.regional()
            row['country'] = country
            with self.subTest(country=country):
                self.assertTrue(all(entity['coverage_kind'] == 'direct' for entity in entities_for_row(row)))

    def test_primary_identity_and_no_match_preserve_existing_contract(self):
        row = dict(country='North Borneo', date_1=1939, issuer='British North Borneo Company')
        self.assertEqual(self.keys(row), (NORTH_BORNEO,))
        self.assertEqual(entities_for_row(row)[0]['coverage_note'], '')
        row = dict(country='Burma', date_1=1944, issuer='The Japanese Government')
        self.assertEqual(self.keys(row), ('japanese-burma',))
        self.assertEqual(entities_for_row(dict(country='Unlisted place')), ())

    def test_caller_controls_purchase_status_and_no_sources_are_mutated(self):
        roster_before = copy.deepcopy(entities.ENTITY_CATALOG)
        for status in ('Own', 'Ordered', 'Delivered', 'Sold'):
            row = self.regional(status=status)
            before = copy.deepcopy(row)
            classification = catalog.row_classification(row)
            classification_before = dict(classification)
            coverage = entities_for_row(row, classification)
            self.assertIn(NORTH_BORNEO, tuple(entity['key'] for entity in coverage))
            coverage[0]['label'] = 'Caller-local label'
            self.assertEqual(row, before)
            self.assertEqual(classification, classification_before)
        self.assertEqual(entities.ENTITY_CATALOG, roster_before)

    def test_sqlite_rows_are_supported_without_database_writes(self):
        with sqlite3.connect(':memory:') as db:
            db.row_factory = sqlite3.Row
            row = db.execute('SELECT ? AS country, ? AS date_1, ? AS issuer',
                             ('Malaya and British Borneo', 1959, BOARD)).fetchone()
            db.execute('PRAGMA query_only=ON')
            self.assertIn(NORTH_BORNEO, self.keys(row))
            self.assertEqual(dict(row)['country'], 'Malaya and British Borneo')


if __name__ == '__main__':
    unittest.main()
