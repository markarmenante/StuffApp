"""Evidence boundaries and concise estimates, using synthetic data only."""
import copy
import importlib
import json
import os
import sys
import tempfile
import threading
import types
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import market_valuation as valuation

TODAY = date(2026, 10, 25)
LISTING = 'https://www.ebay.com/itm/123456789012'


def estimate(**changes):
    value = dict(low=150, high=200, currency='USD', as_of='2026-10-25',
                 confidence='medium', grade='PMG 64 EPQ; same catalogue type and grade.',
                 sources=[dict(kind='sold', url='https://currency.ha.com/itm/fixture/90001',
                               title='Heritage fixture sale, realized with buyer premium',
                               date='2026-04-12', amount=178.50, currency='USD', grade='PMG 64 EPQ')])
    value.update(changes)
    return value


class ValuationTests(unittest.TestCase):
    def display(self, value, **item):
        return valuation.display(dict(item, valuation=value, listing_url=LISTING), today=TODAY)

    def test_terse_range_separate_from_listing_price_and_source_amount(self):
        shown = self.display(estimate(), price='$599.89')
        self.assertEqual(shown['label'], '$150–$200')
        self.assertEqual(shown['evidence'][0]['amount_label'], '$178.50')
        self.assertEqual(shown['evidence'][0]['date'], '2026-04-12')

    def test_legacy_notes_and_all_observed_source_types_do_not_invent_estimates(self):
        for sources in ([], ['watched'], ['sponsored'], ['watched', 'sponsored']):
            item = dict(price='$599.89', fair='$600–$900; seller reports a scarce grade.',
                        discovery_sources=sources, listing_url=LISTING)
            before = copy.deepcopy(item)
            self.assertEqual(valuation.display(item, today=TODAY)['label'], 'No estimate')
            self.assertEqual(item, before)

    def test_invalid_ranges_are_unavailable(self):
        for low, high in [(0, 100), (-1, 100), (200, 150), (150, 150),
                          (True, 200), ('150', 200), (float('nan'), 200),
                          (150, float('inf')), (.00001, 200), (1, 10**20)]:
            with self.subTest(low=low, high=high):
                self.assertEqual(self.display(estimate(low=low, high=high))['label'], 'No estimate')

    def test_invalid_structures_and_unknown_currency_are_unavailable(self):
        for value in (None, '150–200', [], {}, estimate(currency=[]),
                      estimate(currency='ZZZ'), estimate(confidence=[]), estimate(sources={})):
            self.assertEqual(self.display(value)['label'], 'No estimate')

    def test_exact_cents_and_non_usd_currency_survive(self):
        value = estimate(low=149.95, high=199.99, currency='EUR')
        value['sources'][0].update(currency='EUR', amount=178.51)
        self.assertEqual(self.display(value)['label'], '€149.95–€199.99')
        self.assertEqual(self.display(value)['evidence'][0]['amount_label'], '€178.51')
        value.update(low=1200, high=1500, currency='GBP')
        value['sources'][0]['currency'] = 'GBP'
        self.assertEqual(self.display(value)['label'], '£1,200–£1,500')

    def test_missing_grade_source_amount_or_date_is_unavailable(self):
        for field in ('grade', 'sources'):
            value = estimate(); value.pop(field)
            self.assertEqual(self.display(value)['label'], 'No estimate')
        for field in ('grade', 'date', 'amount', 'title', 'currency'):
            value = estimate(); value['sources'][0].pop(field)
            self.assertEqual(self.display(value)['label'], 'No estimate', field)

    def test_future_malformed_and_expired_estimate_dates_are_unavailable(self):
        for date_text in ('2026-10-26', '2025-01-01', '2026-02-30', '2026-10', ''):
            self.assertEqual(self.display(estimate(as_of=date_text))['label'], 'No estimate')
        for date_text in ('2026-10-26', '2026-02-30', '2026-04', ''):
            value = estimate(); value['sources'][0]['date'] = date_text
            self.assertEqual(self.display(value)['label'], 'No estimate')
        value = estimate(as_of='2026-04-01')
        self.assertEqual(self.display(value)['label'], 'No estimate', 'source is newer than estimate')

    def test_candidate_own_price_cannot_be_evidence_across_ebay_url_variants(self):
        for url in (LISTING, LISTING + '?_trksid=tracking',
                    'https://www.ebay.co.uk/itm/Fixture-title/123456789012#details',
                    'https://m.ebay.com/itm/123456789012',
                    'https://www.ebay.com.sg/itm/123456789012',
                    'https://m.ebay.com.hk/itm/Fixture-title/123456789012'):
            value = estimate(); value['sources'][0]['url'] = url
            self.assertEqual(self.display(value)['label'], 'No estimate')

    def test_mobile_and_international_duplicates_cannot_inflate_confidence(self):
        value = estimate(confidence='high')
        value['sources'] = [dict(value['sources'][0], url=url) for url in (
            'https://www.ebay.com/itm/234567890123',
            'https://m.ebay.com/itm/234567890123',
            'https://www.ebay.com.sg/itm/234567890123')]
        shown = self.display(value)
        self.assertEqual(len(shown['evidence']), 1)
        self.assertEqual(shown['confidence'], 'medium')

    def test_asking_census_and_sponsored_claims_are_not_valuation_sources(self):
        for kind in ('asking', 'sponsored', 'census', 'seller_estimate', '', None):
            value = estimate(); value['sources'][0]['kind'] = kind
            self.assertEqual(self.display(value)['label'], 'No estimate')

    def test_malicious_nonpublic_search_and_homepage_urls_are_rejected(self):
        for url in ('javascript:alert(1)', 'data:text/html,hi', 'file:///etc/passwd',
                    'https://trusted:password@ha.com/lot/1', 'https://127.0.0.1/lot/1',
                    'http://localhost/lot/1', 'http://metadata.google.internal/lot/1',
                    'https://ha.com/lot/1\nX-Test:hi', 'https://ha.com\\evil/lot/1',
                    'https://ha.com:123/lot/1', 'https://ha.com/',
                    'https://google.com/search?q=banknote', 'https://ha.com/search/notes',
                    'https://www.ebay.com/sch/i.html?_nkw=note'):
            value = estimate(); value['sources'][0]['url'] = url
            self.assertEqual(self.display(value)['label'], 'No estimate', url)

    def test_specialist_auction_source_is_not_excluded_by_domain_whitelist(self):
        value = estimate()
        value['sources'][0].update(url='https://auctions.dnw.co.uk/auctions/lot.php?lot_uid=8123',
                                   title='Specialist auction fixture, hammer excluding premium')
        self.assertEqual(self.display(value)['label'], '$150–$200')

    def test_no_implicit_currency_conversion(self):
        value = estimate(); value['sources'][0]['currency'] = 'EUR'
        self.assertEqual(self.display(value)['label'], 'No estimate')

    def test_confidence_is_limited_by_evidence(self):
        self.assertEqual(self.display(estimate(confidence='high'))['confidence'], 'medium')
        value = estimate(confidence='high'); value['sources'][0]['date'] = '2001-05-01'
        self.assertEqual(self.display(value)['confidence'], 'low')
        value = estimate(confidence='high')
        value['sources'][0].update(kind='price_guide', url='https://www.pmgnotes.com/priceguide/fixture')
        self.assertEqual(self.display(value)['confidence'], 'low')
        value = estimate(confidence='high')
        value['sources'] = [dict(value['sources'][0], url=f'https://currency.ha.com/itm/fixture/{n}')
                            for n in range(3)]
        self.assertEqual(self.display(value)['confidence'], 'high')

    def test_sources_are_bounded_deduplicated_and_inputs_preserved(self):
        value = estimate()
        source = value['sources'][0]
        value['sources'] = [source, dict(source, url=source['url'] + '?utm_source=duplicate')]
        value['sources'] += [dict(source, url=f'https://currency.ha.com/itm/fixture/{n}')
                             for n in range(20)]
        before = copy.deepcopy(value)
        self.assertEqual(len(self.display(value)['evidence']), 6)
        self.assertEqual(value, before)


class AppValuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = tempfile.TemporaryDirectory(prefix='stuff-market-valuation-')
        dotenv = types.SimpleNamespace(load_dotenv=lambda **_: None)
        with patch.dict(os.environ, {'DATA_DIR': cls.data.name, 'ANTHROPIC_API_KEY': ''}), \
                patch.dict(sys.modules, {'dotenv': dotenv}), \
                patch.object(threading.Thread, 'start', lambda *_: None):
            cls.stuff = importlib.import_module('app')

    @classmethod
    def tearDownClass(cls):
        cls.data.cleanup()

    def test_main_prompt_requests_evidence_for_banknotes_only(self):
        text = self.stuff._market_scan_prompt('banknotes', 'fixture', 'fixture', '', '')
        self.assertIn('"valuation":', text)
        self.assertIn('"kind": "sold"|"price_guide"', text)
        self.assertIn('return valuation:null', text)
        self.assertIn("candidate's own listing", text)
        coins = self.stuff._market_scan_prompt('coins', 'fixture', 'fixture', '', '')
        self.assertNotIn('"valuation":', coins)
        self.assertNotIn('VALUE ESTIMATES:', coins)

    def test_normalization_preserves_asking_cents_and_estimate_independently(self):
        raw = dict(title='India 1937 10 Rupees PMG64 EPQ', country='India', year=1937,
                   issuer='Government of India', pick_number='P-18', grade_numeric=64,
                   grading_authority='PMG', grade='Choice UNC', designation='EPQ',
                   price='$599.89', listing_url='https://dealer.example/item/valuation',
                   valuation=estimate(as_of=date.today().isoformat()))
        with self.stuff.app.app_context(), \
                patch.object(self.stuff, '_market_fetch_page', side_effect=AssertionError('network forbidden')), \
                patch.object(self.stuff, '_fetch_usd_rate', side_effect=AssertionError('FX forbidden')):
            db = self.stuff.get_db()
            item = self.stuff._market_normalize_item(db, 'banknotes', raw)
            self.assertIsNotNone(item)
            self.assertEqual(item['price'], '$599.89')
            self.assertEqual(item['price_usd'], 599.89)
            self.assertEqual(item['valuation']['low'], 150)
            saved = json.loads(json.dumps(item))
            rendered = self.stuff.app.jinja_env.filters['market_valuation'](saved)
            self.assertEqual(rendered['label'], '$150–$200')
            invalid = dict(raw, valuation=estimate(low=-1))
            self.assertIsNone(self.stuff._market_normalize_item(db, 'banknotes', invalid)['valuation'])
            self.assertEqual(self.stuff._market_normalize_item(db, 'banknotes', invalid)['price'], '$599.89')

    def test_cached_filter_does_not_research_or_mutate_legacy_payload(self):
        saved = dict(price='$200', fair='$150–$200 estimated in old free text',
                     listing_url=LISTING, discovery_sources=['watched', 'sponsored'])
        before = copy.deepcopy(saved)
        with patch.object(self.stuff, '_market_fetch_page', side_effect=AssertionError('network forbidden')):
            self.assertEqual(self.stuff.app.jinja_env.filters['market_valuation'](saved)['label'], 'No estimate')
        self.assertEqual(saved, before)

    def test_observed_source_shaping_discards_unresearched_model_valuation(self):
        card = dict(title='India 1937 10 Rupees PMG64 EPQ', listing_url=LISTING,
                    listing_text='India 1937 10 Rupees PMG64 EPQ',
                    sources=['watched', 'sponsored'], price='$599.89', image_url='', live_state='live')
        model_item = dict(listing_url=LISTING, valuation=estimate())
        client = types.SimpleNamespace(close=lambda: None)
        feed = self.stuff.market_ebay_feed
        with patch.object(feed, 'queue', return_value='fixture'), \
                patch.object(feed, 'get_result', return_value=([card], {})), \
                patch('anthropic.Anthropic', return_value=client), \
                patch.object(self.stuff, '_market_resolve_model', return_value='fixture'), \
                patch.object(self.stuff.market_runtime, 'model_call', return_value=None), \
                patch.object(self.stuff, '_market_model_json', return_value={'items': [model_item]}):
            items, _, _ = self.stuff._market_ebay_source('fixture', ('', '', '', '', ''))
        self.assertEqual(len(items), 1)
        self.assertIsNone(items[0]['valuation'])
        self.assertEqual(items[0]['price'], '$599.89')


if __name__ == '__main__':
    unittest.main()
