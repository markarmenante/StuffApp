"""An unreadable eBay offer must never become an actionable recommendation."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from datetime import date, timedelta
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='market-ebay-verification-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import app as stuff
import market_scan as market

URL = 'https://www.ebay.ca/itm/185386368846'
TITLE = 'Canada 1937 $20 Bank of Canada, Gordon-Towers'
EVIDENCE = 'Active eBay.ca Buy It Now listing (item not flagged sold/ended)'


def candidate(**extra):
    return dict(title=TITLE, listing_url=URL, country='Canada', theme='denominations',
                live_evidence=EVIDENCE, **extra)


class EbayVerificationTests(unittest.TestCase):
    def setUp(self):
        self.db = stuff.open_db_connection()
        self.db.execute('DELETE FROM market_scan_items')
        self.db.execute('DELETE FROM market_scans')
        self.db.execute('DELETE FROM banknotes')
        self.db.execute("INSERT INTO market_scans(id,category,status,started_at) VALUES ('scan','banknotes','done',datetime('now'))")
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def seed(self, ident='offer', status='new', **extra):
        item = candidate(**extra)
        self.db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,title,listing_url,payload,created_at) VALUES (?,'scan','banknotes',?,?,?,?,datetime('now'))",
                        (ident, status, TITLE, URL, json.dumps(item)))
        self.db.commit()
        return item

    def test_model_claim_and_future_date_cannot_override_unreadable_page(self):
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        for response in (market.PageResult(403, 'Forbidden', URL),
                         market.PageResult(200, 'captcha', 'https://www.ebay.ca/splashui/captcha', True),
                         market.PageResult(None, '', URL)):
            with self.subTest(status=response.status, challenged=response.challenged):
                ctx = market.ScanContext(seconds=10)
                ctx.fetcher = market.FetchService(ctx, lambda *args: response, pace=0)
                with market.scope(ctx):
                    self.assertEqual(stuff._market_verify_live([
                        candidate(verified=True), candidate(closes=tomorrow, sale_type='auction')]), [])

    def test_ended_banner_wins_over_recommendations_and_model(self):
        html = ('<h1>Canada 20 Dollars 1937 BC-25b Pick-62b Ch UNC PMG 64 EPQ</h1>'
                '<p>This listing was ended by the seller on Sat, May 25 at 18:33 '
                'because the item is no longer available.</p><span>US $599.00</span>'
                '<h2>Similar Items</h2><button>Buy It Now</button>')
        with patch.object(stuff, '_market_fetch_page', return_value=(200, html)):
            self.assertEqual(stuff._market_verify_live([candidate()]), [])

    def test_unverified_saved_offers_move_out_of_current_results(self):
        self.seed('legacy', verified=False)
        self.seed('missing')
        self.seed('verified', verified=True)
        self.seed('paid', status='ordered', verified=False)
        rows = stuff._market_items(self.db, 'banknotes')
        self.assertEqual([r['id'] for r in rows], ['verified'])
        statuses = dict(self.db.execute('SELECT id,status FROM market_scan_items'))
        self.assertEqual(statuses, {'legacy':'superseded', 'missing':'superseded',
                                   'verified':'new', 'paid':'ordered'})
        self.assertEqual({r['id'] for r in stuff._market_items(self.db, 'banknotes', earlier=True)}, {'legacy', 'missing'})

    def test_buy_and_listing_recheck_even_previously_verified_offer(self):
        self.seed(verified=True)
        client = stuff.app.test_client()
        with patch.object(stuff, '_market_listing_probe', return_value={'state':'unknown', 'why':'status 403'}):
            reply = client.post('/banknotes/market/offer/buy', json={'location':'Home'})
            self.assertEqual(reply.status_code, 409)
            self.assertIn('verif', reply.get_json()['error'].lower())
            self.assertNotEqual(client.get('/banknotes/market/offer/listing').status_code, 302)
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0], 0)
        self.assertEqual(stuff._market_items(self.db, 'banknotes'), [])

    def test_live_offer_and_already_paid_recording_still_work(self):
        item = self.seed(verified=False)
        live = '<h1>' + TITLE + '</h1><button>Buy It Now</button>'
        client = stuff.app.test_client()
        with patch.object(stuff, '_market_fetch_page', return_value=(200, live)):
            self.assertTrue(stuff._market_verify_live([item])[0]['verified'])
            reply = client.get('/banknotes/market/offer/listing')
            self.assertEqual(reply.status_code, 302)
            self.assertEqual(reply.location, URL)
        with patch.object(stuff, '_market_listing_probe', side_effect=AssertionError('Bought must not require a live listing')), \
             patch.object(stuff, '_market_store_images', return_value={}), \
             patch.object(stuff, '_market_vendor_name', return_value='Test seller'), \
             patch.object(stuff, 'ensure_country_history'), \
             patch.object(stuff, 'property_choices_for_category', return_value=['Home']):
            reply = client.post('/banknotes/market/offer/buy', json={'location':'Home', 'bought':True})
            self.assertEqual(reply.status_code, 200, reply.get_json())
        self.assertEqual(self.db.execute('SELECT status FROM banknotes').fetchone()[0], 'Ordered')


if __name__ == '__main__':
    unittest.main()
