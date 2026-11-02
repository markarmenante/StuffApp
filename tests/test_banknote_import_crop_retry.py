"""Explicit crop recovery uses retained originals without replaying manual edits."""
import io
import json
from pathlib import Path
import time
import unittest
from unittest.mock import Mock, patch

import test_banknote_imports as fixtures

imports = fixtures.imports
stuff = fixtures.stuff


class CropRetryTests(unittest.TestCase):
    setUp = fixtures.DraftTests.setUp
    tearDown = fixtures.DraftTests.tearDown
    batch = fixtures.DraftTests.batch
    payload = fixtures.DraftTests.payload
    imported = fixtures.DraftTests.imported
    check = fixtures.DraftTests.check
    download = fixtures.DraftTests.download
    classify = fixtures.DraftTests.classify
    current_item = fixtures.DraftTests.current_item
    crop = fixtures.DraftTests.crop
    crop_info = fixtures.DraftTests.crop_info
    choose = fixtures.DraftTests.choose
    preview_crop = staticmethod(fixtures.DraftTests.preview_crop)

    def row(self, item):
        return dict(self.db.execute('SELECT * FROM banknote_import_items WHERE id=?', (item['id'],)).fetchone())

    def assets(self, item):
        return [dict(row) for row in self.db.execute('SELECT * FROM banknote_import_assets WHERE item_id=?', (item['id'],))]

    def smaller_crop(self, raw, note):
        original = fixtures.Image.open(io.BytesIO(raw))
        self.assertEqual(original.size, (160, 80), 'Retries must render from the full retained original')
        output = io.BytesIO()
        original.crop((10, 10, 150, 70)).save(output, format='JPEG')
        return dict(data=output.getvalue(), quad=[[10, 10], [150, 10], [150, 70], [10, 70]])

    def test_automatic_crop_is_preserved_by_check_but_explicit_retry_replaces_it(self):
        batch = self.imported()
        item = batch['items'][0]
        batch = self.check(batch, item, prepare_photo=self.preview_crop)
        item = self.current_item(batch, item)
        before = dict(item['fields'])
        originals = {field: stuff._banknote_vision_source(before[field], self.db) for field in ('image_1', 'image_2')}
        row, assets = self.row(item), self.assets(item)
        self.assertEqual(imports._uncropped_draft_photos(self.db, row, before, assets), {})
        self.assertEqual(imports._uncropped_draft_photos(self.db, row, before, assets, retry_automatic=True), originals)
        with patch.object(stuff, '_prepare_import_photo') as detector:
            batch = self.check(batch, item, prepare_photo=detector, retry_uncropped=True)
        detector.assert_not_called()
        item = self.current_item(batch, item)
        imports.queue_photo_retries(self.db, batch['id'])
        self.assertEqual(self.row(item)['retry_photos'], 1)
        batch = self.check(batch, item, prepare_photo=self.smaller_crop, retry_uncropped=True)
        updated = self.current_item(batch, item)
        self.assertEqual(self.row(item)['retry_photos'], 0)
        for field, original in originals.items():
            self.assertNotEqual(updated['fields'][field], before[field])
            self.assertEqual(stuff._banknote_vision_source(updated['fields'][field], self.db), original)
            with fixtures.Image.open(Path(stuff.UPLOAD_FOLDER) / updated['fields'][field]) as image:
                self.assertEqual(image.size, (140, 60))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)

    def test_manual_crops_selections_and_existing_collection_photos_are_not_retry_candidates(self):
        batch = self.imported()
        batch = self.check(batch, batch['items'][0], prepare_photo=self.preview_crop)
        item = batch['items'][0]
        item = self.crop(item, 'image_1').json['item']
        original = stuff._banknote_vision_source(item['fields']['image_2'], self.db)
        item = self.choose(item, 'image_2', original).json['item']
        self.assertEqual(imports._uncropped_draft_photos(self.db, self.row(item), item['fields'], self.assets(item), retry_automatic=True), {})
        row = self.row(item)
        row['manual_photos_json'] = '{}'
        row['existing_snapshot_json'] = json.dumps({field: item['fields'][field] for field in ('image_1', 'image_2')})
        self.assertEqual(imports._uncropped_draft_photos(self.db, row, item['fields'], self.assets(item), retry_automatic=True), {})

    def test_queued_preview_survives_worker_loss_and_duplicate_workers_do_not_replay(self):
        batch = self.imported(lambda payload: payload['items'][0].update(status_text='Payment pending'))
        item = next(row for row in batch['items'] if row['state'] == 'blocked')
        token = imports.claim_previews(self.db, batch['id'], item['id'])
        self.assertIn(batch['id'], imports.pending_preview_batches(self.db))
        self.assertEqual(imports.claim_previews(self.db, batch['id'], item['id']), token)
        self.assertEqual(imports.claim_previews(self.db, batch['id'], item['id'], retry=True), token)
        nested_detector = Mock(side_effect=AssertionError('A second worker replayed the same crop'))
        seen = []
        def crop(raw, note):
            seen.append(raw)
            imports.run_previews(stuff.open_db_connection, batch['id'], item['id'], token,
                                 stuff.UPLOAD_FOLDER, nested_detector)
            return self.preview_crop(raw, note)
        class Inline:
            def __init__(self, target, args=(), **kwargs): self.target, self.args = target, args
            def start(self): self.target(*self.args)
        with patch.object(imports.listing_images, 'download', side_effect=self.download), \
                patch.object(stuff.threading, 'Thread', Inline), \
                patch.object(stuff, '_prepare_import_photo', side_effect=crop):
            stuff._start_import_previews(batch['id'])
        nested_detector.assert_not_called()
        self.assertEqual(len(seen), 2)
        self.assertEqual(self.current_item(batch, item)['preview_state'], 'done')
        self.assertNotIn(batch['id'], imports.pending_preview_batches(self.db))

    def test_explicit_preview_retry_replaces_previous_crop_from_originals_without_redownload(self):
        batch = self.imported(lambda payload: payload['items'][0].update(status_text='Payment pending'))
        item = next(row for row in batch['items'] if row['state'] == 'blocked')
        first = imports.claim_previews(self.db, batch['id'], item['id'])
        with patch.object(imports.listing_images, 'download', side_effect=self.download):
            imports.run_previews(stuff.open_db_connection, batch['id'], item['id'], first, stuff.UPLOAD_FOLDER, self.preview_crop)
        before = [dict(row) for row in self.db.execute('SELECT * FROM banknote_import_photo_previews ORDER BY position')]
        asset = dict(source_url=before[0]['source_url'], sha256=before[0]['source_sha256'])
        self.assertIsNotNone(imports._saved_preview_crop(self.db, self.row(item), asset, stuff.UPLOAD_FOLDER))
        self.assertIsNone(imports._saved_preview_crop(self.db, self.row(item), asset, stuff.UPLOAD_FOLDER, retry=True))
        self.assertIsNone(imports.claim_previews(self.db, batch['id'], item['id']))
        retry = imports.claim_previews(self.db, batch['id'], item['id'], retry=True)
        self.assertNotEqual(retry, first)
        with patch.object(imports.listing_images, 'download') as download:
            imports.run_previews(stuff.open_db_connection, batch['id'], item['id'], retry, stuff.UPLOAD_FOLDER, self.smaller_crop)
        download.assert_not_called()
        after = [dict(row) for row in self.db.execute('SELECT * FROM banknote_import_photo_previews ORDER BY position')]
        for old, new in zip(before, after):
            self.assertEqual(old['source_filename'], new['source_filename'])
            self.assertEqual(old['source_sha256'], new['source_sha256'])
            self.assertNotEqual(old['filename'], new['filename'])
            with fixtures.Image.open(Path(stuff.UPLOAD_FOLDER) / new['filename']) as image:
                self.assertEqual(image.size, (140, 60))
        updated = self.current_item(batch, item)
        self.assertEqual(updated['state'], 'blocked')
        self.assertFalse(updated['fields'].get('image_1'))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_import_assets').fetchone()[0], 0)

    def test_preview_restart_does_not_replay_checking_or_expired_work(self):
        batch = self.imported(lambda payload: payload['items'][0].update(status_text='Payment pending'))
        item = next(row for row in batch['items'] if row['state'] == 'blocked')
        token = imports.claim_previews(self.db, batch['id'], item['id'])
        self.db.execute("UPDATE banknote_import_preview_jobs SET state='checking' WHERE item_id=?", (item['id'],))
        self.db.commit()
        self.assertNotIn(batch['id'], imports.pending_preview_batches(self.db))
        self.assertIsNone(imports.claim_previews(self.db, batch['id'], item['id'], retry=True))
        self.db.execute("UPDATE banknote_import_preview_jobs SET expires=? WHERE item_id=?", (time.time() - 1, item['id']))
        self.db.commit()
        self.assertNotIn(batch['id'], imports.pending_preview_batches(self.db))
        replacement = imports.claim_previews(self.db, batch['id'], item['id'], retry=True)
        self.assertNotEqual(replacement, token)
        detector = Mock(side_effect=AssertionError('An expired worker reused its stale token'))
        imports.run_previews(stuff.open_db_connection, batch['id'], item['id'], token, stuff.UPLOAD_FOLDER, detector)
        detector.assert_not_called()
        self.assertEqual(self.db.execute('SELECT token FROM banknote_import_preview_jobs WHERE item_id=?', (item['id'],)).fetchone()[0], replacement)

    def test_expired_queued_preview_reissues_token_on_ordinary_resume(self):
        batch = self.imported(lambda payload: payload['items'][0].update(status_text='Payment pending'))
        item = next(row for row in batch['items'] if row['state'] == 'blocked')
        original = imports.claim_previews(self.db, batch['id'], item['id'])
        with patch.object(imports.listing_images, 'download', side_effect=self.download):
            imports.run_previews(stuff.open_db_connection, batch['id'], item['id'], original,
                                 stuff.UPLOAD_FOLDER, self.preview_crop)
        # An explicit retry can be queued behind other work, then lose its
        # coordinator for longer than the lease. Cached old crops must not eat it.
        old_token = imports.claim_previews(self.db, batch['id'], item['id'], retry=True)
        self.db.execute('UPDATE banknote_import_preview_jobs SET expires=? WHERE item_id=?',
                        (time.time() - 1, item['id']))
        self.db.commit()
        self.assertIn(batch['id'], imports.pending_preview_batches(self.db))
        replacement = imports.claim_previews(self.db, batch['id'], item['id'])
        self.assertTrue(replacement)
        self.assertNotEqual(replacement, old_token)
        job = self.db.execute('SELECT * FROM banknote_import_preview_jobs WHERE item_id=?', (item['id'],)).fetchone()
        self.assertEqual(job['state'], 'queued')
        self.assertGreater(job['expires'], time.time())
        stale_detector = Mock(side_effect=AssertionError('The expired token must not run'))
        imports.run_previews(stuff.open_db_connection, batch['id'], item['id'], old_token,
                             stuff.UPLOAD_FOLDER, stale_detector)
        stale_detector.assert_not_called()
        imports.run_previews(stuff.open_db_connection, batch['id'], item['id'], replacement,
                             stuff.UPLOAD_FOLDER, self.smaller_crop)
        self.assertEqual(self.current_item(batch, item)['preview_state'], 'done')
        self.assertIsNone(imports.claim_previews(self.db, batch['id'], item['id']))

    def test_expired_queued_resume_still_revalidates_exact_purchase_membership(self):
        batch = self.imported(lambda payload: payload['items'][0].update(status_text='Payment pending'))
        item = next(row for row in batch['items'] if row['state'] == 'blocked')
        token = imports.claim_previews(self.db, batch['id'], item['id'])
        self.db.execute('UPDATE banknote_import_preview_jobs SET expires=? WHERE item_id=?',
                        (time.time() - 1, item['id']))
        self.db.execute("UPDATE banknote_import_batches SET snapshot_json='[]' WHERE id=?", (batch['id'],))
        self.db.commit()
        with self.assertRaises(imports.ImportProblem):
            imports.claim_previews(self.db, batch['id'], item['id'])
        self.assertEqual(self.db.execute('SELECT token FROM banknote_import_preview_jobs WHERE item_id=?',
                                        (item['id'],)).fetchone()[0], token)


if __name__ == '__main__':
    unittest.main()
