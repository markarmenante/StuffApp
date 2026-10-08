"""Original purchase evidence, persistent links and one-time comparison safety."""
import json
from html.parser import HTMLParser
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from flask import g

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-original-listing-')
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ['ORIGINAL_LISTING_AI_CHECKS'] = '0'
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)

import original_listings as sources
import listing_checks as checks
import source_documents as archives
import purchase_orders as orders
import app as stuff

URL = 'https://www.vcoins.com/en/stores/dealer/123/product/silver_tetradrachm/123456/Default.aspx'
HTML = '<html><title>Silver coin</title><h1>Ancient silver tetradrachm</h1><p>Weight: 13.15 g. Sold.</p></html>'
TEXT = 'Ancient silver tetradrachm. Weight: 13.15 g. Sold.'


class ListingTests(unittest.TestCase):
    def setUp(self):
        self.client = stuff.app.test_client()
        self.id = 'original-test-' + self._testMethodName
        self.context = stuff.app.app_context()
        self.context.push()
        self.db = stuff.get_db()
        self.db.execute("INSERT INTO coins (id,region,weight,status) VALUES (?,'Syria',12.5,'Own')", (self.id,))
        self.db.execute("INSERT INTO banknotes (id,country,status) VALUES (?,'Canada','Own')", (self.id,))
        self.db.commit()

    def tearDown(self):
        self.db.rollback()
        for table in ('coins', 'banknotes'):
            self.db.execute(f'DELETE FROM {table} WHERE id=?', (self.id,))
        self.db.execute('DELETE FROM original_listing_pages')
        self.db.execute('DELETE FROM purchase_source_archives')
        self.db.execute('DELETE FROM record_documents WHERE record_id=?', (self.id,))
        self.db.commit()
        self.context.pop()

    def available(self, category='coins'):
        sources.add_source(self.db, category, self.id, URL)
        self.db.execute("UPDATE original_listing_pages SET state='available',checked_at=?,next_check_at=?",
                        (time.time(), time.time() + 86400))
        self.db.commit()

    def get(self, path):
        # This fixture retains an app context; real requests get a fresh g.
        g.pop('ebay_deliveries', None)
        g.pop('listing_review_reasons', None)
        return self.client.get(path, base_url='https://localhost')

    def state(self, category='coins'):
        return self.get(f'/{category}/{self.id}/original-listing').json

    def post(self, data, category='coins'):
        self.get(f'/{category}/{self.id}')
        with self.client.session_transaction(base_url='https://localhost') as session:
            csrf = session['ebay_csrf']
        return self.client.post(f'/{category}/{self.id}/original-listing/review',
                                base_url='https://localhost', data=dict(csrf_token=csrf, **data))

    def test_only_exact_item_urls(self):
        for url in [URL, 'https://ebay.com/itm/123456789012?abc=1',
                    'https://cngcoins.com/Coin.aspx?CoinID=123',
                    'https://www.cngcoins.com/Lot.aspx?LOT_ID=4',
                    'https://ma-shops.com/dealer/item.php?id=123']:
            self.assertIsNotNone(sources.exact_listing(url), url)
        for url in ['https://www.vcoins.com/en/Search.aspx?searchQuery=SKU',
                    'https://www.ebay.com/sch/i.html', 'https://www.cngcoins.com/Search.aspx',
                    'https://localhost/itm/123456789012', URL.replace('www.vcoins.com', 'www.vcoins.com.evil.test'),
                    URL.replace('https://', 'file://'), URL.replace('www.', 'user:pass@www.'),
                    URL.replace('www.vcoins.com', 'www.vcoins.com:8443')]:
            self.assertIsNone(sources.exact_listing(url), url)

    def test_page_liveness_includes_sold_excludes_blocked_and_gone(self):
        self.assertEqual(sources.page_state(URL, 200, HTML, URL), 'available')
        for status, body, expected in [(410, '', 'gone'), (404, '', 'gone'), (503, HTML, 'unknown'),
            (200, '<h1>Access denied</h1>', 'unknown'),
            (200, '<h1>Just a moment</h1>', 'unknown'),
            (200, '<h1>Search our inventory</h1>', 'unknown'),
            (200, '<h1>This listing was removed</h1>', 'gone')]:
            self.assertEqual(sources.page_state(URL, status, body, URL), expected)
        self.assertEqual(sources.page_state(URL, 200, HTML, URL.replace('123456/', '999999/')), 'unknown')
        lot = 'https://www.cngcoins.com/Lot.aspx?LOT_ID=4'
        self.assertEqual(sources.page_state(lot, 200, '<h3 id="_ctl0_txtName">AEOLIS, Myrina. Silver coin.</h3>', lot), 'available')
        shop = 'https://www.cngcoins.com/Coin.aspx?CoinID=123'
        self.assertEqual(sources.page_state(shop, 200, '<title>CNG: The Coin Shop. KINGS of MACEDON. Perseus. Silver.</title>', shop), 'available')

    def test_reference_links_not_promoted_but_explicit_purchase_is(self):
        row = dict(self.db.execute('SELECT * FROM coins WHERE id=?', (self.id,)).fetchone())
        row['coin_references'] = 'Compare with ' + URL
        self.assertIsNone(sources.candidate(self.db, 'coins', row))
        row['description'] = 'Listing: ' + URL
        self.assertEqual(sources.candidate(self.db, 'coins', row), URL)
        row['description'] += '\nListing: ' + URL.replace('123456/', '999999/')
        self.assertIsNone(sources.candidate(self.db, 'coins', row))

    def test_link_without_warning_both_categories_no_network_in_request(self):
        for category in ('coins', 'banknotes'):
            self.available(category)
            with patch.object(sources, 'fetch_listing', side_effect=AssertionError('network during request')):
                result = self.state(category)
                self.assertEqual(result['link']['url'], URL)
                page = self.get(f'/{category}/{self.id}')
                self.assertEqual(page.status_code, 200)
                self.assertTrue(b'VCoins Original Listing' in page.data)
                self.assertIsNone(result['review'])

    def test_stale_unreadable_link_hidden(self):
        self.available()
        for state, age in [('available', 86401), ('gone', 0), ('unknown', 0)]:
            self.db.execute('UPDATE original_listing_pages SET state=?,checked_at=?', (state, time.time()-age))
            self.db.commit()
            self.assertIsNone(self.state()['link'])

    def test_review_header_retains_invoice_listing_and_order_after_reload(self):
        self.available()
        self.db.execute('INSERT INTO coin_purchase_reviews VALUES (?,?,?)', (self.id, 'Check currency', 'today'))
        self.db.execute('INSERT INTO coin_purchase_review_sources VALUES (?,?,?,?)',
                        (self.id, 'https://www.vcoins.com/en/MyAccount/ShowOrder.aspx?IdOrder=1', 'VCoins order 1', 0))
        self.db.execute('INSERT INTO record_documents (id,category,record_id,title,filename) VALUES (?,?,?,?,?)',
                        (self.id, 'coins', self.id, 'Invoice', 'test-invoice.pdf'))
        self.db.commit()
        current = self.state()
        before = dict(self.db.execute('SELECT * FROM coins WHERE id=?', (self.id,)).fetchone())
        result = self.post(dict(action='dismiss', review_token=current['review']['token'], check_token=''))
        self.assertEqual(result.status_code, 200)
        self.assertTrue(result.json['review']['dismissed'])
        self.assertEqual(len(result.json['links']), 3)
        page = self.get('/coins/' + self.id).data.decode()
        header = page.split('data-listing-title')[1].split('</div>')[0]
        for text in ('Marked reviewed', 'VCoins Original Listing', 'Invoice', 'VCoins order 1'):
            self.assertIn(text, header)
        self.assertNotIn('id="coinReviewReason"', page)
        self.assertEqual(before, dict(self.db.execute('SELECT * FROM coins WHERE id=?', (self.id,)).fetchone()))
        result = self.post(dict(action='restore', review_token=current['review']['token'], check_token=''))
        self.assertFalse(result.json['review']['dismissed'])

    def test_check_once_never_overwrites_facts_and_dismisses(self):
        self.available()
        checks.ensure(self.db, 'coins', self.id, URL)
        self.db.commit()
        analyze = Mock(return_value={'comparisons': [{'field': 'weight', 'listing_value': '13.15',
                        'evidence': 'Weight: 13.15 g.', 'outcome': 'different'}]})
        fetch = Mock(return_value=('available', TEXT))
        self.assertTrue(checks.run_once(stuff.open_db_connection, fetch, analyze))
        self.assertFalse(checks.run_once(stuff.open_db_connection, fetch, analyze))
        self.assertEqual(analyze.call_count, 1)
        self.assertEqual(self.db.execute('SELECT weight FROM coins WHERE id=?', (self.id,)).fetchone()[0], 12.5)
        state = self.state()
        self.assertEqual(state['check']['state'], 'checked')
        self.assertEqual(len(state['check']['differences']), 1)
        data = dict(action='dismiss', review_token='', check_token=state['check']['token'])
        self.assertTrue(self.post(data).json['check']['dismissed'])
        self.assertFalse(checks.run_once(stuff.open_db_connection, fetch, analyze))
        self.assertFalse(self.post(dict(data, action='restore')).json['check']['dismissed'])

    def banknote_order(self, attention='Refunded; delivery not confirmed', status='Refunded'):
        self.db.execute("UPDATE banknotes SET status='Ordered' WHERE id=?", (self.id,))
        self.db.execute('INSERT INTO ebay_order_items '
                        '(line_key,order_id,item_id,title,quantity,delivery_status,attention,last_seen) '
                        "VALUES (?,'10-15260-84325','226073044650','Japan 10 Yen',1,'Ordered',?,'today')",
                        (self.id, attention))
        self.db.execute('INSERT INTO banknote_ebay_links '
                        '(banknote_id,line_key,matched_by,matched_at) VALUES (?,?,?,?)',
                        (self.id, self.id, 'listing', 'today'))
        self.db.execute('INSERT INTO ebay_purchase_observations VALUES (?,?,?,?)',
                        (self.id, 'today', status, ''))
        self.db.commit()

    def test_banknote_shipping_reason_displays_and_review_clears_both_views(self):
        self.banknote_order()
        before = dict(self.db.execute('SELECT * FROM banknotes WHERE id=?', (self.id,)).fetchone())
        state = self.state('banknotes')
        self.assertEqual(state['review']['reason'], 'Refunded; delivery not confirmed')
        source = dict(label='eBay Order 10-15260-84325',
                      url='https://order.ebay.com/ord/show?orderId=10-15260-84325')
        self.assertEqual(state['review']['sources'], [source])
        self.assertIn(source, state['links'])
        page = self.get('/banknotes/' + self.id).data.decode()
        self.assertIn('Review Reason', page)
        self.assertIn('href="' + source['url'] + '"', page)
        self.assertNotIn('href="https://www.ebay.com/mye/myebay/purchase"', page)
        self.assertIn('Refunded; delivery not confirmed</textarea>', page)
        self.assertIn('Refunded \u00b7 Review', page)
        self.assertIn('Please Review', self.get('/banknotes').data.decode())
        data = dict(action='dismiss', review_token=state['review']['token'], check_token='')
        response = self.post(data, 'banknotes')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json['review']['dismissed'])
        self.assertFalse(response.json['delivery']['attention'])
        self.assertEqual(response.json['delivery']['status'], 'Refunded')
        page = self.get('/banknotes/' + self.id).data.decode()
        self.assertIn('Marked reviewed', page)
        self.assertIn('eBay Order 10-15260-84325', page)
        self.assertIn(source, response.json['links'])
        self.assertNotIn('id="coinReviewReason"', page)
        self.assertNotIn('Refunded \u00b7 Review', page)
        listing = self.get('/banknotes').data.decode()
        self.assertNotIn('Please Review', listing)
        self.assertNotIn('Refunded \u00b7 Review', listing)
        self.assertEqual(before, dict(self.db.execute('SELECT * FROM banknotes WHERE id=?', (self.id,)).fetchone()))
        restored = self.post(dict(data, action='restore'), 'banknotes')
        self.assertTrue(restored.json['delivery']['attention'])
        self.assertIn('Refunded; delivery not confirmed</textarea>', self.get('/banknotes/' + self.id).data.decode())

    def test_banknote_review_stays_dismissed_until_evidence_changes(self):
        self.banknote_order()
        state = self.state('banknotes')
        data = dict(action='dismiss', review_token=state['review']['token'], check_token='')
        self.assertEqual(self.post(data, 'banknotes').status_code, 200)
        self.db.execute('UPDATE ebay_order_items SET last_seen=? WHERE line_key=?', ('tomorrow', self.id))
        self.db.execute('UPDATE ebay_purchase_observations SET observed_at=? WHERE line_key=?', ('tomorrow', self.id))
        self.db.commit()
        self.assertTrue(self.state('banknotes')['review']['dismissed'])
        self.db.execute('UPDATE ebay_order_items SET attention=? WHERE line_key=?', ('Payment disputed', self.id))
        self.db.commit()
        self.assertFalse(self.state('banknotes')['review']['dismissed'])
        self.assertEqual(self.post(data, 'banknotes').status_code, 409)
        self.db.execute('DELETE FROM banknote_ebay_links WHERE banknote_id=?', (self.id,))
        self.assertIsNone(self.db.execute('SELECT * FROM banknote_purchase_review_dismissals WHERE banknote_id=?', (self.id,)).fetchone())

    def test_banknote_tracking_does_not_reopen_dismissed_listing_review(self):
        self.banknote_order('Tracking available; shipment or delivery not confirmed', 'Tracking available')
        self.available('banknotes')
        checks.ensure(self.db, 'banknotes', self.id, URL)
        self.db.execute("UPDATE original_listing_checks SET state='checked',dismissed=1,result=? WHERE banknote_id=?",
                        (json.dumps([dict(field='grade', label='Grade', stored='EF', listed='VF',
                                          evidence='Grade: VF', outcome='different')]), self.id))
        self.db.commit()
        state = self.state('banknotes')
        self.assertIsNone(state['review'])
        self.assertFalse(state['delivery']['attention'])
        self.assertEqual(state['delivery']['status'], 'Ordered')
        page = self.get('/banknotes/' + self.id).data.decode()
        self.assertIn('Marked reviewed', page)
        self.assertNotIn('Ordered \u00b7 Review', page)
        self.assertNotIn('Ordered \u00b7 Review', self.get('/banknotes').data.decode())

    def test_banknote_listing_discrepancy_has_visible_reason_and_dismissal(self):
        self.available('banknotes')
        checks.ensure(self.db, 'banknotes', self.id, URL)
        self.db.execute("UPDATE original_listing_checks SET state='checked',result=? WHERE banknote_id=?",
                        (json.dumps([dict(field='grade', label='Grade', stored='EF', listed='VF',
                                          evidence='Grade: VF', outcome='different')]), self.id))
        self.db.commit()
        page = self.get('/banknotes/' + self.id).data.decode()
        self.assertIn('Review Reason', page)
        self.assertIn('<strong>Grade</strong>: EF; listing: VF', page)
        state = self.state('banknotes')
        result = self.post(dict(action='dismiss', review_token='', check_token=state['check']['token']), 'banknotes')
        self.assertTrue(result.json['check']['dismissed'])
        self.assertIn('Marked reviewed', self.get('/banknotes/' + self.id).data.decode())

    def test_banknote_unverified_email_has_explanation_not_false_delivery(self):
        self.banknote_order('', 'Delivered')
        self.db.execute('DELETE FROM ebay_purchase_observations WHERE line_key=?', (self.id,))
        self.db.execute('INSERT INTO ebay_mail_receipts VALUES (?,?,?,?,?)',
                        (self.id, self.id, 'Delivered', 'Email says delivered', 'today'))
        self.db.commit()
        state = self.state('banknotes')
        self.assertIn('Email alone does not confirm', state['review']['reason'])
        self.assertEqual(state['delivery']['status'], 'Unverified')
        result = self.post(dict(action='dismiss', review_token=state['review']['token']), 'banknotes')
        self.assertFalse(result.json['delivery']['attention'])
        self.assertEqual(result.json['delivery']['status'], 'Unverified')

    def test_banknote_review_requires_owner_csrf_and_current_evidence(self):
        self.banknote_order()
        path = f'/banknotes/{self.id}/original-listing/review'
        state = self.state('banknotes')
        data = dict(action='dismiss', review_token=state['review']['token'])
        self.assertEqual(self.client.post(path, data=data, base_url='https://localhost').status_code, 403)
        self.get('/banknotes/' + self.id)
        with self.client.session_transaction(base_url='https://localhost') as session:
            data['csrf_token'] = session['ebay_csrf']
        self.assertEqual(self.client.post(path, data=data, base_url='https://localhost',
                         headers={'Cf-Access-Authenticated-User-Email': 'outsider@example.com'}).status_code, 403)
        self.assertEqual(self.post(dict(action='dismiss', review_token='stale'), 'banknotes').status_code, 409)

    def test_banknote_header_hides_only_redundant_delivery_labels(self):
        class BadgeParser(HTMLParser):
            attrs = None
            text = ''
            active = False
            def handle_starttag(self, tag, attrs):
                if 'data-delivery-badge' in dict(attrs):
                    self.attrs = dict(attrs)
                    self.active = True
            def handle_data(self, data):
                if self.active:
                    self.text += data
            def handle_endtag(self, tag):
                if tag == 'a':
                    self.active = False

        self.banknote_order('', 'Awaiting shipment')
        for ownership, shipping, attention, hidden, label in [
            ('Own', 'Delivered', '', True, 'Delivered'),
            ('Ordered', 'Ordered', '', True, 'Ordered'),
            ('Ordered', 'Shipped', '', False, 'Shipped'),
            ('Ordered', 'Delivered', '', False, 'Delivered'),
            ('Sold', 'Delivered', '', False, 'Delivered'),
            ('Own', 'Delivered', 'Partially refunded', False, 'Please Review'),
            ('Ordered', 'Ordered', 'Check the order', False, 'Please Review'),
        ]:
            with self.subTest(ownership=ownership, shipping=shipping, attention=attention):
                self.db.execute('UPDATE banknotes SET status=? WHERE id=?', (ownership, self.id))
                self.db.execute('UPDATE ebay_order_items SET delivery_status=?,attention=? WHERE line_key=?',
                                (shipping, attention, self.id))
                self.db.commit()
                parser = BadgeParser()
                html = self.get('/banknotes/' + self.id).data.decode()
                parser.feed(html)
                self.assertIsNotNone(parser.attrs)
                self.assertEqual('hidden' in parser.attrs, hidden)
                self.assertEqual(parser.text, label)
                self.assertEqual('purchase-review-pill' in parser.attrs['class'], bool(attention))
                self.assertIn('id="statusFlipPill"', html)
                self.assertEqual(self.db.execute('SELECT status FROM banknotes WHERE id=?',
                                                (self.id,)).fetchone()[0], ownership)

    def test_failed_checks_need_evidence_and_never_write_item_fields(self):
        self.available()
        checks.ensure(self.db, 'coins', self.id, URL)
        self.db.commit()
        analyze = Mock(return_value={'comparisons': [{'field': 'weight', 'listing_value': '99',
                        'evidence': 'Invented quote', 'outcome': 'different'}]})
        checks.run_once(stuff.open_db_connection, lambda _: ('available', TEXT), analyze)
        self.assertEqual(self.state()['check']['state'], 'failed')
        self.assertEqual(self.db.execute('SELECT weight FROM coins WHERE id=?', (self.id,)).fetchone()[0], 12.5)
        self.assertFalse(checks.run_once(stuff.open_db_connection, lambda _: ('available', TEXT), analyze))

    def test_review_recovers_after_deployment_expires_session_both_categories(self):
        self.banknote_order()
        self.db.execute('INSERT INTO coin_purchase_reviews VALUES (?,?,?)', (self.id, 'Check price', 'today'))
        self.db.commit()
        for category in ('coins', 'banknotes'):
            with self.subTest(category=category):
                path = f'/{category}/{self.id}/original-listing'
                current = self.state(category)
                before = dict(self.db.execute(f'SELECT * FROM {category} WHERE id=?', (self.id,)).fetchone())
                data = dict(action='dismiss', review_token=current['review']['token'], check_token='',
                            csrf_token=current['csrf_token'])
                with patch.dict(stuff.app.config, SECRET_KEY=os.urandom(32)):
                    rejected = self.client.post(path + '/review', data=data, base_url='https://localhost')
                    self.assertEqual(rejected.status_code, 403)
                    self.assertEqual(rejected.json['code'], 'csrf_expired')
                    self.assertEqual(rejected.headers['Cache-Control'], 'no-store')
                    refreshed = self.get(path)
                    self.assertEqual(refreshed.headers['Cache-Control'], 'no-store')
                    self.assertNotEqual(refreshed.json['csrf_token'], data['csrf_token'])
                    self.assertFalse(refreshed.json['review']['dismissed'])
                    self.assertEqual(refreshed.json['review']['token'], data['review_token'])
                    data['csrf_token'] = refreshed.json['csrf_token']
                    saved = self.client.post(path + '/review', data=data, base_url='https://localhost')
                    self.assertEqual(saved.status_code, 200)
                    self.assertTrue(saved.json['review']['dismissed'])
                    self.assertTrue(self.state(category)['review']['dismissed'])
                    data['action'] = 'restore'
                    restored = self.client.post(path + '/review', data=data, base_url='https://localhost')
                    self.assertEqual(restored.status_code, 200)
                    self.assertFalse(restored.json['review']['dismissed'])
                self.assertEqual(before, dict(self.db.execute(f'SELECT * FROM {category} WHERE id=?',
                                                              (self.id,)).fetchone()))

    def test_refreshed_session_still_rejects_changed_review_and_cross_site_requests(self):
        self.banknote_order()
        path = f'/banknotes/{self.id}/original-listing'
        current = self.state('banknotes')
        data = dict(action='dismiss', review_token=current['review']['token'], check_token='',
                    csrf_token=current['csrf_token'])
        with self.client.session_transaction(base_url='https://localhost') as session:
            session.clear()
        self.db.execute('UPDATE ebay_order_items SET attention=? WHERE line_key=?',
                        ('Partially refunded; verify amount', self.id))
        self.db.commit()
        data['csrf_token'] = self.state('banknotes')['csrf_token']
        rejected = self.client.post(path + '/review', data=data, base_url='https://localhost')
        self.assertEqual(rejected.status_code, 409)
        self.assertFalse(self.state('banknotes')['review']['dismissed'])
        data['review_token'] = self.state('banknotes')['review']['token']
        rejected = self.client.post(path + '/review', data=data, base_url='https://localhost',
                                    headers={'Origin': 'https://untrusted.example'})
        self.assertEqual(rejected.status_code, 403)
        self.assertFalse(rejected.is_json)
        self.assertFalse(self.state('banknotes')['review']['dismissed'])
        forbidden = self.client.get(path, base_url='https://localhost',
                                    headers={'Cf-Access-Authenticated-User-Email': 'outsider@example.com'})
        self.assertEqual(forbidden.status_code, 403)
        self.assertNotIn(b'csrf_token', forbidden.data)

    def test_concurrent_edit_defers_report(self):
        self.available()
        checks.ensure(self.db, 'coins', self.id, URL)
        self.db.commit()
        def analyze(*args):
            self.db.execute('UPDATE coins SET weight=13.15 WHERE id=?', (self.id,))
            self.db.commit()
            return {'comparisons': [{'field': 'weight', 'listing_value': '13.15',
                                     'evidence': 'Weight: 13.15 g.', 'outcome': 'different'}]}
        checks.run_once(stuff.open_db_connection, lambda _: ('available', TEXT), analyze)
        self.assertEqual(self.state()['check']['state'], 'pending')
        self.assertEqual(self.state()['check']['differences'], [])

    def test_read_and_write_authorization_csrf_and_stale_versions(self):
        path = f'/coins/{self.id}/original-listing'
        self.assertEqual(self.client.get(path, headers={'Cf-Access-Authenticated-User-Email':'outsider@example.com'}).status_code, 403)
        self.assertEqual(self.client.post(path+'/review', data={'action':'dismiss'}).status_code, 403)
        self.assertEqual(self.post(dict(action='dismiss', check_token='stale')).status_code, 409)
        with patch.object(stuff, 'TENANT_CATEGORIES', {'banknotes'}):
            self.assertEqual(self.get(path).status_code, 403)
        self.assertEqual(self.get('/coins/missing/original-listing').status_code, 404)

    def test_worker_caches_and_deduplicates_checks(self):
        sources.add_source(self.db, 'coins', self.id, URL)
        self.db.commit()
        with patch.object(sources, 'check_page', return_value='available') as fetch:
            self.assertTrue(stuff._original_listing_service.work_once())
            self.assertFalse(stuff._original_listing_service.work_once())
            self.assertEqual(fetch.call_count, 1)
        self.assertIsNotNone(self.state()['link'])

    def test_asking_prices_are_not_purchase_discrepancies(self):
        weight = {'field': 'weight', 'listing_value': '13.15', 'evidence': 'Weight: 13.15 g', 'outcome': 'match'}
        for quote, value, outcome in [('Price: $45.00 or Best Offer', '$45 asking price', 'uncertain'),
                                      ('Price: $45', '$45', 'different'),
                                      ('Hammer price paid: $45', '$45', 'different')]:
            result = checks.validate_result('coins', {'weight': '13.15', 'price': '$50'},
                quote + ' Weight: 13.15 g', {'comparisons': [weight, {
                    'field': 'price', 'listing_value': value, 'evidence': quote, 'outcome': outcome}]})
            self.assertEqual([r['field'] for r in result], ['weight'])
        result = checks.validate_result('coins', {'price': '$50'}, 'Order total paid: $45',
            {'comparisons': [{'field': 'price', 'listing_value': '$45',
                              'evidence': 'Order total paid: $45', 'outcome': 'different'}]})
        self.assertEqual(result[0]['outcome'], 'different')

    def test_comparison_opt_in_required(self):
        self.available()
        self.assertIsNone(self.state()['check'])
        with patch.dict(os.environ, ORIGINAL_LISTING_AI_CHECKS='1'):
            self.assertEqual(self.state()['check']['state'], 'pending')

    def test_foreign_keys_remove_sources_and_checks(self):
        self.available()
        checks.ensure(self.db, 'coins', self.id, URL)
        self.db.execute('DELETE FROM coins WHERE id=?', (self.id,))
        self.db.commit()
        self.assertFalse(self.db.execute('SELECT * FROM coin_original_listings WHERE coin_id=?', (self.id,)).fetchone())
        self.assertFalse(self.db.execute('SELECT * FROM original_listing_checks WHERE coin_id=?', (self.id,)).fetchone())

    def test_pdf_archives_attach_once_to_both_categories(self):
        for category in ('coins','banknotes'):
            archives.enqueue(self.db,category,self.id,URL,'VCoins Original Listing','listing')
        self.db.commit()
        with patch.object(archives,'fetch_bytes',return_value=(HTML.encode(),'text/html',URL)) as fetch:
            self.assertTrue(archives.run_once(stuff.open_db_connection,stuff.UPLOAD_FOLDER,stuff._pdf_fonts))
            self.assertFalse(archives.run_once(stuff.open_db_connection,stuff.UPLOAD_FOLDER,stuff._pdf_fonts))
            self.assertEqual(fetch.call_count,1)
        docs = self.db.execute('SELECT category,title,filename FROM record_documents WHERE record_id=?',(self.id,)).fetchall()
        self.assertEqual(len(docs),2)
        self.assertEqual(docs[0]['filename'],docs[1]['filename'])
        import pypdfium2
        pdf = pypdfium2.PdfDocument(str(Path(stuff.UPLOAD_FOLDER)/docs[0]['filename']))
        text = ''.join(pdf[i].get_textpage().get_text_range() for i in range(len(pdf)))
        self.assertIn('Weight: 13.15 g.',text)
        self.assertIn('VCoins Original Listing',text)
        pdf.close()

    def test_existing_invoice_reused_without_duplication(self):
        filename = 'invoice-test.pdf'
        Path(stuff.UPLOAD_FOLDER).mkdir(exist_ok=True,parents=True)
        (Path(stuff.UPLOAD_FOLDER)/filename).write_bytes(b'%PDF-1.4 existing invoice')
        self.db.execute("INSERT INTO record_documents (id,category,record_id,title,filename) VALUES (?,?,?,?,?)",
                        (self.id,'coins',self.id,'Invoice',filename))
        archives.enqueue(self.db,'coins',self.id,'/uploads/'+filename,'CNG Invoice','invoice')
        self.db.commit()
        archives.run_once(stuff.open_db_connection,stuff.UPLOAD_FOLDER,stuff._pdf_fonts)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM record_documents WHERE record_id=?',(self.id,)).fetchone()[0],1)
        self.assertEqual((Path(stuff.UPLOAD_FOLDER)/filename).read_bytes(),b'%PDF-1.4 existing invoice')

    def test_pdf_does_not_archive_a_removed_listing_or_login_page(self):
        archives.enqueue(self.db,'coins',self.id,URL,'VCoins Original Listing','listing')
        self.db.commit()
        with patch.object(archives,'fetch_bytes',return_value=(b'<h1>Sign in to your account</h1>','text/html',URL)):
            archives.run_once(stuff.open_db_connection,stuff.UPLOAD_FOLDER,stuff._pdf_fonts)
        self.assertFalse(self.db.execute('SELECT * FROM record_documents WHERE record_id=?',(self.id,)).fetchone())
        self.assertFalse(self.db.execute('SELECT filename FROM purchase_source_archives WHERE url=?',(URL,)).fetchone()[0])

    def test_source_archive_hosts_and_unsafe_redirects(self):
        self.assertTrue(archives.safe_remote(URL))
        for url in ('http://127.0.0.1/invoice.pdf','https://evil.test/invoice.pdf',
                    'https://www.vcoins.com:8443/invoice.pdf','https://user@www.vcoins.com/invoice.pdf'):
            self.assertFalse(archives.safe_remote(url))

    def test_order_number_from_receipt_after_vendor_both_categories(self):
        order_url = 'https://order.ebay.com/ord/show?orderId=23-15242-04872'
        for category in ('coins', 'banknotes'):
            archives.enqueue(self.db, category, self.id, order_url, 'eBay Order Receipt', 'order')
            self.db.commit()
            expected = [dict(number='23-15242-04872', url=order_url)]
            self.assertEqual(sources.ebay_purchase_orders(self.db, category, self.id), expected)
            page = self.get(f'/{category}/{self.id}').data.decode()
            purchase = page.split('purchase-with-marketplace"', 1)[1].split('</a>', 1)[0]
            self.assertLess(purchase.index('name="vendor"'), purchase.index('23-15242-04872'))
            self.assertIn('href="' + order_url + '"', purchase)
            self.assertIn('Order Number', page)
            self.assertNotIn('eBay Order Number', page)
            self.assertLess(page.index('id="orderNumberLabel"'), page.index('name="purchase_date"'))

    def test_order_numbers_from_matched_purchase_and_exact_listing_deduplicate(self):
        order_url = 'https://order.ebay.com/ord/show?orderId=23-15242-04872'
        self.db.execute("INSERT INTO ebay_order_items (line_key,order_id,item_id,title,quantity,delivery_status,last_seen) "
                        "VALUES (?,'23-15242-04872','325643741723','Tonga 1 Pound',1,'Ordered','now')", (self.id,))
        self.db.execute("INSERT INTO banknote_ebay_links (banknote_id,line_key,matched_by,matched_at) VALUES (?,?,'manual','now')",
                        (self.id, self.id))
        for category in ('coins', 'banknotes'):
            sources.add_source(self.db, category, self.id, 'https://www.ebay.com/itm/325643741723')
            archives.enqueue(self.db, category, self.id, order_url, 'Order receipt', 'order')
            self.assertEqual(sources.ebay_purchase_orders(self.db, category, self.id),
                             [dict(number='23-15242-04872', url=order_url)])
        self.db.execute('DELETE FROM banknote_ebay_links WHERE banknote_id=?', (self.id,))
        self.db.execute('DELETE FROM ebay_order_items WHERE line_key=?', (self.id,))

    def test_order_numbers_do_not_guess_from_reviews_or_listing_ids(self):
        self.db.execute('INSERT INTO coin_purchase_reviews VALUES (?,?,?)', (self.id, 'Uncertain purchase match', 'today'))
        self.db.execute('INSERT INTO coin_purchase_review_sources VALUES (?,?,?,?)',
                        (self.id, 'https://order.ebay.com/ord/show?orderId=23-15242-04872', 'Possible eBay order', 0))
        sources.add_source(self.db, 'coins', self.id, 'https://www.ebay.com/itm/325643741723')
        self.assertEqual(sources.ebay_purchase_orders(self.db, 'coins', self.id), [])
        self.assertEqual(sources.ebay_purchase_orders(self.db, 'banknotes', None), [])
        self.assertEqual(sources.ebay_purchase_orders(self.db, 'watches', self.id), [])

    def test_order_urls_must_be_exact_not_generic_or_malformed(self):
        for url in ['https://www.ebay.com/mye/myebay/purchase?orderId=23-15242-04872',
                    'https://order.ebay.com/ord/show?orderId=invalid',
                    'https://order.ebay.com/ord/show?orderId=23-15242-04872&orderId=99-99999-99999',
                    'https://order.ebay.com/ord/show?itemId=325643741723',
                    'https://www.vcoins.com/ord/show?orderId=23-15242-04872']:
            archives.enqueue(self.db, 'banknotes', self.id, url, 'Order receipt', 'order')
        self.assertEqual(sources.ebay_purchase_orders(self.db, 'banknotes', self.id), [])

    def test_vcoins_printed_number_not_internal_id_both_categories(self):
        url = 'https://www.vcoins.com/en/MyAccount/Invoice.aspx?IdOrder=332942'
        order_url = 'https://www.vcoins.com/en/MyAccount/ShowOrder.aspx?IdOrder=332942'
        for category in ('coins', 'banknotes'):
            archives.enqueue(self.db, category, self.id, url, 'VCoins Invoice 315-155', 'invoice')
            self.db.commit()
            self.assertEqual(orders.purchase_orders(self.db, category, self.id),
                             [dict(provider='VCoins', number='315-155', url=order_url, kind='order')])
            page = self.get(f'/{category}/{self.id}').data.decode()
            self.assertIn('Open VCoins order 315-155', page)
            self.assertIn(f'href="{order_url}"', page)
            self.assertIn('>315-155</a>', page)
            self.assertNotIn('>332942</a>', page)
            self.assertLess(page.index('name="vendor"'), page.index('id="orderNumberLabel"'))
            self.assertLess(page.index('id="orderNumberLabel"'), page.index('name="purchase_date"'))

    def test_vcoins_order_link_uses_only_verified_order_id(self):
        result = orders.archive_order(
            'https://www.vcoins.com/fr/MyAccount/Invoice.aspx?IdOrder=332942&print=true#receipt',
            'VCoins Invoice 315-155', 'invoice')
        self.assertEqual(result, dict(provider='VCoins', number='315-155', kind='order',
            url='https://www.vcoins.com/fr/MyAccount/ShowOrder.aspx?IdOrder=332942'))
        self.assertEqual(orders.archive_order('/uploads/vcoins.pdf', 'VCoins Invoice 315-155', 'invoice'),
            dict(provider='VCoins', number='315-155', kind='invoice', url='/uploads/vcoins.pdf'))

    def test_cng_and_other_supplier_invoice_documents(self):
        for category in ('coins', 'banknotes'):
            self.db.execute("INSERT INTO record_documents (id,category,record_id,title,filename) VALUES (?,?,?,?,?)",
                            (category + self.id, category, self.id, 'CNG Invoice 431062', 'cng-invoice.pdf'))
            archives.enqueue(self.db, category, self.id, '/uploads/dealer-invoice.pdf',
                             'Example Dealer Invoice AB-123', 'invoice')
            self.db.commit()
            result = orders.purchase_orders(self.db, category, self.id)
            self.assertEqual([o['number'] for o in result], ['431062', 'AB-123'])
            self.assertEqual(result[0]['url'], '/uploads/cng-invoice.pdf')
            self.assertIn('Open CNG invoice 431062', self.get(f'/{category}/{self.id}').data.decode())

    def test_order_source_priority_and_duplicates(self):
        entries = [
            ('https://order.ebay.com/ord/show?orderId=23-15242-04872', 'eBay Order 23-15242-04872', 'order'),
            ('/uploads/cng.pdf', 'CNG Invoice 431062', 'invoice'),
            ('/uploads/vcoins.pdf', 'VCoins Invoice 315-155', 'invoice'),
            ('https://www.vcoins.com/en/MyAccount/Invoice.aspx?IdOrder=332942', 'VCoins Invoice 315-155', 'invoice'),
            ('https://www.vcoins.com/en/MyAccount/ShowOrder.aspx?IdOrder=332942', 'VCoins Order 315-155', 'order')]
        for category in ('coins', 'banknotes'):
            for url, title, kind in entries:
                archives.enqueue(self.db, category, self.id, url, title, kind)
        result = orders.purchase_orders(self.db, 'coins', self.id)
        self.assertEqual([o['provider'] for o in result], ['VCoins', 'CNG', 'eBay'])
        self.assertIn('/ShowOrder.aspx?', result[0]['url'])
        self.assertEqual([o['provider'] for o in orders.purchase_orders(self.db, 'banknotes', self.id)],
                         ['eBay', 'VCoins', 'CNG'])

    def test_same_number_different_supplier_is_not_collapsed(self):
        archives.enqueue(self.db, 'coins', self.id, '/uploads/cng.pdf', 'CNG Invoice 431062', 'invoice')
        archives.enqueue(self.db, 'coins', self.id, '/uploads/dealer.pdf', 'Dealer Invoice 431062', 'invoice')
        self.assertEqual(len(orders.purchase_orders(self.db, 'coins', self.id)), 2)

    def test_order_numbers_reject_listing_lot_generic_and_unsafe_sources(self):
        invalid = [
            ('https://www.cngcoins.com/Coin.aspx?CoinID=394565', 'CNG Invoice 577810'),
            ('https://www.cngcoins.com/Lot.aspx?LOT_ID=431062', 'CNG Invoice 431062'),
            ('https://www.vcoins.com/en/MyAccount.aspx', 'VCoins Order 315-155'),
            ('https://www.vcoins.com/en/MyAccount/ShowOrder.aspx?IdOrder=332942', 'VCoins Order 332942'),
            ('https://www.vcoins.com/en/MyAccount/ShowOrder.aspx?IdOrder=1&IdOrder=2', 'VCoins Order 315-155'),
            ('https://www.vcoins.com/en/MyAccount/Invoice.aspx?IdOrder=332942', 'CNG Invoice 431062'),
            ('https://evil.test/invoice.pdf', 'CNG Invoice 431062'),
            ('https://www.vcoins.com:8443/en/MyAccount/Invoice.aspx?IdOrder=1', 'VCoins Order 315-155'),
            ('/uploads/../private.pdf', 'CNG Invoice 431062'),
            ('/uploads/cng.pdf', 'CNG invoice item 577810'),
            ('/uploads/possible.pdf', 'Possible CNG Invoice 431062')]
        for url, title in invalid:
            self.assertIsNone(orders.archive_order(url, title, 'invoice'), (url, title))
        self.assertIsNone(orders.archive_order('/uploads/x.pdf', 'CNG Invoice 431062', 'listing'))

    def test_shared_order_field_does_not_promote_uncertain_review_sources(self):
        self.db.execute('INSERT INTO coin_purchase_reviews VALUES (?,?,?)', (self.id, 'Possible order match', 'today'))
        self.db.execute('INSERT INTO coin_purchase_review_sources VALUES (?,?,?,?)',
                        (self.id, 'https://www.vcoins.com/en/MyAccount/ShowOrder.aspx?IdOrder=332942',
                         'VCoins order 315-155', 0))
        self.assertEqual(orders.purchase_orders(self.db, 'coins', self.id), [])
        self.assertEqual(orders.purchase_orders(self.db, 'coins', None), [])
        self.assertEqual(orders.purchase_orders(self.db, 'watches', self.id), [])

    def test_marketplace_is_independent_of_vendor_and_unknown_by_default(self):
        for category, choices in [('coins', ('Direct', 'VCoins', 'CNG')), ('banknotes', ('Direct', 'eBay'))]:
            self.db.execute(f"UPDATE {category} SET vendor='Shanna Schmidt',price=6750 WHERE id=?", (self.id,))
            self.db.commit()
            self.assertIsNone(self.db.execute(f'SELECT marketplace FROM {category} WHERE id=?', (self.id,)).fetchone()[0])
            for choice in (*choices, ''):
                response = self.client.post(f'/{category}/{self.id}/save-field', base_url='https://localhost',
                                            json={'field': 'marketplace', 'value': choice})
                self.assertEqual(response.status_code, 200, response.data)
                row = self.db.execute(f'SELECT vendor,marketplace,price FROM {category} WHERE id=?', (self.id,)).fetchone()
                self.assertEqual(tuple(row), ('Shanna Schmidt', choice or None, 6750))
                page = self.get(f'/{category}/{self.id}').data.decode()
                self.assertIn('name="marketplace"', page)
                if choice:
                    self.assertIn(f'value="{choice}" selected', page)
            self.assertEqual(self.client.post(f'/{category}/{self.id}/save-field', base_url='https://localhost',
                             json={'field': 'marketplace', 'value': 'Shanna Schmidt'}).status_code, 400)

    def test_marketplace_options_and_legacy_source_preserved(self):
        for category, choices in [('coins', ['', 'Direct', 'VCoins', 'CNG']), ('banknotes', ['', 'Direct', 'eBay'])]:
            field = next(f for f in stuff.FIELDS[category] if f['name'] == 'marketplace')
            self.assertEqual(field['options'], choices)
        self.db.execute("UPDATE coins SET marketplace='eBay' WHERE id=?", (self.id,))
        self.db.commit()
        self.assertIn('value="eBay" selected', self.get(f'/coins/{self.id}').data.decode())

    def test_marketplace_create_full_edit_and_constraint(self):
        for category in ('coins', 'banknotes'):
            form = {'vendor': 'Shanna Schmidt', 'marketplace': 'Direct', 'owner': 'Mark', 'status': 'Own'}
            response = self.client.post(f'/{category}/new', base_url='https://localhost', data=form)
            self.assertEqual(response.status_code, 302, response.data)
            created = self.db.execute(f"SELECT id FROM {category} WHERE vendor='Shanna Schmidt' AND marketplace='Direct'").fetchone()[0]
            try:
                choice = 'VCoins' if category == 'coins' else 'eBay'
                response = self.client.post(f'/{category}/{created}', base_url='https://localhost', data=dict(form, marketplace=choice))
                self.assertEqual(response.status_code, 302, response.data)
                self.assertEqual(self.db.execute(f'SELECT marketplace FROM {category} WHERE id=?', (created,)).fetchone()[0], choice)
                with self.assertRaises(sqlite3.IntegrityError):
                    self.db.execute(f"UPDATE {category} SET marketplace='Not a source' WHERE id=?", (created,))
                self.db.rollback()
            finally:
                self.db.execute(f'DELETE FROM {category} WHERE id=?', (created,))
                self.db.commit()


if __name__ == '__main__':
    unittest.main(verbosity=2)
