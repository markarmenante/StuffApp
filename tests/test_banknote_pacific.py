"""Regional presentation preserves territorial catalogue identity and saved facts."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-pacific-')
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
import banknote_catalog as catalog
import banknote_entities as entities
import app as stuff


class PacificTests(unittest.TestCase):
    def setUp(self):
        self.context = stuff.app.app_context()
        self.context.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknotes')
        self.db.commit()

    def tearDown(self):
        self.context.pop()

    def add(self, ident, country, issuer, denom, pick, year, **extra):
        row = dict(id=ident, country=country, issuer=issuer, denomination=denom,
                   pick_number=pick, date_1=year, status='Ordered', cat_id='B'+ident,
                   price='$599.89', image_1='front.jpg', image_2='reverse.jpg',
                   serial_number='123456', slab_number='777777-001', notes='Preserve me')
        row.update(extra)
        self.db.execute('INSERT INTO banknotes (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', list(row.values()))
        self.db.commit()

    def rows(self):
        return self.db.execute('SELECT * FROM banknotes ORDER BY ' + stuff.CATEGORY_ORDER_BY['banknotes']).fetchall()

    def fixture(self):
        self.add('307', 'New Caledonia', "Banque de l'Indochine Nouméa", '5 Francs', 'P-48, TBB 321', 1944)
        self.add('351', 'New Caledonia', "Banque de l'Indochine Nouméa", '20 Francs', 'P49', 1944)
        self.add('414', 'New Caledonia', "Banque de l'Indochine (Nouméa branch)", '20 Francs', 'P-50c, KM#414c; The Banknote Book B325', 1963)
        self.add('404', 'French Pacific Territories', 'IEOM', '500 Francs', 'P1e', 1992)
        self.add('428', 'Tahiti', 'IEOM', '100 Francs', 'P24b', 1973)
        self.add('366', 'New Hebrides', 'IEOM', '1000 Francs', 'P20c', 1980)

    def test_real_types_group_and_order_without_editing_facts(self):
        self.fixture()
        before = {row['id']: dict(row) for row in self.rows()}
        rows = self.rows()
        self.assertEqual([r['id'] for r in rows], ['428', '307', '351', '414', '404', '366'])
        self.assertEqual(catalog.row_classification(rows[-1])['key'], 'joint')
        for history in ('0', '1'):
            html = stuff.app.test_client().get('/banknotes?history=' + history).get_data(as_text=True)
            self.assertEqual(html.count('data-banknote-family="french-pacific"'), 1)
            for text in ('1944 Australian-printed issue', '1951–1963 type',
                         'Issued: 5, 20 francs', 'Issued: 20 francs',
                         'Issued: 100, 500, 1,000, 5,000 francs',
                         'Issued: 500, 1,000, 5,000, 10,000 francs'):
                self.assertIn(text, html)
            self.assertLess(html.index('data-banknote-family-end="french-pacific"'), html.index('id="item-366"'))
        self.assertEqual(before, {row['id']: dict(row) for row in self.rows()})

    def test_no_country_rewrite_or_common_issue_inference(self):
        for country in ('Tahiti', 'French Oceania', 'French Polynesia'):
            self.assertEqual(catalog.canonical_country(country), country)
            self.assertEqual(catalog.french_pacific_issue(country, 1992, 'IEOM')['branch'], 'polynesia')
        for country in (None, '', 'Oceania', 'France', 'French Indo-China', 'New Hebrides'):
            self.assertIsNone(catalog.french_pacific_issue(country, 1992, 'IEOM'))
        wrong = catalog.french_pacific_issue('New Caledonia', 1944, "Banque de l'Indochine Papeete")
        self.assertEqual(wrong['issuer_key'], 'unresolved')
        self.assertNotIn('denoms', wrong)
        self.assertEqual(catalog.french_pacific_issue('French Pacific Territories', 1986, 'IEOM')['branch'], 'common')

    def test_scoped_rosters_require_unambiguous_pick_and_compatible_date(self):
        base = dict(country='New Caledonia', issuer="Banque de l'Indochine Nouméa", date_1=1944)
        for ref in ('P48', 'Pick #48', 'P-48, TBB 321', '48'):
            self.assertEqual(catalog.collection_family_for_row(dict(base, pick_number=ref))['denoms'], '5, 20 francs')
        for ref in ('B48', 'P48 or P49', 'P48 / P50c', 'P148', '48 or 49'):
            self.assertNotIn('denoms', catalog.collection_family_for_row(dict(base, pick_number=ref)))
        self.assertNotIn('denoms', catalog.collection_family_for_row(dict(base, pick_number='P48', date_1=1951)))
        self.assertEqual(catalog.collection_family_for_row(dict(base, pick_number='P50c, KM#414c; The Banknote Book B325', date_1=1963))['denoms'], '20 francs')

    def test_report_preserves_territory_and_distinct_type_and_unresolved_issuer(self):
        self.fixture()
        sections = stuff._banknote_report_sections(self.db)
        self.assertEqual([key for _, key, _ in sections[:4]], [
            'french-pacific-polynesia-ieom', 'french-pacific-new-caledonia-bdi-1944',
            'french-pacific-new-caledonia-bdi-p50', 'french-pacific-common-ieom'])
        self.assertEqual([len(rows) for _, _, rows in sections], [1, 2, 1, 1, 1])
        for title, key, rows in sections[:4]:
            self.assertEqual(stuff._banknote_report_history(title, key, rows)[0], title)
            self.assertIn(rows[0]['country'], stuff._banknote_report_lines(rows[0])[0])
        self.add('u1', 'Tahiti', 'Unidentified Bank A', '1 Franc', 'P1', 1920)
        self.add('u2', 'Tahiti', 'Unidentified Bank B', '1 Franc', 'P1', 1920)
        unknown = [(title, key) for title, key, _ in stuff._banknote_report_sections(self.db) if 'unresolved' in str(key)]
        self.assertEqual(len(unknown), 2)
        self.assertNotEqual(unknown[0][1], unknown[1][1])

    def test_lineage_coverage_merges_only_pills_and_gap_retirement(self):
        self.add('tahiti', 'Tahiti', 'IEOM', '100 Francs', 'P24b', 1973)
        self.add('polynesia', 'French Polynesia', 'IEOM', '500 Francs', 'P25b', 1980)
        with stuff.app.test_request_context('/banknotes'):
            stuff.g.current_user = {'role': 'owner'}
            pills = {p['key']: p for p in stuff.banknote_entity_pills(self.db, self.rows())['french']}
        self.assertNotIn('french-french-polynesia', pills)
        self.assertEqual(pills['french-french-oceania']['label'], 'Tahiti / French Polynesia')
        self.assertIn('2 notes', pills['french-french-oceania']['title'])
        self.assertIn('does not claim', pills['french-french-oceania']['title'])
        self.assertNotIn('french-french-oceania', {e['key'] for e in stuff._banknote_wantlist_open(self.db)})
        self.assertEqual(entities.ENTITY_BY_KEY['french-french-polynesia']['scan_period']['year_start'], 1957)
        self.db.execute("UPDATE banknotes SET status='Sold'"); self.db.commit()
        self.assertIn('french-french-oceania', {e['key'] for e in stuff._banknote_wantlist_open(self.db)})

    def test_catalogue_matching_still_requires_country_namespace_and_full_suffix(self):
        self.add('tahiti', 'Tahiti', 'IEOM', '100 Francs', 'P1e', 1973)
        for country, reference, match in (('Tahiti', 'P1e', True), ('Tahiti', 'P1a', False),
                ('Tahiti', 'B1e', False), ('New Caledonia', 'P1e', False),
                ('French Pacific Territories', 'P1e', False), ('French Polynesia', 'P1e', False)):
            result = stuff._market_collection_matches(self.db, {'country': country, 'pick_number': reference})
            self.assertEqual(bool(result), match, (country, reference))

    def test_collection_search_finds_lineage_without_expanding_other_territories(self):
        for ident, country in (('t', 'Tahiti'), ('o', 'French Oceania'), ('p', 'French Polynesia'),
                               ('nc', 'New Caledonia'), ('common', 'French Pacific Territories')):
            self.add(ident, country, 'IEOM', '100 Francs', 'P1a', 1973)
        for query in ('Tahiti', 'French Oceania', 'French Polynesia'):
            sql, params = stuff.build_search_query('banknotes', query)
            self.assertEqual({r['id'] for r in self.db.execute(sql, params)}, {'t', 'o', 'p'})

    def test_african_successors_do_not_cover_colonial_territories(self):
        self.add('togo', 'Togo', 'BCEAO', '1000 Francs', 'P104T', 1959)
        self.add('cameroon', 'Cameroon', 'BEAC', '1000 Francs', 'P21c', 1983)
        self.add('bceao-date', 'Senegal', 'BCEAO', '100 Francs', 'P101A', 1958)
        keys = {entities.entity_for_row(row)['key'] for row in self.rows()}
        self.assertEqual(keys, {'french-west-african-states', 'french-central-african-states'})
        self.assertIsNone(entities.ENTITY_BY_KEY['french-central-african-states']['scan_period'])
        with stuff.app.test_request_context('/banknotes'):
            stuff.g.current_user = {'role': 'owner'}
            pills = {p['key']: p for p in stuff.banknote_entity_pills(self.db, self.rows())['french']}
        self.assertEqual(pills['french-central-african-states']['coverage'], 'held')
        self.assertEqual(pills['french-cameroon']['coverage'], 'missing')
        self.assertFalse(any(k.startswith('french-record-cameroon') for k in pills))
        for history in ('0', '1'):
            html = stuff.app.test_client().get('/banknotes?history=' + history).get_data(as_text=True)
            self.assertIn('Review date: saved 1958', html)
            self.assertIn('Review territorial date: Togo joined', html)

    def test_distinct_families_close_and_reopen_in_arbitrary_order(self):
        self.fixture()
        self.add('caribbean', 'East Caribbean States', 'ECCA', '1 Dollar', 'P13a', 1965)
        rows = {r['id']: r for r in self.rows()}
        placed = stuff.banknote_grouping([rows['428'], rows['caribbean'], rows['307'], rows['366']])
        for ident in ('428', 'caribbean', '307'):
            self.assertTrue(placed[ident]['regional_heading'])
            self.assertTrue(placed[ident]['regional_end'])
        self.assertNotIn('regional', placed['366'])

    def test_v32_migration_only_changes_position_once(self):
        self.fixture()
        self.db.execute("UPDATE banknotes SET banknote_id='P 999'")
        self.db.execute("DELETE FROM migration_state WHERE key='banknote_display_number_v32'")
        self.db.commit()
        before = {r['id']: dict(r) for r in self.rows()}
        stuff.init_db()
        self.assertEqual([r['banknote_id'] for r in self.rows()], [f'P {i:03}' for i in range(1, 7)])
        for row in self.rows():
            self.assertEqual({k:v for k,v in dict(row).items() if k != 'banknote_id'},
                             {k:v for k,v in before[row['id']].items() if k != 'banknote_id'})
        with patch.object(stuff, '_renumber_banknotes', wraps=stuff._renumber_banknotes) as renumber:
            stuff.init_db()
        renumber.assert_not_called()


if __name__ == '__main__':
    unittest.main()
