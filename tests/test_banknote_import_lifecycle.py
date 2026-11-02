"""Explicit order retries recover expired reader work without replacing live work."""
import json
import time
import unittest
from unittest.mock import patch

import test_banknote_imports as fixture_module


class ReaderLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture_module.DraftTests()
        self.fixture.setUp()

    def tearDown(self):
        self.fixture.tearDown()

    def claim(self):
        return self.fixture.client.post(
            '/ebay/today/requests', json={'action': 'claim'},
            headers=fixture_module.HEADERS).json['request']

    def test_expired_claim_is_replaced_by_explicit_retry_without_mac_poll(self):
        fixture = self.fixture
        batch = fixture.batch()
        previous = self.claim()
        fixture.db.execute(
            'UPDATE ebay_purchase_request_sessions SET expires_at=? WHERE request_id=?',
            (time.time() - 1, previous['id']))
        fixture.db.commit()
        response = fixture.client.post('/banknotes/imports', json={
            'order_number': batch['order_number'], 'refresh': True})
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['id'], batch['id'])
        self.assertEqual(response.json['state'], 'queued')
        current = fixture.db.execute(
            'SELECT * FROM ebay_purchase_requests WHERE order_id=?',
            (batch['order_number'],)).fetchone()
        self.assertNotEqual(current['id'], previous['id'])
        self.assertEqual(current['status'], 'queued')
        # A delayed result from the abandoned reader must not fail its successor.
        stale = fixture.client.post('/ebay/today/requests',
            json=fixture.payload(previous), headers=fixture_module.HEADERS)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(fixture.db.execute(
            'SELECT status FROM ebay_purchase_requests WHERE id=?',
            (current['id'],)).fetchone()[0], 'queued')
        self.assertEqual(fixture.db.execute(
            'SELECT COUNT(*) FROM banknote_import_items').fetchone()[0], 0)

    def test_unexpired_reader_is_reused_even_when_request_timestamp_is_old(self):
        fixture = self.fixture
        batch = fixture.batch()
        previous = self.claim()
        fixture.db.execute('UPDATE ebay_purchase_requests SET requested_at=? WHERE id=?',
                           (time.time() - 1000, previous['id']))
        fixture.db.commit()
        response = fixture.client.post('/banknotes/imports', json={
            'order_number': batch['order_number'], 'refresh': True})
        self.assertEqual(response.status_code, 200, response.json)
        current = fixture.db.execute(
            'SELECT id,status FROM ebay_purchase_requests WHERE order_id=?',
            (batch['order_number'],)).fetchone()
        self.assertEqual(tuple(current), (previous['id'], 'reading'))

    def test_expired_queued_request_gets_a_fresh_session(self):
        fixture = self.fixture
        batch = fixture.batch()
        previous = fixture.db.execute(
            'SELECT id FROM ebay_purchase_requests WHERE order_id=?',
            (batch['order_number'],)).fetchone()[0]
        fixture.db.execute(
            'UPDATE ebay_purchase_request_sessions SET expires_at=? WHERE request_id=?',
            (time.time() - 1, previous))
        fixture.db.commit()
        response = fixture.client.post('/banknotes/imports', json={
            'order_number': batch['order_number'], 'refresh': True})
        self.assertEqual(response.status_code, 200, response.json)
        current = self.claim()
        self.assertNotEqual(current['id'], previous)
        self.assertGreater(current['expires_at'], time.time())

    def test_refreshed_gallery_does_not_select_retained_removed_photos(self):
        fixture = self.fixture
        batch = fixture.imported()
        item = batch['items'][0]

        def failed_evaluate(*_):
            raise RuntimeError('Catalogue provider unavailable')

        batch = fixture.check(batch, item, failed_evaluate)
        item = next(row for row in batch['items'] if row['id'] == item['id'])
        self.assertEqual(item['check_state'], 'failed')
        original_files = {
            row['filename'] for row in fixture.db.execute(
                'SELECT filename FROM banknote_import_assets WHERE item_id=?',
                (item['id'],))
        }
        self.assertEqual(len(original_files), 2)
        ebay_id = fixture.db.execute(
            'SELECT item_id FROM banknote_import_items WHERE id=?',
            (item['id'],)).fetchone()[0]
        current_urls = [
            'https://i.ebayimg.com/images/g/refreshed-front/s-l1600.jpg',
            'https://i.ebayimg.com/images/g/refreshed-back/s-l1600.jpg',
        ]
        fixture.db.execute(
            'UPDATE ebay_listing_captures SET images_json=?,captured_at=? WHERE url=?',
            (json.dumps(current_urls), time.time(), 'https://www.ebay.com/itm/' + ebay_id))
        fixture.db.commit()
        classified = []
        classify = fixture.classify

        def current_gallery(photos):
            classified.extend(photo['filename'] for photo in photos if photo['gallery'])
            return classify(photos)

        with patch.object(fixture, 'classify', side_effect=current_gallery):
            batch = fixture.check(batch, item)
        current = next(row for row in batch['items'] if row['id'] == item['id'])
        self.assertEqual(current['check_state'], 'done')
        self.assertEqual(len(classified), 2)
        self.assertFalse(original_files.intersection(classified))
        for field in ('image_1', 'image_2'):
            self.assertIn(current['fields'][field], classified)
        # Refresh is not deletion: original gallery photos remain inspectable.
        retained = {
            row['filename'] for row in fixture.db.execute(
                'SELECT filename FROM banknote_import_assets WHERE item_id=?',
                (item['id'],))
        }
        self.assertTrue(original_files.issubset(retained))


if __name__ == '__main__':
    unittest.main()
