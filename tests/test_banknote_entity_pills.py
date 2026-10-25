"""Historical-entity coverage and navigation use the authorized whole collection."""
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from html.parser import HTMLParser
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-entity-pills-')
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import app as stuff


class Pills(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.pills, self.targets, self.regions = {}, set(), []
        self.feed(html)

    def handle_starttag(self, tag, attributes):
        attrs = dict(attributes)
        if attrs.get('data-entity-key'):
            self.pills[attrs['data-entity-key']] = dict(attrs, tag=tag)
        if 'item-row' in attrs.get('class', '').split():
            self.targets.add(attrs['id'])
        if 'banknote-entity-pills' in attrs.get('class', '').split():
            self.regions.append(attrs)


class EntityPillTests(unittest.TestCase):
    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknotes')
        self.db.commit()
        self.client = stuff.app.test_client()

    def tearDown(self):
        self.ctx.pop()

    def note(self, ident, country='India', year=1930, status='Own', issuer='', **fields):
        row = dict(id=ident, country=country, date_1=year, status=status,
                   issuer=issuer, denomination='5 Dollars', **fields)
        columns = ','.join(row)
        self.db.execute(f"INSERT INTO banknotes({columns}) VALUES({','.join('?' for _ in row)})", list(row.values()))
        self.db.commit()

    def page(self, path='/banknotes?history=0', headers=None):
        response = self.client.get(path, headers=headers or {})
        self.assertEqual(response.status_code, 200)
        return Pills(response.get_data(as_text=True))

    def test_heading_pills_and_exact_targets_survive_history_toggle(self):
        self.note('india')
        for history in ('0', '1'):
            page = self.page('/banknotes?history=' + history)
            pill = page.pills['british-india']
            self.assertEqual((pill['tag'], pill['data-coverage'], pill['href']),
                             ('a', 'held', '#item-india'))
            self.assertIn(pill['href'][1:], page.targets)
            self.assertIn('includes owned and pending purchases', pill['aria-label'])
            self.assertTrue(all(region['tabindex'] == '0' for region in page.regions))

    def test_coverage_counts_all_purchase_phases_but_no_disposed_notes(self):
        for index, status in enumerate(('Own', 'Owned', '', None, 'Ordered', 'Shipped', 'Delivered',
                                        'Sold', 'Gifted', 'Lost', 'Consigned', 'Loaned')):
            self.note(str(index), status=status)
        self.assertIn('7 notes', self.page().pills['british-india']['title'])
        self.db.execute("DELETE FROM banknotes WHERE status IS NULL OR status IN ('Own','Owned','','Ordered','Shipped','Delivered')")
        self.db.commit()
        pill = self.page().pills['british-india']
        self.assertEqual((pill['tag'], pill['data-coverage']), ('span', 'missing'))
        self.assertNotIn('href', pill)

    def test_north_borneo_coverage_links_shared_board_notes_and_explains_basis(self):
        issuer = 'Board of Commissioners of Currency, Malaya and British Borneo'
        self.note('board-1953', country='Malaya and British Borneo', year=1953,
                  status='Delivered', issuer=issuer, description='Earlier board note')
        self.note('board-1959', country='Malaya and British Borneo', year=1959,
                  status='Ordered', issuer=issuer, description='Later board note')
        for history in ('0', '1'):
            page = self.page('/banknotes?history=' + history)
            pill = page.pills['british-british-north-borneo']
            self.assertEqual(pill['data-coverage'], 'held')
            self.assertIn('2 notes', pill['title'])
            self.assertIn('shared Malaya and British Borneo', pill['title'])
            self.assertIn(pill['href'], ('#item-board-1953', '#item-board-1959'))
            self.assertIn(pill['href'][1:], page.targets)
        page = self.page('/banknotes?history=0&filter=ordered')
        self.assertEqual(page.pills['british-british-north-borneo']['href'], '#item-board-1959')
        self.db.execute("UPDATE banknotes SET status='Sold'")
        self.db.commit()
        self.assertEqual(self.page().pills['british-british-north-borneo']['data-coverage'], 'missing')

    def test_search_and_status_filters_keep_whole_collection_coverage_with_live_fallback(self):
        self.note('india-owned', description='Distinct owned note')
        self.note('canada-ordered', country='Canada', year=1954, status='Ordered', description='Visible order')
        for path in ('/banknotes?history=0&filter=ordered', '/banknotes?history=0&q_banknotes=Visible'):
            page = self.page(path)
            pill = page.pills['british-india']
            self.assertEqual(pill['data-coverage'], 'held')
            self.assertNotIn('item-india-owned', page.targets)
            link = urlsplit(pill['href'])
            self.assertEqual(parse_qs(link.query), {'filter': ['heritage_british'], 'history': ['0']})
            self.assertEqual(link.fragment, 'item-india-owned')
            target = self.page(pill['href'])
            self.assertIn(link.fragment, target.targets)
            self.assertEqual(page.pills['british-canada']['href'], '#item-canada-ordered')

    def test_visible_held_match_is_preferred_without_changing_current_filters(self):
        self.note('india-own', status='Own')
        self.note('india-order', status='Ordered')
        page = self.page('/banknotes?filter=ordered&q_banknotes=India&history=0')
        self.assertEqual(page.pills['british-india']['href'], '#item-india-order')
        self.assertEqual(page.targets, {'item-india-order'})

    def test_cross_group_identity_uses_targets_existing_filing_for_hidden_navigation(self):
        self.note('palestine-mandate', country='Palestine', year=1939)
        self.note('canada-order', country='Canada', year=1954, status='Ordered')
        original_group = stuff.banknote_catalog.classify('Palestine', 1939)['key']
        self.assertEqual(original_group, 'other')
        page = self.page('/banknotes?filter=ordered&history=0')
        pill = page.pills['british-palestine']
        self.assertEqual(pill['data-coverage'], 'held')
        target = urlsplit(pill['href'])
        self.assertEqual(parse_qs(target.query)['filter'], ['heritage_other'])
        self.assertIn('item-palestine-mandate', self.page(pill['href']).targets)
        self.assertEqual(self.db.execute("SELECT country FROM banknotes WHERE id='palestine-mandate'").fetchone()[0], 'Palestine')

    def test_successor_and_occupation_holdings_do_not_credit_another_administration(self):
        self.note('spanish-marker', country='Puerto Rico', year=1890)
        self.note('cuban-republic', country='Cuba', year=1958, issuer='Banco Nacional de Cuba')
        self.note('british-marker', country='Canada', year=1954)
        self.note('occupied', country='Burma', year=1944, issuer='The Japanese Government')
        page = self.page()
        self.assertEqual(page.pills['spanish-cuba']['data-coverage'], 'missing')
        self.assertEqual(page.pills['british-burma']['data-coverage'], 'missing')

    def test_neutral_requires_known_nonissuer_and_unknown_is_explicit(self):
        self.note('india')
        fixture = (
            dict(key='fixture-none', group='british', label='No separate issues', countries=('Fixture no issues',), issued=False, note=''),
            dict(key='fixture-unknown', group='british', label='Unknown issuance', countries=('Fixture unknown',), issued=None, note=''),
        )
        with patch.object(stuff.banknote_entities, 'ENTITY_CATALOG', fixture):
            page = self.page()
        self.assertEqual(page.pills['fixture-none']['data-coverage'], 'nonissuer')
        self.assertEqual(page.pills['fixture-unknown']['data-coverage'], 'unknown')
        self.assertIn('not yet established', page.pills['fixture-unknown']['title'])
        self.assertNotIn('href', page.pills['fixture-none'])

    def test_pitcairn_is_a_documented_nonissuer_without_a_collection_link(self):
        self.note('india')
        pill = self.page().pills['british-pitcairn-islands']
        self.assertEqual((pill['tag'], pill['data-coverage']), ('span', 'nonissuer'))
        self.assertIn('Did not issue its own banknotes', pill['title'])
        self.assertNotIn('href', pill)

    def test_row_access_restrictions_apply_to_coverage_and_navigation(self):
        self.note('restricted-india')
        self.note('visible-canada', country='Canada', year=1954)
        self.db.execute("INSERT OR REPLACE INTO users(id,email,display_name,role,categories,row_filters) VALUES(?,?,?,?,?,?)",
                        ('entity-viewer', 'entity-viewer@example.test', 'Viewer', 'viewer', 'banknotes',
                         json.dumps({'banknotes': {'country': ['Canada']}})))
        self.db.commit()
        page = self.page(headers={'Cf-Access-Authenticated-User-Email': 'entity-viewer@example.test'})
        self.assertEqual(page.pills['british-india']['data-coverage'], 'missing')
        self.assertNotIn('href', page.pills['british-india'])
        self.assertEqual(page.pills['british-canada']['href'], '#item-visible-canada')
        self.assertEqual(page.targets, {'item-visible-canada'})
        self.assertEqual(self.page().pills['british-india']['data-coverage'], 'held')

    def test_rendering_preserves_rows_numbering_sort_and_unrelated_pages(self):
        self.note('india', cat_id='B123', banknote_id='P 456', image_1='fixture.png', price='$17.29')
        self.note('canada', country='Canada', year=1954, cat_id='B124', banknote_id='P 457')
        before = [dict(row) for row in self.db.execute('SELECT * FROM banknotes ORDER BY id')]
        ordered = [row['id'] for row in self.db.execute('SELECT * FROM banknotes ORDER BY ' + stuff.CATEGORY_ORDER_BY['banknotes'])]
        page = self.page()
        self.assertEqual(page.targets, {'item-india', 'item-canada'})
        self.assertEqual(before, [dict(row) for row in self.db.execute('SELECT * FROM banknotes ORDER BY id')])
        self.assertEqual(ordered, [row['id'] for row in self.db.execute('SELECT * FROM banknotes ORDER BY ' + stuff.CATEGORY_ORDER_BY['banknotes'])])
        self.assertFalse(self.page('/coins').pills)
        self.assertFalse(self.page('/banknotes/market').pills)


if __name__ == '__main__':
    unittest.main()
