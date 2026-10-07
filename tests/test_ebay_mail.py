"""Purchases, not eBay email, controls shipping. Merchant mail stays separate."""
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


def purchase(**changes):
    return dict(dict(item_id='166226977838', order_id='18-15170-60765',
        title='Australia 5 Pounds PMG 55 banknote', seller='note-dealer', quantity=1,
        status_text='Delivered', delivery_text='Delivered on Tue, Sep 22', ordered_date='Sep 18, 2026'), **changes)


class PurchasesTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.execute('CREATE TABLE banknotes (id TEXT PRIMARY KEY,status TEXT,description TEXT,note_references TEXT,photo TEXT,price REAL)')
        ebay_orders.init_schema(self.db)
        self.db.execute("INSERT INTO banknotes VALUES ('n1','Own','Listing: https://www.ebay.com/itm/166226977838','','photo.jpg',1000)")
        self.db.commit()
        app = Flask(__name__)
        ebay_mail.register(app, lambda: self.db)
        self.client = app.test_client()
        self.env = patch.dict(os.environ, {'STUFFAPP_TODAY_TOKEN': 'x' * 40})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.db.close()

    def post(self, items=None, **changes):
        payload = dict(source='ebay_purchases', account='test-buyer', observed_at='2026-10-07T06:00:00Z',
                       items=items if items is not None else [purchase()])
        payload.update(changes)
        return self.client.post('/ebay/today', json=payload, headers={'Authorization': 'Bearer ' + 'x' * 40})

    def test_updates_only_shipping_and_replays_are_idempotent(self):
        before = tuple(self.db.execute('SELECT * FROM banknotes').fetchone())
        self.assertEqual(self.post().json['matched'], 1)
        self.assertEqual(self.post().json['updated'], 0)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM banknotes').fetchone()), before)
        row = self.db.execute('SELECT * FROM ebay_order_items').fetchone()
        self.assertEqual(row['delivery_status'], 'Delivered')
        self.assertEqual(row['delivered_at'], '2026-09-22T00:00:00Z')
        self.assertIsNone(row['shipped_at'])

    def test_status_proof_and_year_boundaries(self):
        ambiguous = ebay_mail.validate_purchase(purchase(identity_ambiguous=True))
        self.assertEqual(ambiguous['delivery_status'], 'Ordered')
        self.assertIn('review required', ambiguous['attention'])
        self.assertIsNone(ambiguous['delivered_at'])
        for text in ('Tracking available', 'Awaiting shipment', 'Estimated delivery', 'Not delivered', 'Returned'):
            p = ebay_mail.validate_purchase(purchase(status_text=text, delivery_text='Est. delivery Thu, Oct 8 - Tue, Oct 13'))
            self.assertEqual(p['delivery_status'], 'Ordered')
            self.assertIsNone(p['delivered_at'])
        self.assertEqual(ebay_mail.validate_purchase(purchase(status_text='Shipped', delivery_text='Estimated delivery'))['delivery_status'], 'Shipped')
        self.assertEqual(ebay_mail.date_only('Fri, Jan 2', '2025-12-31T00:00:00Z'), '2026-01-02T00:00:00Z')
        self.assertIsNone(ebay_mail.date_only('Thu, Dec 31', '2026-10-01T00:00:00Z'))

    def test_tracking_available_is_normal_progress_not_a_review_warning(self):
        item = ebay_mail.validate_purchase(purchase(status_text='Tracking available', delivery_text=''))
        self.assertEqual(item['delivery_status'], 'Ordered')
        self.assertEqual(item['attention'], '')
        self.assertIsNone(item['shipped_at'])
        self.assertIsNone(item['delivered_at'])
        for status in ('Returned', 'Not delivered', 'Payment pending', 'Cancelled'):
            self.assertTrue(ebay_mail.validate_purchase(purchase(status_text=status))['attention'])

    def test_legacy_order_ids_and_seller_names_are_not_unreadable(self):
        for order_id in ('362612610393-1028917710023', '238257826017'):
            result = ebay_mail.validate_purchase(purchase(order_id=order_id, seller='*old*dealer*'))
            self.assertEqual(result['order_id'], order_id)
        good, skipped = ebay_mail.validate_purchases([
            purchase(order_id='238257826017', seller=''),
            purchase(order_id='238257826017', item_id='166226977839'), purchase()])
        self.assertEqual(len(good), 1)
        self.assertEqual(len(skipped), 1)
        for order_id in ('bad', '../238257826017', '123-abc', '1' * 32):
            with self.assertRaises(ValueError):
                ebay_mail.validate_purchase(purchase(order_id=order_id))

    def test_refund_and_delivery_are_independent(self):
        for status in ('Refunded', 'Partially refunded'):
            with self.subTest(status=status):
                delivered = ebay_mail.validate_purchase(purchase(status_text=status))
                self.assertEqual(delivered['delivery_status'], 'Delivered')
                self.assertEqual(delivered['delivered_at'], '2026-09-22T00:00:00Z')
                self.assertEqual(delivered['attention'], status)
                missing = ebay_mail.validate_purchase(purchase(status_text=status, delivery_text=''))
                self.assertEqual(missing['delivery_status'], 'Ordered')
                self.assertIn('delivery not confirmed', missing['attention'])
                display = ebay_orders.purchase_display_status(dict(missing,
                    purchase_status=status, manual_status=None))
                self.assertEqual(display, 'Refunded' if status == 'Refunded' else 'Ordered')
        manual = dict(missing, purchase_status='Refunded', manual_status='Delivered')
        self.assertEqual(ebay_orders.purchase_display_status(manual), 'Delivered')
        self.assertEqual(ebay_orders.purchase_display_status(dict(manual, manual_status=None), True), 'Unverified')

    def test_refund_does_not_erase_previous_confirmed_delivery(self):
        self.post()
        for hour in ('07', '08'):
            self.post([purchase(status_text='Refunded', delivery_text='')],
                      observed_at=f'2026-10-07T{hour}:00:00Z')
            row = dict(self.db.execute('SELECT * FROM ebay_order_items').fetchone())
            self.assertEqual(row['delivery_status'], 'Delivered')
            self.assertEqual(row['delivered_at'], '2026-09-22T00:00:00Z')
            self.assertEqual(ebay_orders.purchase_display_status(dict(row,
                purchase_status='Refunded', manual_status=None)), 'Delivered')
        self.post([purchase(status_text='Refunded', delivery_text='', identity_ambiguous=True)],
                  observed_at='2026-10-07T09:00:00Z')
        row = dict(self.db.execute('SELECT * FROM ebay_order_items').fetchone())
        self.assertEqual(ebay_orders.purchase_display_status(dict(row,
            purchase_status='Refunded', manual_status=None)), 'Unverified')

    def test_full_refund_flags_an_existing_link_without_changing_ownership(self):
        before = tuple(self.db.execute('SELECT * FROM banknotes').fetchone())
        self.post([purchase(status_text='Awaiting shipment', delivery_text='')])
        self.post([purchase(status_text='Refunded', delivery_text='')], observed_at='2026-10-07T07:00:00Z')
        row = dict(self.db.execute('SELECT i.*,l.manual_status,o.status_text AS purchase_status '
            'FROM ebay_order_items i JOIN banknote_ebay_links l ON l.line_key=i.line_key '
            'JOIN ebay_purchase_observations o ON o.line_key=i.line_key').fetchone())
        self.assertEqual(ebay_orders.purchase_display_status(row), 'Refunded')
        self.assertEqual(tuple(self.db.execute('SELECT * FROM banknotes').fetchone()), before)
        self.assertIsNone(row['delivered_at'])

    def test_legal_tender_refund_is_retained_for_review_without_a_false_match(self):
        result = self.post([purchase(item_id='206480786083',
            title='AC Fr 40 1923 $1 Legal Tender PCGS 64', status_text='Refunded', delivery_text='')]).json
        self.assertEqual(result['items_seen'], 1)
        self.assertEqual(result['matched'], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0], 0)

    def test_purchases_corrects_legacy_email_but_not_manual_override(self):
        self.post()
        self.db.execute("INSERT INTO ebay_mail_receipts VALUES ('old', 'purchases:18-15170-60765:166226977838','Delivered','email','2026-09-01T00:00:00Z')")
        self.db.execute('DELETE FROM ebay_purchase_observations')
        self.db.execute("UPDATE banknote_ebay_links SET manual_status='Shipped'")
        self.db.commit()
        self.assertTrue(ebay_orders.unverified_email_keys(self.db))
        self.post([purchase(status_text='Awaiting shipment', delivery_text='Est. delivery Thu, Oct 8')])
        self.assertFalse(ebay_orders.unverified_email_keys(self.db))
        row = self.db.execute('SELECT * FROM ebay_order_items').fetchone()
        self.assertEqual(row['delivery_status'], 'Ordered')
        self.assertIsNone(row['delivered_at'])
        self.assertEqual(self.db.execute('SELECT manual_status FROM banknote_ebay_links').fetchone()[0], 'Shipped')
        self.post(observed_at='2026-10-06T00:00:00Z')
        self.assertEqual(self.db.execute('SELECT delivery_status FROM ebay_order_items').fetchone()[0], 'Ordered')

    def test_rejects_legacy_auth_wrong_account_and_bad_envelopes(self):
        self.assertEqual(self.client.post('/ebay/today', json={'source':'ebay_purchases'}).status_code, 401)
        self.assertEqual(self.post(source='email', events=[]).status_code, 410)
        self.assertEqual(self.post(items=[]).status_code, 400)
        self.assertEqual(self.post(items='unreadable').status_code, 400)
        self.assertEqual(self.post(observed_at='2099-01-01T00:00:00Z').status_code, 400)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)
        self.post()
        self.assertEqual(self.post(account='another-buyer').status_code, 409)
        self.db.execute('UPDATE ebay_mail_connection SET enabled=0')
        self.db.commit()
        self.assertEqual(self.post().status_code, 409)

    def test_bad_orders_and_duplicate_identities_do_not_block_good_orders(self):
        for bad in (purchase(item_id='bad'), purchase(seller=''), purchase(ordered_date='invalid'),
                    purchase(delivery_text='Delivered on invalid')):
            with self.subTest(bad=bad):
                good = purchase(order_id='19-15170-60765')
                result = self.post([purchase(), bad, good]).json
                self.assertTrue(result['ok'])
                self.assertEqual(result['skipped'][0]['order_id'], purchase()['order_id'])
                self.assertEqual(result['items_accepted'], 1)
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items WHERE order_id=?',
                                                (purchase()['order_id'],)).fetchone()[0], 0)
        result = self.post([purchase(), purchase(), purchase(order_id='20-15170-60765')]).json
        self.assertEqual(result['skipped'][0]['reason'], 'Duplicate purchase identity')
        self.assertEqual(result['items_accepted'], 1)

    def test_skipped_existing_order_is_unchanged_while_other_orders_update(self):
        self.post()
        before = tuple(self.db.execute('SELECT * FROM ebay_order_items').fetchone())
        response = self.post([purchase(seller='', status_text='Shipped'),
                              purchase(order_id='19-15170-60765', status_text='Shipped')],
                             observed_at='2026-10-07T07:00:00Z')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM ebay_order_items WHERE order_id=?',
                                              (purchase()['order_id'],)).fetchone()), before)
        self.assertEqual(self.db.execute("SELECT delivery_status FROM ebay_order_items WHERE order_id='19-15170-60765'").fetchone()[0], 'Shipped')

    def test_ambiguous_stored_identity_skips_only_its_order(self):
        self.post()
        row = dict(self.db.execute('SELECT * FROM ebay_order_items').fetchone())
        row['line_key'] = 'duplicate-existing-line'
        self.db.execute('INSERT INTO ebay_order_items (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
        self.db.commit()
        result = self.post([purchase(status_text='Shipped'), purchase(order_id='19-15170-60765')],
                           observed_at='2026-10-07T07:00:00Z').json
        self.assertEqual(result['items_accepted'], 1)
        self.assertIn('Ambiguous stored', result['skipped'][0]['reason'])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM ebay_order_items WHERE delivery_status='Delivered'").fetchone()[0], 3)

    def test_all_skipped_is_explicit_and_partial_sets_do_not_infer_new_links(self):
        result = self.post([None, purchase(seller='')]).json
        self.assertEqual(result['items_accepted'], 0)
        self.assertEqual(len(result['skipped']), 2)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)
        result = self.post(skipped=[dict(order_id='19-15170-60765', reason='Unreadable fields: seller')]).json
        self.assertEqual(result['items_seen'], 1)
        self.assertEqual(result['matched'], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0], 0)

    def test_multi_quantity_and_repeat_purchases_do_not_auto_match(self):
        self.post([purchase(quantity=2)])
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0], 0)
        self.assertEqual(self.post([purchase(), purchase(order_id='19-15170-60765')], observed_at='2026-10-07T07:00:00Z').status_code, 200)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM banknote_ebay_links').fetchone()[0], 0)

    def test_purchase_account_deletion_suppresses_reimport(self):
        from ebay_notifications import delete_account_data
        self.post()
        delete_account_data(self.db, {'metadata': {'topic': 'MARKETPLACE_ACCOUNT_DELETION'},
            'notification': {'data': {'username': 'test-buyer'}}})
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_purchase_account').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_purchase_observations').fetchone()[0], 0)
        self.db.execute('UPDATE ebay_mail_connection SET enabled=1')
        self.db.commit()
        self.assertEqual(self.post().status_code, 409)

    def test_non_ebay_mail_is_review_only_minimal_and_deduplicated(self):
        notice = dict(message_id='a'*64, sender='orders@dealer.test', subject='Your order has shipped',
            order_id='123-ABC', status='Shipped', observed_at='2026-10-06T00:00:00Z',
            evidence='Your order has shipped', body='PRIVATE ADDRESS')
        self.assertEqual(self.post(source='merchant_email', events=[notice]).json['items_seen'], 1)
        self.assertEqual(self.post(source='merchant_email', events=[notice]).json['items_seen'], 0)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)
        self.assertNotIn('PRIVATE ADDRESS', '\n'.join(self.db.iterdump()))
        self.assertEqual(self.post(source='merchant_email', events=[dict(notice, sender='notice@ebay.co.uk')]).status_code, 400)


if __name__ == '__main__':
    unittest.main()
