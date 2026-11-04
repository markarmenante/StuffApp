"""Owner-cookie exact-order reader claims stay isolated from Today and each other."""
import hashlib
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
import test_ebay_purchase_lookup as fixtures


class BrowserRequestTests(unittest.TestCase):
    tearDown = fixtures.LookupTests.tearDown
    post = fixtures.LookupTests.post
    item = fixtures.LookupTests.item
    receipt = fixtures.LookupTests.receipt
    cached_listing = fixtures.LookupTests.cached_listing

    def setUp(self):
        fixtures.LookupTests.setUp(self)
        self.db.execute("INSERT INTO ebay_purchase_account VALUES (1,'buyer')")
        self.db.commit()

    def browser_post(self, **payload):
        return self.client.post('/ebay/browser/requests', json=payload, headers={'Origin': 'http://localhost'})

    def job(self):
        return lookup.ensure(self.db, self.note, reader='browser')

    def claim(self, job):
        result = self.browser_post(action='claim', id=job['id'])
        self.assertEqual(result.status_code, 200, result.json)
        return result.json

    def complete(self, claim, **changes):
        payload = dict(action='complete', id=claim['request']['id'], token=claim['token'], account='buyer',
                       observed_at=ebay_orders.now_iso(), items=[self.item()])
        payload.update(changes)
        return self.browser_post(**payload)

    def state(self, job):
        return self.db.execute('SELECT status FROM ebay_purchase_requests WHERE id=?', (job['id'],)).fetchone()[0]

    def test_browser_round_trip_without_today_credential_preserves_price_gallery_and_note(self):
        before = tuple(self.db.execute('SELECT * FROM banknotes').fetchone())
        with patch.dict(os.environ, {'STUFFAPP_TODAY_TOKEN': ''}):
            job = self.job()
            self.assertEqual(job['reader'], 'browser')
            claim = self.claim(job)
            self.assertEqual(claim['request']['expected_account'], 'buyer')
            self.assertFalse(claim['request']['import_checkout'])
            self.assertEqual(self.complete(claim, receipt=self.receipt(), listing=self.cached_listing()).status_code, 200)
        stored = self.db.execute('SELECT token_hash FROM ebay_purchase_browser_claims').fetchone()[0]
        self.assertEqual(stored, hashlib.sha256(claim['token'].encode()).hexdigest())
        self.assertNotEqual(stored, claim['token'])
        self.assertEqual(self.db.execute('SELECT unit_amount_minor FROM ebay_purchase_prices').fetchone()[0], 59989)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_listing_captures').fetchone()[0], 1)
        self.assertEqual(tuple(self.db.execute('SELECT * FROM banknotes').fetchone()), before)

    def test_native_claim_and_completion_cannot_take_browser_work(self):
        job = self.job()
        self.assertIsNone(self.post(action='claim').json['request'])
        claim = self.claim(job)
        self.assertEqual(self.post(action='complete', id=job['id'], token=claim['token'], error='browser').status_code, 409)
        self.assertEqual(self.state(job), 'reading')
        self.assertEqual(self.complete(claim).status_code, 200)

    def test_browser_cannot_complete_today_request_even_with_missing_token(self):
        job = lookup.ensure(self.db, self.note)
        self.post(action='claim')
        self.assertEqual(self.browser_post(action='complete', id=job['id'], error='browser').status_code, 409)
        self.assertEqual(self.state(job), 'reading')

    def test_owner_exact_origin_and_json_are_all_required(self):
        job = self.job()
        payload = dict(action='claim', id=job['id'])
        self.owner = False
        self.assertEqual(self.browser_post(**payload).status_code, 403)
        self.owner = True
        for headers in ({}, {'Origin':'https://gerri.armenante.com'}, {'Origin':'https://localhost'},
                        {'Origin':'http://localhost', 'Sec-Fetch-Site':'cross-site'},
                        {'Origin':'chrome-extension://reader'}):
            with self.subTest(headers=headers):
                self.assertEqual(self.client.post('/ebay/browser/requests', json=payload, headers=headers).status_code, 403)
        self.assertEqual(self.client.post('/ebay/browser/requests', data=payload, headers={'Origin':'http://localhost'}).status_code, 403)
        self.assertEqual(self.state(job), 'queued')

    def test_duplicate_claim_requires_original_token_and_returns_same_claim(self):
        job = self.job(); claim = self.claim(job)
        self.assertEqual(self.browser_post(action='claim', id=job['id']).status_code, 409)
        again = self.browser_post(action='claim', id=job['id'], token=claim['token'])
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json, claim)
        self.assertEqual(self.complete(claim, token='x'*43).status_code, 409)
        self.assertEqual(self.state(job), 'reading')
        self.assertEqual(self.complete(claim).status_code, 200)
        self.assertEqual(self.complete(claim).status_code, 409)

    def test_public_https_origin_works_behind_internal_http_without_forwarded_trust(self):
        job=self.job()
        response=self.client.post('/ebay/browser/requests',base_url='http://stuff.armenante.com',
                                  json={'action':'claim','id':job['id']},headers={'Origin':'https://stuff.armenante.com'})
        self.assertEqual(response.status_code,200,response.json)
        response=self.client.post('/ebay/browser/requests',base_url='http://stuff.armenante.com',
                                  json={'action':'claim','id':job['id']},
                                  headers={'Origin':'http://stuff.armenante.com','X-Forwarded-Proto':'http'})
        self.assertEqual(response.status_code,403)

    def test_signin_challenge_and_schema_restart_keep_same_browser_reservation(self):
        job = self.job(); claim = self.claim(job)
        for state in ('sign_in_required','challenge_required'):
            result = self.browser_post(action='complete', id=job['id'], token=claim['token'], session={'state':state})
            self.assertEqual(result.status_code, 200)
            self.assertEqual(self.state(job), 'reading')
            self.assertEqual(self.client.get('/banknotes/note/purchase-refresh/'+job['id']).json['status'], state)
            ebay_orders.init_schema(self.db)
            self.assertIsNone(self.post(action='claim').json['request'])
        self.assertEqual(self.complete(claim).status_code, 200)

    def test_changed_note_does_not_become_valid_because_sibling_has_old_order(self):
        job = self.job(); claim = self.claim(job)
        self.db.execute("INSERT INTO banknotes(id,order_number,marketplace) VALUES('sibling',?,'eBay')", (self.note['order_number'],))
        self.db.execute("UPDATE banknotes SET order_number='11-11111-11111' WHERE id='note'")
        self.db.commit()
        self.assertEqual(self.complete(claim).status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)

    def test_paused_or_changed_account_rejects_claim_and_completion(self):
        job = self.job()
        self.db.execute('INSERT INTO ebay_mail_connection(id,enabled) VALUES(1,0)'); self.db.commit()
        self.assertEqual(self.browser_post(action='claim',id=job['id']).status_code, 409)
        self.db.execute('UPDATE ebay_mail_connection SET enabled=1'); self.db.commit()
        claim = self.claim(job)
        self.db.execute('UPDATE ebay_mail_connection SET enabled=0'); self.db.commit()
        self.assertEqual(self.complete(claim).status_code, 409)
        self.db.execute('UPDATE ebay_mail_connection SET enabled=1')
        self.db.execute("UPDATE ebay_purchase_account SET account_name='other-buyer'"); self.db.commit()
        self.assertEqual(self.complete(claim).status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)

    def test_wrong_signed_in_account_and_invalid_evidence_are_atomic(self):
        for changes in (dict(account='other-buyer'), dict(items=[self.item(order_id='11-11111-11111')]),
                        dict(receipt=self.receipt(unit_amount='999.99'))):
            with self.subTest(changes=changes):
                job=self.job(); claim=self.claim(job)
                self.assertEqual(self.complete(claim, **changes).status_code, 409)
                self.assertEqual(self.state(job), 'failed')
                self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)
                self.db.execute('UPDATE ebay_purchase_requests SET requested_at=?',(time.time()-20,)); self.db.commit()

    def test_expiry_cancellation_and_late_result_cannot_write(self):
        job=self.job(); claim=self.claim(job)
        self.assertEqual(self.client.post('/banknotes/note/purchase-refresh/'+job['id']+'/cancel',json={}).status_code, 200)
        self.assertEqual(self.complete(claim).status_code, 409)
        new_job=self.job(); newer=self.claim(new_job)
        self.assertNotEqual(new_job['id'],job['id'])
        self.assertEqual(self.complete(claim).status_code, 409)
        self.assertEqual(self.state(new_job),'reading')
        with patch.object(lookup.time,'time',return_value=new_job['expires_at']+1):
            self.assertEqual(self.complete(newer).status_code, 409)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM ebay_order_items').fetchone()[0], 0)

    def test_same_order_sibling_cannot_replace_or_cancel_original_note_claim(self):
        job=self.job(); claim=self.claim(job)
        self.db.execute("INSERT INTO banknotes(id,order_number,marketplace) VALUES('sibling',?,'eBay')", (self.note['order_number'],))
        self.db.commit()
        sibling=dict(self.db.execute("SELECT * FROM banknotes WHERE id='sibling'").fetchone())
        self.assertEqual(lookup.ensure(self.db,sibling,reader='browser')['status'],'failed')
        self.assertEqual(self.client.post('/banknotes/sibling/purchase-refresh/'+job['id']+'/cancel',json={}).status_code,404)
        self.assertEqual(self.state(job),'reading')
        self.assertEqual(self.complete(claim).status_code,200)

    def test_browser_selection_precedes_polling_and_cannot_steal_active_today_read(self):
        first=lookup.ensure(self.db,self.note)
        job=self.job()
        self.assertNotEqual(first['id'],job['id'])
        self.assertIsNone(self.post(action='claim').json['request'])
        self.db.execute("UPDATE ebay_purchase_requests SET reader='today'"); self.db.commit()
        self.post(action='claim')
        self.assertEqual(self.job()['status'],'failed')

    def test_unknown_reader_missing_account_and_malformed_id_are_rejected(self):
        with self.assertRaises(ValueError):lookup.ensure(self.db,self.note,reader='other')
        for request_id in (None, [], {}, 'bad-id', 'a'*32):
            self.assertEqual(self.browser_post(action='complete',id=request_id,error='browser').status_code,409)
        self.db.execute('DELETE FROM ebay_purchase_account'); self.db.commit()
        self.assertEqual(self.job()['status'],'failed')

    def test_legacy_schema_migration_preserves_today_requests(self):
        db=sqlite3.connect(':memory:'); db.row_factory=sqlite3.Row
        db.execute('CREATE TABLE ebay_purchase_requests (id TEXT PRIMARY KEY,order_id TEXT UNIQUE,requested_at REAL,status TEXT,message TEXT)')
        db.execute("INSERT INTO ebay_purchase_requests VALUES ('legacy','12-15265-43926',1,'queued','Waiting')")
        ebay_orders.init_schema(db)
        self.assertEqual(db.execute('SELECT reader FROM ebay_purchase_requests').fetchone()[0],'today')
        ebay_orders.init_schema(db)
        self.assertEqual(db.execute('SELECT COUNT(*) FROM ebay_purchase_requests').fetchone()[0],1)
        db.close()


if __name__=='__main__':unittest.main()
