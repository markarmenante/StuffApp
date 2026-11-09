"""Synthetic monetary identities: parity, CPI bases, date and unit boundaries."""
import copy
from datetime import date
import json
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import banknote_economics as economics
import banknote_face_value as face
import banknote_historical_rates as rates


class HistoricalEconomics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads(economics.SEED.read_text())

    def note(self, country, issuer, denomination, year, **kwargs):
        return dict(country=country, issuer=issuer, denomination=denomination, date_1=year, **kwargs)

    def calc(self, note):
        return economics.calculate(note, self.data, date(2026, 11, 8))

    def test_abbreviated_series_ranges_detect_conflicts_without_changing_dates(self):
        note = self.note('French Guiana', "Caisse Centrale de la France d'Outre-Mer", '5 Francs', 2026, series='1947-49 ND Issue')
        original = dict(note)
        self.assertIn('conflicts', self.calc(note)['note'])
        self.assertEqual(note, original)
        self.assertEqual(economics.comparison_dates(dict(note, date_1=1948))['years'], [1948])
        self.assertEqual(economics.comparison_dates(dict(note, date_1='1948-05-10'))['years'], [1948])
        self.assertIn('1971', self.calc(self.note('Malawi', 'Reserve Bank of Malawi', '1 Kwacha', 1964))['note'])

    def test_leading_value_and_units(self):
        for text, amount, unit in [('$2', 2, 'dollars'), ('One Pound (£1)', 1, 'pound'),
                ('1 Pound (20 Shillings)', 1, 'pound'), ('2 Shillings, 6 Pence (Half a Crown)', 2.5, 'shillings'),
                ('Twenty-five Cents', 25, 'cents'), ('1/4 Dinar', .25, 'dinar'), ('2½ Shillings', 2.5, 'shillings'),
                ('100,000 Dollars', 100000, 'dollars'), ('5 Francs = 1 Ariary', 5, 'francs')]:
            with self.subTest(text=text):
                parsed = face.parse(text)
                self.assertEqual((parsed['amount'], parsed['unit']), (amount, unit))
        for text in ['One two dollars', 'One Pound (£2)', '1.000 Dollars', '1,00 Dollars', '2 Shillings 12 Pence', '0 Dollars', '1/0 Dinar']:
            with self.subTest(text=text): self.assertIsNone(face.parse(text))

    def test_same_name_units_do_not_cross_franc_reform_or_german_issuers(self):
        for note in [self.note('France', 'Banque de France', '100 Old Francs', 1960),
                     self.note('France', 'Banque de France', '100 Francs CFA', 1960),
                     self.note('Germany', 'Deutsche Notenbank', '10 Deutsche Mark', 1955),
                     self.note('Germany', 'Staatsbank der DDR', '10 Deutsche Mark', 1975)]:
            with self.subTest(note=note):
                value = self.calc(note)
                self.assertIsNone(value['at_issue'])
                self.assertIsNone(value['today'])

    def test_explicit_currency_prefix_cannot_change_country_identity(self):
        for text in ['HK$2', 'A$2', 'C$2', '£2 Dollars', '€2 Dollars']:
            with self.subTest(text=text):
                self.assertIsNone(self.calc(self.note('United States of America', 'United States Treasury', text, 1917))['at_issue'])
        self.assertIsNotNone(self.calc(self.note('United States of America', 'United States Treasury', 'US$2', 1917))['at_issue'])

    def test_board_parity_and_sourced_method(self):
        for country, issuer, denomination, year, factor in [
            ('British East Africa', 'East African Currency Board', '5 Shillings', 1955, 1/20),
            ('Malaya', 'Board of Commissioners of Currency, Malaya', '10 Cents', 1941, 7/6000),
            ('British Caribbean Territories', 'Currency Board of the British Caribbean Territories (Eastern Group)', '1 Dollar', 1950, 1/4.8),
            ('Fiji', 'Government of Fiji', '1 Pound', 1965, 100/111),
            ('Hong Kong', 'Government of Hong Kong', '1 Dollar', 1946, 1/16),
        ]:
            note = self.note(country, issuer, denomination, year)
            with self.subTest(country=country):
                parsed = face.parse(denomination)
                rule = rates.reference(note, year, parsed['unit'])
                self.assertAlmostEqual(rule['factor'], factor)
                value = self.calc(note)
                self.assertIsNotNone(value['at_issue'])
                self.assertEqual(value['estimate_kind'], 'historical_parity')
                self.assertIn('benchmark', value['estimate_basis'])
                self.assertTrue(value['sources'])

    def test_no_same_name_occupation_or_transition_inheritance(self):
        for note in [self.note('Malaya', 'The Japanese Government', '1 Dollar', 1942),
                     self.note('British East Africa', 'Central Bank of Kenya', '5 Shillings', 1966),
                     self.note('Fiji', 'Government of Fiji', '1 Pound', 1969),
                     self.note('Malaya', 'Board of Commissioners of Currency, Malaya', '1 Pound', 1941),
                     self.note('Hong Kong', 'Government of Hong Kong', '1 Dollar', 1935)]:
            with self.subTest(note=note):
                self.assertIsNone(rates.reference(note, note['date_1'], face.parse(note['denomination'])['unit']))

    def test_worldbank_annual_fx_resolves_peg_transition_without_guessing_one_peg(self):
        note = self.note('Hong Kong', 'Government of Hong Kong', '1 Dollar', 1967)
        rule = rates.reference(note, 1967, 'dollar')
        self.assertEqual(rule['kind'], 'historical_fx')
        expected = 1/rates.historical_fx_data()['rates']['HKG']['1967']
        self.assertAlmostEqual(rule['factor'], expected)
        self.assertIsNone(rates.worldbank_reference(self.note('Nigeria', 'Central Bank of Nigeria', '1 Pound', 1965), 1965, 'pound'))
        self.assertIsNone(rates.worldbank_reference(self.note('Solomon Islands', 'Japanese Government', '1 Dollar', 1977), 1977, 'dollar'))

    def test_macau_bnu_uses_actual_annual_pataca_rate(self):
        for year in (1968, 1981, 1992):
            note = self.note('Macau', 'Banco Nacional Ultramarino', '5 Patacas', year)
            result = self.calc(note)
            self.assertIsNotNone(result['at_issue'])
            self.assertEqual(result['estimate_kind'], 'historical_fx')
            rule = rates.reference(note, year, 'patacas')
            self.assertAlmostEqual(rule['factor'], 1/rates.historical_fx_data()['rates']['MAC'][str(year)])
        self.assertIsNone(self.calc(self.note('Macau', 'Banco Nacional Ultramarino', '5 Patacas', 1945))['at_issue'])

    def test_worldbank_date_range_evaluates_each_annual_rate(self):
        note = self.note('Mauritius', 'Bank of Mauritius', '5 Rupees', '1967–1968')
        result = self.calc(note)
        self.assertIsInstance(result['at_issue'], list)
        singles = [self.calc(dict(note, date_1=year))['at_issue'] for year in (1967, 1968)]
        self.assertEqual(result['at_issue'], [min(singles), max(singles)])
        self.assertEqual(result['estimate_kind'], 'historical_fx')

    def test_new_zealand_explicit_old_pounds_convert_at_statutory_rate(self):
        note = self.note('New Zealand', 'Reserve Bank of New Zealand', '1 Pound', 1967)
        rule = rates.reference(note, 1967, 'pound')
        self.assertEqual((rule['code'], rule['factor']), ('NZD', 2))
        value = self.calc(note)
        self.assertIsNotNone(value['at_issue'])
        self.assertIn('no sterling parity', value['estimate_basis'])

    def test_philippine_official_parity_not_observed_local_cpi(self):
        value = self.calc(self.note('Philippines', 'Philippine National Bank', '2 Pesos', 1921))
        self.assertIsNotNone(value['at_issue'])
        self.assertIsNone(value['today'])
        self.assertIn('official parity', value['estimate_basis'])
        self.assertIn('discounts', value['estimate_basis'])
        value = self.calc(self.note('Philippines', 'The Japanese Government', '2 Pesos', 1943))
        self.assertIsNone(value['at_issue'])

    def test_cpi_rebase_has_exact_common_anchor_and_no_mutation(self):
        original = copy.deepcopy(self.data['cpi']['CAN'])
        extended, used = rates.cpi_values('CAN', original)
        historical = rates.historical_data()['cpi']['CAN']
        self.assertTrue(used)
        self.assertEqual(extended['2010'], original['values']['2010'])
        self.assertAlmostEqual(extended['1935']/extended['2010'], historical['1935']/historical['2010'])
        self.assertEqual(original, self.data['cpi']['CAN'])
        value = self.calc(self.note('Canada', 'Bank of Canada', '1 Dollar', 1935))
        self.assertIsNotNone(value['at_issue'])
        self.assertEqual(value['estimate_kind'], 'domestic_cpi')
        self.assertTrue(any('macrohistory' in s['url'] for s in value['sources']))

    def test_franc_parities_do_not_merge_comoros_or_new_hebrides(self):
        for note in [self.note('Comoros', 'Banque de Madagascar et des Comores', '100 Francs', 1995),
                     self.note('New Hebrides', "Institut d'Emission d'Outre-Mer", '100 Francs', 1980),
                     self.note('France', 'Unrelated private issuer', '100 Francs', 1944)]:
            self.assertIsNone(rates.reference(note, note['date_1'], 'francs'))
        cfa = rates.reference(self.note('French West Africa', "Banque de l'Afrique Occidentale", '100 Francs', 1954), 1954, 'francs')
        self.assertAlmostEqual(cfa['factor'], 2/100/6.55957)
        old = rates.reference(self.note('French West Africa', "Banque de l'Afrique Occidentale", '100 Francs', 1942), 1942, 'francs')
        self.assertAlmostEqual(old['factor'], 1/100/6.55957)

    def test_explicit_cfa_and_cfp_conflicts_remain_unavailable(self):
        for note in [self.note('French West Africa', "Banque de l'Afrique Occidentale", '100 Francs CFP', 1954),
                     self.note('French Polynesia', "Institut d'Emission d'Outre-Mer", '100 Francs CFA', 1973)]:
            self.assertIsNone(self.calc(note)['at_issue'])

    def test_us_ordinary_dollar_survives_military_catalogue_label(self):
        note = self.note('United States of America', 'United States Treasury', '1 Silver Dollar ($1)', 1886, issue_type='Military / Occupation')
        value = self.calc(note)
        self.assertEqual(value['estimate_kind'], 'domestic_cpi')
        self.assertIsNotNone(value['at_issue'])
        note['series'] = 'Military Payment Certificate'
        self.assertIsNone(self.calc(note)['at_issue'])

    def test_private_bank_face_claim_is_not_nominal_today(self):
        note = self.note('United States of America', 'Example State Bank', '$5', 1857, issue_type='Private / Scrip')
        value = self.calc(note)
        self.assertIsNotNone(value['at_issue'])
        self.assertIsNone(value['today'])
        self.assertIn('before issuer credit discounts', value['estimate_basis'])

    def test_colonial_shilling_relationships_are_local(self):
        for country, issuer, year, factor, code in [
            ('New Jersey Colony', 'Colony of New Jersey', 1776, 1/7.5, 'USD'),
            ('North Carolina Colony', 'Province of North Carolina', 1771, .5625/20, 'GBP')]:
            note = self.note(country, issuer, '1 Shilling', year)
            rule = rates.reference(note, year, 'shilling')
            self.assertAlmostEqual(rule['factor'], factor)
            self.assertEqual(rule['code'], code)
            value = self.calc(note)
            self.assertIsNotNone(value['at_issue'])
            self.assertIsNone(value['today'])


if __name__ == '__main__': unittest.main()
