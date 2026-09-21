"""Direct buyer sync: evidence, matching, isolation, OAuth and failure recovery."""
import copy
import base64
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

REPO = str(Path(__file__).resolve().parents[1])
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-ebay-tests-')
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
for key in ('EBAY_CLIENT_ID', 'EBAY_CLIENT_SECRET', 'EBAY_RUNAME'):
    os.environ.pop(key, None)

import ebay_orders as ebay
import ebay_notifications as notices
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec


def tx(item='185386368846', transaction='0', extra='', quantity=1):
    return f'''<Transaction><Item><ItemID>{item}</ItemID><Title>Canada $20 PMG 64 EPQ banknote</Title></Item>
      <TransactionID>{transaction}</TransactionID><QuantityPurchased>{quantity}</QuantityPurchased>
      <CreatedDate>2026-09-01T12:00:00Z</CreatedDate>{extra}</Transaction>'''


def response(transactions=None, extra='', more=False, ack='Success'):
    return f'''<GetOrdersResponse xmlns="{ebay.NS}"><Ack>{ack}</Ack><HasMoreOrders>{str(more).lower()}</HasMoreOrders>
    <OrderArray><Order><OrderID>12-12345-12345</OrderID><OrderStatus>Completed</OrderStatus>
    <SellerUserID>note-dealer</SellerUserID><SellerEIASToken>seller-stable-id</SellerEIASToken>
    <CreatedTime>2026-09-01T12:00:00Z</CreatedTime>{extra}
    <TransactionArray>{transactions or tx()}</TransactionArray></Order></OrderArray></GetOrdersResponse>'''.encode()


def package(actual='', estimate='2026-09-05T12:00:00Z'):
    return f'<ShippingServiceSelected><ShippingPackageInfo><ActualDeliveryTime>{actual}</ActualDeliveryTime><EstimatedDeliveryTimeMax>{estimate}</EstimatedDeliveryTimeMax></ShippingPackageInfo></ShippingServiceSelected>'


def parsed(extra=''):
    return ebay.parse_orders(ebay.parse_response(response(tx(extra=extra))))


def bare_db(path=':memory:'):
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    db.execute('CREATE TABLE IF NOT EXISTS banknotes (id TEXT PRIMARY KEY,status TEXT,description TEXT,note_references TEXT,photo TEXT)')
    ebay.init_schema(db)
    return db


def note(db, note_id='n1', item_id='185386368846'):
    db.execute('INSERT INTO banknotes VALUES (?,?,?,?,?)',
               (note_id, 'Ordered', 'Listing: https://www.ebay.ca/itm/' + item_id, '', 'unchanged.jpg'))
    db.commit()


class EvidenceTests(unittest.TestCase):
    def test_delivery_requires_actual_evidence(self):
        self.assertEqual(parsed(package())[0]['delivery_status'], 'Ordered')
        item = parsed('<ShippedTime>2026-09-02T12:00:00Z</ShippedTime>' + package())[0]
        self.assertEqual(item['delivery_status'], 'Shipped')
        self.assertEqual(parsed(package('2026-09-04T14:00:00Z'))[0]['delivery_status'], 'Delivered')

    def test_tracking_label_not_shipping_and_future_not_delivery(self):
        track = '<ShippingDetails><ShipmentTrackingDetails><ShippingCarrierUsed>USPS</ShippingCarrierUsed><ShipmentTrackingNumber>1234</ShipmentTrackingNumber></ShipmentTrackingDetails></ShippingDetails>'
        item = parsed(track + package('2099-01-01T00:00:00Z'))[0]
        self.assertEqual(item['delivery_status'], 'Ordered')
        self.assertEqual(item['tracking'], [('USPS', '1234')])

    def test_combined_orders_and_partial_packages(self):
        xml = response(tx(extra=package('2026-09-04T14:00:00Z')) + tx('185386368847'),
                       extra='<ShippedTime>2026-09-02T12:00:00Z</ShippedTime>' + package('2026-09-04T14:00:00Z'))
        items = ebay.parse_orders(ebay.parse_response(xml))
        self.assertEqual([i['delivery_status'] for i in items], ['Delivered', 'Ordered'])
        p = '<ShippingServiceSelected><ShippingPackageInfo><ActualDeliveryTime>2026-09-04T14:00:00Z</ActualDeliveryTime></ShippingPackageInfo><ShippingPackageInfo/></ShippingServiceSelected>'
        self.assertEqual(parsed(p)[0]['delivery_status'], 'Ordered')

    def test_failed_and_unsafe_xml_rejected(self):
        for xml in (b'<html>captcha</html>', response(ack='Failure'),
                    b'<!DOCTYPE foo [<!ENTITY a SYSTEM "file:///etc/passwd">]><GetOrdersResponse>&a;</GetOrdersResponse>'):
            with self.assertRaises(ebay.EbayError):
                ebay.parse_response(xml)
        with self.assertRaises(ebay.EbayError):
            ebay.parse_orders(ebay.parse_response(response(tx(quantity=0))))

    def test_no_sensitive_personal_fields_are_retained(self):
        xml = response(extra='<ShippingAddress><Street1>secret address</Street1></ShippingAddress><Total>999.99</Total>')
        self.assertNotIn('secret address', json.dumps(ebay.parse_orders(ebay.parse_response(xml))))
        self.assertNotIn('999.99', json.dumps(ebay.parse_orders(ebay.parse_response(xml))))

    def test_api_is_buyer_only_and_paginates(self):
        client = ebay.EbayClient('client', 'secret', 'runame')
        pages = [response(more=True), response(tx('185386368847'))]
        with patch.object(client, '_request', side_effect=pages) as request:
            self.assertEqual(len(client.orders('private-token')), 2)
            sent = request.call_args_list[0].args
            self.assertIn(b'<OrderRole>Buyer</OrderRole>', sent[1])
            self.assertEqual(sent[2]['X-EBAY-API-IAF-TOKEN'], 'private-token')
        with self.assertRaises(ValueError):
            client.trading('CompleteSale', 'token')
        with patch.object(client, '_request', side_effect=[response(more=True), response(more=True)]):
            with self.assertRaises(ebay.EbayError):
                client.orders('token')

    def test_oauth_request_contract(self):
        client = ebay.EbayClient('client', 'secret', 'my-runame')
        with patch.object(client, '_request', return_value=b'{"access_token":"a","refresh_token":"r","expires_in":7200}') as request:
            client.token(code='one-use-code')
            fields = parse_qs(request.call_args.args[1].decode())
            self.assertEqual(fields['redirect_uri'], ['my-runame'])
            self.assertEqual(fields['grant_type'], ['authorization_code'])
        params = parse_qs(urlparse(client.authorize_url('nonce')).query)
        self.assertEqual(params['scope'], [ebay.SCOPE])
        self.assertEqual(params['state'], ['nonce'])

    def test_order_pages_excluded_from_offline_cache(self):
        source = Path(REPO, 'static/js/sw.js').read_text()
        self.assertIn("'/banknotes/ebay', '/ebay'", source)
        self.assertIn('urls.filter(u => !shouldNotCache', source)


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.db = bare_db()
        note(self.db)

    def tearDown(self):
        self.db.close()

    def test_exact_id_hosts_and_purchase_source_only(self):
        self.assertEqual(ebay.listing_id('https://www.ebay.co.uk/itm/a-note/185386368846?x=1'), '185386368846')
        for url in ('https://ebay.com.evil.test/itm/185386368846', 'https://ebay.evil/itm/185386368846',
                    'https://evil.test/?item=185386368846', 'https://ebay.com/sch/185386368846'):
            self.assertIsNone(ebay.listing_id(url))
        self.db.execute("UPDATE banknotes SET description='Comparison: https://www.ebay.com/itm/185386368846'")
        self.assertFalse(ebay.listing_candidates(self.db))

    def test_idempotent_monotonic_and_metadata_untouched(self):
        before = dict(self.db.execute('SELECT * FROM banknotes').fetchone())
        items = parsed()
        self.assertEqual(ebay.apply_items(self.db, items)['matched'], 1)
        self.assertEqual(ebay.apply_items(self.db, items)['updated'], 0)
        delivered = parsed(package('2026-09-04T14:00:00Z'))
        self.assertEqual(ebay.apply_items(self.db, delivered)['updated'], 1)
        self.assertEqual(ebay.apply_items(self.db, items)['updated'], 0)
        self.assertEqual(self.db.execute('SELECT delivery_status FROM ebay_order_items').fetchone()[0], 'Delivered')
        self.assertEqual(dict(self.db.execute('SELECT * FROM banknotes').fetchone()), before)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_status_events').fetchone()[0], 2)

    def test_ambiguous_records_repeated_purchase_or_quantity_never_auto_match(self):
        note(self.db, 'n2')
        ebay.apply_items(self.db, parsed())
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_ebay_links').fetchone()[0], 0)
        self.db.execute("DELETE FROM banknotes WHERE id='n2'")
        another = parsed()[0]
        another['line_key'] = '185386368846-1'
        ebay.apply_items(self.db, parsed() + [another])
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_ebay_links').fetchone()[0], 0)
        self.db.execute('DELETE FROM ebay_order_items')
        many = parsed()[0]
        many['quantity'] = 2
        ebay.apply_items(self.db, [many])
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknote_ebay_links').fetchone()[0], 0)

    def test_manual_corrections_and_cancellations_are_preserved(self):
        ebay.apply_items(self.db, parsed('<ShippedTime>2026-09-02T12:00:00Z</ShippedTime>'))
        cancelled = parsed(package('2026-09-04T14:00:00Z') + '<Status><CancelStatus>CancelRequested</CancelStatus></Status>')
        self.assertEqual(ebay.apply_items(self.db, cancelled)['updated'], 0)
        self.assertEqual(self.db.execute('SELECT delivery_status FROM ebay_order_items').fetchone()[0], 'Shipped')
        self.db.execute("UPDATE banknote_ebay_links SET manual_status='Ordered'")
        self.assertEqual(ebay.apply_items(self.db, parsed(package('2026-09-04T14:00:00Z')))['updated'], 0)
        self.assertEqual(self.db.execute('SELECT manual_status FROM banknote_ebay_links').fetchone()[0], 'Ordered')

    def test_unrelated_orders_not_stored_and_ignored_not_rematched(self):
        unrelated = parsed()[0]
        unrelated.update(item_id='999999999999', line_key='999999999999-0', title='Coffee machine')
        self.assertEqual(ebay.apply_items(self.db, [unrelated])['items_seen'], 0)
        ebay.apply_items(self.db, parsed())
        self.db.execute('DELETE FROM banknote_ebay_links')
        self.db.execute('UPDATE ebay_order_items SET ignored=1')
        self.assertEqual(ebay.apply_items(self.db, parsed())['matched'], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM ebay_status_events').fetchone()[0], 1)


class WorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'test.db')
        db = bare_db(self.path)
        note(db)
        db.close()
        def open_db():
            db = sqlite3.connect(self.path)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            return db
        self.open_db = open_db
        self.client = ebay.EbayClient('client', 'secret', 'runame')
        self.sync = ebay.OrderSync(Mock(), open_db, self.tmp.name, self.client)
        db = open_db()
        db.execute('INSERT INTO ebay_connection (id,account_key,account_name,owner_email,refresh_token,access_token,access_expires,connected_at) VALUES (1,?,?,?,?,?,?,?)',
                   ('identity', 'buyer', 'owner@example.com', self.sync.encrypt('refresh-secret'),
                    self.sync.encrypt('access-secret'), time.time() + 7200, ebay.now_iso()))
        db.commit()
        db.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_sync_tokens_encrypted_and_not_due_or_busy(self):
        with patch.object(self.client, 'orders', return_value=parsed()):
            self.assertEqual(self.sync.run_once()['status'], 'done')
            self.assertEqual(self.sync.run_once()['status'], 'not_due')
            with self.sync.exclusive():
                self.assertEqual(self.sync.run_once(force=True)['status'], 'busy')
        db = self.open_db()
        conn = db.execute('SELECT * FROM ebay_connection').fetchone()
        self.assertNotIn('access-secret', conn['access_token'])
        self.assertEqual(self.sync.decrypt(conn['refresh_token']), 'refresh-secret')
        self.assertEqual(Path(self.tmp.name, '.ebay-token-key').stat().st_mode & 0o777, 0o600)
        db.close()

    def test_network_failure_after_page_one_applies_nothing(self):
        with patch.object(self.client, '_request', side_effect=[response(more=True), ebay.EbayError('Network unavailable')]):
            self.assertEqual(self.sync.run_once()['status'], 'failed')
        db = self.open_db()
        self.assertEqual(db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0], 0)
        self.assertIsNone(db.execute('SELECT last_success FROM ebay_connection').fetchone()[0])
        db.close()

    def test_pause_during_fetch_prevents_commit(self):
        def paused(_token):
            db = self.open_db()
            db.execute('UPDATE ebay_connection SET enabled=0,generation=generation+1')
            db.commit()
            db.close()
            return parsed()
        with patch.object(self.client, 'orders', side_effect=paused):
            self.assertEqual(self.sync.run_once()['status'], 'failed')
        db = self.open_db()
        self.assertEqual(db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0], 0)
        db.close()

    def test_expired_access_token_refresh_and_revoked_authorization(self):
        db = self.open_db()
        db.execute('UPDATE ebay_connection SET access_expires=0')
        db.commit()
        db.close()
        with patch.object(self.client, 'token', return_value={'access_token': 'renewed-secret', 'expires_in': 7200}) as token, patch.object(self.client, 'orders', return_value=parsed()):
            self.assertEqual(self.sync.run_once()['status'], 'done')
            token.assert_called_once_with(refresh_token='refresh-secret')
        with patch.object(self.client, 'orders', side_effect=ebay.Reauthorize('Reconnect eBay')):
            self.assertEqual(self.sync.run_once(force=True)['status'], 'failed')
        db = self.open_db()
        self.assertEqual(db.execute('SELECT enabled FROM ebay_connection').fetchone()[0], 0)
        db.close()


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import app
        cls.stuff = app
        cls.app = app.app
        cls.app.config.update(TESTING=True)
        cls.sync = cls.app.extensions['ebay_orders']

    def setUp(self):
        self.client = self.app.test_client()
        self.sync.client = ebay.EbayClient('client', 'secret', 'runame')
        with self.app.app_context():
            db = self.stuff.get_db()
            for table in ('ebay_status_events', 'banknote_ebay_links', 'ebay_item_tracking', 'ebay_order_items', 'ebay_connection', 'ebay_oauth_states', 'ebay_sync_runs', 'ebay_deleted_accounts'):
                db.execute('DELETE FROM ' + table)
            db.commit()

    def get(self, url):
        return self.client.get(url, base_url='https://localhost')

    def csrf(self):
        self.get('/banknotes/ebay')
        with self.client.session_transaction(base_url='https://localhost') as session:
            return session['ebay_csrf']

    def post(self, url, data=None):
        return self.client.post(url, data=dict(data or {}, csrf_token=self.csrf()), base_url='https://localhost')

    def begin(self):
        res = self.post('/banknotes/ebay/connect')
        self.assertEqual(res.status_code, 302)
        return parse_qs(urlparse(res.location).query)['state'][0]

    def test_dashboard_private_and_csrf_required(self):
        res = self.get('/banknotes/ebay')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.headers['Cache-Control'], 'no-store')
        self.assertEqual(self.client.post('/banknotes/ebay/connect', base_url='https://localhost').status_code, 403)
        self.assertEqual(self.client.get('/banknotes/ebay', headers={'Cf-Access-Authenticated-User-Email': 'outsider@example.com'}).status_code, 403)

    def test_oauth_binding_denial_and_replay(self):
        state = self.begin()
        other = self.app.test_client()
        self.assertEqual(other.get('/banknotes/ebay/callback?state=' + state + '&code=x', base_url='https://localhost').status_code, 400)
        self.assertEqual(self.get('/banknotes/ebay/callback?state=' + state + '&error=access_denied').status_code, 302)
        self.assertEqual(self.get('/banknotes/ebay/callback?state=' + state + '&code=x').status_code, 400)

    def test_successful_oauth_encrypts_and_enables_automatic_updates(self):
        state = self.begin()
        with patch.object(self.sync.client, 'token', return_value={'access_token': 'access-private', 'refresh_token': 'refresh-private', 'expires_in': 7200}), patch.object(self.sync.client, 'identity', return_value=('stable', 'buyer')), patch('ebay_orders.threading.Thread'):
            self.assertEqual(self.get('/banknotes/ebay/callback?state=' + state + '&code=one-use').status_code, 302)
        with self.app.app_context():
            row = self.stuff.get_db().execute('SELECT * FROM ebay_connection').fetchone()
            self.assertEqual(row['enabled'], 1)
            self.assertNotIn('refresh-private', row['refresh_token'])
        page = self.get('/banknotes/ebay').data
        self.assertNotIn(b'access-private', page)
        self.assertNotIn(b'refresh-private', page)
        self.assertIn(b'Connected to buyer', page)
        self.post('/banknotes/ebay/settings', {'action': 'disconnect'})
        with self.app.app_context():
            row = self.stuff.get_db().execute('SELECT * FROM ebay_connection').fetchone()
            self.assertIsNone(row['refresh_token'])
            self.assertEqual(row['enabled'], 0)

    def test_connection_expiry_and_missing_setup(self):
        state = self.begin()
        with self.app.app_context():
            db = self.stuff.get_db()
            db.execute('UPDATE ebay_oauth_states SET expires=0')
            db.commit()
        self.assertEqual(self.get('/banknotes/ebay/callback?state=' + state + '&code=x').status_code, 400)
        self.sync.client = ebay.EbayClient()
        self.assertIn(b'Waiting for one-time', self.get('/banknotes/ebay').data)

    def test_public_notification_challenge_and_rejected_signature(self):
        endpoint = 'https://localhost/ebay/account-deletion'
        with patch.dict(os.environ, {'EBAY_DELETION_VERIFICATION_TOKEN': 't' * 40, 'EBAY_DELETION_ENDPOINT': endpoint}):
            res = self.client.get('/ebay/account-deletion?challenge_code=abc', headers={'Cf-Access-Authenticated-User-Email': 'unregistered@example.com'})
            self.assertEqual(res.status_code, 200)
            self.assertEqual(res.json['challengeResponse'], ebay.digest('abc' + 't' * 40 + endpoint))
            self.assertEqual(self.client.post('/ebay/account-deletion', json=deletion('buyer')).status_code, 412)
            verifier = self.app.extensions['ebay_notification_verifier']
            with patch.object(verifier, 'verify', return_value=deletion('nobody')):
                self.assertEqual(self.client.post('/ebay/account-deletion', json=deletion('nobody')).status_code, 204)
        self.assertEqual(self.client.get('/ebay/privacy', headers={'Cf-Access-Authenticated-User-Email': 'unregistered@example.com'}).status_code, 200)

    def test_delete_data_preserves_collection(self):
        with self.app.app_context():
            count = self.stuff.get_db().execute('SELECT count(*) FROM banknotes').fetchone()[0]
        self.assertEqual(self.post('/banknotes/ebay/settings', {'action': 'delete_data'}).status_code, 302)
        with self.app.app_context():
            self.assertEqual(self.stuff.get_db().execute('SELECT count(*) FROM banknotes').fetchone()[0], count)


def deletion(name, eias=''):
    return {'metadata': {'topic': 'MARKETPLACE_ACCOUNT_DELETION'},
            'notification': {'notificationId': 'test-notification', 'data': {'username': name, 'eiasToken': eias}}}


class NotificationTests(unittest.TestCase):
    def test_signature_authenticity_and_public_key_cache(self):
        private = ec.generate_private_key(ec.SECP256R1())
        pem = private.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
        client = ebay.EbayClient('client', 'secret', '')
        verifier = notices.NotificationVerifier(client)
        raw = json.dumps(deletion('buyer'), separators=(',', ':')).encode()
        signature = private.sign(raw, ec.ECDSA(hashes.SHA1()))
        header = base64.b64encode(json.dumps({'kid': 'test-key', 'signature': base64.b64encode(signature).decode()}).encode()).decode()
        with patch.object(client, '_request', side_effect=[b'{"access_token":"app-only-token","expires_in":7200}', json.dumps({'key': pem, 'digest': 'SHA1'}).encode()]) as request:
            self.assertEqual(verifier.verify(raw, header), deletion('buyer'))
            self.assertEqual(verifier.verify(raw, header), deletion('buyer'))
            self.assertEqual(request.call_count, 2)
            with self.assertRaises(ValueError):
                verifier.verify(raw.replace(b'buyer', b'attacker'), header)
            with self.assertRaises(ValueError):
                verifier.public_key('../../evil')
            self.assertEqual(request.call_count, 2)

    def test_seller_deletion_is_scoped_and_suppresses_reimport(self):
        db = bare_db()
        note(db)
        ebay.apply_items(db, parsed())
        db.commit()
        notices.delete_account_data(db, deletion('note-dealer', 'seller-stable-id'))
        self.assertEqual(db.execute('SELECT count(*) FROM ebay_order_items').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT count(*) FROM banknote_ebay_links').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT count(*) FROM ebay_status_events').fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT photo FROM banknotes').fetchone()[0], 'unchanged.jpg')
        self.assertEqual(ebay.apply_items(db, parsed())['items_seen'], 0)
        db.commit()
        notices.delete_account_data(db, deletion('note-dealer', 'seller-stable-id'))
        db.close()

    def test_buyer_deletion_removes_tokens_not_notes(self):
        db = bare_db()
        note(db)
        ebay.apply_items(db, parsed())
        db.execute('INSERT INTO ebay_connection (id,account_key,account_name,owner_email,refresh_token,connected_at) VALUES (1,?,?,?,?,?)',
                   (ebay.digest('stable-buyer'), 'buyer', 'owner@example.com', 'encrypted-token', ebay.now_iso()))
        db.commit()
        notices.delete_account_data(db, deletion('buyer', 'stable-buyer'))
        for table in ('ebay_connection', 'ebay_order_items', 'banknote_ebay_links', 'ebay_status_events'):
            self.assertEqual(db.execute('SELECT count(*) FROM ' + table).fetchone()[0], 0)
        self.assertEqual(db.execute('SELECT count(*) FROM banknotes').fetchone()[0], 1)
        db.close()


if __name__ == '__main__':
    unittest.main(verbosity=2)
