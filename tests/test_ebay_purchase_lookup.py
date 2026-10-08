import os
from pathlib import Path
import sqlite3
import sys
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask, abort
import ebay_orders
import ebay_purchase_lookup as lookup


class LookupTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('CREATE TABLE banknotes (id TEXT PRIMARY KEY,order_number TEXT,marketplace TEXT, '
                        'status TEXT, description TEXT, note_references TEXT)')
        ebay_orders.init_schema(self.db)
        self.db.execute("INSERT INTO banknotes (id,order_number,marketplace) VALUES ('note','12-15265-43926','eBay')")
        self.db.commit()
        self.env = patch.dict(os.environ, {'STUFFAPP_TODAY_TOKEN': 'x' * 40})
        self.env.start()
        self.note = dict(self.db.execute('SELECT * FROM banknotes').fetchone())
        app = Flask(__name__)
        self.owner = True
        lookup.register(app, lambda: self.db, lambda: None if self.owner else abort(403))
        self.client = app.test_client()

    def tearDown(self):
        self.env.stop()
        self.db.close()

    def post(self, **payload):
        return self.client.post('/ebay/today/requests', json=payload,
                                headers={'Authorization': 'Bearer ' + 'x' * 40})

    def item(self, **changes):
        return dict(dict(order_id=self.note['order_number'], item_id='178536931638',
            title='French Antilles 10 Francs PMG 67 EPQ', seller='dealer', quantity=1,
            status_text='Order processing', delivery_text='', ordered_date='Oct 08, 2026'), **changes)

    def complete(self, job, **changes):
        payload = dict(action='complete', id=job['id'], account='buyer',
                       observed_at=ebay_orders.now_iso(), items=[self.item()])
        payload.update(changes)
        return self.post(**payload)

    def test_missing_order_round_trip_and_status_is_owner_only(self):
        job = lookup.ensure(self.db, self.note)
        self.assertEqual(job['status'], 'queued')
        self.assertEqual(lookup.ensure(self.db, self.note)['id'], job['id'])
        self.assertEqual(self.post(action='claim').json['request']['id'], job['id'])
        self.assertIsNone(self.post(action='claim').json['request'])
        self.assertEqual(self.complete(job).status_code, 200)
        item = dict(self.db.execute('SELECT * FROM ebay_order_items').fetchone())
        self.assertEqual(item['attention'], '')
        self.assertEqual(item['delivery_status'], 'Ordered')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0], 0)
        self.assertIsNone(lookup.ensure(self.db, self.note))
        url = '/banknotes/note/purchase-refresh/' + job['id']
        self.assertEqual(self.client.get(url).json['status'], 'done')
        self.owner = False
        self.assertEqual(self.client.get(url).status_code, 403)
        self.owner = True
        self.db.execute("UPDATE banknotes SET order_number='11-11111-11111'")
        self.db.commit()
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_old_processing_warning_requests_a_fresh_observation(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        self.assertEqual(self.complete(job).status_code, 200)
        self.db.execute("UPDATE ebay_order_items SET attention='Order processing; shipment or delivery not confirmed'")
        self.db.execute('UPDATE ebay_purchase_requests SET requested_at=?', (time.time()-20,))
        self.db.commit()
        retry = lookup.ensure(self.db, self.note)
        self.assertEqual(retry['status'], 'queued')

    def test_auth_account_scope_pause_and_bad_results(self):
        self.assertEqual(self.client.post('/ebay/today/requests', json={'action':'claim'}).status_code, 401)
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        self.db.execute("INSERT INTO ebay_purchase_account VALUES (1,'buyer')")
        self.db.commit()
        for changes in (dict(account='other'), dict(items=[self.item(order_id='11-11111-11111')]),
                        dict(items=[self.item(), self.item()]), dict(items=[self.item(seller='')]),
                        dict(items=[]), dict(observed_at='2099-01-01T00:00:00Z')):
            self.assertEqual(self.complete(job, **changes).status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)
        self.db.execute('INSERT OR IGNORE INTO ebay_mail_connection (id,enabled) VALUES (1,0)')
        self.db.execute('UPDATE ebay_mail_connection SET enabled=0')
        self.db.commit()
        self.assertEqual(self.complete(job).status_code, 409)

    def test_multiple_items_preserved_for_matcher_not_silently_selected(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        result = self.complete(job, items=[self.item(), self.item(item_id='178536931639')])
        self.assertEqual(result.status_code, 200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 2)

    def test_filtered_non_banknote_sibling_cannot_turn_a_multi_item_order_into_one_note(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        result = self.complete(job, items=[self.item(), self.item(item_id='178536931639', title='Album')])
        self.assertEqual(result.status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)

    def test_failure_expiry_retry_and_source_scoping(self):
        self.assertIsNone(lookup.ensure(self.db, dict(self.note, marketplace='Direct')))
        self.assertIsNone(lookup.ensure(self.db, dict(self.note, order_number='not-an-order')))
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        self.assertEqual(self.post(action='complete', id=job['id'], error='browser').status_code, 200)
        self.assertEqual(lookup.ensure(self.db, self.note)['status'], 'failed')
        self.db.execute('UPDATE ebay_purchase_requests SET requested_at=?', (time.time()-20,))
        self.db.commit()
        retry = lookup.ensure(self.db, self.note)
        self.assertNotEqual(retry['id'], job['id'])
        self.db.execute('UPDATE ebay_purchase_requests SET requested_at=?', (time.time()-121,))
        self.db.commit()
        self.assertIsNone(self.post(action='claim').json['request'])
        self.assertEqual(self.complete(retry).status_code, 409)
        self.assertEqual(self.db.execute('SELECT status FROM ebay_purchase_requests').fetchone()[0], 'failed')


if __name__ == '__main__':
    unittest.main()
