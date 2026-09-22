"""Today mail imports never change collection ownership or duplicate orders."""
import os
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
import ebay_mail
import ebay_orders


def evidence(status='Delivered', message='a', **changes):
    return dict(message_id=message * 64, item_id='166226977838', order_id='18-15170-60765',
                title='Australia 5 Pounds PMG 55 banknote', seller='note-dealer', status=status,
                observed_at='2026-09-20T12:00:00Z', quantity=1,
                evidence='your order has arrived', **changes)


class MailTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE banknotes (id TEXT PRIMARY KEY,status TEXT,description TEXT,note_references TEXT,photo TEXT,price REAL)')
        ebay_orders.init_schema(self.db)
        self.db.execute("INSERT INTO banknotes VALUES ('n1','Own','Listing: https://www.ebay.com/itm/166226977838','','photo.jpg',1000)")
        self.db.commit()
        self.app = Flask(__name__)
        ebay_mail.register(self.app, lambda: self.db)
        self.client = self.app.test_client()
        self.env = patch.dict(os.environ, {'STUFFAPP_TODAY_TOKEN': 'x' * 40})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.db.close()

    def post(self, events, auth=True):
        return self.client.post('/ebay/today', json={'events': events},
                                headers={'Authorization': 'Bearer ' + 'x' * 40} if auth else {})

    def test_own_and_all_collection_fields_unchanged(self):
        before = tuple(self.db.execute('SELECT * FROM banknotes').fetchone())
        self.assertEqual(self.post([evidence('Shipped')]).json['matched'], 1)
        self.assertEqual(self.post([evidence('Delivered', 'b')]).json['updated'], 1)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM banknotes').fetchone()), before)
        self.assertEqual(self.db.execute('SELECT delivery_status FROM ebay_order_items').fetchone()[0], 'Delivered')
        self.assertTrue(all('Today' in r[0] for r in self.db.execute('SELECT source FROM ebay_status_events')))

    def test_replay_older_notice_and_manual_override(self):
        self.post([evidence()])
        self.assertEqual(self.post([evidence()]).json['updated'], 0)
        self.post([evidence('Ordered', 'c')])
        self.assertEqual(self.db.execute('SELECT delivery_status FROM ebay_order_items').fetchone()[0], 'Delivered')
        self.db.execute("UPDATE banknote_ebay_links SET manual_status='Ordered'")
        self.db.commit()
        self.post([evidence('Delivered', 'd')])
        self.assertEqual(self.db.execute('SELECT manual_status FROM banknote_ebay_links').fetchone()[0], 'Ordered')

    def test_auth_validation_and_pause_write_nothing(self):
        self.assertEqual(self.post([evidence()], auth=False).status_code, 401)
        bad = dict(evidence(), observed_at='2099-01-01T00:00:00Z')
        self.assertEqual(self.post([evidence(), bad]).status_code, 400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)
        self.db.execute('INSERT INTO ebay_mail_connection(id,enabled) VALUES(1,0)')
        self.db.commit()
        self.assertEqual(self.post([evidence()]).status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)

    def test_repeat_listing_purchases_and_quantity_need_review(self):
        self.post([dict(evidence(), quantity=2)])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0], 0)

    def test_same_batch_repeat_purchases_do_not_match_the_first_order(self):
        self.post([evidence(), dict(evidence('Ordered', 'b'), order_id='19-15170-60765')])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0], 0)
        self.post([dict(evidence('Ordered', 'b'), order_id='19-15170-60765')])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0], 0)

    def test_api_order_reused_and_no_raw_body_stored(self):
        ebay_orders.apply_items(self.db, [{
            'line_key': '166226977838-123', 'order_id': '18-15170-60765', 'item_id': '166226977838',
            'title': 'Australia PMG banknote', 'seller': 'note-dealer', 'seller_key': '', 'quantity': 1,
            'ordered_at': '2026-09-01T12:00:00Z', 'shipped_at': None, 'delivered_at': None,
            'estimated_delivery': None, 'delivery_status': 'Ordered', 'attention': '', 'tracking': [],
        }])
        self.db.commit()
        self.assertEqual(self.post([dict(evidence('Delivered', 'b'), body='private address')]).status_code, 200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 1)
        self.assertEqual(self.db.execute('SELECT line_key FROM ebay_order_items').fetchone()[0], '166226977838-123')
        self.assertNotIn('private address', '\n'.join(self.db.iterdump()))


if __name__ == '__main__':
    unittest.main()
