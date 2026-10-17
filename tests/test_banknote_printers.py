"""Printer aliases group consistently without changing catalogue evidence."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-printers-test-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuff
from banknote_printers import canonical_printer


ALIASES = {
    'Thomas De La Rue': (
        'Thomas De La Rue',
        'Thomas De La Rue & Company, Limited',
        'Thomas De La Rue & Company, Limited, London',
        'Thomas De La Rue (TDLR)',
        'TDLR', 'T.D.L.R.', 'De La Rue',
        'Thomas De La Rue & Co., Ltd. (London, England)',
        'Thomas De La Rue and Company Limited, London, England, United Kingdom',
        '  THOMAS\tDE LA RUE & CO. LTD., LONDON  ',
    ),
    'Bradbury Wilkinson': (
        'Bradbury Wilkinson',
        'Bradbury, Wilkinson & Co Ltd',
        'Bradbury, Wilkinson & Co Ltd, New Malden, Surrey, England',
        'Bradbury Wilkinson and Company',
        'BWC (Bradbury Wilkinson and Company)',
        'Bradbury, Wilkinson & Co. Ltd. (BWC), New Malden, Surrey, England',
        'Bradbury & Wilkinson, London', 'BWC', 'B.W.C.',
    ),
    'Banque de France': (
        'Banque de France', 'Banque de France (BdF)',
        'Banque de France, Paris, France', 'BdF', 'B.d.F.',
        'Banque de France (BdF), Paris, France',
        '  BANQUE DE FRANCE (PARIS)  ',
    ),
}


class PrinterIdentityTests(unittest.TestCase):
    def test_known_aliases_addresses_and_legal_suffixes(self):
        for canonical, aliases in ALIASES.items():
            for alias in aliases:
                with self.subTest(alias=alias):
                    self.assertEqual(canonical_printer(alias), canonical)
                    self.assertEqual(canonical_printer(canonical_printer(alias)), canonical)

    def test_unknown_distinct_uncertain_and_joint_credits_are_preserved(self):
        credits = (
            'Waterlow & Sons', 'Waterlow Brothers & Layton',
            'American Bank Note Company', 'Canadian Bank Note Company',
            'British American Bank Note Company', 'National Bank Note Company',
            'Harrison & Sons', 'Banque de France et des Pays-Bas',
            'De La Rue International Ltd', 'Thomas De La Rue (possibly)',
            'Thomas De La Rue?', 'Attributed to Thomas De La Rue',
            'Thomas De La Rue (overprint by another firm)',
            'Bradbury Wilkinson, unknown works',
            'Thomas De La Rue / Bradbury Wilkinson',
            'Thomas De La Rue; Banque de France',
            'Thomas De La Rue & Bradbury Wilkinson',
            'Thomas De La Rue and Bradbury Wilkinson',
            'Thomas De La Rue, Bradbury Wilkinson',
            'Banque de France (BdF) / Bradbury Wilkinson (BWC)',
        )
        for credit in credits:
            with self.subTest(credit=credit):
                self.assertEqual(canonical_printer(credit), credit)
        self.assertEqual(len({canonical_printer(c) for c in credits}), len(credits))

    def test_empty_values_do_not_create_a_printer(self):
        for value in (None, '', ' \n\t '):
            self.assertEqual(canonical_printer(value), '')


class PrinterAnalysisTests(unittest.TestCase):
    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM banknotes')
        self.db.execute('DELETE FROM collection_analyses')
        self.db.commit()

    def tearDown(self):
        self.ctx.pop()

    def add(self, printer, country='British East Africa', year=1940,
            issue_type='Colonial', status='Own'):
        ident = str(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0] + 1)
        self.db.execute(
            'INSERT INTO banknotes(id,country,date_1,issue_type,denomination,printer,status) '
            'VALUES(?,?,?,?,?,?,?)',
            (ident, country, year, issue_type, '5 Dollars', printer, status))
        self.db.commit()
        return ident

    def seed_screenshot(self):
        for printer in ALIASES['Thomas De La Rue'][1:4]:
            self.add(printer)
        for printer in ALIASES['Bradbury Wilkinson'][1:3]:
            self.add(printer)
        for printer in ALIASES['Banque de France'][:3]:
            self.add(printer, 'French Indochina')
        for printer in ('Bradbury Wilkinson and Company', 'Thomas De La Rue',
                        'BWC (Bradbury Wilkinson and Company)'):
            self.add(printer, 'Angola')

    def test_screenshot_counts_and_all_analysis_buckets_share_identity(self):
        self.seed_screenshot()
        self.add('TDLR', 'United States', 1943, 'Military')
        self.add('Thomas De La Rue (TDLR)', 'United States', 1944, 'Military')
        self.add('BWC', 'United States', 1920, 'National')
        self.add('BdF', 'Austria', 1920, 'National', 'Ordered')
        self.add(None, 'Austria', 1920, 'National')
        self.add('TDLR', status='Sold')
        before = [dict(r) for r in self.db.execute('SELECT * FROM banknotes ORDER BY id')]

        profile = stuff._analysis_banknotes_profile(self.db)
        empires = {e['empire']: e for e in profile['empires']}
        self.assertEqual(empires['British']['printers'], ['Thomas De La Rue', 'Bradbury Wilkinson'])
        self.assertEqual(empires['British']['count'], 5)
        self.assertEqual(empires['French']['printers'], ['Banque de France'])
        self.assertEqual(empires['Portuguese']['printers'], ['Bradbury Wilkinson', 'Thomas De La Rue'])
        self.assertEqual(profile['military_groups'][0]['printers'], ['Thomas De La Rue'])
        self.assertEqual(profile['military_groups'][0]['count'], 2)
        self.assertEqual(dict(profile['printers']), {
            'Thomas De La Rue': 6, 'Bradbury Wilkinson': 5, 'Banque de France': 4})
        self.assertEqual(profile['total'], 16)
        for bucket in ('colonial', 'military', 'us', 'other'):
            self.assertTrue(profile['items_' + bucket])
            for item in profile['items_' + bucket]:
                self.assertEqual(item['printer_group'], canonical_printer(item['printer']))
        original_credit = ALIASES['Thomas De La Rue'][1]
        self.assertTrue(any(i['printer'] == original_credit for i in profile['items_colonial']))
        prompt = stuff._analysis_prompt('banknotes', profile)
        self.assertIn('"printer_group": "Thomas De La Rue"', prompt)
        self.assertIn(original_credit, prompt)
        self.assertEqual(before, [dict(r) for r in self.db.execute('SELECT * FROM banknotes ORDER BY id')])

    def test_merge_happens_before_top_five_and_top_ten_limits(self):
        for printer in ALIASES['Thomas De La Rue']:
            self.add(printer)
        for printer in ('Banque de France', 'Bradbury Wilkinson', 'Harrison & Sons',
                        'Waterlow & Sons', 'American Bank Note Company',
                        'Canadian Bank Note Company', 'National Bank Note Company',
                        'Continental Bank Note Company', 'Waterlow Brothers & Layton',
                        'Other printing works'):
            self.add(printer)
        profile = stuff._analysis_banknotes_profile(self.db)
        self.assertEqual(profile['printers'][0], ('Thomas De La Rue', 10))
        self.assertEqual(len(profile['printers']), 10)
        self.assertEqual(len(profile['empires'][0]['printers']), 5)
        self.assertEqual(profile['empires'][0]['printers'][0], 'Thomas De La Rue')
        self.assertEqual(len(set(profile['empires'][0]['printers'])), 5)

    def test_page_uses_merged_labels_and_flags_existing_essay_stale(self):
        self.seed_screenshot()
        # Reconstruct the old profile using raw credits, then save its essay.
        with patch.object(stuff.banknote_printers, 'canonical_printer', side_effect=lambda v: v):
            old_profile = stuff._analysis_banknotes_profile(self.db)
        old_hash = stuff._analysis_profile_hash(old_profile)
        new_profile = stuff._analysis_banknotes_profile(self.db)
        self.assertNotEqual(old_hash, stuff._analysis_profile_hash(new_profile))
        self.db.execute(
            'INSERT INTO collection_analyses '
            '(id,category,started_at,finished_at,status,markdown,profile_hash) '
            'VALUES(?,?,?,?,?,?,?)',
            ('old', 'banknotes', '2026-10-17T00:00:00', '2026-10-17T00:01:00',
             'done', 'Existing essay remains available.', old_hash))
        self.db.commit()
        with patch.object(stuff, '_run_collection_analysis') as generate:
            response = stuff.app.test_client().get('/banknotes/analysis')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('<td>Thomas De La Rue; Bradbury Wilkinson</td>', html)
        self.assertIn('<td>Banque de France</td>', html)
        self.assertIn('<td>Bradbury Wilkinson; Thomas De La Rue</td>', html)
        self.assertNotIn('Thomas De La Rue &amp; Company', html)
        self.assertNotIn('Banque de France (BdF)', html)
        self.assertIn('the collection has changed since', html)
        self.assertIn('Existing essay remains available.', html)
        generate.assert_not_called()

        # Opening analysis has not simplified the original record's detail.
        detail = stuff.app.test_client().get('/banknotes/1').get_data(as_text=True)
        self.assertIn('Thomas De La Rue &amp; Company, Limited', detail)


if __name__ == '__main__':
    unittest.main()
