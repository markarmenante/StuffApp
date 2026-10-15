"""Exact, reusable feedback handoffs; no provider or ownership writes."""
from pathlib import Path
import sqlite3
import sys
import unittest
from unittest.mock import patch

from flask import Flask, abort

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import banknote_feedback as feedback


class FeedbackHandoffTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:')
        self.db.row_factory = sqlite3.Row
        self.db.executescript('''
            CREATE TABLE banknotes(id TEXT PRIMARY KEY,status TEXT,marketplace TEXT,order_number TEXT);
            CREATE TABLE ebay_order_items(line_key TEXT PRIMARY KEY,order_id TEXT,item_id TEXT,
                title TEXT,seller TEXT,quantity INTEGER,ignored INTEGER DEFAULT 0);
            CREATE TABLE banknote_ebay_links(banknote_id TEXT,line_key TEXT);
            CREATE TABLE banknote_original_listings(banknote_id TEXT,url TEXT);
            CREATE TABLE banknote_source_archives(banknote_id TEXT,url TEXT);
            CREATE TABLE purchase_source_archives(url TEXT,title TEXT,kind TEXT);
            CREATE TABLE record_documents(category TEXT,record_id TEXT,doc_set TEXT,title TEXT,filename TEXT);
            INSERT INTO banknotes VALUES('note-1','Own','eBay',NULL);
            INSERT INTO ebay_order_items VALUES('purchases:12-34567-89012:123456789012',
                '12-34567-89012','123456789012','Canada 1 Dollar','seller-one',1,0);
            INSERT INTO banknote_ebay_links VALUES('note-1','purchases:12-34567-89012:123456789012');
        ''')
        self.db.commit()
        self.app = Flask(__name__, template_folder=str(ROOT / 'templates'))
        self.app.config.update(TESTING=True)
        self.allowed = True
        self.visible = True
        def require_owner():
            if not self.allowed:
                abort(403)
        feedback.register(self.app, lambda: self.db, require_owner, lambda c, r: self.visible)
        self.client = self.app.test_client()

    def tearDown(self):
        self.db.close()

    def handoff(self):
        return feedback.handoff(self.db, 'banknotes',
                                self.db.execute("SELECT * FROM banknotes WHERE id='note-1'").fetchone())

    def test_exact_purchase_uses_validated_order_and_same_origin_page(self):
        before = self.db.total_changes
        item = self.handoff()
        self.assertEqual(item['state'], 'ready')
        self.assertEqual(item['url'], '/banknotes/note-1/feedback?order=12-34567-89012&item=123456789012')
        self.assertEqual(item['order_url'], 'https://order.ebay.com/ord/show?orderId=12-34567-89012')
        self.assertEqual(item['item_id'], '123456789012')
        self.assertEqual(item['comment'], 'Banknote as described. Very smooth transaction.')
        self.assertEqual((item['rating'], item['stars']), ('Positive', 5))
        self.assertNotIn('transaction_id', item)
        self.assertNotIn('submitted', item)
        self.assertEqual(self.handoff(), item)
        self.assertEqual(self.db.total_changes, before)

    def test_shared_listing_in_different_order_keeps_exact_link(self):
        self.db.execute("INSERT INTO ebay_order_items VALUES ('another','98-76543-21098',"
                        "'123456789012','Another purchase','another-seller',1,0)")
        self.db.execute("INSERT INTO banknote_original_listings VALUES('note-1','https://www.ebay.com/itm/123456789012')")
        self.assertEqual(self.handoff()['order_id'], '12-34567-89012')

    def test_no_guessed_order_from_listing_or_seller(self):
        self.db.execute('DELETE FROM banknote_ebay_links')
        self.db.execute("INSERT INTO banknote_original_listings VALUES('note-1','https://www.ebay.com/itm/123456789012')")
        self.db.execute("UPDATE banknotes SET order_number='12-34567-89012'")
        item = self.handoff()
        self.assertEqual(item['state'], 'unavailable')
        self.assertIsNone(item['url'])
        self.assertIsNone(item['order_url'])

    def test_duplicates_and_shared_match_are_unavailable(self):
        self.db.execute("INSERT INTO ebay_order_items SELECT 'duplicate',order_id,item_id,title,seller,quantity,ignored FROM ebay_order_items")
        self.assertEqual(self.handoff()['state'], 'unavailable')
        self.db.execute("DELETE FROM ebay_order_items WHERE line_key='duplicate'")
        self.db.execute("INSERT INTO banknote_ebay_links SELECT 'note-2',line_key FROM banknote_ebay_links")
        self.assertEqual(self.handoff()['state'], 'unavailable')

    def test_ignored_multi_quantity_and_invalid_ids_have_no_url(self):
        for field, value in [('ignored', 1), ('quantity', 2), ('order_id', '123456789012'),
                             ('order_id', '12-34567-89012&other=1'), ('item_id', 'not-an-id')]:
            with self.subTest(field=field, value=value):
                self.db.execute('SAVEPOINT invalid')
                self.db.execute(f'UPDATE ebay_order_items SET {field}=?', (value,))
                self.assertEqual(self.handoff()['state'], 'unavailable')
                self.assertIsNone(self.handoff()['order_url'])
                self.db.execute('ROLLBACK TO invalid')
                self.db.execute('RELEASE invalid')

    def test_explicit_order_and_marketplace_conflicts_are_unavailable(self):
        for field, value in [('order_number', '98-76543-21098'), ('order_number', ''), ('marketplace', 'Direct')]:
            with self.subTest(field=field, value=value):
                self.db.execute('SAVEPOINT invalid')
                self.db.execute(f'UPDATE banknotes SET {field}=?', (value,))
                self.assertEqual(self.handoff()['state'], 'unavailable')
                self.db.execute('ROLLBACK TO invalid')
                self.db.execute('RELEASE invalid')
        self.db.execute("UPDATE banknotes SET order_number='12-34567-89012'")
        self.assertEqual(self.handoff()['state'], 'ready')

    def test_only_inspected_owned_banknotes_get_handoff(self):
        for status in ('Ordered', 'Shipped', 'Delivered', 'Sold', 'Loaned', '', None):
            self.db.execute('UPDATE banknotes SET status=?', (status,))
            self.assertEqual(self.handoff()['state'], 'unavailable', status)
        self.db.execute("UPDATE banknotes SET status='Owned'")
        self.assertEqual(self.handoff()['state'], 'ready')
        self.assertIsNone(feedback.handoff(self.db, 'coins', {'id': 'note-1', 'status': 'Own'}))

    def test_order_helper_must_return_exact_ebay_url(self):
        for url in ('https://evil.example/ord/show?orderId=12-34567-89012',
                    'https://order.ebay.com.evil.example/ord/show?orderId=12-34567-89012',
                    'https://order.ebay.com/ord/show?orderId=98-76543-21098',
                    'https://order.ebay.com/ord/show?orderId=12-34567-89012&redirect=https://evil.example',
                    'javascript:alert(1)'):
            with self.subTest(url=url), patch.object(feedback.purchase_orders, 'order_reference',
                    return_value=dict(provider='eBay', number='12-34567-89012', url=url)):
                self.assertEqual(self.handoff()['state'], 'unavailable')

    def test_page_reopens_without_writes_and_escapes_purchase_text(self):
        self.db.execute('UPDATE ebay_order_items SET title=?,seller=?',
                        ('<script>alert(1)</script>', '\"><img src=x onerror=alert(1)>'))
        before = self.db.total_changes
        for _ in range(2):
            response = self.client.get('/banknotes/note-1/feedback')
            self.assertEqual(response.status_code, 200)
            text = response.get_data(as_text=True)
            self.assertIn('&lt;script&gt;alert(1)&lt;/script&gt;', text)
            self.assertNotIn('<img src=x', text)
            self.assertIn(feedback.COMMENT, text)
            self.assertIn('target="_blank" rel="noopener noreferrer"', text)
            self.assertIn('choose <strong>Leave feedback</strong>', text)
            self.assertNotIn('<form', text)
            self.assertNotIn('fetch(', text)
            self.assertNotIn('window.open', text)
            self.assertEqual(response.headers['Cache-Control'], 'private, no-store')
            self.assertEqual(response.headers['Referrer-Policy'], 'no-referrer')
        self.assertEqual(self.db.total_changes, before)
        self.assertEqual(self.db.execute('SELECT status FROM banknotes').fetchone()[0], 'Own')

    def test_reopened_handoff_stays_bound_to_purchase_identity(self):
        url = self.handoff()['url']
        self.assertIn('id="open-ebay-order"', self.client.get(url).get_data(as_text=True))
        for wrong in (url.replace('123456789012', '999999999999'), url + '&order=98-76543-21098'):
            self.assertNotIn('id="open-ebay-order"', self.client.get(wrong).get_data(as_text=True))
        self.db.execute("UPDATE ebay_order_items SET order_id='98-76543-21098'")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn('linked purchase has changed', response.get_data(as_text=True))
        self.assertNotIn('id="open-ebay-order"', response.get_data(as_text=True))

    def test_unavailable_page_has_no_ebay_action(self):
        self.db.execute('DELETE FROM banknote_ebay_links')
        response = self.client.get('/banknotes/note-1/feedback')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('id="open-ebay-order"', response.get_data(as_text=True))

    def test_route_is_read_only_owner_and_row_scoped(self):
        self.assertEqual(self.client.post('/banknotes/note-1/feedback').status_code, 405)
        self.allowed = False
        self.assertEqual(self.client.get('/banknotes/note-1/feedback').status_code, 403)
        self.allowed = True
        self.visible = False
        self.assertEqual(self.client.get('/banknotes/note-1/feedback').status_code, 404)
        self.assertEqual(self.client.get('/banknotes/missing/feedback').status_code, 404)


if __name__ == '__main__':
    unittest.main()
