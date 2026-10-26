"""Evidence-backed roster completeness and conservative historical matching."""
import ast
from datetime import date
from collections import Counter
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import banknote_catalog as filing
from banknote_entities import ENTITY_CATALOG, ENTITY_BY_KEY, entity_for_row


class BanknoteEntityTests(unittest.TestCase):
    def match(self, country, year=None, issuer='', series=''):
        return entity_for_row(dict(country=country, date_1=year, issuer=issuer, series=series))

    def key(self, country, year=None, issuer='', series=''):
        result = self.match(country, year, issuer, series)
        return result['key'] if result else None

    def test_caribbean_regional_aliases_share_coverage_without_territorial_credit(self):
        authority = 'East Caribbean Currency Authority'
        for country in (None, '', 'East Caribbean States',
                        'East Caribbean States - Grenada',
                        'East Caribbean Currency Authority'):
            with self.subTest(country=country):
                row = dict(country=country, date_1=1965, issuer=authority,
                           series='ND (1965)', pick_number='P-14k')
                before = dict(row)
                match = entity_for_row(row)
                self.assertEqual(match['key'], 'british-east-caribbean-states')
                self.assertIsNone(match['scan_period'])
                self.assertEqual(row, before)
        self.assertEqual(self.key('East Caribbean States', 1985,
                                  'Eastern Caribbean Central Bank'),
                         'british-east-caribbean-states')
        self.assertEqual(self.key('British Caribbean Territories', 1959,
                                  'British Caribbean Territories Currency Board'),
                         'british-british-caribbean-territories')
        self.assertEqual(self.key('Grenada', 1920, 'Colonial Bank'),
                         'british-grenada')
        self.assertIsNone(self.match('Grenada', 1985, 'Unspecified national issuer'))
        self.assertIsNone(self.match('British Caribbean Territories', 1959,
                                     'National Bank of Grenada'))
        self.assertIsNone(self.match('East Caribbean States', 1965,
                                     'Unidentified private bank'))

    def test_solomon_1977_pre_independence_issue_counts_without_successor_credit(self):
        for issuer in ('', 'Solomon Islands Monetary Authority'):
            self.assertEqual(self.key('Solomon Islands', 1977, issuer),
                             'british-british-solomon-islands')
        for year in (None, 1978, 1980):
            self.assertIsNone(self.match('Solomon Islands', year,
                                         'Solomon Islands Monetary Authority'))
        self.assertIsNone(self.match('Solomon Islands', 1977,
                                     'Central Bank of Solomon Islands'))
        entry = ENTITY_BY_KEY['british-british-solomon-islands']
        self.assertEqual(entry['independence_date'], '1978-07-07')
        self.assertEqual(entry['scan_period']['year_end'], 1978)

    def test_unique_evidence_bearing_roster_with_explicit_three_state_issuance(self):
        self.assertEqual(len(ENTITY_CATALOG), len(ENTITY_BY_KEY))
        self.assertEqual(len(ENTITY_CATALOG), 195)
        for entity in ENTITY_CATALOG:
            with self.subTest(entity=entity['key']):
                self.assertIn(entity['group'], filing.GROUP_BY_KEY)
                self.assertTrue(entity['key'].startswith(entity['group'] + '-'))
                self.assertTrue(entity['countries'])
                self.assertTrue(entity['label'])
                self.assertTrue(entity['note'])
                self.assertTrue(entity['sources'])
                self.assertTrue(all(source.startswith('https://') for source in entity['sources']))
                self.assertTrue(entity['issued'] is None or type(entity['issued']) is bool)
        counts = Counter(entity['issued'] for entity in ENTITY_CATALOG)
        self.assertGreater(counts[True], 100)
        self.assertGreater(counts[None], 20)
        self.assertEqual(counts[False], 1)

    def test_all_existing_filing_rosters_are_represented(self):
        present = {(entry['group'], filing.fold(filing.canonical_country(name)))
                   for entry in ENTITY_CATALOG for name in entry['countries']}
        expected = [(group, name) for name, (group, *_rest) in filing.PERIODS.items()]
        expected += [(group, name) for name, (group, _label) in filing.HISTORIC.items()]
        expected += [('british', name) for name in filing.BRITISH_DEPENDENCIES]
        expected += [('french', name) for name in filing.FRENCH_OVERSEAS]
        expected += [('british', name) for name in filing.AMERICAN_COLONIES.values()]
        for group, name in expected:
            with self.subTest(group=group, name=name):
                self.assertIn((group, filing.fold(name)), present)

    def test_all_legacy_wantlist_subjects_have_a_roster_identity(self):
        # Read only the literal, without importing the app or opening a database.
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'app.py').read_text())
        legacy = next(ast.literal_eval(node.value) for node in tree.body
                      if isinstance(node, ast.Assign)
                      and any(isinstance(target, ast.Name) and target.id == 'BANKNOTE_COLONIAL_WANTLIST'
                              for target in node.targets))
        equivalents = {
            'Syria (mandate)': 'french-syria',
            'Tahiti / French Oceania': 'french-french-oceania',
            'Saint-Pierre et Miquelon': 'french-saint-pierre-and-miquelon',
            'São Tomé e Príncipe (colonial)': 'portuguese-sao-tome-and-principe',
            'Puerto Rico (Spanish)': 'spanish-puerto-rico',
            'Cuba (Spanish colonial)': 'spanish-cuba',
            'Philippines (Spanish colonial)': 'us-philippines',
            'Italian Somaliland (rupia)': 'italian-italian-somaliland',
            'Kiautschou (Tsingtau)': 'german-kiautschou',
            'Taiwan (Japanese)': 'japanese-taiwan',
        }
        names = {filing.fold(name) for entity in ENTITY_CATALOG for name in entity['countries']}
        self.assertEqual(len(legacy), 35)
        for name, *_rest in legacy:
            with self.subTest(name=name):
                if name in equivalents:
                    self.assertIn(equivalents[name], ENTITY_BY_KEY)
                else:
                    self.assertIn(filing.fold(name), names)

    def test_modern_successors_do_not_credit_colonial_entities(self):
        for country, year, issuer in (
            ('India', 1960, 'Reserve Bank of India'),
            ('Cuba', 1960, 'Banco Nacional de Cuba'),
            ('Burma', 1965, 'Peoples Bank of Burma'),
            ('Belize', 1990, 'Central Bank of Belize'),
            ('Macau', 2000, 'Banco Nacional Ultramarino'),
            ('Suriname', 1986, 'Centrale Bank van Suriname'),
            ('Bahrain', 1980, 'Bahrain Monetary Agency'),
            ('Brunei', 1990, 'Brunei Currency Board'),
            ('Palestine', 2000, 'Palestinian Monetary Authority'),
            ('Newfoundland', 2000, 'Bank of Canada'),
            ('Iceland', 1961, 'Central Bank of Iceland'),
            ('Syria', 1950, 'Banque Centrale de Syrie'),
            ('Taiwan', 1946, 'Bank of Taiwan'),
            ('Taiwan', 2000, 'Central Bank of China'),
            ('Kiautschou', 1920, 'Japanese Government'),
        ):
            with self.subTest(country=country, year=year):
                self.assertIsNone(self.match(country, year, issuer))

    def test_explicit_historical_names_can_match_without_refiling(self):
        for country, year, key in (
            ('Palestine', 1939, 'british-palestine'),
            ('Newfoundland', 1920, 'british-newfoundland'),
            ('North Borneo', 1939, 'british-british-north-borneo'),
            ('Italian East Africa', 1938, 'italian-italian-east-africa'),
            ('Danish West Indies', 1905, 'danish-danish-west-indies'),
            ('Portuguese India', 1959, 'portuguese-portuguese-india'),
            ('French India', 1936, 'french-french-india'),
            ('Hawaii', 1897, 'other-hawaii'),
            ('Alderney', 1810, 'british-alderney'),
            ('St. Helena', 1976, 'british-saint-helena'),
            ('Faeroe Islands', 2001, 'danish-faroe-islands'),
        ):
            with self.subTest(country=country):
                row = dict(country=country, date_1=year)
                before = dict(row)
                old_classification = filing.row_classification(row)
                self.assertEqual(old_classification['key'], 'other')
                self.assertEqual(entity_for_row(row, old_classification)['key'], key)
                self.assertEqual(row, before)
                self.assertEqual(filing.row_classification(row), old_classification)

    def test_afars_spellings_share_one_french_entity_without_merging_djibouti(self):
        for spelling in ('French Afars & Issas', 'French Afars and Issas',
                         'French Territory of the Afars and the Issas'):
            with self.subTest(spelling=spelling):
                row = dict(country=spelling, date_1=1975, pick_number='P-34', cat_id='B413')
                before = dict(row)
                self.assertEqual(filing.row_classification(row)['key'], 'french')
                entity = entity_for_row(row)
                self.assertEqual(entity['key'], 'french-french-territory-of-the-afars-and-issas')
                self.assertIs(entity['issued'], True)
                self.assertEqual(row, before)
        self.assertIsNone(self.match('Djibouti', 1980, 'Banque Nationale de Djibouti'))
        self.assertEqual(self.key('French Somaliland', 1960), 'french-french-somaliland')

    def test_shared_territories_keep_occupation_and_american_exception_separate(self):
        self.assertEqual(self.key('Burma', 1937, 'Government of Burma'), 'british-burma')
        self.assertEqual(self.key('Burma', 1942, 'Japanese Government'), 'japanese-burma')
        self.assertEqual(self.key('Netherlands Indies', 1944, 'Japanese Government'), 'japanese-netherlands-indies')
        self.assertEqual(self.key('Netherlands Indies', 1930, 'De Javasche Bank'), 'dutch-netherlands-indies')
        for year, issuer in ((1896, 'Banco Español Filipino'), (1943, 'Japanese Government'), (1970, 'Central Bank')):
            self.assertEqual(self.key('Philippines', year, issuer), 'us-philippines')
        self.assertEqual(self.key('Puerto Rico', 1896), 'spanish-puerto-rico')
        self.assertEqual(self.key('Puerto Rico', 1909), 'us-puerto-rico')
        self.assertEqual(self.key('New Hebrides', 1977), 'joint-new-hebrides')
        self.assertEqual(self.key('Canada', 1967), 'british-canada')
        self.assertIn('independent', filing.classify('Canada', 1967)['period'])

    def test_ambiguous_dates_and_issuer_mismatches_are_not_guessed(self):
        for date in (None, '', True, 1940.5, '1939–1945', 1945):
            self.assertIsNone(self.match('Taiwan', date, 'Bank of Taiwan'))
        self.assertIsNone(self.match('Taiwan', 1930, 'Unidentified issuer'))
        self.assertEqual(self.key('Formosa', 1930, 'Bank of Taiwan'), 'japanese-taiwan')
        self.assertEqual(self.key('Kiautschou', 1907, 'Deutsch-Asiatische Bank'), 'german-kiautschou')
        self.assertIsNone(self.match('Kiautschou', 1907, 'Japanese Government'))
        self.assertEqual(self.key('Saint Kitts', 2000, 'Eastern Caribbean Central Bank'),
                         'british-east-caribbean-states')
        self.assertEqual(self.key('Saint Kitts', 1976, 'East Caribbean Currency Authority'),
                         'british-east-caribbean-states')
        self.assertEqual(self.key('Saint Kitts', 1920, 'Colonial Bank'), 'british-saint-kitts')
        self.assertIsNone(self.match('German New Guinea', 1922, 'Reichsbank', 'Commemorative Notgeld'))
        self.assertIsNone(self.match('German New Guinea', 1915, 'Australian Military Administration'))
        self.assertIsNone(self.match('Kuwait', 1961))
        self.assertEqual(self.key('Kuwait', 1961, 'Kuwait Currency Board'), 'british-kuwait')
        self.assertIsNone(self.match('Yemen', 1964, 'Yemen Currency Board'))
        self.assertEqual(self.key('Aden', 1965, 'South Arabian Currency Authority'), 'british-south-arabia')
        for country in ('Palestine', 'Newfoundland', 'Suriname', 'Bahrain', 'Iceland'):
            self.assertIsNone(self.match(country))

    def test_unknown_is_not_nonissuer_and_current_currency_is_not_all_history(self):
        self.assertIs(ENTITY_BY_KEY['british-pitcairn-islands']['issued'], False)
        self.assertIs(ENTITY_BY_KEY['portuguese-nyassa-company']['issued'], None)
        self.assertIs(ENTITY_BY_KEY['german-german-new-guinea']['issued'], None)
        self.assertIs(ENTITY_BY_KEY['british-kenya']['issued'], None)
        self.assertIs(ENTITY_BY_KEY['danish-greenland']['issued'], True)
        self.assertIs(ENTITY_BY_KEY['british-alderney']['issued'], True)
        self.assertIs(ENTITY_BY_KEY['british-gilbert-and-ellice-islands']['issued'], True)
        self.assertIsNone(self.match('Uncatalogued territory', 1920))

    def test_scan_periods_have_explicit_bounds_and_independence_evidence(self):
        for entity in ENTITY_CATALOG:
            with self.subTest(entity=entity['key']):
                period = entity['scan_period']
                if period is not None:
                    self.assertIs(entity['issued'], True)
                    self.assertIs(type(period['year_start']), int)
                    self.assertTrue(period['source'])
                    self.assertTrue(period['note'])
                    end = period['year_end']
                    if end is None:
                        self.assertIn(period['end_kind'], ('continuing_dependency', 'continuing_crown_dependency', 'continuing_kingdom_member'))
                        self.assertIsNone(entity['independence_date'])
                    else:
                        self.assertIs(type(end), int)
                        self.assertGreater(end, period['year_start'])
                if entity['independence_date']:
                    date.fromisoformat(entity['independence_date'])
                    self.assertTrue(entity['independence_source'].startswith('https://'))
                    self.assertEqual(period['end_date'], entity['independence_date'])
                    self.assertLessEqual(period['year_end'], int(entity['independence_date'][:4]))

    def test_independence_and_transfer_are_separate_facts(self):
        afars = ENTITY_BY_KEY['french-french-territory-of-the-afars-and-issas']
        self.assertEqual(afars['independence_date'], '1977-06-27')
        self.assertEqual(afars['scan_period']['year_end'], 1977)
        for key in ('british-british-north-borneo', 'british-sarawak'):
            entry = ENTITY_BY_KEY[key]
            self.assertIsNone(entry['independence_date'])
            self.assertEqual(entry['scan_period']['end_kind'], 'transfer')
            self.assertEqual(entry['scan_period']['end_date'], '1963-09-16')
        self.assertEqual(ENTITY_BY_KEY['british-malaya']['independence_date'], '1957-08-31')
        self.assertEqual(ENTITY_BY_KEY['british-brunei']['independence_date'], '1984-01-01')
        for key in ('british-canada', 'british-australia', 'british-new-zealand'):
            self.assertIsNone(ENTITY_BY_KEY[key]['independence_date'])
            self.assertNotEqual(ENTITY_BY_KEY[key]['scan_period']['end_kind'], 'independence')

    def test_singapore_requires_historic_issuer_and_excludes_national_successor(self):
        self.assertEqual(self.key('Singapore', 1840, 'Union Bank of Calcutta'), 'british-singapore')
        self.assertEqual(self.key('Singapore', 1953, 'Board of Commissioners of Currency, Malaya and British Borneo'), 'british-singapore')
        for year, issuer in ((1965, 'Union Bank of Calcutta'),
                             (1967, 'Board of Commissioners of Currency, Singapore'),
                             (1959, 'Monetary Authority of Singapore'),
                             (1943, 'Japanese Government'), (1953, 'Unidentified issuer')):
            with self.subTest(year=year, issuer=issuer):
                self.assertIsNone(self.match('Singapore', year, issuer))
        self.assertEqual(ENTITY_BY_KEY['british-singapore']['independence_date'], '1965-08-09')

    def test_known_legacy_and_current_dependency_scopes_remain_eligible(self):
        for key in ('british-jersey', 'british-guernsey', 'british-alderney',
                    'british-cayman-islands', 'british-bermuda', 'danish-faroe-islands',
                    'dutch-curacao', 'french-french-oceania',
                    'french-saint-pierre-and-miquelon', 'german-kamerun', 'british-kuwait',
                    'british-british-solomon-islands', 'british-turks-and-caicos-islands',
                    'french-french-polynesia', 'french-dahomey', 'french-french-sudan',
                    'french-upper-senegal-and-niger', 'japanese-hong-kong',
                    'dutch-aruba', 'dutch-netherlands-new-guinea',
                    'belgian-belgian-congo-and-ruanda-urundi', 'belgian-ruanda-urundi'):
            with self.subTest(key=key):
                self.assertIsNotNone(ENTITY_BY_KEY[key]['scan_period'])
        for key in ('british-east-caribbean-states', 'french-west-african-states',
                    'us-united-states', 'us-confederate-states', 'other-hawaii',
                    'portuguese-nyassa-company', 'british-pitcairn-islands',
                    'british-south-africa'):
            with self.subTest(key=key):
                self.assertIsNone(ENTITY_BY_KEY[key]['scan_period'])
        colonial = [entity for entity in ENTITY_CATALOG
                    if entity['countries'][0] in filing.AMERICAN_COLONIES.values()]
        self.assertEqual(len(colonial), 13)
        self.assertTrue(all(entity['scan_period']['year_end'] == 1776 for entity in colonial))

    def test_sqlite_rows_and_supplied_classification_work_without_mutation(self):
        connection = sqlite3.connect(':memory:')
        self.addCleanup(connection.close)
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT 'Cuba' AS country, 1896 AS date_1, 'Banco Español' AS issuer").fetchone()
        classification = filing.row_classification(row)
        before = dict(classification)
        self.assertEqual(entity_for_row(row, classification)['key'], 'spanish-cuba')
        self.assertEqual(classification, before)


if __name__ == '__main__':
    unittest.main()
