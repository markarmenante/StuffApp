"""Open-ended colonial/occupation eligibility, with isolated metadata and listings.

The .example URLs and catalogue references below are controlled test fixtures,
not historical source verification. No model, provider, or live scan is called.
"""
import copy
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='market-administrations-')
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff
import market_colonial as policy


def candidate(country='Philippines', year=1943, empire='Japanese',
              kind='military occupation', start=1942, end=1945,
              name='Japanese occupation of the Philippines',
              issuer='Japanese Government', **changes):
    item = dict(
        title=f'{country} {year} banknote PMG 64 EPQ', country=country,
        year=year, date_1=year, empire=empire, theme='colonial-worldwide',
        issuer=issuer, pick_number='P-110', denomination='10 Pesos',
        issue_year_start=year, issue_year_end=year,
        issue_date_source='https://catalogue.example/issue/110',
        administration=dict(kind=kind, name=name, territory=country,
                            year_start=start, year_end=end,
                            source='https://museum.example/administrations/issue-110',
                            evidence=f'Test catalogue identifies this {issuer} issue under {name}.'),
        grading_authority='PMG', grade_numeric=64, grade='Choice UNC 64',
        designation='EPQ', price='$150', listing_url='https://dealer.example/item/110',
        sale_type='fixed', venue='Fixture dealer', rarity='', fills='')
    item.update(changes)
    return item


class AdministrationTests(unittest.TestCase):
    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.addCleanup(self.ctx.pop)
        self.db = stuff.get_db()
        for table in ('market_scan_items', 'market_scans', 'market_dismissals', 'banknotes'):
            self.db.execute('DELETE FROM ' + table)
        self.db.commit()
        # A mistaken fetch must fail, never become a provider/network request.
        guard = patch('socket.socket.connect', side_effect=AssertionError('Network is forbidden in this suite'))
        guard.start()
        self.addCleanup(guard.stop)

    def save(self, item, ident='offer', status='new'):
        self.db.execute("INSERT OR IGNORE INTO market_scans "
                        "(id,category,status,started_at,finished_at) "
                        "VALUES ('admin-scan','banknotes','done',datetime('now'),datetime('now'))")
        self.db.execute("INSERT INTO market_scan_items "
                        "(id,scan_id,category,status,payload,created_at) "
                        "VALUES (?,'admin-scan','banknotes',?,?,datetime('now'))",
                        (ident, status, json.dumps(item)))
        self.db.commit()
        return self.db.execute('SELECT * FROM market_scan_items WHERE id=?', (ident,)).fetchone()

    def normalize(self, item):
        return stuff._market_normalize_item(self.db, 'banknotes', item)

    def test_japanese_territories_and_allied_occupation(self):
        for country in ('Philippines', 'Burma', 'Malaya', 'Netherlands Indies'):
            with self.subTest(country=country):
                item = candidate(country=country, name='Japanese occupation of ' + country)
                self.assertEqual(policy.problem(item), '')
                self.assertIn('military occupation', policy.administration_label(item))
                self.assertTrue(policy.problem(dict(item, administration={})))
        korea = candidate(country='Korea', year=1938, kind='colony', start=1910,
                          name='Japanese administration of Korea', issuer='Bank of Chosen')
        self.assertEqual(policy.problem(korea), '')
        for country, year, start, end in (('Germany', 1944, 1944, 1948),
                                          ('Italy', 1943, 1943, 1947),
                                          ('Japan', 1946, 1945, 1952)):
            with self.subTest(country=country):
                item = candidate(country=country, year=year, start=start, end=end,
                                 empire='Allied', issuer='Allied Military Authority',
                                 name='Allied military administration of ' + country)
                self.assertEqual(policy.problem(item), '')
                self.assertTrue(policy.problem(dict(item, administration={})))

    def test_unlisted_administrations_and_all_supported_relationships(self):
        # Deliberately not in a finite country table: eligibility follows the
        # supplied issue/admin evidence rather than membership in that table.
        unknown = 'Fixture Island Protectorate'
        self.assertNotIn(unknown, policy.PERIODS)
        for kind in ('colony', 'protectorate', 'mandate', 'trust territory',
                     'dependency', 'condominium', 'leased territory', 'client state'):
            with self.subTest(kind=kind):
                item = candidate(country=unknown, year=1930, start=1900, end=1950,
                                 kind=kind, empire='Danish', issuer='Territorial Currency Board',
                                 name='Fixture joint administration')
                self.assertEqual(policy.problem(item), '')
                self.assertTrue(policy.problem(dict(item, administration={})))
        for country, kind, year, start, end, name, issuer in (
            ('Brunei', 'protectorate', 1967, 1888, 1984, 'British protectorate of Brunei', 'Government of Brunei'),
            ('Palestine', 'mandate', 1939, 1920, 1948, 'British Mandate for Palestine', 'Palestine Currency Board'),
            ('Faroe Islands', 'dependency', 1974, 1948, 2026, 'Danish administration of the Faroe Islands', 'Danmarks Nationalbank'),
            ('New Hebrides', 'condominium', 1975, 1906, 1980, 'Anglo-French New Hebrides', 'Institut d Emission d Outre-Mer'),
        ):
            with self.subTest(country=country):
                self.assertEqual(policy.problem(candidate(country, year, 'Joint', kind, start, end, name, issuer)), '')

    def test_british_america_and_domestic_us_remain_distinct(self):
        item = candidate(country='United States', year=1773, empire='British', kind='colony',
                         start=1664, end=1776, name='British Province of New York',
                         issuer='Colony of New York', pick_number='', other_catalog='Newman NY-166')
        self.assertEqual(policy.problem(item), '')
        self.assertIn('British Province of New York', policy.administration_label(item))
        self.assertTrue(policy.problem(dict(item, administration={})))
        domestic = dict(country='United States', date_1=1886, theme='us-large-treasury', empire='')
        self.assertEqual(policy.problem(domestic), '')

    def test_required_sources_identity_and_relationship(self):
        base = candidate()
        mutations = [
            ('administration source missing', ('administration', 'source'), ''),
            ('administration source invalid', ('administration', 'source'), 'https:///missing-host'),
            ('administration source not web', ('administration', 'source'), 'file:///tmp/catalogue'),
            ('administration source has credentials', ('administration', 'source'), 'https://user@museum.example/issue'),
            ('issue source missing', ('issue_date_source',), ''),
            ('issue source invalid', ('issue_date_source',), 'not a URL'),
            ('evidence missing', ('administration', 'evidence'), ''),
            ('name missing', ('administration', 'name'), ''),
            ('unknown relationship', ('administration', 'kind'), 'foreign printer'),
            ('mismatched territory', ('administration', 'territory'), 'Burma'),
            ('issuer missing', ('issuer',), ''),
            ('catalogue missing', ('pick_number',), ''),
        ]
        for label, path, value in mutations:
            with self.subTest(label=label):
                changed = copy.deepcopy(base)
                target = changed if len(path) == 1 else changed[path[0]]
                target[path[-1]] = value
                self.assertTrue(policy.problem(changed))
                self.assertIsNone(self.normalize(changed))
        # Additional catalogue namespaces are valid, without fabricating Pick.
        self.assertEqual(policy.problem(dict(base, pick_number='', other_catalog='TBB B-110')), '')

    def test_date_ranges_are_required_ordered_and_within_administration(self):
        cases = [
            ('issue_year_start', None), ('issue_year_end', None),
            ('issue_year_start', '1943.5'), ('issue_year_end', True),
            ('issue_year_start', 1944), ('issue_year_end', 1941),
            ('issue_year_start', 1499), ('issue_year_end', 2101),
        ]
        for key, value in cases:
            with self.subTest(key=key, value=value):
                self.assertTrue(policy.problem(candidate(**{key: value})))
        for start, end in ((None, 1945), (1942, None), (1946, 1942),
                           (1499, 1945), (1942, 2101), (1942.5, 1945),
                           (1944, 1945), (1942, 1942)):
            with self.subTest(start=start, end=end):
                self.assertTrue(policy.problem(candidate(start=start, end=end)))
        # Issue-specific source evidence permits a known boundary year.
        self.assertEqual(policy.problem(candidate(year=1945)), '')

    def test_successors_and_explicit_later_reissues_cannot_use_admin_metadata(self):
        for changes in ({'issuer': 'Central Bank of the Philippines'},
                        {'title': 'Republic of the Philippines banknote'},
                        {'issuer': 'BCEAO'}, {'issuer': 'BEAC'},
                        {'title': 'Philippines 1943 issue, reissue 1948 PMG 64 EPQ'},
                        {'series': 'Overprint 1948'}):
            with self.subTest(changes=changes):
                self.assertTrue(policy.problem(candidate(**changes)))
        congo = candidate(country='Belgian Congo', year=1955, empire='Belgian', kind='colony',
                          start=1908, end=1960, name='Belgian Congo',
                          issuer='Banque Centrale du Congo Belge et du Ruanda-Urundi')
        self.assertEqual(policy.problem(congo), '')

    def test_victory_exception_still_has_its_own_label(self):
        item = dict(country='Philippines', date_1=1949, empire='US',
                    theme='colonial-worldwide', title='Philippine Victory overprint 1949',
                    issuer='Central Bank of the Philippines', pick_number='P-121')
        self.assertEqual(policy.problem(item), '')
        self.assertIn('post-independence', policy.victory_label(item))
        self.assertTrue(policy.problem(dict(item, pick_number='P-200')))

    def test_source_theme_or_missing_empire_cannot_bypass_administration_evidence(self):
        for theme in ('ebay-personalized', 'denominations', 'pattern', 'sources'):
            with self.subTest(theme=theme):
                item = candidate(empire='', theme=theme)
                self.assertEqual(policy.problem(item), '')
                self.assertIsNotNone(self.normalize(item))
                item['administration']['source'] = ''
                self.assertTrue(policy.problem(item))
                self.assertIsNone(self.normalize(item))

    def test_manchukuo_identity_is_resolved_before_administration_gate(self):
        item = candidate(country='China', year=1938, empire='Japanese', kind='client state',
                         start=1932, end=1945, name='Manchukuo', issuer='Central Bank of Manchukuo',
                         title='Manchukuo 1938 banknote PMG 64 EPQ')
        for territory in ('China', 'Manchukuo'):
            item['administration']['territory'] = territory
            normalized = self.normalize(item)
            self.assertIsNotNone(normalized)
            self.assertEqual(normalized['country'], 'Manchukuo')
            self.assertEqual(normalized['administration']['territory'], 'Manchukuo')

    def test_worldwide_discovery_survives_finite_wantlist_and_equal_priority(self):
        themes = dict(stuff._MARKET_POLICIES['banknotes'].themes(self.db))
        self.assertTrue(any(key.startswith('entity-gap-') for key in themes))
        self.assertIn('colonial-japanese', themes)
        self.assertIn('colonial-worldwide', themes)
        self.assertIn('fixed want-list', themes['colonial-worldwide'])
        for key in ('colonial-british', 'colonial-continental', 'colonial-japanese', 'colonial-worldwide'):
            self.assertNotIn('leave missing-issuer coverage', themes[key])
            self.assertNotIn('issuers already held', themes[key])
        scores = {empire: stuff._market_score('banknotes', candidate(empire=empire))
                  for empire in ('British', 'French', 'Dutch', 'Belgian', 'Spanish',
                                 'Japanese', 'Danish', 'Allied', 'Unlisted administration')}
        self.assertEqual(len(set(scores.values())), 1, scores)

    def test_normalize_store_render_and_action_preserve_administration(self):
        item = self.normalize(candidate())
        self.assertIsNotNone(item)
        self.assertEqual(item['administration'], candidate()['administration'])
        row = self.save(item)
        reloaded = stuff._market_items(self.db, 'banknotes')
        self.assertEqual([note['id'] for note in reloaded], ['offer'])
        label = 'Japanese occupation of the Philippines · military occupation'
        self.assertEqual(reloaded[0]['issue_label'], label)
        response = stuff.app.test_client().get('/banknotes/market')
        self.assertEqual(response.status_code, 200)
        self.assertIn(label, response.get_data(as_text=True))
        probe = dict(state='live', title=item['title'], why='fixture buy control')
        with patch.object(stuff, '_market_listing_probe', return_value=probe):
            self.assertFalse(stuff._market_action_problem(self.db, row, item))
        with patch.object(stuff, '_market_listing_probe') as fetch:
            self.assertFalse(stuff._market_action_problem(self.db, row, item, already_paid=True))
            fetch.assert_not_called()
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0], 0)

    def test_saved_bad_evidence_is_hidden_and_blocks_actions(self):
        bad = candidate(administration={})
        row = self.save(bad)
        with patch.object(stuff, '_market_listing_probe') as fetch:
            self.assertTrue(stuff._market_action_problem(self.db, row, bad, already_paid=True))
            fetch.assert_not_called()
        self.assertEqual(stuff._market_items(self.db, 'banknotes'), [])
        self.assertEqual(self.db.execute("SELECT status FROM market_scan_items WHERE id='offer'").fetchone()[0], 'unavailable')

    def test_grade_nonissued_and_exact_listing_gates_remain(self):
        self.assertIsNotNone(self.normalize(candidate(grade_numeric=63, grade='Choice UNC 63')))
        self.assertIsNone(self.normalize(candidate(grade_numeric=58, grade='AU 58')))
        rare = candidate(grade_numeric=50, grade='AU 50', rarity='Fixture PMG census: 3 graded')
        self.assertIsNotNone(self.normalize(rare))
        self.assertIsNone(self.normalize(dict(rare, grade_numeric=45, grade='XF 45')))
        for changes in ({'grading_authority': '', 'grade_numeric': None, 'grade': 'UNC', 'title': 'Ungraded banknote'},
                        {'title': 'Philippines raw banknote, PMG 64 potential'},
                        {'title': 'Philippines ungraded banknote, PCGS 64 estimate'},
                        {'description': 'Not graded; suggested PMG 64'},
                        {'title': 'Philippines 1943 specimen PMG 64 EPQ'},
                        {'pick_number': 'P-110s'}, {'grade': 'Choice UNC 64 NET'},
                        {'listing_url': 'https://dealer.example/inventory'}):
            with self.subTest(changes=changes):
                self.assertIsNone(self.normalize(candidate(**changes)))
        self.assertIsNotNone(self.normalize(candidate(title='Philippines PMG 64 EPQ, not raw')))
        self.assertIsNone(self.normalize(candidate(title='Philippines contemporary counterfeit PMG 64')))
        for description in ('Original note with an anti-counterfeit background.',
                            'Counterfeit protection includes a watermark.'):
            self.assertIsNotNone(self.normalize(candidate(description=description)))

    def test_live_verification_still_rejects_ended_and_unverified_ebay(self):
        url = 'https://www.ebay.com/itm/123456789012'
        item = self.normalize(candidate(listing_url=url))
        self.assertIsNotNone(item)
        for state in ('ended', 'unknown', 'live'):
            with self.subTest(state=state):
                def listing_state(unused_url):
                    stuff._MARKET_LAST_PROBE.probe = {'state': state, 'title': item['title'], 'why': 'fixture'}
                    return state
                with patch.object(stuff, '_market_listing_state', side_effect=listing_state):
                    result = stuff._market_verify_live([copy.deepcopy(item)], workers=1)
                self.assertEqual(len(result), 1 if state == 'live' else 0)
                if result:
                    self.assertTrue(result[0]['verified'])

    def test_fresh_listing_evidence_rechecks_administration_before_display_and_action(self):
        item = self.normalize(candidate())
        row = self.save(item)
        probe = dict(state='live', title='Philippines reissue 1948 PMG 64 EPQ', why='fixture buy control')

        def listing_state(unused_url):
            stuff._MARKET_LAST_PROBE.probe = probe
            return 'live'

        # Isolate the administration recheck: generic identity comparison is
        # separately tested and must not be the reason this regression passes.
        with patch.object(stuff, '_market_listing_identity_problem', return_value=''):
            with patch.object(stuff, '_market_listing_state', side_effect=listing_state):
                self.assertEqual(stuff._market_verify_live([copy.deepcopy(item)], workers=1), [])
            with patch.object(stuff, '_market_listing_probe', return_value=probe):
                self.assertTrue(stuff._market_action_problem(self.db, row, item))
        self.assertEqual(self.db.execute("SELECT status FROM market_scan_items WHERE id='offer'").fetchone()[0], 'unavailable')

    def test_owned_and_ordered_catalogue_matches_warn_without_hiding(self):
        for ident, status in (('held', 'Own'), ('pending', 'Ordered')):
            self.db.execute('INSERT INTO banknotes (id,country,pick_number,status) VALUES (?,?,?,?)',
                            (ident, 'Philippines', 'P-110', status))
        self.db.commit()
        item = self.normalize(candidate())
        self.assertIsNotNone(item)
        self.save(item)
        visible = stuff._market_items(self.db, 'banknotes')
        self.assertEqual(len(visible), 1)
        self.assertEqual({match['id'] for match in visible[0]['collection_matches']}, {'held', 'pending'})
        html = stuff.app.test_client().get('/banknotes/market').get_data(as_text=True)
        self.assertIn('Already in your collection', html)
        self.assertIn('(ordered)', html)
        self.assertIn('same catalogue reference', html)


if __name__ == '__main__':
    unittest.main()
