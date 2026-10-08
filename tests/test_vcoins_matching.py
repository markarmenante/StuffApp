import copy
import unittest

from vcoins_matching import match_orders


class VCoinsMatchingTests(unittest.TestCase):
    def setUp(self):
        self.coin = dict(id='coin-1', vendor='Example Coins', purchase_date='2022-02-04',
                         marketplace=None, price=3750, weight=None, size=None)
        self.order = dict(url='https://www.vcoins.com/en/MyAccount/ShowOrder.aspx?IdOrder=123',
                          columns=['2/4/2022', '45-123', 'Example Coins'],
                          items=[dict(quantity=1, title='Kroton AR Stater', price='US$ 3,750.00', listing='listing')])

    def matches(self, coins=None, orders=None, invoices=(), listings=()):
        return match_orders(coins or [self.coin], orders or [self.order], invoices, listings)['matches']

    def test_price_is_enough_with_vendor_and_date(self):
        self.assertEqual(len(self.matches()), 1)

    def test_weight_is_enough_with_vendor_and_date(self):
        self.coin.update(price=None, weight=7.71)
        self.order['items'][0]['title'] += ' (7.71g)'
        self.assertEqual(len(self.matches()), 1)

    def test_pair_of_identity_fields_is_enough(self):
        self.coin.update(price=None, mint='Kroton', denomination='Stater')
        self.assertEqual(len(self.matches()), 1)

    def test_vendor_and_date_alone_are_not_enough(self):
        self.coin['price'] = None
        self.assertFalse(self.matches())

    def test_seven_day_boundary_is_inclusive(self):
        for date in ('2022-01-28', '2022-02-11'):
            self.coin['purchase_date'] = date
            self.assertEqual(len(self.matches()), 1)
        for date in ('2022-01-27', '2022-02-12', None, 'invalid'):
            self.coin['purchase_date'] = date
            self.assertFalse(self.matches())

    def test_vendor_is_required(self):
        for vendor in ('Other Dealer', None, ''):
            self.coin['vendor'] = vendor
            self.assertFalse(self.matches())

    def test_explicit_other_marketplace_is_preserved(self):
        for marketplace in ('Direct', 'CNG', 'eBay'):
            self.coin['marketplace'] = marketplace
            self.assertFalse(self.matches())

    def test_duplicate_coins_are_unresolved(self):
        self.assertFalse(self.matches(coins=[self.coin, dict(self.coin, id='coin-2')]))

    def test_reused_coin_across_orders_is_unresolved(self):
        other = copy.deepcopy(self.order)
        other['columns'][1] = '45-124'
        self.assertFalse(self.matches(orders=[self.order, other]))

    def test_foreign_currency_is_not_same_price(self):
        for currency in ('EUR', 'GBP', 'AUD', 'CAD', 'CHF'):
            self.order['items'][0]['price'] = currency + ' 3,750.00'
            self.assertFalse(self.matches())

    def test_conflicting_measurement_is_not_hidden_by_price(self):
        self.coin['weight'] = 8.1
        self.order['items'][0]['title'] += ' (7.71g)'
        self.assertFalse(self.matches())

    def test_short_listing_capture_does_not_hide_order_title(self):
        self.coin.update(price=None, weight=7.71)
        self.order['items'][0]['title'] += ' (7.71g)'
        self.assertEqual(len(self.matches(listings=[dict(url='listing', text='s')])), 1)

    def test_invoice_listing_sku_conflict_is_unresolved(self):
        invoices = [dict(number='45-123', items=[dict(desc='Kroton AR Stater', sku='ABC123')])]
        listings = [dict(url='listing', sku='XYZ123')]
        self.assertFalse(self.matches(invoices=invoices, listings=listings))

    def test_multi_quantity_is_not_assigned_to_one_coin(self):
        self.order['items'][0]['quantity'] = 2
        self.assertFalse(self.matches())
