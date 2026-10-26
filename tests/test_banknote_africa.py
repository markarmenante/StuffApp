"""African filing must unify issuer aliases without erasing territorial facts."""
import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from banknote_africa import regional_issue


BCEAO = "Banque Centrale des États de l'Afrique de l'Ouest (BCEAO)"
BEAC = "Banque des États de l'Afrique Centrale (BEAC)"
BAO = "Banque de l'Afrique Occidentale"
CCFOM = "Caisse Centrale de la France d'Outre-Mer"
INSTITUTE = "Institut d'Emission de l'Afrique Equatoriale Française et du Cameroun"


class AfricaFamilyTests(unittest.TestCase):
    def test_actual_bceao_country_variants_share_authority_but_keep_attribution(self):
        cases = (
            ('West African States', 1965, BCEAO, 'P-2b'),
            ('West African States (Senegal)', 1959, BCEAO.replace('États', 'Etats'), 'P-702Kn'),
            ('Togo', 1959, BCEAO, 'P-803Tn'),
            ('Togo', 1992, BCEAO, 'P-808Tm'),
            ('West African States', 1958, BCEAO, 'P-1'),
        )
        for country, year, issuer, pick in cases:
            with self.subTest(country=country, pick=pick):
                original = dict(country=country, date=year, issuer=issuer,
                                series='S.195 T' if pick == 'P-803Tn' else None,
                                pick=pick, price='$599.89', serial='A12345', image='front.jpg')
                snapshot = copy.deepcopy(original)
                value = regional_issue(*(original[k] for k in ('country', 'date', 'issuer', 'series')))
                self.assertEqual((value['family_key'], value['key']), ('west-african-franc', 'bceao'))
                self.assertEqual(value['catalogue_scope'], country)
                self.assertEqual(value['entity_country'], 'West African States')
                self.assertEqual(original, snapshot)

    def test_predecessor_bao_is_a_distinct_section_and_western_scope(self):
        bao = regional_issue('French West Africa', 1942, BAO)
        bceao = regional_issue('West African States', 1965, BCEAO)
        self.assertEqual(bao['family_key'], bceao['family_key'])
        self.assertNotEqual(bao['key'], bceao['key'])
        self.assertLess(bao['rank'], bceao['rank'])
        for country in (None, 'Cameroon', 'French Equatorial Africa', 'Madagascar'):
            self.assertIsNone(regional_issue(country, 1930, BAO))

    def test_central_successive_issuers_remain_three_sections(self):
        cases = (
            ('French Equatorial Africa', 1944, CCFOM, 'ccfom'),
            ('French Equatorial Africa', 1957, INSTITUTE, 'ieaefc'),
            ('Cameroon', 1983, BEAC, 'beac'),
        )
        values = [regional_issue(country, year, issuer) for country, year, issuer, _ in cases]
        self.assertEqual([v['key'] for v in values], [case[3] for case in cases])
        self.assertEqual({v['family_key'] for v in values}, {'central-african-franc'})
        self.assertEqual([v['rank'] for v in values], sorted(v['rank'] for v in values))
        self.assertEqual(values[-1]['catalogue_scope'], 'Cameroon')
        self.assertEqual(values[-1]['entity_country'], 'Central African States')
        self.assertIn('independent states', values[-1]['history'])
        self.assertEqual(values[0]['entity_country'], 'French Equatorial Africa')

    def test_exact_accent_spelling_aliases_are_bounded(self):
        self.assertEqual(regional_issue('Cameroun', 1983, BEAC)['key'], 'beac')
        self.assertEqual(regional_issue('Cameroon', 1983, 'Banque des Etats de l Afrique Centrale')['key'], 'beac')
        self.assertEqual(regional_issue('French Equatorial Africa', 1957,
                         'Institut d’Émission de l’Afrique Équatoriale Française et du Cameroun')['key'], 'ieaefc')
        for issuer in ('BCEAO commercial subsidiary', 'BCEAO / BEAC',
                       'Banque de l’Afrique Occidentale et du Cameroun', 'Unknown bank'):
            self.assertIsNone(regional_issue('West African States', 1965, issuer))

    def test_shared_french_issuer_never_absorbs_unrelated_territory(self):
        for country in (None, '', 'French Antilles', 'Guadeloupe', 'Martinique',
                        'Réunion', 'French Somaliland', 'French West Africa',
                        'Equatorial Guinea', 'Democratic Republic of the Congo',
                        'Belgian Congo', 'Congo'):
            with self.subTest(country=country):
                self.assertIsNone(regional_issue(country, 1944, CCFOM))
        for country in ('British West Africa', 'Ghana', 'British East Africa', 'Kenya', 'Atlantis'):
            self.assertIsNone(regional_issue(country, 1965, BCEAO))
        self.assertIsNone(regional_issue('West African States - Atlantis', 1965, BCEAO))
        self.assertIsNone(regional_issue('Central African States (Atlantis)', 1983, BEAC))

    def test_british_and_independent_national_issuers_are_unchanged(self):
        for country, year, issuer in (
            ('British East Africa', 1943, 'The East African Currency Board'),
            ('British East Africa', 1956, 'East African Currency Board'),
            ('British West Africa', 1930, 'West African Currency Board'),
            ('Kenya', 1982, 'Central Bank of Kenya'),
            ('Uganda', 1966, 'Bank of Uganda'),
            ('Rhodesia', 1964, 'Reserve Bank of Rhodesia'),
            ('Rhodesia and Nyasaland', 1960, 'Bank of Rhodesia and Nyasaland'),
            ('Rhodesia and Nyasaland', 1955, 'Central African Currency Board'),
            ('Gambia', 1965, 'The Gambia Currency Board'),
            ('Mali', 1962, 'Banque de la République du Mali'),
            ('Equatorial Guinea', 1969, 'Banco Central'),
            ('Togo', 1959, 'Trésor Public'),
        ):
            with self.subTest(country=country, issuer=issuer):
                self.assertIsNone(regional_issue(country, year, issuer))

    def test_regional_issuer_can_resolve_blank_or_issuer_country_but_not_conflict(self):
        for issuer, key in ((BCEAO, 'bceao'), (INSTITUTE, 'ieaefc'), (BEAC, 'beac')):
            for country in (None, issuer):
                self.assertEqual(regional_issue(country, None, issuer)['key'], key)
            self.assertEqual(regional_issue(issuer, None, '')['key'], key)
        self.assertIsNone(regional_issue(BCEAO, 1965, 'Private Bank'))
        self.assertIsNone(regional_issue(BCEAO, 1965, BEAC))
        self.assertIsNone(regional_issue(None, 1944, CCFOM))
        self.assertIsNone(regional_issue('West African States', 1965, None))

    def test_known_chronology_issues_are_review_notes_not_rewritten_dates(self):
        value = regional_issue('West African States', 1958, BCEAO)
        self.assertIn('saved 1958', value['review_note'])
        self.assertIn('creation in 1959', value['review_note'])
        self.assertEqual(value['key'], 'bceao')
        for country in ('Togo', 'West African States (Togo)', 'West African States - Togo'):
            value = regional_issue(country, 1959, BCEAO)
            self.assertIn('Togo joined UMOA in December 1963', value['review_note'])
            self.assertIn('saved 1959', value['review_note'])
        self.assertNotIn('review_note', regional_issue('Togo', 1992, BCEAO))
        self.assertNotIn('review_note', regional_issue('West African States', '1958–1965', BCEAO))
        self.assertNotIn('review_note', regional_issue('West African States', None, BCEAO, '1958'))
        self.assertIn('1985', regional_issue('Equatorial Guinea', 1983, BEAC)['review_note'])

    def test_issued_denominations_are_documented_rosters_not_held_values(self):
        cases = (
            ('French West Africa', BAO, '5, 10, 25, 50, 100, 500, 1,000, 5,000 francs'),
            ('West African States', BCEAO, '50, 100, 500, 1,000, 2,000, 2,500, 5,000, 10,000 francs'),
            ('French Equatorial Africa', CCFOM, '5, 10, 20, 50, 100, 500, 1,000, 5,000 francs'),
            ('French Equatorial Africa', INSTITUTE, '5, 10, 20, 50, 100, 500, 1,000 francs'),
            ('Cameroon', BEAC, '500, 1,000, 2,000, 5,000, 10,000 francs'),
        )
        for country, issuer, denominations in cases:
            self.assertEqual(regional_issue(country, None, issuer)['denoms'], denominations)
        self.assertIn('modified', regional_issue('French Equatorial Africa', 1957, INSTITUTE)['denoms_note'])
        self.assertIn('2003', regional_issue('West African States', 1965, BCEAO)['denoms_note'])

    def test_fresh_metadata_cannot_mutate_later_results(self):
        first = regional_issue('Togo', 1992, BCEAO)
        first['title'] = 'changed'
        first['catalogue_scope'] = 'changed'
        later = regional_issue('West African States', 1965, BCEAO)
        self.assertEqual(later['title'], 'West African States — BCEAO')
        self.assertEqual(later['catalogue_scope'], 'West African States')


if __name__ == '__main__':
    unittest.main()
