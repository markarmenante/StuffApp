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
import ebay_listing_captures as captures


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

    def test_public_listing_capture_is_bound_to_exact_single_item(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        listing = dict(url='https://www.ebay.com/itm/178536931638',
                       title='French Antilles 10 Francs PMG 67 EPQ',
                       text='Seller notes: French Antilles 10 Francs, certificate 1151490-008. <script>bad()</script>',
                       images=['https://i.ebayimg.com/images/g/front/s-l1600.webp'])
        for bad in (dict(listing, url='https://www.ebay.com/itm/178536931639'),
                    dict(listing, images=['http://localhost/private']),
                    dict(listing, images=['https://i.ebayimg.com@evil.example/image.jpg'])):
            self.assertEqual(self.complete(job, listing=bad).status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)
        self.assertEqual(self.complete(job, listing=listing).status_code, 200)
        html = captures.html(self.db, listing['url'])
        self.assertIn('&lt;script&gt;bad()', html)
        self.assertNotIn('<script>bad()', html)
        self.db.execute('UPDATE ebay_purchase_requests SET requested_at=?', (time.time()-400,))
        self.db.commit()
        self.assertIsNone(lookup.ensure(self.db, self.note))
        self.db.execute('DELETE FROM ebay_listing_captures')
        self.db.commit()
        self.assertEqual(lookup.ensure(self.db, self.note)['status'], 'queued')

    def test_public_capture_cannot_choose_a_multi_item_order(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        self.assertEqual(self.complete(job, items=[self.item(), self.item(item_id='178536931639')],
                                       listing={}).status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)

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


    def receipt(self, **changes):
        return dict(dict(order_id=self.note['order_number'], item_id='178536931638',
            quantity=1, url='https://order.ebay.com/ord/show?orderId=' + self.note['order_number'],
            currency='USD', unit_amount='599.89', observed_at=ebay_orders.now_iso(),
            evidence='Order number ' + self.note['order_number'] + '\nItem info\n'
                     'French Antilles 10 Francs PMG 67 EPQ\nUnit price USD 599.89\n'
                     'Item number: 178536931638\nPayment summary\nTax USD 20.00\nOrder total USD 619.89'), **changes)

    def cached_listing(self):
        return dict(url='https://www.ebay.com/itm/178536931638',
                    title='French Antilles 10 Francs PMG 67 EPQ',
                    text='French Antilles 10 Francs PMG 67 EPQ. Asking price USD 750.00.',
                    images=[])

    def test_receipt_round_trip_stores_exact_unit_amount_and_does_not_edit_record(self):
        self.db.execute('ALTER TABLE banknotes ADD COLUMN price TEXT')
        self.db.execute("UPDATE banknotes SET price='$600'")
        self.db.commit()
        job = lookup.ensure(self.db, dict(self.note, price='$600'))
        self.post(action='claim')
        response = self.complete(job, receipt=self.receipt(), listing=self.cached_listing())
        self.assertEqual(response.status_code, 200, response.json)
        row = dict(self.db.execute('SELECT * FROM ebay_purchase_prices').fetchone())
        self.assertEqual((row['currency'], row['unit_amount_minor']), ('USD', 59989))
        self.assertEqual(row['source_url'], self.receipt()['url'])
        self.assertEqual(row['evidence'], self.receipt()['evidence'])
        self.assertEqual(self.db.execute('SELECT price FROM banknotes').fetchone()[0], '$600')
        self.assertIsNone(lookup.ensure(self.db, dict(self.note, price='')))
        self.assertEqual(self.complete(job, receipt=self.receipt()).status_code, 409)

    def test_receipt_failure_rolls_back_purchase_listing_and_observation_together(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        response = self.complete(job, receipt=self.receipt(unit_amount='619.89'),
                                 listing=self.cached_listing())
        self.assertEqual(response.status_code, 409, response.json)
        for table in ('ebay_order_items', 'ebay_purchase_observations', 'ebay_listing_captures',
                      'ebay_purchase_prices'):
            self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ' + table).fetchone()[0], 0, table)
        self.assertEqual(self.db.execute('SELECT status FROM ebay_purchase_requests').fetchone()[0], 'reading')
        self.assertEqual(self.complete(job, receipt=self.receipt()).status_code, 200)

    def test_receipt_rejects_wrong_identity_currency_amount_and_stale_observations(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        wrong = [
            dict(order_id='11-11111-11111'), dict(item_id='178536931639'),
            dict(url='https://www.ebay.com/itm/178536931638'),
            dict(url=self.receipt()['url'] + '&other=1'), dict(quantity=2),
            dict(currency='CAD'), dict(unit_amount=599.89), dict(unit_amount='599,89'),
            dict(unit_amount='599.899'), dict(unit_amount='0.00'),
            dict(unit_amount='1000000.01'), dict(evidence='Unit price USD 599.89'),
            dict(evidence='x' * 2501), dict(observed_at='2020-01-01T00:00:00Z'),
            dict(observed_at='2099-01-01T00:00:00Z'),
            dict(observed_at='2026-10-13T08:00:00'),
        ]
        for change in wrong:
            with self.subTest(change=change):
                response = self.complete(job, receipt=self.receipt(**change))
                self.assertEqual(response.status_code, 409, response.json)
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_purchase_prices').fetchone()[0], 0)
        self.assertEqual(self.complete(job, receipt=self.receipt()).status_code, 200)

    def test_receipt_requires_explicit_currency_and_ignores_totals_and_financing(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        good = self.receipt()['evidence']
        for evidence in (
                good.replace('USD 599.89', '$599.89'),
                good.replace('USD 599.89', '599.89'),
                good.replace('Unit price USD 599.89', 'Order total USD 599.89'),
                good.replace('Unit price USD 599.89', 'As low as USD 599.89/mo'),
                good.replace('Item number: 178536931638', 'Item number: 178536931639'),
                good.replace(self.note['order_number'], '11-11111-11111'),
                good + '\nCoupon USD 10.00', good + '\nPartially refunded',
                good + '\nOrder number 11-11111-11111', good + good):
            with self.subTest(evidence=evidence):
                self.assertEqual(self.complete(job, receipt=self.receipt(evidence=evidence)).status_code, 409)
        evidence = good.replace('USD 599.89', '$599.89') + '\nCurrency: USD'
        self.assertEqual(self.complete(job, receipt=self.receipt(evidence=evidence)).status_code, 200)
        self.assertEqual(self.db.execute('SELECT unit_amount_minor FROM ebay_purchase_prices').fetchone()[0], 59989)

    def test_receipt_preserves_native_euro_currency(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        receipt = self.receipt(currency='EUR', unit_amount='479.50',
                               evidence=self.receipt()['evidence'].replace('USD 599.89', 'EUR 479.50'))
        response = self.complete(job, receipt=receipt)
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(tuple(self.db.execute('SELECT currency,unit_amount_minor FROM ebay_purchase_prices').fetchone()),
                         ('EUR', 47950))

    def test_receipt_rejects_multi_quantity_siblings_and_attention(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        for items in (
                [self.item(quantity=2)],
                [self.item(), self.item(item_id='178536931639')],
                [self.item(identity_ambiguous=True)],
                [self.item(status_text='Partially refunded')]):
            with self.subTest(items=items):
                self.assertEqual(self.complete(job, items=items, receipt=self.receipt()).status_code, 409)
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)

    def test_receipt_cannot_cross_account_or_bypass_bridge_token(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        self.db.execute("INSERT INTO ebay_purchase_account VALUES (1,'buyer')")
        self.db.commit()
        response = self.complete(job, account='different-buyer', receipt=self.receipt())
        self.assertEqual(response.status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_purchase_prices').fetchone()[0], 0)
        payload = dict(action='complete', id=job['id'], account='buyer',
                       observed_at=ebay_orders.now_iso(), items=[self.item()], receipt=self.receipt())
        response = self.client.post('/ebay/today/requests', json=payload,
                                    headers={'Authorization': 'Bearer wrong-token'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(self.db.execute('SELECT status FROM ebay_purchase_requests').fetchone()[0], 'reading')

    def test_blank_price_refreshes_missing_receipt_despite_cached_public_listing(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        self.assertEqual(self.complete(job, listing=self.cached_listing()).status_code, 200)
        # A just-completed reader with no receipt may be a layout/currency limitation.
        # Keep the cooldown rather than sending every repeated Check back to Chrome.
        self.assertIsNone(lookup.ensure(self.db, dict(self.note, price='')))
        self.db.execute('UPDATE ebay_purchase_requests SET requested_at=?', (time.time() - 400,))
        self.db.commit()
        self.assertIsNone(lookup.ensure(self.db, dict(self.note, price='$600')))
        refresh = lookup.ensure(self.db, dict(self.note, price=''))
        self.assertEqual(refresh['status'], 'queued')
        self.assertNotEqual(refresh['id'], job['id'])


    def test_literal_dollar_receipt_preserves_symbol_without_inventing_usd(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        evidence = self.receipt()['evidence'].replace('USD 599.89', '$599.89')
        response = self.complete(job, receipt=self.receipt(currency='$', evidence=evidence))
        self.assertEqual(response.status_code, 200, response.json)
        row = self.db.execute('SELECT currency,unit_amount_minor FROM ebay_purchase_prices').fetchone()
        self.assertEqual(tuple(row), ('$', 59989))
        import ebay_purchase_prices
        item = self.db.execute('SELECT * FROM ebay_order_items').fetchone()
        self.assertEqual(ebay_purchase_prices.for_item(self.db, item)['price'], '$599.89')
        self.assertNotIn('Currency: USD', self.db.execute('SELECT evidence FROM ebay_purchase_prices').fetchone()[0])


if __name__ == '__main__':
    unittest.main()
