"""Review eligibility must not depend on the purchase matcher's currency list."""
from pathlib import Path
import hashlib
import json
import time
import unittest
from unittest.mock import Mock, patch

import test_banknote_imports as fixtures

imports = fixtures.imports
stuff = fixtures.stuff
BRAZIL_TITLE = 'Brazil 100 Cruzeiros ND(1964) P170b Uncirculated Grade 68 Top Pop (1)'


class ReviewCurrencyTests(unittest.TestCase):
    setUp = fixtures.DraftTests.setUp
    tearDown = fixtures.DraftTests.tearDown
    batch = fixtures.DraftTests.batch
    payload = fixtures.DraftTests.payload
    imported = fixtures.DraftTests.imported
    single_imported = fixtures.DraftTests.single_imported
    group_receipt_payload = fixtures.DraftTests.group_receipt_payload
    check = fixtures.DraftTests.check
    classify = fixtures.DraftTests.classify
    release = fixtures.DraftTests.release
    current_item = fixtures.DraftTests.current_item
    prepare_previews = fixtures.DraftTests.prepare_previews
    preview_crop = staticmethod(fixtures.DraftTests.preview_crop)

    def download(self, url, folder):
        asset = fixtures.DraftTests.download(self, url, folder)
        if 'extra-note' in url:
            path = Path(folder) / asset['filename']
            fixtures.Image.new('RGB', (160, 80), 'yellow').save(path)
            asset['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        return asset

    def review_item(self, title=BRAZIL_TITLE, quantity=1, extra_image=False):
        def change(payload):
            self.group_receipt_payload(payload)
            payload['items'][0].update(title=title)
            payload['listings'][0].update(title=title, text=title + '; exact purchased listing.')
            if extra_image:
                payload['listings'][0]['images'].append('https://i.ebayimg.com/images/g/extra-note/s-l1600.jpg')
            receipt = payload['receipts'][0]
            receipt.update(unit_amount='299.99',
                evidence=f"Order number: {receipt['order_id']}\nItem info\nUnit price USD 299.99\n"
                         f"Item number: {receipt['item_id']}\nShipping USD 9.00\nTax USD 23.45\nOrder total USD 999.99")
        batch = self.imported(change)
        item = next(item for item in batch['items'] if item['title'] == title)
        if quantity != 1:
            source = dict(self.db.execute('SELECT * FROM ebay_order_items WHERE item_id=?', (fixtures.IDS[0],)).fetchone())
            source['quantity'] = quantity
            self.db.execute('UPDATE ebay_order_items SET quantity=? WHERE item_id=?', (quantity, fixtures.IDS[0]))
            self.db.execute('UPDATE banknote_import_items SET source_json=?,source_digest=? WHERE id=?',
                            (json.dumps(source), imports._digest(source), item['id']))
            self.db.commit()
            item = self.current_item(batch, item)
        return batch, item

    def test_brazil_review_uses_originals_and_exact_price_then_releases_only_that_note(self):
        batch, item = self.review_item()
        self.assertTrue(item['can_check'], 'Cruzeiros must not leave the exact purchased note frozen')
        self.assertFalse(item['can_edit'], 'Check must establish the unknown title as one banknote first')
        self.assertFalse(item['can_release'])
        self.assertEqual(item['state'], 'blocked')
        self.assertEqual(item['fields']['price'], '$299.99')
        self.assertFalse(item['fields'].get('image_1'))
        item = self.prepare_previews(batch, item)
        originals = {row['source_filename'] for row in self.db.execute(
            'SELECT source_filename FROM banknote_import_photo_previews WHERE item_id=?', (item['id'],))}
        self.assertEqual(len(originals), 2)

        def evaluate(note, prepared):
            for field in ('image_1', 'image_2'):
                self.assertIn(note[field], originals)
                with fixtures.Image.open(Path(stuff.UPLOAD_FOLDER) / note[field]) as image:
                    self.assertEqual(image.size, (160, 80), 'Check reads full originals, not display crops')
            return dict(filled=dict(country='Brazil', denomination='100 Cruzeiros', pick_number='P-170b',
                date_1=1964, grading_authority='PMG', grade_numeric=68,
                price='$999.99', status='Own'))

        batch = self.check(batch, item, evaluate, prepare_photo=self.preview_crop)
        item = self.current_item(batch, item)
        self.assertIn(item['check_state'], ('done', 'partial'))
        self.assertTrue(item['can_edit'])
        self.assertTrue(item['can_release'])
        self.assertEqual(item['fields']['country'], 'Brazil')
        self.assertEqual(item['fields']['denomination'], '100 Cruzeiros')
        self.assertEqual(item['fields']['pick_number'], 'P-170b')
        self.assertEqual(item['fields']['price'], '$299.99')
        self.assertEqual(item['fields']['status'], 'Ordered')
        self.assertIn('Multiple items', ' '.join(item['warnings']))
        for field in ('image_1', 'image_2'):
            self.assertIn(stuff._banknote_vision_source(item['fields'][field], self.db), originals)
            response = self.client.get('/uploads/' + item['fields'][field])
            self.assertEqual(response.status_code, 200)
            response.close()
        self.assertIsNone(stuff._finish_single_import(self.db, batch['id']))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)
        saved = self.client.post(item['detail_url'], json={'revision': item['revision'],
            'updates': {'notes': 'Reviewed exact Brazil note'}})
        self.assertEqual(saved.status_code, 200, saved.json)
        item = saved.json['item']
        response = self.release(batch, [item])
        self.assertEqual(response.status_code, 200, response.json)
        rows = self.db.execute('SELECT * FROM banknotes').fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]['country'], 'Brazil')
        self.assertEqual(rows[0]['price'], '$299.99')
        self.assertEqual(rows[0]['status'], 'Ordered')
        self.assertEqual(rows[0]['notes'], 'Reviewed exact Brazil note')
        after = self.client.get(batch['status_url']).json
        self.assertEqual(after['pending_count'], 2)

    def test_review_accepts_other_historical_currency_families(self):
        for title in (BRAZIL_TITLE, 'Peru 10 Soles de Oro P84a Uncirculated Grade 66',
                      'Brazil 1000 Cruzados P214a Uncirculated Grade 66',
                      'Hungary 100 Pengo P98 Uncirculated Grade 66',
                      'Germany 100 Reichsmark P183 Uncirculated Grade 66'):
            with self.subTest(title=title):
                try:
                    batch, item = self.review_item(title)
                    self.assertTrue(item['can_check'])
                    self.assertFalse(item['can_edit'])
                    self.assertFalse(item['can_release'])
                    self.assertEqual(item['state'], 'blocked')
                    batch = self.check(batch, item)
                    item = self.current_item(batch, item)
                    self.assertTrue(item['can_edit'], item['check_message'])
                    self.assertTrue(item['can_release'])
                    self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)
                finally:
                    self.tearDown(); self.setUp()

    def test_review_keeps_bundle_quantity_and_known_object_guards(self):
        cases = [(BRAZIL_TITLE, 2), ('3 x ' + BRAZIL_TITLE, 1),
                 ('Camera P170b 100 Cruzeiros', 1),
                 ('Brazil 100 Cruzeiros P170b and P171a', 1),
                 ('Brazil 100 Cruzeiros and 200 Cruzeiros P170b', 1),
                 ('Brazil 100 Cruzeiros & 200 Cruzeiros P170b', 1),
                 ('Peru 10 Soles de Oro and 20 Soles de Oro P84a', 1)]
        for title, quantity in cases:
            with self.subTest(title=title, quantity=quantity):
                try:
                    batch, item = self.review_item(title, quantity)
                    self.assertFalse(item['can_check'])
                    self.assertFalse(item['can_edit'])
                    self.assertFalse(item['can_release'])
                    self.assertEqual(self.release(batch, [item]).status_code, 409)
                finally:
                    self.tearDown(); self.setUp()

    def test_unknown_words_and_catalogue_only_need_photo_proof_before_editing(self):
        for title in ('Brazil P170b Uncirculated Grade 68', 'Brazil 100 Widgets P170b',
                      'Unidentified collectible'):
            with self.subTest(title=title):
                try:
                    batch, item = self.review_item(title)
                    self.assertTrue(item['can_check'])
                    self.assertFalse(item['can_edit'])
                    self.assertFalse(item['can_release'])
                    saved = self.client.post(item['detail_url'], json={'revision': item['revision'],
                        'updates': {'country': 'Brazil', 'denomination': '100 Cruzeiros', 'pick_number': 'P-170b'}})
                    self.assertEqual(saved.status_code, 409)
                    self.assertEqual(self.release(batch, [item]).status_code, 409)
                    batch = self.check(batch, item)
                    self.assertTrue(self.current_item(batch, item)['can_edit'])
                    self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)
                finally:
                    self.tearDown(); self.setUp()

    def test_unverified_or_mixed_originals_cannot_unlock_unknown_currency_review(self):
        for defect in ('pair_unverified', 'low_confidence', 'incomplete', 'other_side', 'extra_other_note'):
            with self.subTest(defect=defect):
                try:
                    batch, item = self.review_item(extra_image=defect == 'extra_other_note')
                    def classify(photos):
                        result = fixtures.DraftTests.classify(self, photos)
                        if defect == 'pair_unverified': result['pair_verified'] = False
                        elif defect == 'low_confidence': result['photos'][0]['confidence'] = 'low'
                        elif defect == 'incomplete': result['photos'][0]['complete_note'] = False
                        elif defect == 'other_side': result['photos'][0]['same_note'] = False
                        else: result['photos'][2]['same_note'] = False
                        return result
                    evaluate = Mock(return_value=dict(filled={'country': 'Must not publish'}))
                    with patch.object(self, 'classify', side_effect=classify):
                        batch = self.check(batch, item, evaluate)
                    evaluate.assert_not_called()
                    item = self.current_item(batch, item)
                    self.assertTrue(item['can_check'], 'An uncertain result remains retryable')
                    self.assertFalse(item['can_edit'])
                    self.assertFalse(item['can_release'])
                    self.assertFalse(item['fields'].get('country'))
                    self.assertFalse(item['fields'].get('image_1'))
                    self.assertFalse(item['fields'].get('image_2'))
                    self.assertGreaterEqual(len(item['photos']), 2, 'Full originals remain available for inspection')
                    self.assertEqual(self.release(batch, [item]).status_code, 409)
                    self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)
                    if defect != 'extra_other_note':
                        batch = self.check(batch, item)
                        self.assertTrue(self.current_item(batch, item)['can_edit'], 'A later verified Check recovers the draft')
                finally:
                    self.tearDown(); self.setUp()

    def test_clean_pair_with_holder_only_photo_can_establish_note_identity(self):
        batch, item = self.review_item(extra_image=True)
        def classify(photos):
            result = fixtures.DraftTests.classify(self, photos)
            result['photos'][2].update(side='unknown', complete_note=False, same_note=True)
            return result
        with patch.object(self, 'classify', side_effect=classify):
            batch = self.check(batch, item)
        item = self.current_item(batch, item)
        self.assertTrue(item['can_edit'], item['check_message'])
        self.assertTrue(item['can_release'])
        self.assertEqual(len(item['photos']), 3)

    def test_source_capture_or_original_change_invalidates_saved_photo_identity(self):
        for changed in ('source', 'capture', 'original'):
            with self.subTest(changed=changed):
                original_path = None
                try:
                    batch, item = self.review_item()
                    batch = self.check(batch, item)
                    item = self.current_item(batch, item)
                    self.assertTrue(item['can_edit'])
                    if changed == 'source':
                        source = dict(self.db.execute('SELECT * FROM ebay_order_items WHERE item_id=?', (fixtures.IDS[0],)).fetchone())
                        source['title'] = BRAZIL_TITLE.replace('100 Cruzeiros', '200 Cruzeiros')
                        self.db.execute('UPDATE ebay_order_items SET title=? WHERE item_id=?', (source['title'], fixtures.IDS[0]))
                        self.db.execute('UPDATE banknote_import_items SET source_json=?,source_digest=? WHERE id=?',
                                        (json.dumps(source), imports._digest(source), item['id']))
                    elif changed == 'capture':
                        self.db.execute('UPDATE ebay_listing_captures SET text=text || ? WHERE url=?',
                                        (' Changed banknote evidence.', item['listing_url']))
                    else:
                        filename = stuff._banknote_vision_source(item['fields']['image_1'], self.db)
                        original_path = Path(stuff.UPLOAD_FOLDER) / filename
                        original_bytes = original_path.read_bytes()
                        original_path.write_bytes(b'Changed original image')
                    self.db.commit()
                    updated = self.current_item(batch, item)
                    if changed != 'original':
                        self.assertFalse(updated['can_edit'])
                        self.assertFalse(updated['can_release'])
                    # Status reads use saved asset metadata; the committing
                    # release action must additionally verify original bytes.
                    self.assertEqual(self.release(batch, [updated]).status_code, 409)
                    self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)
                finally:
                    if original_path: original_path.write_bytes(original_bytes)
                    self.tearDown(); self.setUp()

    def test_capture_age_does_not_freeze_a_verified_banknote_draft(self):
        batch, item = self.review_item()
        batch = self.check(batch, item)
        item = self.current_item(batch, item)
        self.db.execute('UPDATE ebay_listing_captures SET captured_at=? WHERE url=?',
                        (time.time() - imports.ebay_listing_captures.MAX_AGE - 60, item['listing_url']))
        self.db.commit()
        item = self.current_item(batch, item)
        self.assertFalse(item['can_check'], 'A new Check needs a fresh captured listing')
        self.assertTrue(item['can_edit'], 'Existing verified originals remain editable after time alone')
        self.assertTrue(item['can_release'])
        saved = self.client.post(item['detail_url'], json={'revision': item['revision'],
            'updates': {'notes': 'Reviewed after capture aged'}})
        self.assertEqual(saved.status_code, 200, saved.json)
        self.assertEqual(self.release(batch, [saved.json['item']]).status_code, 200)

    def test_currency_review_does_not_expand_automatic_single_note_completion(self):
        def change(payload):
            payload['items'][0]['title'] = BRAZIL_TITLE
            payload['listings'][0].update(title=BRAZIL_TITLE, text=BRAZIL_TITLE)
        batch = self.single_imported(change)
        batch = self.check(batch, batch['items'][0], lambda *_: dict(filled={}))
        self.assertIsNone(stuff._finish_single_import(self.db, batch['id']))
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknotes').fetchone()[0], 0)


if __name__ == '__main__':
    unittest.main()
