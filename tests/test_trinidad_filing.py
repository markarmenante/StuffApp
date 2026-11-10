"""Trinidad spelling, colonial filing, coverage and saved-position recovery."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-trinidad-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER'):
    os.environ[name] = '0'

import banknote_catalog as catalog
import banknote_entities as entities
import app as stuff


class TrinidadFilingTests(unittest.TestCase):
    COUNTRY = 'Trinidad and Tobago'
    ALIAS = 'Trinidad & Tobago'
    BOARD = 'Currency Board of the British Caribbean Territories (Eastern Group)'
    MIGRATION = 'banknote_display_number_v41'

    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknotes')
        self.db.commit()

    def tearDown(self):
        self.ctx.pop()

    def add(self, ident, year, **fields):
        row = dict(id=ident, country=self.ALIAS, date_1=year,
                   issuer='Government of Trinidad and Tobago', denomination='1 Dollar',
                   status='Delivered', cat_id='B-' + ident, banknote_id='P 999',
                   pick_number='P-7b', price='$121.39', image_1='front.jpg', image_2='back.jpg',
                   serial_number='A123456', slab_number='1234567-001', notes='Preserve me',
                   purchase_date='2026-10-01', order_number='12-34567-89012')
        row.update(fields)
        self.db.execute('INSERT INTO banknotes (' + ','.join(row) + ') VALUES (' +
                        ','.join('?' for _ in row) + ')', tuple(row.values()))

    def seed(self):
        self.add('tt1939', 1939, issuer='The Government of Trinidad and Tobago')
        self.add('tt1943', 1943)
        self.add('ttmodern', 1977, issuer='Central Bank of Trinidad and Tobago')
        self.add('ttundated', None)
        self.db.commit()

    def records(self):
        return {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')}

    def filtered(self, query, group):
        sql, params = stuff.build_search_query('banknotes', query, coin_filter='heritage_' + group)
        return self.db.execute(sql, params).fetchall()

    def test_spelling_and_dates_file_the_actual_government_issues_as_british(self):
        for country in (self.COUNTRY, self.ALIAS):
            self.assertEqual(catalog.canonical_country(country), self.COUNTRY)
            for year in (1905, 1939, 1943, 1961):
                for issuer in ('Government of Trinidad and Tobago', 'The Government of Trinidad and Tobago'):
                    row = dict(country=country, date_1=year, issuer=issuer)
                    with self.subTest(**row):
                        info = catalog.row_classification(row)
                        self.assertEqual(info['key'], 'british')
                        self.assertFalse(info['uncertain'])
                        self.assertEqual(entities.entity_for_row(row)['key'], 'british-trinidad-and-tobago')
        self.assertEqual(catalog.canonical_country('Trinidad'), 'Trinidad')
        self.assertEqual(catalog.canonical_country('Tobago'), 'Tobago')
        self.assertEqual(stuff._coerce_banknote_spec('country', self.ALIAS), self.COUNTRY)

    def test_later_or_uncertain_notes_do_not_fill_colonial_coverage(self):
        for year, issuer in ((1963, 'Government of Trinidad and Tobago'),
                             (1964, 'Central Bank of Trinidad and Tobago'),
                             (1943, 'Central Bank of Trinidad & Tobago'),
                             (None, 'Government of Trinidad and Tobago')):
            row = dict(country=self.ALIAS, date_1=year, issuer=issuer)
            with self.subTest(**row):
                self.assertEqual(catalog.row_classification(row)['key'], 'other')
                self.assertIsNone(entities.entity_for_row(row))
        boundary = dict(country=self.COUNTRY, date_1=1962, issuer='Government of Trinidad and Tobago')
        self.assertTrue(catalog.row_classification(boundary)['uncertain'])
        self.assertIsNone(entities.entity_for_row(boundary))

    def test_alias_search_filters_report_and_held_pill_agree_without_writes(self):
        self.seed()
        before = self.records()
        client = stuff.app.test_client()
        with patch.object(stuff, 'ensure_country_history'):
            for query in ('Trinidad', self.COUNTRY, self.ALIAS):
                for group, expected in (('british', ['tt1939', 'tt1943']),
                                        ('other', ['ttmodern', 'ttundated'])):
                    rows = self.filtered(query, group)
                    self.assertEqual([r['id'] for r in rows], expected)
                    sections = stuff._banknote_report_sections(self.db, {'q': query, 'filter': 'heritage_' + group})
                    self.assertEqual(len(sections), 1)
                    self.assertEqual(catalog.canonical_country(sections[0][0]), self.COUNTRY)
                    self.assertEqual([r['id'] for r in sections[0][2]], expected)
                    for history in ('0', '1'):
                        response = client.get('/banknotes', query_string={
                            'q': query, 'filter': 'heritage_' + group, 'history': history})
                        self.assertEqual(response.status_code, 200)
                        html = response.get_data(as_text=True)
                        for ident in before:
                            self.assertEqual('id="item-' + ident + '"' in html, ident in expected)
        with stuff.app.test_request_context('/banknotes'):
            groups = stuff.banknote_entity_pills(self.db, self.filtered('Trinidad', 'british'))
        pill = next(p for p in groups['british'] if p['key'] == 'british-trinidad-and-tobago')
        self.assertEqual(pill['coverage'], 'held')
        self.assertIn('2 notes', pill['status'])
        self.assertEqual(pill['href'], '#item-tt1939')
        self.assertEqual(before, self.records())

    def test_startup_audits_country_and_resequences_once_preserving_other_facts(self):
        self.seed()
        self.add('kgvi', 1950, country='British Caribbean Territories', issuer=self.BOARD,
                 pick_number='P-1', series='1950–1952 King George VI issue')
        self.add('qeii', 1956, country='British Caribbean Territories', issuer='British Caribbean Currency Board',
                 series='1953–1964 Elizabeth II issue')
        self.db.execute('DELETE FROM migration_state WHERE key=?', (self.MIGRATION,))
        self.db.commit()
        before = self.records()
        with patch.object(stuff, '_renumber_banknotes', wraps=stuff._renumber_banknotes) as renumber:
            stuff.init_db()
        self.assertEqual(renumber.call_count, 1)
        after = self.records()
        for ident, row in before.items():
            ignored = {'banknote_id'}
            if row['country'] == self.ALIAS:
                ignored.update(('country', 'updated_at'))
                self.assertEqual(after[ident]['country'], self.COUNTRY)
            self.assertEqual({k: v for k, v in row.items() if k not in ignored},
                             {k: v for k, v in after[ident].items() if k not in ignored})
        audit = self.db.execute('SELECT original_country, canonical_country FROM banknote_country_alias_history').fetchall()
        self.assertEqual([tuple(row) for row in audit], [(self.ALIAS, self.COUNTRY)] * 4)
        rows = self.db.execute('SELECT * FROM banknotes ORDER BY ' + stuff.CATEGORY_ORDER_BY['banknotes']).fetchall()
        self.assertEqual([r['banknote_id'] for r in rows], [f'P {i:03d}' for i in range(1, 7)])
        self.assertEqual([r['id'] for r in rows[:4]], ['kgvi', 'qeii', 'tt1939', 'tt1943'])
        sections = stuff._banknote_report_sections(self.db, {'q': self.ALIAS, 'filter': 'heritage_british'})
        self.assertEqual([(title, [r['id'] for r in group]) for title, _, group in sections],
                         [(self.COUNTRY, ['tt1939', 'tt1943'])])
        with patch.object(stuff, '_renumber_banknotes') as renumber:
            stuff.init_db()
        renumber.assert_not_called()
        self.assertEqual(after, self.records())
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_country_alias_history').fetchone()[0], 4)

    def test_failed_position_migration_rolls_back_and_can_retry(self):
        self.add('tt1943', 1943, country=self.COUNTRY)
        self.db.execute('DELETE FROM migration_state WHERE key=?', (self.MIGRATION,))
        self.db.commit()
        before = self.records()

        def fail_after_update(db):
            db.execute("UPDATE banknotes SET banknote_id='P 001'")
            raise sqlite3.OperationalError('synthetic interrupted renumber')

        with patch.object(stuff, '_renumber_banknotes', side_effect=fail_after_update):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'synthetic interrupted renumber'):
                stuff.init_db()
        self.assertEqual(before, self.records())
        self.assertIsNone(self.db.execute('SELECT 1 FROM migration_state WHERE key=?', (self.MIGRATION,)).fetchone())
        stuff.init_db()
        self.assertEqual(self.records()['tt1943']['banknote_id'], 'P 001')


if __name__ == '__main__':
    unittest.main()
