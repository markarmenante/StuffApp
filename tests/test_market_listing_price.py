"""Primary-product asking prices override discovery errors without touching purchases."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='market-price-')
os.environ.pop('ANTHROPIC_API_KEY', None)
import app as stuff
from market_listing_price import read
from market_scan import PageResult

URL = 'https://www.ma-shops.com/notescoinshobby/item.php?id=569&curr=USD'
TITLE = '5 Yen 1945 Japan Allied Military Currency Pick-69b GEM UNC PMG 65 EPQ'


def micro(amount='249.99', currency='USD', url=URL, title=TITLE):
    # Attribute order/quotes and nesting follow the observed MA-Shops offer.
    return (f'<div itemscope itemtype="http://schema.org/Product"><h1 itemprop="name">{title}</h1>'
            '<div itemprop="offers" itemscope itemtype="http://schema.org/Offer">'
            '<div itemprop="seller" itemscope itemtype="http://schema.org/Organization">'
            '<span itemprop="name">NOTESCOINSHOBBY</span></div>'
            f"<strong class='primaryPrice'><span><meta itemprop='price' content='{amount}'>{amount}</span>"
            f"<span content='{currency}' itemprop='priceCurrency'>US$</span></strong>"
            f"<meta content='{url}' itemprop='url'>"
            '<div itemprop="shippingDetails" itemscope itemtype="https://schema.org/OfferShippingDetails">'
            '<div itemprop="shippingRate" itemscope itemtype="https://schema.org/MonetaryAmount">'
            '<meta itemprop="value" content="14.99"><meta itemprop="currency" content="USD">'
            '</div></div><button>Add to cart</button></div></div>')


def jsonld(products):
    return '<script type="application/ld+json">' + json.dumps(products) + '</script>'


def product(amount, url=URL, currency='USD'):
    return {'@type': 'Product', 'name': TITLE, 'url': url,
            'offers': {'@type': 'Offer', 'price': amount, 'priceCurrency': currency}}


def candidate(**kw):
    return dict(dict(title=TITLE, country='Japan', issuer='Allied Military Command',
                     listing_url=URL, price='$39.99', price_usd=39.99, sale_type='fixed',
                     grade_numeric=65, pick_number='P-69b', date_1=1945, verified=True,
                     issue_year_start=1945, issue_year_end=1945,
                     issue_date_source='https://catalogue.example/issue/69b',
                     administration=dict(kind='military occupation', territory='Japan',
                         name='Allied military administration of Japan', year_start=1945,
                         year_end=1952, source='https://museum.example/occupation',
                         evidence='Test catalogue identifies this Allied Military Command issue.')), **kw)


class PriceTests(unittest.TestCase):
    def test_ma_shops_primary_offer_not_shipping_threshold(self):
        html = '<p>Regular shipping for items value up to $39.99; tracked shipping $14.99.</p>'
        html += micro(url=URL.replace('&curr=USD', ''))
        html += '<p>Worldwide regular shipping for items value up to $39.99.</p>'
        html += micro('139.99', url=URL.replace('569', '570'), title='Another banknote')
        self.assertEqual(read(URL, html), dict(amount=249.99, currency='USD', kind='product-microdata'))

    def test_shipping_and_plain_numbers_never_become_prices(self):
        for html in ('Shipping $39.99', 'Price on request; minimum order $39.99',
                     '<h1>5 Yen</h1><p>Price $39.99</p><button>Add to cart</button>',
                     jsonld({'shippingRate': {'price': '39.99', 'priceCurrency': 'USD'}})):
            self.assertIsNone(read(URL, html))
        self.assertIsNone(read(URL, jsonld({'@graph': None})))

    def test_jsonld_only_exact_product_and_offer(self):
        html = jsonld({'@type': 'ItemList', 'itemListElement': [product('39.99')]})
        html += jsonld({'@graph': [product('139.99', URL.replace('569', '570')), product('249.99')]})
        self.assertEqual(read(URL, html)['amount'], 249.99)
        self.assertIsNone(read(URL, jsonld(product('39.99', URL.replace('569', '570')))))
        wrong_offer = product('39.99')
        wrong_offer['offers']['url'] = URL.replace('569', '570')
        self.assertIsNone(read(URL, jsonld(wrong_offer)))

    def test_ambiguous_offers_and_missing_currency_stay_unknown(self):
        ambiguous = product('249.99')
        ambiguous['offers'] = [ambiguous['offers'], dict(ambiguous['offers'], price='39.99')]
        self.assertIsNone(read(URL, jsonld(ambiguous)))
        for amount, currency in (('NaN', 'USD'), ('Infinity', 'USD'), ('0', 'USD'),
                                 ('249.999', 'USD'), ('10000000', 'USD'), ('249.99', '')):
            self.assertIsNone(read(URL, micro(amount, currency)))

    def test_metadata_requires_explicit_currency_and_head(self):
        meta = '<meta content="249.99" property="product:price:amount">'
        self.assertIsNone(read(URL, '<head>' + meta + '</head>'))
        meta += '<meta content="CAD" property="product:price:currency">'
        self.assertEqual(read(URL, '<head>' + meta + '</head>')['currency'], 'CAD')
        self.assertIsNone(read(URL, '<body>' + meta + '</body>'))

    def test_other_identity_queries_stay_significant(self):
        other = 'https://dealer.example/item.php?id=569&variety=rare'
        self.assertIsNone(read(other, jsonld(product('249.99', other.replace('rare', 'common')))))

    def test_probe_and_scan_override_nonempty_wrong_price(self):
        probe = stuff._market_listing_probe(URL, PageResult(200, micro(), URL, False))
        self.assertEqual(probe['state'], 'live')
        with patch.object(stuff, '_market_fetch_page', return_value=(200, micro())):
            item = stuff._market_verify_live([candidate()], workers=1)[0]
        self.assertEqual(item['price'], '$249.99')
        self.assertEqual(item['price_usd'], 249.99)
        self.assertEqual(item['asking_price_source']['url'], URL)

    def test_unknown_ended_wrong_identity_and_auction_do_not_override(self):
        probe = stuff._market_listing_probe(URL, PageResult(200, micro(), URL, False))
        for changes, item_changes in (({'state': 'unknown'}, {}), ({'state': 'ended'}, {}),
                                      ({'title': TITLE.replace('1945', '1946')}, {}),
                                      ({}, {'sale_type': 'auction'})):
            item = candidate(**item_changes)
            self.assertFalse(stuff._market_apply_listing_price(item, dict(probe, **changes)))
            self.assertEqual(item['price'], '$39.99')

    def test_foreign_price_does_not_keep_stale_usd_amount(self):
        probe = stuff._market_listing_probe(URL, PageResult(200, micro(currency='CAD'), URL, False))
        item = candidate()
        self.assertTrue(stuff._market_apply_listing_price(item, probe))
        self.assertEqual(item['price'], 'C$249.99')
        self.assertIsNone(item['price_usd'])
        with patch.object(stuff, '_usd_rate', return_value=.75):
            self.assertTrue(stuff._market_apply_listing_price(item, probe, object()))
        self.assertEqual(item['price_usd'], 187)

    def test_missing_price_fetch_uses_primary_structured_offer(self):
        with patch.object(stuff, '_market_fetch_page', return_value=(200, micro())) as fetch:
            stuff._MARKET_LAST_URL.final = URL
            self.assertEqual(stuff._market_price_from_page(URL), '$249.99')
            fetch.assert_called_once()
        with patch.object(stuff, '_market_fetch_page', return_value=(200, 'Shipping up to $39.99')):
            self.assertIsNone(stuff._market_price_from_page(URL))


class SavedPriceTests(unittest.TestCase):
    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        self.db.execute('DELETE FROM market_scan_items')
        self.db.execute('DELETE FROM market_dismissals')
        self.db.execute('DELETE FROM banknotes')
        self.db.execute("INSERT OR IGNORE INTO market_scans(id,category,status,started_at) VALUES('prices','banknotes','done','2026-11-10')")
        self.db.commit()

    def tearDown(self):
        self.ctx.pop()

    def save(self, status='new'):
        self.db.execute("INSERT INTO market_scan_items(id,scan_id,category,status,title,listing_url,price,price_usd,payload,created_at) "
                        "VALUES('price-note','prices','banknotes',?,?,?,?,?,?, '2026-11-10')",
                        (status, TITLE, URL, '$39.99', 39.99, json.dumps(candidate())))
        self.db.commit()
        return self.db.execute("SELECT * FROM market_scan_items WHERE id='price-note'").fetchone()

    def probe(self, *args, **kw):
        return stuff._market_listing_probe(URL, PageResult(200, micro(), URL, False))

    def test_view_repairs_saved_card_and_columns_without_purchase(self):
        self.save('superseded')
        with patch.object(stuff, '_market_fetch_page', return_value=(200, micro())):
            result = stuff.app.test_client().get('/banknotes/market/price-note/listing')
        self.assertEqual(result.status_code, 302)
        saved = self.db.execute("SELECT * FROM market_scan_items WHERE id='price-note'").fetchone()
        self.assertEqual(saved['price'], '$249.99')
        self.assertEqual(saved['price_usd'], 249.99)
        self.assertEqual(json.loads(saved['payload'])['price'], '$249.99')
        self.assertEqual(saved['status'], 'superseded')
        self.assertEqual(self.db.execute('SELECT count(*) FROM banknotes').fetchone()[0], 0)

    def test_paid_and_dismissed_history_not_rewritten(self):
        for status in ('ordered', 'dismissed'):
            self.db.execute('DELETE FROM market_scan_items')
            row = self.save(status)
            item = candidate()
            with patch.object(stuff, '_market_fetch_page', return_value=(200, micro())):
                stuff._market_action_problem(self.db, row, item, already_paid=status == 'ordered')
            saved = self.db.execute("SELECT * FROM market_scan_items WHERE id='price-note'").fetchone()
            self.assertEqual(saved['price'], '$39.99')
            self.assertEqual(saved['status'], status)

    def test_concurrent_delete_wins_over_price_refresh(self):
        row = self.save()
        def fetch(*args, **kw):
            stuff.market_runtime.dismiss_listing(self.db, 'banknotes', URL)
            return 200, micro()
        with patch.object(stuff, '_market_fetch_page', side_effect=fetch):
            stuff._market_action_problem(self.db, row, candidate())
        saved = self.db.execute("SELECT * FROM market_scan_items WHERE id='price-note'").fetchone()
        self.assertEqual(saved['status'], 'dismissed')
        self.assertEqual(saved['price'], '$39.99')

    def test_buy_files_the_verified_price_with_cents(self):
        self.save()
        with patch.object(stuff, '_market_fetch_page', return_value=(200, micro())), \
                patch.object(stuff, '_market_store_images', return_value={}), \
                patch.object(stuff, '_market_vendor_name', return_value='NOTESCOINSHOBBY'), \
                patch.object(stuff, 'property_choices_for_category', return_value=[]), \
                patch.object(stuff, 'ensure_country_history'), \
                patch.object(stuff.market_purchase_capture, 'enqueue'):
            result = stuff.app.test_client().post('/banknotes/market/price-note/buy', json={'location': 'Home'})
        self.assertEqual(result.status_code, 200, result.get_json())
        note = self.db.execute('SELECT * FROM banknotes WHERE id=?', (result.get_json()['record_id'],)).fetchone()
        self.assertEqual(note['price'], '$249.99')
        self.assertEqual(note['status'], 'Ordered')


if __name__ == '__main__':
    unittest.main()
