"""Viewing an exact eBay offer does not relax Buy's availability requirement."""
from contextlib import contextmanager, ExitStack
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
    item = dict(title=TITLE, listing_url=URL, country='Canada', theme='denominations',
                live_evidence=EVIDENCE)
    item.update(extra)
    return item


class EbayVerificationTests(unittest.TestCase):
    def setUp(self):
        self.db = stuff.open_db_connection()
        for table in ('market_scan_items', 'market_scans', 'market_dismissals', 'banknotes', 'coins'):
            self.db.execute('DELETE FROM ' + table)
        for category in ('banknotes', 'coins'):
            self.db.execute("INSERT INTO market_scans(id,category,status,started_at) VALUES (?,?,'done',datetime('now'))",
                            ('scan-' + category, category))
        self.db.commit()

    def tearDown(self):
        self.db.close()

    def seed(self, ident='offer', status='new', category='banknotes', **extra):
        if category == 'coins':
            extra = {'title':'Lucania Velia AR Nomos NGC XF40', 'country':'Italy', **extra}
        item = candidate(**extra)
        self.db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,title,listing_url,payload,created_at) VALUES (?,?,?,?,?,?,?,datetime('now'))",
                        (ident, 'scan-' + category, category, status, item['title'], item['listing_url'], json.dumps(item)))
        self.db.commit()
        return item

    @contextmanager
    def page(self, response):
        ctx = market.ScanContext(seconds=10)
        ctx.fetcher = market.FetchService(ctx, lambda *args: response, pace=0)
        with market.scope(ctx), patch.object(stuff.market_ebay_feed, 'live_probe', return_value=None) as browser:
            yield browser

    @contextmanager
    def no_purchase_work(self):
        with ExitStack() as stack:
            calls = [stack.enter_context(patch.object(stuff, name)) for name in (
                '_market_create_record', '_market_store_images', '_market_fetch_image',
                '_trim_banknote_image', '_market_resolve_model', 'ensure_country_history')]
            calls.append(stack.enter_context(patch.object(stuff.market_purchase_capture, 'enqueue')))
            yield
            for call in calls:
                call.assert_not_called()
        for category in ('banknotes', 'coins'):
            self.assertEqual(self.db.execute('SELECT count(*) FROM ' + category).fetchone()[0], 0)

    def assert_unverified(self, ident, status='superseded'):
        row = self.db.execute('SELECT status,payload,record_id FROM market_scan_items WHERE id=?', [ident]).fetchone()
        self.assertEqual(row['status'], status)
        self.assertIsNone(row['record_id'])
        item = json.loads(row['payload'])
        self.assertIs(item['verified'], False)
        self.assertNotIn('_checkout_url', item)

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

    def test_exact_view_opens_unknown_ebay_page_without_claiming_availability(self):
        exact = URL + '?_trksid=fixture&utm_source=market'
        client = stuff.app.test_client()
        pages = (market.PageResult(403, 'Forbidden', exact),
                 market.PageResult(200, 'Security Measure', 'https://www.ebay.ca/splashui/captcha', True),
                 market.PageResult(None, '', exact))
        for category in ('banknotes', 'coins'):
            for index, response in enumerate(pages):
                with self.subTest(category=category, status=response.status, challenged=response.challenged):
                    ident = category + str(index)
                    self.seed(ident, category=category, listing_url=exact, verified=True)
                    with self.page(response) as browser, self.no_purchase_work():
                        reply = client.get(f'/{category}/market/{ident}/listing')
                    self.assertEqual(reply.status_code, 302)
                    self.assertEqual(reply.location, exact)
                    browser.assert_called_once()
                    self.assertEqual(browser.call_args.args[1], exact)
                    self.assert_unverified(ident)
            self.assertEqual(stuff._market_items(self.db, category), [])

    def test_view_still_opens_after_buy_rejects_unknown_availability(self):
        client = stuff.app.test_client()
        for category in ('banknotes', 'coins'):
            with self.subTest(category=category):
                self.seed(category, category=category, verified=True)
                route = f'/{category}/market/{category}'
                with self.page(market.PageResult(403, 'Forbidden', URL)), self.no_purchase_work():
                    reply = client.post(route + '/buy', json={'location':'Home'})
                    self.assertEqual(reply.status_code, 409)
                    self.assertIn('verif', reply.get_json()['error'].lower())
                    self.assert_unverified(category)
                    view = client.get(route + '/listing')
                self.assertEqual(view.status_code, 302)
                self.assertEqual(view.location, URL)
                self.assert_unverified(category)
                self.assertEqual(stuff._market_items(self.db, category), [])

    def test_view_still_rejects_ended_and_invalid_pages(self):
        client = stuff.app.test_client()
        pages = (market.PageResult(200, '<p>This listing has ended</p><button>Buy It Now</button>', URL),
                 market.PageResult(404, '', URL),
                 market.PageResult(200, '<h1>Search results</h1>', 'https://www.ebay.ca/sch/i.html'),
                 market.PageResult(200, '<button>Buy It Now</button>', 'https://www.ebay.ca/itm/185386368847'))
        for category in ('banknotes', 'coins'):
            for index, response in enumerate(pages):
                with self.subTest(category=category, page=index):
                    ident = category + str(index)
                    self.seed(ident, category=category, verified=True)
                    with self.page(response), self.no_purchase_work():
                        reply = client.get(f'/{category}/market/{ident}/listing')
                    self.assertEqual(reply.status_code, 410)
                    self.assertEqual(self.db.execute('SELECT status FROM market_scan_items WHERE id=?', [ident]).fetchone()[0], 'unavailable')

    def test_view_preserves_readable_page_identity_and_eligibility_checks(self):
        client = stuff.app.test_client()
        cases = ((TITLE.replace('1937', '1954'), '', 'identity'),
                 (TITLE, '<p>Specimen</p>', 'eligibility'),
                 (TITLE + ' PMG 64 NET', '', 'eligibility'))
        for index, (title, text, kind) in enumerate(cases):
            with self.subTest(kind=kind, title=title):
                ident = str(index)
                self.seed(ident, verified=True)
                html = '<h1>' + title + '</h1>' + text + '<button>Buy It Now</button>'
                with self.page(market.PageResult(200, html, URL)), self.no_purchase_work():
                    reply = client.get('/banknotes/market/' + ident + '/listing')
                self.assertEqual(reply.status_code, 410)
                row = self.db.execute('SELECT status,payload FROM market_scan_items WHERE id=?', [ident]).fetchone()
                self.assertEqual(row['status'], 'unavailable')
                self.assertEqual(json.loads(row['payload'])['_unavailable_kind'], kind)

    def test_view_never_reopens_stored_unavailable_or_generic_urls(self):
        client = stuff.app.test_client()
        cases = (('new', {'listing_url':'https://www.ebay.ca/sch/i.html?_nkw=canada'}),
                 ('unavailable', {'_unavailable_kind':'ended', 'unavailable_reason':'Listing ended'}))
        for category in ('banknotes', 'coins'):
            for index, (status, extra) in enumerate(cases):
                with self.subTest(category=category, status=status):
                    ident = category + str(index)
                    self.seed(ident, category=category, status=status, verified=True, **extra)
                    with patch.object(stuff, '_market_listing_probe') as probe, self.no_purchase_work():
                        reply = client.get(f'/{category}/market/{ident}/listing')
                    self.assertEqual(reply.status_code, 410)
                    probe.assert_not_called()

    def test_browser_observed_ended_offer_still_blocks_view_after_server_challenge(self):
        self.seed(verified=True)
        with self.page(market.PageResult(403, 'Forbidden', URL)) as browser, self.no_purchase_work():
            browser.return_value = {'state':'ended', 'why':'Exact signed-in listing has ended'}
            reply = stuff.app.test_client().get('/banknotes/market/offer/listing')
        self.assertEqual(reply.status_code, 410)
        browser.assert_called_once()

    def test_view_of_dismissed_history_keeps_permanent_suppression(self):
        client = stuff.app.test_client()
        for category in ('banknotes', 'coins'):
            with self.subTest(category=category):
                self.seed(category, category=category, verified=True)
                market.dismiss_listing(self.db, category, URL)
                route = f'/{category}/market/{category}'
                with self.page(market.PageResult(403, 'Forbidden', URL)), self.no_purchase_work():
                    view = client.get(route + '/listing')
                    self.assertEqual(client.post(route + '/buy', json={'location':'Home'}).status_code, 409)
                self.assertEqual(view.status_code, 302)
                self.assertEqual(view.location, URL)
                self.assert_unverified(category, status='dismissed')
                self.assertTrue(market.is_dismissed(self.db, category, URL))
                self.assertEqual(stuff._market_items(self.db, category), [])
                self.assertEqual([r['id'] for r in stuff._market_items(self.db, category, earlier=True)], [category])

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
