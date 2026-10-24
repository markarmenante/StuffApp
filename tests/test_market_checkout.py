"""Pure checkout handoffs must stay bound to an actual fixed-price listing."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from market_checkout import checkout_url


ITEM = 'https://www.ebay.com/itm/287619084102'
CHECKOUT = ('https://www.ebay.com/bin/ctb?item=287619084102'
            '&quantity=1&fromPage=4429486&rev=0&fb=1')


def probe(**overrides):
    return dict(state='live', challenged=False, final=ITEM,
                identity_text='1918 $1 banknote\nUS $1,650.00\nBuy It Now', **overrides)


class MarketCheckoutTests(unittest.TestCase):
    def test_verified_fixed_price_uses_observed_exact_order_page(self):
        self.assertEqual(checkout_url(ITEM, probe()), CHECKOUT)
        second = 'https://www.ebay.com/itm/147612392914'
        evidence = dict(probe(), final=second)
        self.assertEqual(checkout_url(second, evidence), CHECKOUT.replace('287619084102', '147612392914'))

    def test_exact_item_slug_tracking_and_default_https_port_keep_identity(self):
        for url in ('https://ebay.com/itm/Banknote/287619084102?hash=abc',
                    'https://www.ebay.com:443/itm/287619084102/',
                    ITEM + '?utm_source=watchlist#details'):
            self.assertEqual(checkout_url(url, probe()), CHECKOUT)

    def test_bid_only_auction_and_make_offer_fall_back_to_listing(self):
        for text in ('Place bid\nCurrent bid $100\nTime left 2 days',
                     'Make offer', 'Add to cart', 'Available', ''):
            self.assertEqual(checkout_url(ITEM, dict(probe(), identity_text=text)), ITEM)

    def test_probe_requires_live_unchallenged_exact_page(self):
        for changes in ({'state':'ended'}, {'state':'unknown'}, {'challenged':True},
                        {'final':'https://www.ebay.com/itm/147612392914'},
                        {'final':'https://www.ebay.com/sch/i.html'}, {'final':None}):
            self.assertEqual(checkout_url(ITEM, dict(probe(), **changes)), ITEM)

    def test_model_summary_or_card_title_is_not_checkout_evidence(self):
        for evidence in (None, {}, {'state':'live'},
                         dict(probe(), identity_text='', live_evidence='Buy It Now', title='Buy now')):
            self.assertEqual(checkout_url(ITEM, evidence), ITEM)

    def test_dealers_and_unverified_regional_formats_keep_exact_ordering_page(self):
        for url in ('https://sanchezcurrency.com/product/fr-0018-1869-1/',
                    'https://www.ebay.co.uk/itm/287619084102',
                    'https://dealer.example/lot?id=287619084102'):
            self.assertEqual(checkout_url(url, dict(probe(), final=url)), url)

    def test_malformed_or_other_host_cannot_become_ebay_checkout(self):
        for url in ('https://www.ebay.com.evil.test/itm/287619084102',
                    'https://user@www.ebay.com/itm/287619084102',
                    'https://www.ebay.com:444/itm/287619084102',
                    'https://www.ebay.com:notaport/itm/287619084102',
                    'http://www.ebay.com/itm/287619084102',
                    'https://www.ebay.com/itm/123',
                    'https://www.ebay.com/itm/287619084102/other',
                    'https://www.ebay.com/sch/i.html?item=287619084102',
                    'https://www.ebay.com/itm/287619084102%2f147612392914'):
            self.assertEqual(checkout_url(url, dict(probe(), final=url)), url)


if __name__ == '__main__':
    unittest.main()
