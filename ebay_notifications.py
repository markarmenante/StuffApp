"""Public eBay compliance endpoint. Only verified eBay signatures can erase
integration-derived data; collection records and photos are never touched.
Protocol: developer.ebay.com/develop/guides/sell/marketplace-user-account-deletion
"""
import base64
import hashlib
import json
import os
import re
import threading
import time
from urllib.parse import urlencode

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from flask import Blueprint, abort, jsonify, request

from ebay_orders import EbayError, SCOPE, digest


class NotificationVerifier:
    def __init__(self, client):
        self.client = client
        self.keys = {}
        self.lock = threading.Lock()
        self.next_fetch = 0
        self.app_token = None
        self.token_expiry = 0

    def public_key(self, kid):
        # A header is never allowed to choose an external URL or algorithm.
        if not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', kid):
            raise ValueError('Invalid key id')
        with self.lock:
            cached = self.keys.get(kid)
            if cached and cached[0] > time.time():
                return cached[1]
            if time.time() < self.next_fetch:
                raise EbayError('Notification key lookup is temporarily limited; retry.')
            self.next_fetch = time.time() + 2
            if not self.client.client_id or not self.client.client_secret:
                raise EbayError('Notification verification is not configured.')
            if not self.app_token or self.token_expiry <= time.time() + 60:
                token = json.loads(self.client._request('https://api.ebay.com/identity/v1/oauth2/token',
                    urlencode({'grant_type': 'client_credentials', 'scope': SCOPE}).encode(), {
                        'Content-Type': 'application/x-www-form-urlencoded',
                        'Authorization': 'Basic ' + base64.b64encode(
                            (self.client.client_id + ':' + self.client.client_secret).encode()).decode(),
                    }))
                self.app_token = token['access_token']
                self.token_expiry = time.time() + int(token['expires_in'])
            value = json.loads(self.client._request(
                'https://api.ebay.com/commerce/notification/v1/public_key/' + kid,
                headers={'Authorization': 'Bearer ' + self.app_token, 'Accept': 'application/json'}))
            encoded = value['key'].replace('-----BEGIN PUBLIC KEY-----', '').replace('-----END PUBLIC KEY-----', '')
            encoded = ''.join(encoded.split())
            pem = '-----BEGIN PUBLIC KEY-----\n' + encoded + '\n-----END PUBLIC KEY-----\n'
            key = serialization.load_pem_public_key(pem.encode())
            if not isinstance(key, ec.EllipticCurvePublicKey):
                raise ValueError('Expected eBay ECC key')
            # eBay's official Notification SDK uses ECDSA/SHA1. Honor SHA256
            # only when declared by the authenticated public-key API response.
            algorithm = value.get('digest', 'SHA1').upper().replace('-', '')
            if algorithm not in ('SHA1', 'SHA256'):
                raise ValueError('Unsupported notification digest')
            result = key, hashes.SHA256() if algorithm == 'SHA256' else hashes.SHA1()
            self.keys = {k: v for k, v in self.keys.items() if v[0] > time.time()}
            if len(self.keys) >= 100:
                self.keys.pop(next(iter(self.keys)))
            self.keys[kid] = time.time() + 3600, result
            return result

    def verify(self, raw, header):
        if not header or len(header) > 4096:
            raise ValueError('Missing signature')
        signed = json.loads(base64.b64decode(header, validate=True))
        kid, signature = signed['kid'], base64.b64decode(signed['signature'], validate=True)
        key, algorithm = self.public_key(kid)
        payload = json.loads(raw)
        # Verify the exact wire bytes first; the official Node SDK also accepts
        # compact JSON.stringify payloads. No user-selected algorithms/keys.
        compact = json.dumps(payload, separators=(',', ':'), ensure_ascii=False).encode()
        for body in (raw, compact):
            try:
                key.verify(signature, body, ec.ECDSA(algorithm))
                return payload
            except InvalidSignature:
                pass
        raise ValueError('Invalid notification signature')


def delete_account_data(db, payload):
    if payload.get('metadata', {}).get('topic') != 'MARKETPLACE_ACCOUNT_DELETION':
        raise ValueError('Unexpected notification topic')
    data = payload.get('notification', {}).get('data', {})
    values = [data.get(field) for field in ('username', 'userId', 'eiasToken')]
    values = [v for v in values if isinstance(v, str) and v and len(v) <= 4096]
    if not values:
        raise ValueError('Missing account identity')
    identities = {digest(v) for v in values} | {digest(v.lower()) for v in values}
    db.execute('BEGIN IMMEDIATE')
    db.executemany('INSERT OR IGNORE INTO ebay_deleted_accounts VALUES (?)', [(v,) for v in identities])
    connection = db.execute('SELECT account_key,account_name FROM ebay_connection WHERE id=1').fetchone()
    if connection and ({connection['account_key'], digest(connection['account_name'].lower())} & identities):
        for table in ('ebay_status_events', 'ebay_order_items', 'ebay_connection', 'ebay_oauth_states', 'ebay_sync_runs'):
            db.execute('DELETE FROM ' + table)
    else:
        # Invalidate any in-flight snapshot before erasing the seller's data.
        db.execute('UPDATE ebay_connection SET generation=generation+1 WHERE id=1')
        for row in db.execute('SELECT line_key,seller,seller_key FROM ebay_order_items').fetchall():
            if {row['seller_key'], digest(row['seller'].lower())} & identities:
                db.execute('DELETE FROM ebay_status_events WHERE banknote_id IN '
                           '(SELECT banknote_id FROM banknote_ebay_links WHERE line_key=?)', (row['line_key'],))
                db.execute('DELETE FROM ebay_order_items WHERE line_key=?', (row['line_key'],))
    db.commit()


def register_notifications(app, get_db, client):
    bp = Blueprint('ebay_public', __name__)
    verifier = NotificationVerifier(client)
    app.extensions['ebay_notification_verifier'] = verifier

    @bp.route('/ebay/account-deletion', methods=['GET', 'POST'])
    def account_deletion():
        token = os.environ.get('EBAY_DELETION_VERIFICATION_TOKEN', '')
        endpoint = os.environ.get('EBAY_DELETION_ENDPOINT', '')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,80}', token) or not endpoint.startswith('https://'):
            abort(503)
        if request.method == 'GET':
            challenge = request.args.get('challenge_code', '')
            if not challenge or len(challenge) > 1024:
                abort(400)
            return jsonify(challengeResponse=hashlib.sha256((challenge + token + endpoint).encode()).hexdigest())
        if request.content_length is None or request.content_length > 65536:
            abort(413)
        try:
            payload = verifier.verify(request.get_data(), request.headers.get('X-EBAY-SIGNATURE', ''))
            delete_account_data(get_db(), payload)
        except EbayError:
            # Never acknowledge an unverified deletion as successfully processed.
            abort(503)
        except (ValueError, TypeError, KeyError, AttributeError):
            get_db().rollback()
            abort(412)
        return '', 204

    @bp.get('/ebay/privacy')
    def privacy():
        # Standalone page: no collection navigation, account details or cookies.
        return '''<!doctype html><html lang="en"><meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>StuffApp eBay connection — data use</title><main style="max-width:48rem;margin:3rem auto;padding:1rem;font:18px/1.6 system-ui">
        <h1>StuffApp eBay connection</h1><p>This private collection tool reads the connected
        owner's eBay purchases to match banknotes and track Ordered, Shipped and Delivered.</p>
        <p>It stores relevant order and listing identifiers, titles, seller identifiers,
        shipping dates, tracking numbers and a status-change history. It does not store
        payment-card details or delivery addresses. Access tokens are encrypted on the server.
        It does not place orders, send messages or change anything on eBay.</p>
        <p>The owner can pause checks or disconnect in Banknotes → eBay Orders. Disconnect
        removes authorization tokens; existing shipping history remains. The owner can
        remove that history with Delete eBay data. Verified eBay account-deletion notices
        remove associated integration data. Collection records and photos entered separately
        by the owner are not removed by this connection.</p></main></html>'''

    @bp.after_request
    def no_cache(response):
        response.headers['Cache-Control'] = 'no-store'
        return response

    app.register_blueprint(bp)
