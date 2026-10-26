"""Watched photo evidence, finite queue and derived matching; no external calls."""
import copy
import json
import os
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='market-slab-labels-')
os.environ.pop('ANTHROPIC_API_KEY', None)
os.environ['MARKET_LABEL_WORKER'] = '0'
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import market_slab_labels as labels
import market_ebay_feed as feed
import market_estimates
import market_scan
import app as stuff

URL = 'https://www.ebay.com/itm/123456789012'
PHOTO = 'https://i.ebayimg.com/images/g/fixture/s-l500.jpg'
ACCOUNT = 'fixture-owner'


def card(**changes):
    return dict(dict(item_id='123456789012', listing_url=URL, image_url=PHOTO,
                     title='Seychelles 1968 5 Rupees PMG 64', price='US $299.89', sources=['watched']), **changes)


def reading(**changes):
    row = dict(photo_id='photo-0', confidence='high', literal_label='PMG\nSeychelles\nGovernment of Seychelles\nPick#14a 1968 5 Rupees\n64 EPQ\n123456-001',
               literal_note='', country='Seychelles', issuer='Government of Seychelles',
               reference='Pick#14a', state='', denomination='5 Rupees', series='',
               grading_authority='PMG', grade='64 EPQ', certificate_number='123456-001')
    row.update(changes)
    return row


def result(*rows, **changes):
    rows = rows or (reading(),)
    return dict(dict(photo_id='photo-0', visible_notes=len(rows), all_visible_identified=True, readings=list(rows)), **changes)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(':memory:'); self.db.row_factory = sqlite3.Row
        labels.init_schema(self.db)

    def tearDown(self):
        self.db.close()

    def enqueue(self, rows=None, now=100):
        with self.db:
            return labels.enqueue(self.db, 'snapshot', ACCOUNT, rows or [card()], expires_at=10000, now=now)

    def test_safe_exact_photo_and_cache_identity(self):
        expected = 'https://i.ebayimg.com/images/g/fixture/s-l1600.jpg'
        self.assertEqual(labels.image_url(PHOTO), expected)
        for value in ('http://i.ebayimg.com/images/g/x/s-l500.jpg', 'https://i.ebayimg.com.evil.test/images/g/x/s-l500.jpg',
                      'https://user@i.ebayimg.com/images/g/x/s-l500.jpg', 'https://i.ebayimg.com:444/images/g/x/s-l500.jpg',
                      'https://i.ebayimg.com/logo.jpg', 'file:///private/photo.jpg'):
            self.assertEqual(labels.image_url(value), '', value)
        wanted = labels.target(card(), ACCOUNT)
        self.assertEqual(wanted['key'], labels.target(card(price='$1', title='New title', image_url=expected), ACCOUNT)['key'])
        self.assertNotEqual(wanted['key'], labels.target(card(image_url=PHOTO.replace('fixture', 'changed')), ACCOUNT)['key'])
        self.assertNotEqual(wanted['key'], labels.target(card(), 'other-owner')['key'])
        self.assertIsNone(labels.target(card(sources=['sponsored']), ACCOUNT))

    def test_literal_label_fields_and_full_reference(self):
        out = labels.normalize(result())
        self.assertEqual(out['state'], 'ready')
        self.assertEqual(out['readings'][0]['reference'], 'Pick#14a')
        self.assertIn('\n', out['readings'][0]['literal_label'])
        out = labels.normalize(result(reading(issuer='Central Bank of Seychelles')))
        self.assertEqual(out['readings'][0]['issuer'], '')
        out = labels.normalize(result(reading(reference='Pick#14b')))
        self.assertEqual(out['state'], 'unreadable')
        for reference in ('123456-001', '14a', 'P123456'):
            self.assertEqual(labels.normalize(result(reading(reference=reference)))['state'], 'unreadable')

    def test_serial_certificate_and_barcode_cannot_be_catalogues(self):
        for context in ('S/N ', 'Serial No. ', 'Certificate ', 'Certification number: ', 'Barcode: ',
                        'S/N:\n', 'Certification number:\n', 'Barcode:\n'):
            row = reading(literal_label='PMG\nSeychelles\n' + context + 'P123456\n64', reference='P123456', grade='64')
            self.assertEqual(labels.normalize(result(row))['state'], 'unreadable', context)
        self.assertEqual(labels.normalize(result(reading(grading_authority='')))['state'], 'unreadable')
        for ref in ('PMG 64', 'PCGS64', 'P MG64'):
            row = reading(literal_label='Seychelles PMG PCGS64 P MG64 PMG 64 certificate 1234567', reference=ref)
            self.assertEqual(labels.normalize(result(row))['state'], 'unreadable', ref)

    def test_multi_note_partial_and_unreadable_schema(self):
        second = reading(country='Bermuda', literal_label='PMG Bermuda Pick#18b 64', issuer='', reference='Pick#18b', grade='64', certificate_number='')
        self.assertEqual(labels.normalize(result(reading(), second))['state'], 'ready')
        self.assertEqual(labels.normalize(result(reading(), reading(confidence='low')))['state'], 'partial')
        self.assertEqual(labels.normalize(result(all_visible_identified=False))['state'], 'partial')
        self.assertEqual(labels.normalize(result(reading(), visible_notes=3))['state'], 'partial')
        for raw in ({}, result(photo_id='other'), result(visible_notes=True), result(reading(photo_id='other'))):
            with self.assertRaises(ValueError): labels.normalize(raw)

    def test_criswell_needs_explicit_state(self):
        row = reading(country='United States', issuer='', reference='Cr. 7', state='',
                      literal_label='PMG\nUnited States\nCr. 7\n64', grade='64', certificate_number='')
        self.assertEqual(labels.normalize(result(row))['state'], 'unreadable')
        row.update(state='South Carolina', literal_label=row['literal_label'] + '\nSouth Carolina')
        self.assertEqual(labels.normalize(result(row))['state'], 'ready')

    def test_finite_queue_cache_cooldown_and_read_only_status(self):
        rows = [card(item_id=str(123456789012+n), listing_url=f'https://www.ebay.com/itm/{123456789012+n}') for n in range(105)]
        ident = self.enqueue(rows)
        self.assertEqual(labels.status(self.db, ACCOUNT, now=100)['total'], 100)
        self.assertEqual(self.enqueue(rows), ident)
        self.db.execute('PRAGMA query_only=ON')
        self.assertEqual(labels.status(self.db, ACCOUNT, now=100)['status'], 'queued')
        self.assertIsNone(labels.annotation(self.db, labels.target(card(), 'other-owner'), now=100))
        self.db.execute('PRAGMA query_only=OFF')
        wanted = labels.claim(self.db, lambda *_: True, now=101)
        self.assertTrue(labels.publish(self.db, wanted, result(), 'a'*64, lambda *_: True, now=102))
        self.enqueue(rows, now=103)
        self.assertEqual(self.db.execute('SELECT state FROM market_label_cache WHERE cache_key=?', (wanted['key'],)).fetchone()[0], 'ready')

    def test_global_two_claim_limit_lease_fencing_and_finite_recovery(self):
        self.enqueue([card(listing_url=f'https://www.ebay.com/itm/{123456789012+n}') for n in range(3)])
        first = labels.claim(self.db, lambda *_: True, now=101)
        second = labels.claim(self.db, lambda *_: True, now=101)
        self.assertIsNone(labels.claim(self.db, lambda *_: True, now=102))
        replacement = labels.claim(self.db, lambda *_: True, now=222)
        self.assertFalse(labels.publish(self.db, first, result(), 'a'*64, lambda *_: True, now=223))
        self.assertTrue(replacement)
        labels.claim(self.db, lambda *_: True, now=222)
        labels.claim(self.db, lambda *_: True, now=343)
        self.assertLessEqual(self.db.execute('SELECT MAX(attempts) FROM market_label_cache').fetchone()[0], 2)

    def test_late_or_ineligible_results_do_not_publish_evidence(self):
        self.enqueue()
        wanted = labels.claim(self.db, lambda *_: True, now=101)
        self.assertTrue(labels.publish(self.db, wanted, result(), 'a'*64, lambda *_: False, now=102))
        shown = labels.annotation(self.db, wanted, now=103)
        self.assertEqual(shown['state'], 'unavailable'); self.assertEqual(shown['readings'], [])
        self.assertIsNone(labels.annotation(self.db, wanted, now=102+labels.ERROR_TTL))
        state = labels.status(self.db, ACCOUNT, now=103)
        self.assertFalse(state['retry_available']); self.assertEqual(state['retry_after'], 102+labels.ERROR_TTL)
        self.assertTrue(labels.status(self.db, ACCOUNT, now=103+labels.ERROR_TTL)['retry_available'])

    def test_clock_is_read_after_waiting_for_write_lock(self):
        self.enqueue()
        wanted = labels.claim(self.db, lambda *_: True, now=101)
        clock = [102]
        db = self.db
        class DelayedLock:
            def execute(self, sql, *args):
                result = db.execute(sql, *args)
                if sql == 'BEGIN IMMEDIATE': clock[0] = 300
                return result
            def __getattr__(self, name): return getattr(db, name)
        with patch.object(labels.time, 'time', side_effect=lambda: clock[0]):
            self.assertFalse(labels.publish(DelayedLock(), wanted, result(), 'a'*64, lambda *_: True))
        with patch.object(labels.time, 'time', side_effect=lambda: clock[0]):
            replacement = labels.claim(DelayedLock(), lambda *_: True)
        self.assertIsNotNone(replacement)
        self.assertEqual(self.db.execute('SELECT lease_until FROM market_label_cache').fetchone()[0], 420)

    def test_real_label_readings_keep_printed_dates_separate_from_series(self):
        fixtures = json.loads((Path(__file__).parent/'fixtures/market_slab_readings.json').read_text())
        actual = [labels.normalize(entry['raw']) for entry in fixtures]
        self.assertTrue(all(row['state'] == 'ready' for row in actual))
        readings = [row['readings'][0] for row in actual]
        self.assertEqual([row['reference'] for row in readings], ['Pick# 14a','Fr. 652','Pick# 17d'])
        self.assertEqual([row['date_text'] for row in readings], ['1968','1902','1972'])
        self.assertEqual([row['series'] for row in readings], ['', '1902', ''])

    def test_download_is_one_exact_allowlisted_image(self):
        from io import BytesIO
        from PIL import Image
        buffer = BytesIO(); Image.new('RGB', (160, 160), 'white').save(buffer, 'PNG')
        wanted = labels.target(card(), ACCOUNT)
        with patch.object(labels.source_documents, 'fetch_bytes', return_value=(buffer.getvalue(), 'image/png', wanted['image_url'])) as fetch:
            data, digest = labels.download(wanted)
            self.assertEqual(len(digest), 64)
            fetch.assert_called_once_with(wanted['image_url'], {'i.ebayimg.com'}, labels.MAX_BYTES)
        with patch.object(labels.source_documents, 'fetch_bytes', return_value=(buffer.getvalue(), 'image/png', wanted['image_url'].replace('fixture', 'other'))):
            with self.assertRaises(ValueError): labels.download(wanted)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, STUFFAPP_TODAY_TOKEN='fixture-token-'+'x'*32, RAILWAY_SERVICE_NAME='web')
        self.env.start(); self.ctx = stuff.app.app_context(); self.ctx.push()
        self.db = stuff.get_db(); self.client = stuff.app.test_client()
        for table in ('market_label_job_items','market_label_jobs','market_label_cache','market_estimate_cache',
                      'ebay_market_card_sources','ebay_market_cards','ebay_market_sessions','ebay_market_requests',
                      'market_dismissals','market_scan_items','market_scans','banknote_original_listings','banknote_ebay_links','banknotes',
                      'ebay_purchase_account','ebay_connection'):
            self.db.execute('DELETE FROM '+table)
        self.db.execute('INSERT INTO ebay_purchase_account VALUES(1,?)', (ACCOUNT,)); self.db.commit()

    def tearDown(self):
        self.ctx.pop(); self.env.stop()

    def seed(self, source=None):
        source = source or card()
        ident = feed.queue(self.db)
        self.db.execute("UPDATE ebay_market_requests SET status='reading' WHERE id=?", (ident,)); self.db.commit()
        now = feed.utc(time.time())
        payload = dict(request_id=ident, account=ACCOUNT, observed_at=now,
                       sources={kind:dict(status='ok',message='') for kind in feed.KINDS},
                       items=[dict(source, source_label='Watched', listing_text=source['title']+'\nListing controls: Buy It Now', live_state='live', listing_checked_at=now)])
        feed.complete(self.db, payload)
        with patch.dict(os.environ, ANTHROPIC_API_KEY='synthetic-not-used'):
            stuff._market_enqueue_slab_labels(self.db)
        self.db.commit()
        return labels.target(source, ACCOUNT)

    def publish(self, raw=None):
        wanted = labels.claim(self.db, stuff._market_label_target_current)
        self.assertIsNotNone(wanted)
        self.assertTrue(labels.publish(self.db, wanted, raw or result(), 'a'*64, stuff._market_label_target_current))
        return wanted

    def test_raw_fingerprint_and_estimate_survive_photo_identity(self):
        self.seed()
        before = stuff._market_personal_feed(self.db, [])['cards'][0]
        key = market_estimates.target(before)['key']
        self.publish()
        self.db.execute('PRAGMA query_only=ON')
        after = stuff._market_personal_feed(self.db, [])['cards'][0]
        self.assertEqual(after['label_check']['state'], 'ready')
        self.assertEqual(after['country'], before['country'])
        self.assertEqual(after['pick_number'], before['pick_number'])
        self.assertEqual(after['price'], 'US $299.89')
        self.assertEqual(market_estimates.target(after)['key'], key)
        self.assertEqual(after['_market_identity']['pick_number'], 'Pick#14a')
        self.assertFalse(after['collection_check_incomplete'])
        self.db.execute('PRAGMA query_only=OFF')

    def test_country_variety_and_state_matching_are_exact(self):
        self.db.execute("INSERT INTO banknotes(id,country,pick_number,status) VALUES('bermuda','Bermuda','P-14a','Own')")
        self.db.execute("INSERT INTO banknotes(id,country,pick_number,status) VALUES('wrong-variety','Seychelles','P-14b','Own')")
        self.db.execute("INSERT INTO banknotes(id,country,pick_number,status) VALUES('match','Seychelles','P-14a','Ordered')"); self.db.commit()
        self.seed(); self.publish()
        after = stuff._market_personal_feed(self.db, [])['cards'][0]
        self.assertEqual([row['id'] for row in after['collection_matches']], ['match'])
        self.assertIn('photo label', after['collection_matches'][0]['reason'])

    def test_title_reference_conflict_is_explicit_and_incomplete(self):
        self.seed(card(title='Seychelles P-117d PMG 66 EPQ'))
        self.publish(result(reading(reference='Pick#17d', literal_label='PMG Seychelles Pick#17d 66 EPQ', issuer='', grade='66 EPQ')))
        after = stuff._market_personal_feed(self.db, [])['cards'][0]
        self.assertEqual(after['label_check']['state'], 'conflict')
        self.assertIn('estimates have not been validated', after['label_check']['message'])
        self.assertTrue(after['collection_check_incomplete']); self.assertEqual(after['collection_matches'], [])
        self.assertEqual(after['pick_number'], 'P-117d')

    def test_numeric_grade_disagreement_warns_without_changing_catalogue_match(self):
        self.seed(card(title='Seychelles Pick#14a PMG 58 EPQ')); self.publish()
        after = stuff._market_personal_feed(self.db, [])['cards'][0]
        self.assertEqual(after['label_check']['state'], 'ready')
        self.assertFalse(after['collection_check_incomplete'])
        self.assertIn('numeric grade differs', after['label_check']['message'])

    def test_promoted_candidate_uses_same_raw_watched_evidence(self):
        self.seed(); self.publish()
        candidate = dict(card(), country='Seychelles', pick_number='', issuer='', grade='PMG 64', verified=True)
        before = copy.deepcopy(candidate)
        after = stuff._market_overlay_slab_labels(self.db, candidate, [])
        self.assertEqual(after['label_check']['state'], 'ready')
        self.assertEqual(candidate, before)
        self.assertEqual(market_estimates.target(after)['key'], market_estimates.target(before)['key'])
        self.assertFalse(after['collection_check_incomplete'])
        disagree = stuff._market_overlay_slab_labels(self.db, dict(candidate, country='Bermuda', pick_number='P-22'), [])
        self.assertEqual(disagree['label_check']['state'], 'conflict')
        self.assertTrue(disagree['collection_check_incomplete'])

    def test_multiple_notes_keep_each_match_and_whole_check_incomplete(self):
        self.db.execute("INSERT INTO banknotes(id,country,pick_number,status) VALUES('bermuda','Bermuda','P-18b','Own')"); self.db.commit()
        self.seed(card(title='Two graded banknotes PMG 64'))
        second = reading(country='Bermuda', issuer='', reference='Pick#18b', literal_label='PMG Bermuda Pick#18b 64', grade='64', certificate_number='')
        self.publish(result(reading(), second))
        after = stuff._market_personal_feed(self.db, [])['cards'][0]
        self.assertEqual(after['label_check']['state'], 'partial')
        self.assertEqual([r['id'] for r in after['collection_matches']], ['bermuda'])
        self.assertTrue(after['collection_check_incomplete'])

    def test_one_visible_label_cannot_complete_an_explicit_bundle(self):
        self.seed(card(title='Lot of 3 Seychelles graded banknotes PMG 64'))
        self.publish()
        after = stuff._market_personal_feed(self.db, [])['cards'][0]
        self.assertEqual(after['label_check']['state'], 'partial')
        self.assertTrue(after['collection_check_incomplete'])

    def test_changed_image_account_and_delete_fence_results(self):
        wanted = self.seed(); claimed = labels.claim(self.db, stuff._market_label_target_current)
        self.seed(card(image_url=PHOTO.replace('fixture','changed')))
        self.assertFalse(stuff._market_label_target_current(self.db, wanted))
        labels.publish(self.db, claimed, result(), 'a'*64, stuff._market_label_target_current)
        self.assertEqual(labels.annotation(self.db, wanted)['state'], 'unavailable')
        current = labels.claim(self.db, stuff._market_label_target_current)
        market_scan.dismiss_listing(self.db, 'banknotes', URL) if hasattr(market_scan,'dismiss_listing') else self.db.execute(
            'INSERT INTO market_dismissals(category,canonical_url,dismissed_at) VALUES(?,?,?)', ('banknotes',market_scan.canonical_url(URL),'2026-10-25'))
        self.db.commit()
        self.assertFalse(stuff._market_label_target_current(self.db, current))
        self.db.execute("UPDATE ebay_purchase_account SET account_name='other'"); self.db.commit()
        self.assertFalse(stuff._market_label_target_current(self.db, current))

    def test_excluded_photo_grade_is_hidden_and_purchase_path_refuses(self):
        self.seed(); self.publish(result(reading(literal_label='PMG Seychelles 64 NET', issuer='', reference='', grade='64 NET')))
        self.assertEqual(stuff._market_personal_feed(self.db, [])['cards'], [])
        with patch.object(stuff, '_market_purchase_response', side_effect=AssertionError('no purchase')):
            response = self.client.post('/banknotes/market/ebay-feed/123456789012/buy', json={})
        self.assertEqual(response.status_code, 409)
        self.assertIn('NET', response.json['error'])

    def test_status_is_read_only_and_bootstrap_needs_signed_owner(self):
        self.seed()
        self.db.execute('PRAGMA query_only=ON')
        self.assertEqual(self.client.get('/banknotes/market/labels').status_code, 200)
        self.db.execute('PRAGMA query_only=OFF')
        self.assertEqual(self.client.post('/banknotes/market/labels').status_code, 403)
        with patch.object(stuff, '_market_unwatch_authorized', return_value=True), patch.object(stuff, '_market_wake_label_worker') as wake:
            response = self.client.post('/banknotes/market/labels')
            self.assertEqual(response.status_code, 200); wake.assert_called_once()


if __name__ == '__main__':
    unittest.main()
