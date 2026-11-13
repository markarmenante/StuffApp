"""Explicit listing countries survive an omitted/failed model identification."""
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-country-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER'):
    os.environ[name] = '0'

import app as stuff
import banknote_imports


TITLE = 'PMG France 10 Livres 1792 P-66b Uncirculated 64 EPQ'
MIGRATION = 'banknote_assignat_country_v1'


class CountryRecoveryTests(unittest.TestCase):
    def setUp(self):
        self.context = stuff.app.app_context()
        self.context.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknotes')
        self.db.execute('DELETE FROM migration_state WHERE key=?', (MIGRATION,))
        self.db.commit()
        self.client = stuff.app.test_client()

    def tearDown(self):
        self.db.rollback()
        self.context.pop()

    def add(self, ident='assignat', **changes):
        row = dict(id=ident, country=None, description=TITLE,
                   issuer='Domaines Nationaux (Assignat)', denomination='10 Livres',
                   date_1=1792, pick_number='P-66b', cat_id='B-' + ident,
                   status='Ordered', price='$99', vendor='synthetic dealer',
                   order_number='12-12345-12345', image_1='front.jpg', image_2='back.jpg',
                   serial_number='12345', slab_number='1234567-001',
                   notes='Keep this note', updated_at='2026-01-01T00:00:00')
        row.update(changes)
        self.db.execute('INSERT INTO banknotes (' + ','.join(row) + ') VALUES (' +
                        ','.join('?' for _ in row) + ')', tuple(row.values()))
        self.db.commit()
        return self.record(ident)

    def record(self, ident='assignat'):
        return dict(self.db.execute('SELECT * FROM banknotes WHERE id=?', (ident,)).fetchone())

    def prepared(self):
        return dict(evidence=[], reports=[], documents=[], warnings=[], images={})

    def test_title_country_ignores_grader_prefix_and_keeps_territories_distinct(self):
        cases = [(TITLE, 'France'), ('France 10 Livres 1792 P-66b', 'France'),
                 ('PMG 64 EPQ France 10 Livres 1792', 'France'),
                 ('1792 France 10 Livres P-66b', 'France'),
                 ('Country: France; 10 Livres 1792', 'France'),
                 ('PMG French Somaliland 5 Francs P-6 1945', 'French Somaliland'),
                 ('PMG British Honduras 1 Dollar 1964 P-28b', 'British Honduras')]
        for title, expected in cases:
            with self.subTest(title=title):
                self.assertEqual(stuff._banknote_description_fields(
                    dict(description=title)).get('country'), expected)

    def test_no_currency_only_prose_ambiguous_or_existing_country_rewrite(self):
        for title in ('10 Livres 1792 P-66b', 'Fr. 1500 $1 1928',
                      'Printed in France; 10 Livres', 'Ships from France',
                      'France Germany two banknotes', 'PMG Congo 10 Francs',
                      'Unknown note\nSeller location: France'):
            with self.subTest(title=title):
                self.assertNotIn('country', stuff._banknote_description_fields(dict(description=title)))
        self.assertNotIn('country', stuff._banknote_description_fields(
            dict(country='Hong Kong', description='China Japanese occupation 100 Yen')))

    def test_live_check_recovers_country_when_model_omits_it_or_fails(self):
        self.add(image_1=None, image_2=None)
        for error in (None, RuntimeError('synthetic provider unavailable')):
            with self.subTest(error=error), \
                    patch.object(stuff.ebay_purchase_lookup, 'ensure', return_value=None), \
                    patch.object(stuff.banknote_check_sources, 'prepare', return_value=self.prepared()), \
                    patch.object(stuff, 'fetch_banknote_specs', return_value={}, side_effect=error), \
                    patch.object(stuff, 'ensure_country_history'):
                response = self.client.post('/banknotes/assignat/lookup-specs')
            self.assertEqual(response.status_code, 200, response.get_json())
            self.assertEqual(response.json['filled']['country'], 'France')
            self.assertIsNone(self.record()['country'], 'Check still uses the existing apply flow')

    def test_import_check_uses_same_fallback_and_preserves_conflicting_identification(self):
        note = self.add(image_1=None, image_2=None)
        with patch.object(stuff, 'fetch_banknote_specs', return_value={}):
            result = stuff._evaluate_import_check(note, self.prepared())
        self.assertEqual(result['filled']['country'], 'France')
        with patch.object(stuff, 'fetch_banknote_specs', side_effect=RuntimeError('unavailable')):
            result = stuff._evaluate_import_check(note, self.prepared())
        self.assertEqual(result['filled']['country'], 'France')
        self.assertTrue(result['lookup_error'])
        prepared = self.prepared()
        with patch.object(stuff, 'fetch_banknote_specs', return_value={'country': 'Germany'}):
            result = stuff._evaluate_import_check(note, prepared)
        self.assertNotIn('country', result['filled'])
        self.assertTrue(any('country conflicts' in warning for warning in prepared['warnings']))

    def test_startup_repairs_only_corroborated_assignat_and_preserves_other_fields(self):
        self.add()
        self.add('saved', country='France')
        self.add('territory', country='French India')
        self.add('wrong-year', date_1=1793)
        self.add('wrong-pick', pick_number='P-66a')
        self.add('wrong-denomination', denomination='50 Livres')
        self.add('wrong-issuer', issuer='Bank of France')
        self.add('ambiguous', description=TITLE + ' Germany')
        self.add('other', description='PMG Germany 10 Mark 1910', issuer='Reichsbank')
        before = {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')}
        stuff.init_db()
        after = {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')}
        self.assertEqual(after['assignat']['country'], 'France')
        for ident, row in before.items():
            ignored = {'banknote_id'} | ({'country', 'updated_at'} if ident == 'assignat' else set())
            self.assertEqual({k: v for k, v in row.items() if k not in ignored},
                             {k: v for k, v in after[ident].items() if k not in ignored})
        audit = self.db.execute('SELECT * FROM banknote_country_recovery_history').fetchall()
        self.assertEqual(len(audit), 1)
        self.assertEqual((audit[0]['banknote_id'], audit[0]['country'], audit[0]['description']),
                         ('assignat', 'France', TITLE))
        with patch.object(stuff, '_renumber_banknotes') as renumber:
            stuff.init_db()
        renumber.assert_not_called()
        self.assertEqual(after, {r['id']: dict(r) for r in self.db.execute('SELECT * FROM banknotes')})

    def test_failed_repair_rolls_back_and_can_retry(self):
        self.add()
        before = self.record()
        with patch.object(stuff, '_renumber_banknotes', side_effect=sqlite3.OperationalError('interrupted')):
            with self.assertRaisesRegex(sqlite3.OperationalError, 'interrupted'):
                stuff._migrate_assignat_country(self.db)
        self.assertEqual(self.record(), before)
        self.assertIsNone(self.db.execute('SELECT 1 FROM migration_state WHERE key=?', (MIGRATION,)).fetchone())
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_country_recovery_history').fetchone()[0], 0)
        stuff._migrate_assignat_country(self.db)
        self.assertEqual(self.record()['country'], 'France')

    def test_resolved_country_warning_disappears_without_erasing_audit_or_other_warnings(self):
        record = self.add(country='France', denomination=None)
        original = ('Check could not confirm country, denomination. '
                    'Review the listing and original photos or retry Check. Photo review is incomplete.')
        self.db.execute("INSERT OR REPLACE INTO banknote_import_batches "
                        "(id,account_name,order_id,created_at,updated_at) VALUES ('batch','test','order',0,0)")
        self.db.execute("INSERT OR REPLACE INTO banknote_import_items "
                        "(id,batch_id,account_name,line_key,item_id,source_json,source_digest,fields_json,"
                        "state,released_record_id,check_state,check_message,checked_at,created_at,updated_at) "
                        "VALUES ('item','batch','test','line','listing','{}','digest','{}',"
                        "'released','assignat','partial',?,1,0,0)", (original,))
        message = banknote_imports.collection_check_warning(self.db, record)
        self.assertNotIn('confirm country', message)
        self.assertIn('confirm denomination', message)
        self.assertIn('Photo review is incomplete.', message)
        record['denomination'] = '10 Livres'
        self.assertEqual(banknote_imports.collection_check_warning(self.db, record), 'Photo review is incomplete.')
        self.assertEqual(self.db.execute("SELECT check_message FROM banknote_import_items WHERE id='item'").fetchone()[0], original)


if __name__ == '__main__':
    unittest.main()
