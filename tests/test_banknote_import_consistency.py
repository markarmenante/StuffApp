"""Check publication and release must retain the evidence they actually read."""
from pathlib import Path
import unittest
from unittest.mock import patch

import test_banknote_imports as fixtures

imports = fixtures.imports
stuff = fixtures.stuff


class ImportConsistencyTests(unittest.TestCase):
    # Reuse the isolated checkout fixture without rerunning its entire suite.
    setUp = fixtures.DraftTests.setUp
    tearDown = fixtures.DraftTests.tearDown
    batch = fixtures.DraftTests.batch
    payload = fixtures.DraftTests.payload
    imported = fixtures.DraftTests.imported
    single_imported = fixtures.DraftTests.single_imported
    check = fixtures.DraftTests.check
    download = fixtures.DraftTests.download
    classify = fixtures.DraftTests.classify
    release = fixtures.DraftTests.release
    partial_record = fixtures.DraftTests.partial_record

    def assert_changed_evidence_rejected(self, changed):
        batch = self.single_imported()
        item = batch['items'][0]

        def evaluate(note, prepared):
            if changed == 'capture':
                self.db.execute('UPDATE ebay_listing_captures SET text=text || ? WHERE url=?',
                                (' Changed evidence.', item['listing_url']))
            elif changed == 'original':
                (Path(stuff.UPLOAD_FOLDER) / note['image_1']).write_bytes(b'changed')
            elif changed == 'receipt':
                self.db.execute('UPDATE ebay_purchase_prices SET unit_amount_minor=unit_amount_minor+1')
            else:
                self.db.execute("UPDATE ebay_order_items SET ordered_at='2026-10-25T00:00:00Z'")
            self.db.commit()
            return dict(filled={'country': 'Must not publish'})

        result = self.check(batch, item, evaluate)
        updated = result['items'][0]
        self.assertEqual(updated['check_state'], 'failed')
        self.assertFalse(updated['fields'].get('country'))
        self.assertFalse(updated['fields'].get('image_1'))
        self.assertIsNone(stuff._finish_single_import(self.db, batch['id']))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)

    def test_normal_check_rejects_changed_capture(self):
        self.assert_changed_evidence_rejected('capture')

    def test_normal_check_rejects_changed_original(self):
        self.assert_changed_evidence_rejected('original')

    def test_normal_check_rejects_changed_receipt(self):
        self.assert_changed_evidence_rejected('receipt')

    def test_normal_check_rejects_changed_purchase_date(self):
        self.assert_changed_evidence_rejected('purchase_date')

    def test_release_rejects_original_changed_after_check(self):
        batch = self.imported()
        batch = self.check(batch, batch['items'][0])
        item = batch['items'][0]
        (Path(stuff.UPLOAD_FOLDER) / item['fields']['image_1']).write_bytes(b'changed')
        response = self.release(batch, [item])
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0], 0)

    def test_concurrent_duplicate_purchase_prevents_single_completion(self):
        batch = self.single_imported()
        batch = self.check(batch, batch['items'][0])
        source = dict(self.db.execute('SELECT * FROM ebay_order_items').fetchone())
        source['line_key'] = 'another-transaction-for-the-same-purchase'
        self.db.execute('INSERT INTO ebay_order_items (' + ','.join(source) + ') VALUES (' +
                        ','.join('?' for _ in source) + ')', list(source.values()))
        self.db.commit()
        self.assertIsNone(stuff._finish_single_import(self.db, batch['id']))
        self.assertEqual(self.release(batch).status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)

    def test_release_rejects_changed_original_behind_accepted_crop(self):
        batch = self.imported()
        batch = self.check(batch, batch['items'][0], prepare_photo=lambda raw, note:
                           dict(data=raw, quad=[[0, 0], [159, 0], [159, 79], [0, 79]]))
        item = batch['items'][0]
        source = self.db.execute('SELECT source_filename FROM banknote_import_image_edits '
                                 'WHERE item_id=? AND field=?', (item['id'], 'image_1')).fetchone()[0]
        (Path(stuff.UPLOAD_FOLDER) / source).write_bytes(b'changed')
        self.assertEqual(self.release(batch, [item]).status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)

    def test_single_multiplicative_bundle_cannot_check_or_publish(self):
        batch = self.single_imported(lambda payload: payload['items'][0].update(
            title='3 x Colombia 1 Peso Banknotes PMG 66'))
        item = batch['items'][0]
        self.assertEqual(item['state'], 'blocked')
        self.assertFalse(item['can_check'])
        self.assertIsNone(stuff._finish_single_import(self.db, batch['id']))
        self.assertEqual(self.release(batch).status_code, 409)

    def test_multi_checkout_retains_bundle_without_blocking_exact_siblings(self):
        batch = self.imported(lambda payload: payload['items'][0].update(
            title='3 x Colombia 1 Peso Banknotes PMG 66'))
        bundle = next(item for item in batch['items'] if item['title'].startswith('3 x'))
        siblings = [item for item in batch['items'] if item['id'] != bundle['id']]
        self.assertEqual(bundle['state'], 'blocked')
        self.assertFalse(bundle['can_release'])
        self.assertEqual(self.release(batch, [bundle]).status_code, 409)
        self.assertEqual(self.release(batch, siblings).status_code, 200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 2)

    def test_single_note_dimensions_are_not_multiplicative_quantity(self):
        batch = self.single_imported(lambda payload: payload['items'][0].update(
            title='1 x Colombia 1 Peso Banknote PMG 66 150 x 80 mm'))
        self.assertEqual(batch['items'][0]['state'], 'draft')
        batch = self.check(batch, batch['items'][0])
        self.assertTrue(stuff._finish_single_import(self.db, batch['id']))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 1)

    def test_keywordless_review_does_not_turn_negative_face_value_positive(self):
        self.assertFalse(imports._review_note_title('Colombia -1 Peso Oro P380g Grade66'))
        self.assertTrue(imports._review_note_title('Colombia 1 Peso Oro P380g Grade66'))

    def test_explicit_pack_counts_are_distinct_from_unit_labelled_dimensions(self):
        for title in ('3x Colombia 1 Peso Banknotes PMG 66',
                      'Colombia 1 Peso Banknotes PMG 66 x 3',
                      '2 × Colombia 1 Peso P380g',
                      'Colombia 1 Peso P380g ×2'):
            with self.subTest(title=title):
                self.assertTrue(imports._bundle_title(title))
        for title in ('Colombia 1 Peso P380g 150 x 80 mm',
                      'Colombia 1 Peso P380g 150mm x80mm',
                      'Colombia 1 Peso P380g 15.0 × 8.0 cm',
                      'Colombia 1 Peso P380g 6 x 3 inches',
                      '1 x Colombia 1 Peso P380g'):
            with self.subTest(title=title):
                self.assertFalse(imports._bundle_title(title))

    def test_keywordless_review_refuses_explicit_non_note_objects(self):
        for title in ('Camera P100 5 Dollars', 'P380g 5 dollars book'):
            with self.subTest(title=title):
                self.assertFalse(imports._review_note_title(title))
        self.assertTrue(imports._review_note_title('Colombia 1 Peso catalogue P380g Grade66'))

    def recovery_with_changed_photo(self):
        self.partial_record()
        batch = self.imported()
        item = next(item for item in batch['items'] if item.get('existing_record_id'))
        fixtures.Image.new('RGB', (160, 80), 'purple').save(Path(stuff.UPLOAD_FOLDER) / 'newer-back.jpg')
        self.db.execute("UPDATE banknotes SET image_2='newer-back.jpg' WHERE id='failed-form'")
        self.db.commit()
        return batch, item

    def test_recovery_before_photo_remains_visible_until_review_accepts_new_photo(self):
        batch, item = self.recovery_with_changed_photo()
        response = self.client.get('/uploads/saved-back.jpg')
        self.assertEqual(response.status_code, 200)
        response.close()
        latest = next(value for value in self.client.get(batch['status_url']).json['items']
                      if value['id'] == item['id'])
        response = self.client.post(item['detail_url'] + '/refresh-existing', json={
            'revision': latest['revision'], 'existing_record_version': latest['existing_record_version']})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get('/uploads/saved-back.jpg').status_code, 404)

    def test_recovery_snapshot_uploads_keep_owner_account_and_tenant_boundaries(self):
        self.recovery_with_changed_photo()
        self.db.execute("INSERT OR REPLACE INTO users(id,email,display_name,role,categories) "
                        "VALUES('recovery-viewer','recovery-viewer@example.test','Viewer','viewer','banknotes')")
        self.db.commit()
        with patch.object(stuff, '_resolve_user_email', return_value='recovery-viewer@example.test'):
            self.assertEqual(self.client.get('/uploads/saved-back.jpg').status_code, 404)
        with patch.object(stuff, 'TENANT_CATEGORIES', {'coins'}):
            self.assertEqual(self.client.get('/uploads/saved-back.jpg').status_code, 404)
        self.db.execute("UPDATE ebay_purchase_account SET account_name='another-buyer'")
        self.db.commit()
        self.assertEqual(self.client.get('/uploads/saved-back.jpg').status_code, 404)

    def test_recovery_snapshot_and_crop_original_remain_protected_from_cleanup(self):
        self.recovery_with_changed_photo()
        original = 'saved-back-full-original.jpg'
        fixtures.Image.new('RGB', (180, 100), 'yellow').save(Path(stuff.UPLOAD_FOLDER) / original)
        self.db.execute('INSERT INTO trimmed_image_sources(trimmed,source,quad) VALUES(?,?,?)',
                        ('saved-back.jpg', original, 'null'))
        self.db.commit()
        referenced = stuff._collect_referenced_uploads(self.db)
        self.assertIn('saved-back.jpg', referenced)
        self.assertIn(original, referenced)


if __name__ == '__main__':
    unittest.main()
