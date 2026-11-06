"""Saved Bahrain rows share filing, coverage, analysis and display positions."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
# Import-time migrations and workers must never use a collection database.
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-bahrain-integration-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER'):
    os.environ[name] = '0'

import app as stuff


class BahrainIntegrationTests(unittest.TestCase):
    PERIOD = 'British administrative control — protected state'
    BOARD = 'Bahrain Currency Board'
    MIGRATION = 'banknote_display_number_v39'

    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknotes')
        self.db.commit()

    def tearDown(self):
        self.ctx.pop()

    def add(self, ident, year, issuer=BOARD, **fields):
        row = dict(id=ident, country='Bahrain', date_1=year, issuer=issuer,
                   denomination='1 Dinar', status='Own')
        row.update(fields)
        self.db.execute(
            'INSERT INTO banknotes (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')',
            tuple(row.values()))

    def seed(self):
        # These catalogue shapes also occur in saved collections. 1964 is the
        # authorization year; classification must not rewrite it to 1965.
        for ident, denomination, pick, cat in (
                ('authorization-100', '100 Fils', 'P-1a', 'CAT-100'),
                ('authorization-quarter', '1/4 Dinar', 'P-2a', 'CAT-200'),
                ('authorization-half', '1/2 Dinar', 'P-3', 'CAT-300'),
                ('authorization-one', '1 Dinar', 'P-4a', 'CAT-400')):
            self.add(ident, 1964, denomination=denomination, pick_number=pick, cat_id=cat)
        self.add('first-1965', 1965, pick_number='P-4b')
        self.add('first-1967', 1967, pick_number='P-6')
        self.add('transition-1971', 1971, issue_type='Colonial')
        self.add('undated-board', None, issue_type='Colonial')
        self.add('independent-1973', 1973, 'Bahrain Monetary Agency', issue_type='Colonial')
        self.add('conflicting-1964', 1964, 'Bahrain Monetary Agency')
        self.add('conflicting-series', 1967, series='1973 Monetary Agency issue')
        self.db.commit()
        return {'authorization-100', 'authorization-quarter', 'authorization-half',
                'authorization-one', 'first-1965', 'first-1967'}

    def records(self):
        return {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')}

    def filtered(self, group):
        sql, params = stuff.build_search_query('banknotes', 'Bahrain', coin_filter='heritage_' + group)
        return self.db.execute(sql, params).fetchall()

    def test_saved_authorization_and_issue_rows_share_sql_list_report_and_pills(self):
        british = self.seed()
        before = self.records()
        other = set(before) - british
        client = stuff.app.test_client()
        for group, expected in (('british', british), ('other', other)):
            rows = self.filtered(group)
            self.assertEqual({r['id'] for r in rows}, expected)
            for history in ('0', '1'):
                response = client.get('/banknotes', query_string={
                    'q': 'Bahrain', 'filter': 'heritage_' + group, 'history': history})
                self.assertEqual(response.status_code, 200)
                html = response.get_data(as_text=True)
                for ident in before:
                    self.assertEqual('id="item-' + ident + '"' in html, ident in expected, ident)
                if group == 'british':
                    self.assertEqual(html.count('<div class="banknote-period">' + self.PERIOD), 6)
                    self.assertIn('1964 authorization; first 1965–67 issue', html)
                else:
                    self.assertIn('Independent Bahrain issue', html)
                    self.assertIn('Bahrain independence transition', html)
            sections = stuff._banknote_report_sections(self.db, {'q': 'Bahrain', 'filter': 'heritage_' + group})
            self.assertEqual(len(sections), 1)
            self.assertEqual(sections[0][0], 'Bahrain')
            self.assertEqual([r['id'] for r in sections[0][2]], [r['id'] for r in rows])
        with stuff.app.test_request_context('/banknotes'):
            pills = stuff.banknote_entity_pills(self.db, self.filtered('british'))['british']
        pill = next(p for p in pills if p['key'] == 'british-bahrain')
        self.assertEqual(pill['coverage'], 'held')
        self.assertIn('6 notes', pill['status'])
        self.assertIn(pill['href'].split('#item-')[-1], british)
        self.assertNotIn('british-bahrain', {e['key'] for e in stuff._banknote_wantlist_open(self.db)})
        self.assertEqual(self.records(), before)

    def test_later_or_unresolved_notes_do_not_fill_protected_state_coverage(self):
        self.add('modern', 1973, 'Bahrain Monetary Agency')
        self.add('transition', 1971)
        self.add('undated', None)
        self.db.commit()
        with stuff.app.test_request_context('/banknotes'):
            pills = stuff.banknote_entity_pills(self.db, self.filtered('other'))['british']
        pill = next(p for p in pills if p['key'] == 'british-bahrain')
        self.assertEqual(pill['coverage'], 'missing')
        self.assertIsNone(pill['href'])
        self.assertIn('british-bahrain', {e['key'] for e in stuff._banknote_wantlist_open(self.db)})

    def test_legacy_analysis_uses_same_evidence_before_old_colonial_flag(self):
        british = self.seed()
        before = self.records()
        for ident, row in before.items():
            expected = ident in british
            self.assertEqual(stuff._banknote_is_colonial(row), expected, ident)
            self.assertEqual(stuff._banknote_bucket(row), 'colonial' if expected else 'other', ident)
            self.assertEqual(stuff._banknote_colony(row['country'], row['date_1'], row['issuer'], row['series']),
                             ('British', 'bahrain') if expected else None, ident)
            self.assertEqual(stuff._banknote_empire(row['country'], row['date_1'], row['issuer'], row['series']),
                             'British' if expected else 'Other', ident)
        self.assertIsNone(stuff._banknote_colony('Bahrain'))
        profile = stuff._analysis_banknotes_profile(self.db)
        self.assertEqual((profile['colonial_count'], profile['other_count']), (6, 5))
        self.assertEqual([(g['empire'], g['count']) for g in profile['empires']], [('British', 6)])
        self.assertTrue(all(item['period'].startswith(self.PERIOD) for item in profile['items_colonial']))
        self.assertTrue(all(not item['period'].startswith(self.PERIOD) for item in profile['items_other']))
        self.assertIn(self.PERIOD, profile['colonial_rule'])
        self.assertNotIn('Colonial always counts', profile['colonial_rule'])
        self.assertEqual(profile['decade_series'][0]['name'], 'Colonial / administrative control')
        with stuff.app.test_request_context('/banknotes'):
            html = stuff.render_template('partials/analysis.html', category='banknotes',
                                         cat_info={'name': 'Banknotes'}, profile=profile, analysis=None)
        self.assertIn('Colonial / administrative control, empire by empire', html)
        self.assertIn('Colonial / administrative control by empire', html)
        self.assertIn('Colonial / administrative control by decade', html)
        self.assertIn(self.PERIOD, html)
        self.assertNotIn('Colonial notes', html)
        self.assertIn(self.PERIOD, stuff._analysis_prompt('banknotes', profile))
        self.assertEqual(self.records(), before)

    def test_display_migration_changes_only_positions_and_runs_once(self):
        british = self.seed()
        self.db.execute("UPDATE banknotes SET banknote_id='P 999',price='$82.13',image_1='original-front.jpg',"
                        "image_2='manual-back.jpg',notes='Keep personal notes',order_number='12-34567-89012',"
                        "purchase_date='2026-10-12',status='Delivered'")
        self.db.execute('DELETE FROM migration_state WHERE key=?', (self.MIGRATION,))
        self.db.commit()
        before = self.records()
        with patch.object(stuff, '_renumber_banknotes', wraps=stuff._renumber_banknotes) as renumber:
            stuff.init_db()
        self.assertEqual(renumber.call_count, 1)
        after = self.records()
        for ident, row in before.items():
            self.assertEqual({k: v for k, v in row.items() if k != 'banknote_id'},
                             {k: v for k, v in after[ident].items() if k != 'banknote_id'}, ident)
        rows = self.db.execute('SELECT * FROM banknotes ORDER BY ' + stuff.CATEGORY_ORDER_BY['banknotes']).fetchall()
        self.assertEqual([r['banknote_id'] for r in rows], [f'P {i:03d}' for i in range(1, len(rows) + 1)])
        self.assertEqual({r['id'] for r in rows[:len(british)]}, british)
        marker = self.db.execute('SELECT applied_at FROM migration_state WHERE key=?', (self.MIGRATION,)).fetchone()[0]
        with patch.object(stuff, '_renumber_banknotes') as renumber:
            stuff.init_db()
        renumber.assert_not_called()
        self.assertEqual(self.records(), after)
        self.assertEqual(self.db.execute('SELECT applied_at FROM migration_state WHERE key=?', (self.MIGRATION,)).fetchone()[0], marker)

    def test_failed_display_migration_rolls_back_positions_and_can_retry(self):
        self.add('authorization', 1964, banknote_id='P 987')
        self.db.execute('DELETE FROM migration_state WHERE key=?', (self.MIGRATION,))
        self.db.commit()
        before = self.records()

        def fail_after_update(db):
            db.execute("UPDATE banknotes SET banknote_id='P 001'")
            raise sqlite3.OperationalError('synthetic interrupted renumber')

        with patch.object(stuff, '_renumber_banknotes', side_effect=fail_after_update):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'synthetic interrupted renumber'):
                stuff.init_db()
        self.assertEqual(self.records(), before)
        self.assertIsNone(self.db.execute('SELECT 1 FROM migration_state WHERE key=?', (self.MIGRATION,)).fetchone())
        stuff.init_db()
        self.assertEqual(self.records()['authorization']['banknote_id'], 'P 001')


if __name__ == '__main__':
    unittest.main()
