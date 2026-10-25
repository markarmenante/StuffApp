"""Evidence-backed roster completeness and conservative historical matching."""
import ast
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

    def test_unique_evidence_bearing_roster_with_explicit_three_state_issuance(self):
        self.assertEqual(len(ENTITY_CATALOG), len(ENTITY_BY_KEY))
        self.assertEqual(len(ENTITY_CATALOG), 193)
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
            ('French Afars and Issas', 1970, 'french-french-territory-of-the-afars-and-issas'),
        ):
            with self.subTest(country=country):
                row = dict(country=country, date_1=year)
                before = dict(row)
                old_classification = filing.row_classification(row)
                self.assertEqual(old_classification['key'], 'other')
                self.assertEqual(entity_for_row(row, old_classification)['key'], key)
                self.assertEqual(row, before)
                self.assertEqual(filing.row_classification(row), old_classification)

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
        self.assertIsNone(self.match('Saint Kitts', 2000, 'Eastern Caribbean Central Bank'))
        self.assertIsNone(self.match('Saint Kitts', 1976, 'East Caribbean Currency Authority'))
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
