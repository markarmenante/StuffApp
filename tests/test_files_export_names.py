"""Length-safe Files export names keep exact titles and round-trip through Sweep."""
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-files-names-')
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
import app as stuff

IDENT = 'C512 Syracuse, Second Democracy Tetradrachm'
TITLE = ('VCoins Original Listing - C512 - SICILY. Syracuse. Second Democracy. '
         'Signed by Eumenes and Eukleidas. 413-405 BC. AR Tetradrachm. '
         'Purchased from Maison Platt, January 1985. Ex. CNG 100, 7 Oct 2015, lot 1285')


class LeafTests(unittest.TestCase):
    def test_actual_reported_name_is_bounded_without_losing_identity(self):
        raw = f'{IDENT} — {TITLE}.pdf'
        self.assertEqual(len(raw), 256)
        self.assertEqual(len(raw.encode('utf-8')), 258)
        leaf = stuff._export_leaf_name(IDENT, TITLE, '.pdf')
        self.assertLessEqual(len(leaf.encode('utf-8')), 255)
        self.assertTrue(leaf.startswith(IDENT + ' — '))
        self.assertTrue(leaf.endswith('.pdf'))
        self.assertRegex(leaf, r'~[0-9a-f]{12}\.pdf$')
        self.assertEqual(leaf, stuff._export_leaf_name(IDENT, TITLE, '.pdf'))

    def test_short_names_and_exact_boundary_are_unchanged(self):
        for ident, label, ext in [('C001 Coin', 'Receipt', '.PDF'),
                                  ('B001 Note', 'Front', '.jpg'),
                                  ('Résumé (W001)', 'Achat', '.pdf'),
                                  ('Item', '', '.jpg')]:
            expected = f'{ident} — {label}{ext}' if label else ident + ext
            self.assertEqual(stuff._export_leaf_name(ident, label, ext), expected)
        exact = 'a' * 251 + '.pdf'
        self.assertEqual(stuff._export_leaf_name('a' * 251, '', '.pdf'), exact)
        self.assertEqual(len(exact.encode()), 255)
        self.assertLessEqual(len(stuff._export_leaf_name('a' * 251, '', '.pdf', 2).encode()), 255)

    def test_unicode_suffixes_are_unique_stable_and_valid_utf8(self):
        labels = ['説明é' * 100 + tail for tail in ['alpha', 'beta']]
        names = [stuff._export_leaf_name('B123 Example', label, '.pdf') for label in labels]
        self.assertNotEqual(*names)
        for label, name in zip(labels, names):
            self.assertLessEqual(len(name.encode()), 255)
            self.assertNotIn('\ufffd', name)
            self.assertEqual(name, stuff._export_leaf_name('B123 Example', label, '.pdf'))
            self.assertTrue(name.startswith('B123 '))
        variants = [stuff._export_leaf_name(IDENT, TITLE, '.pdf', n) for n in range(1, 9)]
        self.assertEqual(len(set(variants)), 8)
        self.assertTrue(all(len(name.encode()) <= 255 for name in variants))
        self.assertTrue(variants[1].endswith(' (2).pdf'))

    def test_long_identifier_snapshot_marker_survives(self):
        leaf = stuff._export_leaf_name('B456 ' + 'Very long note ' * 80, '_data', '.json')
        self.assertLessEqual(len(leaf.encode()), 255)
        self.assertTrue(leaf.startswith('B456 '))
        self.assertTrue(leaf.endswith(' — _data.json'))
        self.assertTrue(stuff._is_data_snapshot_path(leaf))


class RoundTripTests(unittest.TestCase):
    def setUp(self):
        self.context = stuff.app.app_context()
        self.context.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM record_documents')
        self.db.execute('DELETE FROM tombstones')
        self.db.execute('DELETE FROM coins')
        self.db.execute('DELETE FROM banknotes')
        self.db.execute('DELETE FROM watches')
        self.db.execute("INSERT INTO coins (id,cat_id,region,authority,denomination,status) VALUES "
                        "('fixture-coin','C512','Sicily','Syracuse, Second Democracy','Tetradrachm','Own')")
        self.titles = [TITLE, 'Receipt', '説明é' * 100 + 'alpha', '説明é' * 100 + 'beta']
        self.docs = []
        for n, title in enumerate(self.titles):
            name = f'fixture-export-{n}.pdf'
            (Path(stuff.UPLOAD_FOLDER) / name).write_bytes(f'%PDF-1.4 synthetic {n}'.encode())
            self.docs.append({'title': title, 'filename': name})
        stuff._docs_update(self.db, 'coins', 'fixture-coin', self.docs)
        self.db.commit()
        self.client = stuff.app.test_client()

    def tearDown(self):
        self.db.rollback()
        self.context.pop()

    def export(self):
        response = self.client.get('/export-files')
        self.assertEqual(response.status_code, 200)
        try:
            with zipfile.ZipFile(io.BytesIO(response.data)) as archive:
                return {name: archive.read(name) for name in archive.namelist()}
        finally:
            response.close()

    def test_zip_and_repeated_sweep_keep_full_titles_and_no_false_deletes(self):
        archive = self.export()
        expected = 'StuffFiles/Coins/Sicily/' + stuff._export_leaf_name(IDENT, TITLE, '.pdf')
        self.assertIn(expected, archive)
        self.assertIn('StuffFiles/Coins/Sicily/' + IDENT + ' — Receipt.pdf', archive)
        self.assertTrue(all(len(Path(name).name.encode()) <= 255 for name in archive))
        snapshot_path = 'StuffFiles/Coins/Sicily/' + IDENT + ' — _data.json'
        snapshot = json.loads(archive[snapshot_path])
        self.assertEqual([d['title'] for d in snapshot['record_documents']['main']], self.titles)
        self.assertEqual(set(archive), set(self.export()))
        for _ in range(2):
            response = self.client.post('/sweep', data={
                'files': [(io.BytesIO(value), name) for name, value in archive.items()
                          if name.startswith('StuffFiles/Coins/Sicily/')],
                'sync_deletes': 'preview',
            }, headers={'Accept': 'application/json'})
            self.assertEqual(response.status_code, 200)
            report = response.get_json()
            self.assertEqual(report['deleted'], [], report)
            self.assertFalse(any('server error' in entry['reason'] for entry in report['skipped']), report)
            self.assertEqual(sum('already in' in entry['reason'] for entry in report['skipped']), len(self.docs), report)
            current = stuff._docs_load(self.db, 'coins', 'fixture-coin')
            self.assertEqual([(d['title'], d['filename']) for d in current],
                             [(d['title'], d['filename']) for d in self.docs])

    def test_deleted_long_document_tombstone_matches_export_and_collision_names(self):
        archive = self.export()
        leaf = stuff._export_leaf_name(IDENT, TITLE, '.pdf')
        exported = 'StuffFiles/Coins/Sicily/' + leaf
        self.assertIn(exported, archive)
        response = self.client.post('/coins/fixture-coin/documents/main/0/delete')
        self.assertEqual(response.status_code, 200)
        manifest = json.loads(self.export()['StuffFiles/_tombstones.json'])
        entry = manifest['tombstones'][0]
        self.assertEqual(entry['path'], exported)
        self.assertEqual(entry['variants'], ['StuffFiles/Coins/Sicily/' +
            stuff._export_leaf_name(IDENT, TITLE, '.pdf', n) for n in range(2, 9)])
        self.assertTrue(all(len(Path(name).name.encode()) <= 255 for name in [entry['path'], *entry['variants']]))
        row = self.db.execute('SELECT label FROM tombstones').fetchone()
        self.assertEqual(row['label'], TITLE)

    def test_long_identifier_sweep_resolves_exact_snapshot_and_full_title(self):
        self.db.execute("UPDATE coins SET authority=? WHERE id='fixture-coin'", ('Long authority ' * 40,))
        self.db.commit()
        archive = self.export()
        files = [(name, value) for name, value in archive.items() if name.startswith('StuffFiles/Coins/Sicily/')]
        self.assertTrue(any(stuff._is_data_snapshot_path(name) for name, _ in files))
        response = self.client.post('/sweep', data={
            'files': [(io.BytesIO(value), name) for name, value in files], 'sync_deletes': 'preview',
        }, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        report = response.get_json()
        self.assertEqual(report['deleted'], [], report)
        self.assertEqual(sum('already in' in entry['reason'] for entry in report['skipped']), len(self.docs), report)

    def test_snapshot_restore_with_new_catalogue_id_keeps_full_document_title(self):
        self.db.execute("INSERT INTO watches (id,cat_id,brand,model,status) VALUES "
                        "('fixture-watch','W901','Example maker','A detailed example model with extra reference information','Own')")
        stuff._docs_update(self.db, 'watches', 'fixture-watch', [self.docs[0]])
        self.db.commit()
        archive = self.export()
        watch_files = [(name, value) for name, value in archive.items()
                       if name.startswith('StuffFiles/Watches/Example maker/')]
        self.assertTrue(any('~' in name and name.endswith('.pdf') for name, _ in watch_files))
        self.db.execute("DELETE FROM record_documents WHERE category='watches'")
        self.db.execute("DELETE FROM watches WHERE id='fixture-watch'")
        self.db.commit()
        response = self.client.post('/sweep', data={
            'files': [(io.BytesIO(value), name) for name, value in watch_files],
            'auto_create': '1', 'auto_create_watches': '1',
        }, headers={'Accept': 'application/json'})
        self.assertEqual(response.status_code, 200)
        report = response.get_json()
        self.assertEqual(report['skipped'], [], report)
        watches = self.db.execute('SELECT id,cat_id FROM watches').fetchall()
        self.assertEqual(len(watches), 1)
        self.assertNotEqual(watches[0]['cat_id'], 'W901')
        docs = stuff._docs_load(self.db, 'watches', watches[0]['id'])
        self.assertEqual(len(docs), 1)
        self.assertEqual(docs[0]['title'], TITLE)

    def test_duplicate_long_titles_get_distinct_bounded_collision_paths(self):
        extra = 'fixture-export-copy.pdf'
        (Path(stuff.UPLOAD_FOLDER) / extra).write_bytes(b'%PDF-1.4 duplicate-title')
        stuff._docs_update(self.db, 'coins', 'fixture-coin', [self.docs[0], {'title': TITLE, 'filename': extra}])
        self.db.commit()
        archive = self.export()
        for n in (1, 2):
            name = 'StuffFiles/Coins/Sicily/' + stuff._export_leaf_name(IDENT, TITLE, '.pdf', n)
            self.assertIn(name, archive)
            self.assertLessEqual(len(Path(name).name.encode()), 255)
        self.assertEqual(set(archive), set(self.export()))

    def test_unknown_short_name_never_creates_a_new_document(self):
        name = 'StuffFiles/Coins/Sicily/' + stuff._export_leaf_name(IDENT, TITLE + 'unknown', '.pdf')
        response = self.client.post('/sweep', data={'files': [(io.BytesIO(b'%PDF-1.4 fake'), name)]},
                                    headers={'Accept': 'application/json'})
        report = response.get_json()
        self.assertEqual(report['uploaded'], [], report)
        self.assertIn('missing or ambiguous', report['skipped'][0]['reason'])
        self.assertEqual(len(stuff._docs_load(self.db, 'coins', 'fixture-coin')), len(self.docs))


if __name__ == '__main__':
    unittest.main()
