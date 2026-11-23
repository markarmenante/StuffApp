"""Danish West Indies colonial filing, including undated Treasury remainders."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-danish-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER'):
    os.environ[name] = '0'

import app as stuff
import banknote_catalog as catalog
import banknote_entities as entities


class DanishFilingTests(unittest.TestCase):
    MIGRATION = 'banknote_display_number_v44'

    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknotes')
        self.db.commit()

    def tearDown(self):
        self.ctx.pop()

    def add(self, ident='remainder', **fields):
        row = dict(id=ident, country='Danish West Indies', date_1=None,
                   issuer='State Treasury', denomination='2 Dalere', series='1898',
                   pick_number='P-8r', issue_type='Remainder', cat_id='B501',
                   banknote_id='P 413', status='Ordered', price='$123.45',
                   image_1='front.jpg', image_2='back.jpg', notes='Preserve notes',
                   serial_number='', slab_number='1234567-001', grade='64',
                   purchase_date='2026-11-22', order_number='12-34567-89012')
        row.update(fields)
        self.db.execute('INSERT INTO banknotes (' + ','.join(row) + ') VALUES (' +
                        ','.join('?' for _ in row) + ')', tuple(row.values()))
        self.db.commit()

    def records(self):
        return {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')}

    def test_historic_identity_establishes_colonial_filing_even_without_a_date(self):
        for year in (None, '', 'ND', 1849, 1860, 1898, 1905, 1917):
            for issuer in ('State Treasury', 'Bank of St. Thomas', 'Danish West Indian Bank', ''):
                with self.subTest(year=year, issuer=issuer):
                    row = dict(country='Danish West Indies', date_1=year, issuer=issuer)
                    before = dict(row)
                    info = catalog.row_classification(row)
                    self.assertEqual(info['key'], 'danish')
                    self.assertEqual(info['period'], 'Danish colonial administration')
                    self.assertFalse(info['uncertain'])
                    self.assertEqual(entities.entity_for_row(row)['key'], 'danish-danish-west-indies')
                    self.assertEqual(row, before)

    def test_modern_virgin_islands_and_unrelated_treasury_notes_stay_distinct(self):
        for country in ('United States Virgin Islands', 'US Virgin Islands',
                        'Virgin Islands', 'British Virgin Islands', 'Denmark', 'Cyprus'):
            with self.subTest(country=country):
                self.assertNotEqual(catalog.classify(country, 1961, 'State Treasury')['key'], 'danish')
        self.assertEqual(catalog.classify('Cyprus', 1961, 'Republic of Cyprus')['key'], 'other')

    def test_list_report_and_held_pill_agree_and_preserve_the_remainder(self):
        self.add()
        before = self.records()
        client = stuff.app.test_client()
        with patch.object(stuff, 'ensure_country_history'):
            for history in ('0', '1'):
                response = client.get('/banknotes', query_string={
                    'filter': 'heritage_danish', 'history': history})
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                self.assertIn('id="item-remainder"', html)
                self.assertIn('Danish colonial administration', html)
                other = client.get('/banknotes?filter=heritage_other&history=' + history).get_data(as_text=True)
                self.assertNotIn('id="item-remainder"', other)
        sections = stuff._banknote_report_sections(self.db, {'filter': 'heritage_danish'})
        self.assertEqual([(title, [r['id'] for r in rows]) for title, _, rows in sections],
                         [('Danish West Indies', ['remainder'])])
        with stuff.app.test_request_context('/banknotes'):
            groups = stuff.banknote_entity_pills(self.db, self.db.execute('SELECT * FROM banknotes').fetchall())
        pill = next(p for p in groups['danish'] if p['key'] == 'danish-danish-west-indies')
        self.assertEqual(pill['coverage'], 'held')
        self.assertEqual(pill['href'], '#item-remainder')
        self.assertEqual(before, self.records())

    def test_startup_moves_positions_once_without_changing_catalogue_or_purchase(self):
        self.add()
        self.add('cyprus', country='Cyprus', date_1=1961, issuer='Republic of Cyprus',
                 cat_id='B004', pick_number='P-37a', series='1961', banknote_id='P 411')
        self.db.execute('DELETE FROM migration_state WHERE key=?', (self.MIGRATION,))
        self.db.commit()
        before = self.records()
        with patch.object(stuff, '_renumber_banknotes', wraps=stuff._renumber_banknotes) as renumber:
            stuff.init_db()
        self.assertEqual(renumber.call_count, 1)
        after = self.records()
        self.assertEqual(after['remainder']['banknote_id'], 'P 001')
        self.assertEqual(after['cyprus']['banknote_id'], 'P 002')
        for ident, row in before.items():
            self.assertEqual({k: v for k, v in row.items() if k != 'banknote_id'},
                             {k: v for k, v in after[ident].items() if k != 'banknote_id'})
        with patch.object(stuff, '_renumber_banknotes') as renumber:
            stuff.init_db()
        renumber.assert_not_called()
        self.assertEqual(after, self.records())

    def test_interrupted_position_migration_rolls_back_and_can_retry(self):
        self.add()
        self.db.execute('DELETE FROM migration_state WHERE key=?', (self.MIGRATION,))
        self.db.commit()
        before = self.records()

        def fail_after_update(db):
            db.execute("UPDATE banknotes SET banknote_id='P 001'")
            raise sqlite3.OperationalError('interrupted renumber')

        with patch.object(stuff, '_renumber_banknotes', side_effect=fail_after_update):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'interrupted renumber'):
                stuff.init_db()
        self.assertEqual(before, self.records())
        self.assertIsNone(self.db.execute('SELECT 1 FROM migration_state WHERE key=?', (self.MIGRATION,)).fetchone())
        stuff.init_db()
        self.assertEqual(self.records()['remainder']['banknote_id'], 'P 001')


if __name__ == '__main__':
    unittest.main()
