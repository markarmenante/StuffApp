"""Optional display cropping must not discard a successful exact-item Check."""
import time
import unittest
from unittest.mock import patch
from pathlib import Path

import test_banknote_imports as fixture_module


class CropTimeoutTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.DraftTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def test_unconfirmed_crop_is_distinct_from_an_already_cropped_photo(self):
        stuff=fixture_module.stuff
        with patch.object(stuff,'_trim_slabbed_note_image',return_value=None):
            with self.assertRaises(fixture_module.imports.ImportProblem):
                stuff._prepare_import_photo(b'fixture',{})
        def already_cropped(raw,expect_aspect=None,meta=None):
            meta['crop_status']='already_cropped'
            return None
        with patch.object(stuff,'_trim_slabbed_note_image',side_effect=already_cropped):
            self.assertIsNone(stuff._prepare_import_photo(b'fixture',{}))

    def assert_metadata_survives_slow_crop(self, *, raises):
        fixture = self.fixture
        batch = fixture.imported()
        item = batch['items'][0]
        evaluated = []

        def evaluate(note, prepared):
            evaluated.append(note['id'])
            return dict(filled=fixture.fills)

        def crop(raw, note):
            # The model already finished. Simulate the existing five-minute
            # lease expiring during optional crop work without a real wait.
            fixture.db.execute(
                'UPDATE banknote_import_items SET check_expires=? WHERE id=?',
                (time.time() - 1, item['id']))
            fixture.db.commit()
            if raises:
                raise TimeoutError('Optional crop provider exceeded its budget')
            return None

        result = fixture.check(batch, item, evaluate, crop)
        current = next(row for row in result['items'] if row['id'] == item['id'])
        self.assertEqual(evaluated, [item['id']])
        self.assertEqual(current['check_state'], 'partial')
        for field, value in fixture.fills.items():
            self.assertEqual(current['fields'].get(field), value)
        assets = {
            row['filename'] for row in fixture.db.execute(
                'SELECT filename FROM banknote_import_assets WHERE item_id=?',
                (item['id'],))
        }
        for field in ('image_1', 'image_2'):
            self.assertIn(current['fields'].get(field), assets)
        self.assertIn('crop', current['check_message'].lower())
        self.assertEqual(fixture.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)

    def test_crop_timeout_preserves_metadata_and_selected_originals(self):
        self.assert_metadata_survives_slow_crop(raises=True)

    def test_crop_returning_after_lease_preserves_metadata_and_originals(self):
        self.assert_metadata_survives_slow_crop(raises=False)

    def test_source_mutation_during_crop_keeps_checkpoint_but_rejects_crop(self):
        fixture = self.fixture
        batch = fixture.imported()
        item = batch['items'][0]
        checkpoint = {}

        def crop(raw, note):
            if not checkpoint:
                current = next(row for row in fixture.client.get(batch['status_url']).json['items']
                               if row['id'] == item['id'])
                checkpoint.update(current['fields'])
                self.assertEqual(checkpoint['country'], fixture.fills['country'])
                self.assertEqual(current['check_state'], 'checking')
                source = Path(fixture_module.stuff.UPLOAD_FOLDER) / checkpoint['image_1']
                source.write_bytes(source.read_bytes() + b'changed during optional crop')
            return fixture.preview_crop(raw, note)

        result = fixture.check(batch, item, prepare_photo=crop)
        current = next(row for row in result['items'] if row['id'] == item['id'])
        self.assertEqual(current['check_state'], 'partial')
        for field, value in fixture.fills.items():
            self.assertEqual(current['fields'][field], value)
        for field in ('image_1', 'image_2'):
            self.assertEqual(current['fields'][field], checkpoint[field])
        self.assertEqual(fixture.db.execute(
            'SELECT COUNT(*) FROM banknote_import_image_edits WHERE item_id=?',
            (item['id'],)).fetchone()[0], 0)
        self.assertEqual(fixture.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
