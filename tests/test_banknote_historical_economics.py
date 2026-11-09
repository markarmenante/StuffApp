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
                     self.note('Malaya', 'Board of Commissioners of Currency, Malaya', '1 Pound', 1941)]:
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

    def test_additional_reviewed_units_use_their_original_parities(self):
        examples = [
            ('Egypt', 'Egyptian Government (Ministry of Finance)', '10 Piastres', 1917, 'GBP', (40/39)/100),
            ('Egypt', 'National Bank of Egypt', '1 Pound', 1945, 'GBP', 40/39),
            ('Faroe Islands', 'Faroese Government (issued under Faroese banknote law)', '50 Kronur', 2011, 'DKK', 1),
            ('Israel', 'Bank of Israel', '5 Lirot', 1968, 'USD', 1/3.5),
            ('Uganda', 'Bank of Uganda', '5 Shillings', 1966, 'USD', .14),
            ('Italian Somaliland', 'Cassa per la Circolazione Monetaria della Somalia', '1 Somalo (1 Somali)', 1950, 'USD', .14),
            ('Italian Somaliland', 'Cassa per la Circolazione Monetaria della Somalia', '10 Somali', 1950, 'USD', .14),
            ('Yemen', 'South Arabian Currency Authority', '250 Fils', 1965, 'GBP', .001),
            ('Laos', 'Banque Nationale du Laos', '100 Kip', 1957, 'USD', 1/35),
        ]
        for country, issuer, denomination, year, code, factor in examples:
            with self.subTest(country=country, denomination=denomination):
                note = self.note(country, issuer, denomination, year)
                before = copy.deepcopy(note)
                rule = rates.reference(note, year, face.parse(denomination)['unit'])
                self.assertEqual(rule['code'], code)
                self.assertAlmostEqual(rule['factor'], factor)
                value = self.calc(note)
                self.assertIsNotNone(value['at_issue'])
                self.assertIsNone(value['today'])
                self.assertIn('benchmark', value['estimate_basis'])
                self.assertEqual(note, before)
        self.assertIn('80–85', self.calc(self.note('Laos', 'Banque Nationale du Laos', '100 Kip', 1957))['estimate_basis'])

    def test_new_parities_reject_other_issuers_units_and_transition_years(self):
        for note in [self.note('Israel', 'Israel Government', '50 Pruta', 1952),
                     self.note('Israel', 'Bank of Israel', '5 Lirot', 1971),
                     self.note('Yemen', 'South Arabian Currency Authority', '1 Rial', 1965),
                     self.note('Uganda', 'Bank of Uganda', '1 Pound', 1966),
                     self.note('Egypt', 'National Bank of Egypt', '1 Pound', 1947),
                     self.note('Italian Somaliland', 'Italian Government', '1 Lira', 1950),
                     self.note('Faroe Islands', 'Unrelated private bank', '50 Kronur', 2011),
                     self.note('Laos', 'Banque Nationale du Laos', '100 Kip', 1958)]:
            with self.subTest(note=note):
                self.assertIsNone(rates.reference(note, note['date_1'], face.parse(note['denomination'])['unit']))

    def test_greek_prewar_rates_are_paper_drachmas_per_dollar(self):
        for year, rate in [(1914, 5.165), (1926, 79.563), (1935, 108.425)]:
            with self.subTest(year=year):
                note = self.note('Greece', 'National Bank of Greece', '50 Drachmai', year)
                result = self.calc(note)
                cpi = self.data['cpi']['USA']
                expected = 50/rate*cpi['current']['value']/cpi['values'][str(year)]
                self.assertAlmostEqual(result['at_issue'], expected)
                self.assertEqual(result['estimate_kind'], 'historical_fx')
                self.assertIn('Official annual FX ' + str(year), result['data_dates'])

    def test_greek_wartime_price_anchor_keeps_old_drachmas_and_partial_period_visible(self):
        for year, price_index, denomination in [(1941, 309.3, '50 Drachmai'),
                                                (1943, 28613.4, '25000 Drachmai'),
                                                (1944, 1731907751492.3, '100000 Drachmai')]:
            with self.subTest(year=year):
                note = self.note('Greece', 'Bank of Greece (Τράπεζα της Ελλάδος)', denomination, year, issue_type='Military / Occupation')
                result = self.calc(note)
                cpi = self.data['cpi']['USA']
                amount = face.parse(denomination)['amount']
                expected = amount*100.2/price_index/125.09*cpi['current']['value']/cpi['values']['1939']
                self.assertAlmostEqual(result['at_issue'], expected)
                self.assertEqual(result['estimate_kind'], 'historical_price')
                self.assertIn('mean-price', result['estimate_basis'])
                self.assertIn('Reference CPI anchor 1939', result['data_dates'])
                self.assertIsNone(result['today'])
                if year == 1944:
                    self.assertIn('10 November', result['estimate_basis'])
                    self.assertEqual(result['at_issue_display'], '≈ <$0.01')
                modified = copy.deepcopy(self.data)
                modified['cpi']['USA']['values'].pop(str(year), None)
                self.assertEqual(economics.calculate(note, modified, date(2026, 11, 8))['at_issue'], result['at_issue'])
        for note in [self.note('Greece', 'Bank of Greece', '100 Drachmai', 1944),
                     self.note('Greece', 'Bank of Greece', '100000 Drachmai', 1944, series='New drachma post-war'),
                     self.note('Greece', 'Unrelated military issuer', '100000 Drachmai', 1944, issue_type='Occupation')]:
            self.assertIsNone(self.calc(note)['at_issue'])

    def test_confederate_range_uses_gold_dollars_and_uk_cpi_not_greenbacks(self):
        note = self.note('Confederate States of America', 'The Confederate States of America', '10 Dollars', 1864)
        result = self.calc(note)
        rule = rates.reference(note, 1864, 'dollars')
        cpi = self.data['cpi']['GBR']
        factor = 10*cpi['current']['value']/cpi['values']['1864']*self.data['fx']['usd_per_unit']['GBP']
        self.assertAlmostEqual(result['at_issue'][0], factor/(49*4.8665))
        self.assertAlmostEqual(result['at_issue'][1], factor/(18*4.8665))
        self.assertEqual(result['estimate_kind'], 'historical_range')
        self.assertIn('North Carolina', result['estimate_basis'])
        self.assertIn('Gold dollars are not treated as Civil War paper US dollars', result['method'])
        self.assertIsNone(result['today'])
        changed = copy.deepcopy(self.data)
        changed['cpi']['USA']['values']['1864'] = 999999
        self.assertEqual(economics.calculate(note, changed, date(2026, 11, 8))['at_issue'], result['at_issue'])
        self.assertIn('April–December 1864 new issue', ' '.join(result['data_dates']))
        for changes in [dict(issuer='Commonwealth of Virginia Treasury'), dict(issue_type='Counterfeit'), dict(series='Old issue'),
                        dict(country='United States of America'), dict(date_1=1862)]:
            self.assertIsNone(self.calc(dict(note, **changes))['at_issue'])

    def test_chinese_legal_tender_quotes_keep_partial_year_and_currency_distinctions(self):
        for year, rate in [(1937, .296064), (1941, .053133)]:
            note = self.note('China', 'Bank of China (中國銀行)' if year == 1937 else 'Bank of Communications', '100 Yuan', year)
            result = self.calc(note)
            cpi = self.data['cpi']['USA']
            self.assertAlmostEqual(result['at_issue'], 100*rate*cpi['current']['value']/cpi['values'][str(year)])
            self.assertEqual(result['estimate_kind'], 'historical_quote')
            self.assertNotIn('Official annual FX', result['method'])
            if year == 1941:
                self.assertIn('July 25', result['method'])
                self.assertIn('nominal', result['estimate_basis'])
                self.assertTrue(any('July 25' in value for value in result['data_dates']))
        for note in [self.note('China', 'Bank of Communications', '10 Yuan', 1914),
                     self.note('China', 'Imperial Japanese Government', '100 Yen', 1945),
                     self.note('China', 'Bank of China', '100 Yuan', 1941, series='Gold yuan')]:
            self.assertIsNone(self.calc(note)['at_issue'])

    def test_reviewed_annual_rates_and_territorial_units(self):
        for country, issuer, denomination, year, code, factor in [
            ('Greenland', 'Handelsstederne i Grønland', '25 Øre', 1905, 'DKK', .01),
            ('Greenland', 'Styrelsen af Kolonierne i Grønland', '25 Øre', 1913, 'DKK', .01),
            ('Hong Kong', 'The Hongkong & Shanghai Banking Corporation', '1 Dollar', 1935, 'GBP', .0979166666666667),
            ('Hong Kong', 'The Chartered Bank of India, Australia & China', '10 Dollars', 1941, 'USD', .245923),
            ('New Hebrides', "Institut d'Émission d'Outre-Mer", '1000 Francs', 1980, 'USD', 1/68.2921212121666),
            ('Cameroon', "Banque des États de l'Afrique Centrale (BEAC)", '500 Francs', 1983, 'EUR', .02/6.55957),
            ('Burundi', 'Banque du Royaume du Burundi', '5 Francs', 1964, 'USD', .02),
            ('Rwanda-Burundi', "Banque d'Emission du Rwanda et du Burundi", '20 Francs', 1960, 'USD', .02),
            ('Rhodesia and Nyasaland', 'Bank of Rhodesia and Nyasaland', '1 Pound', 1960, 'USD', 2.8),
            ('Rhodesia', 'Reserve Bank of Rhodesia', '5 Pounds', 1966, 'USD', 2.8),
            ('Suriname', 'Government of Suriname', '1 Gulden', 1960, 'USD', 1/1.88585),
            ('Lebanon', 'République Libanaise', '10 Piastres', 1950, 'USD', .01/3.74),
            ('Peru', 'Banco Central de Reserva del Perú', '5 Soles de Oro', 1941, 'USD', 1/6.5),
            ('Peru', 'Banco Central de Reserva del Perú', '5 Soles de Oro', 1960, 'USD', 1/27.31),
            ('Afghanistan', 'Da Afghanistan Bank', '10 Afghanis', 1961, 'USD', 1/43.93),
            ('Cuba', 'Banco Nacional de Cuba', '5 Pesos', 1958, 'USD', 1),
            ('Colombia', 'Banco de la República', '1 Peso', 1954, 'USD', 1/2.5),
        ]:
            with self.subTest(country=country, year=year):
                note = self.note(country, issuer, denomination, year)
                rule = rates.reference(note, year, face.parse(denomination)['unit'])
                self.assertEqual(rule['code'], code)
                self.assertAlmostEqual(rule['factor'], factor)
                self.assertIsNotNone(self.calc(note)['at_issue'])

    def test_iran_import_benchmarks_are_a_disclosed_range_not_formal_parity(self):
        note = self.note('Iran', 'Bank Melli Iran', '20 Rials', 1954)
        result = self.calc(note)
        cpi = self.data['cpi']['USA']
        for actual, rate in zip(result['at_issue'], (90.5, 84.5)):
            self.assertAlmostEqual(actual, 20/rate*cpi['current']['value']/cpi['values']['1954'])
        self.assertIn('not a full-year market minimum/maximum', result['estimate_basis'])
        self.assertIn('August 1954', ' '.join(result['data_dates']))
        self.assertIsNone(result['today'])
        for changed in (dict(issuer='Unrelated private bank'), dict(denomination='20 Tomans'), dict(date_1=1953)):
            self.assertIsNone(self.calc(dict(note, **changed))['at_issue'])

    def test_hk_quote_rejects_occupation_and_benchmarks_do_not_reach_later_units(self):
        base = self.note('Hong Kong', 'The Hongkong & Shanghai Banking Corporation', '5 Dollars', 1941)
        self.assertIn('December 24', self.calc(base)['method'])
        for changes in (dict(date_1=1942), dict(issuer='Japanese Government'),
                        dict(series='Notes issued under duress'), dict(issue_type='Military / Occupation')):
            self.assertIsNone(self.calc(dict(base, **changes))['at_issue'])
        for note in [self.note('New Hebrides', "Institut d'Emission d'Outre-Mer", '1000 Francs CFP', 1980),
                     self.note('Cameroon', "Banque des Etats de l'Afrique Centrale", '500 Francs', 1960),
                     self.note('Burundi', 'Banque du Royaume du Burundi', '5 Francs', 1965),
                     self.note('Peru', 'Banco Central de Reserva del Peru', '5 Intis', 1960),
                     self.note('Rhodesia', 'Reserve Bank of Rhodesia', '1 Dollar', 1966)]:
            self.assertIsNone(self.calc(note)['at_issue'])

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
                     self.note('New Hebrides', "Institut d'Emission d'Outre-Mer", '100 Francs', 1979),
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
