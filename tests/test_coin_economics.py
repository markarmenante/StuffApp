"""Coin wage and metal comparisons, verified fineness, and read/write boundaries."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.update(DATA_DIR=tempfile.mkdtemp(prefix='coin-economics-test-'), COIN_ECONOMICS_REFRESH='0',
                  BANKNOTE_ECONOMICS_REFRESH='0', EBAY_SYNC_WORKER='0', BANKNOTE_IMPORT_WORKER='0',
                  ORIGINAL_LISTING_WORKER='0')
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)
import coin_economics as e
import precious_metals as p
with patch('threading.Thread.start'):
    import app as stuff

NOW = datetime(2026, 11, 9, 3, 10, tzinfo=timezone.utc)
COIN = dict(region='Attica', mint='Athens', authority='Athens', denomination='Tetradrachm',
            date_1=-454, date_1_text='454 BC', date_2=-404, date_2_text='404 BC',
            metal='AR Silver', weight=17.15, price=9999, notes='Synthetic collector notes')
INPUTS = dict(quotes={'XAU':dict(price=4000, updated_at=NOW.isoformat()),
                     'XAG':dict(price=50, updated_at=NOW.isoformat())},
              cpi={'USA':dict(values={'2025':967.5}, current=dict(value=1001.3, period='2026', estimated=True),
                              source_url='https://example.org/public-cpi')})


class CoinEconomicsTests(unittest.TestCase):
    def test_period_wage_analogy_and_independent_metal_ceiling(self):
        before = json.dumps((COIN, INPUTS), sort_keys=True)
        result = e.calculate(COIN, INPUTS, NOW)
        self.assertEqual(result['wage_days'], 4)
        self.assertEqual(result['wage_display'], '≈ $743.17')
        self.assertIn('assumed 8-hour', result['wage_method'])
        self.assertIn('period proxy', result['wage_basis'])
        self.assertIn('not a measured wage', result['wage_basis'])
        self.assertIn('2026 (estimate)', result['data_dates'][0])
        self.assertAlmostEqual(result['metal_value'], 17.15 / 31.1034768 * 50)
        self.assertEqual(result['metal_label'], 'Pure-silver ceiling · USD')
        self.assertTrue(result['metal_display'].startswith('≤'))
        self.assertEqual(json.dumps((COIN, INPUTS), sort_keys=True), before)
        self.assertEqual(e.calculate(dict(COIN, price=1), INPUTS, NOW), result)

    def test_wage_and_fineness_match_exact_type_and_consistent_dates(self):
        for change in (dict(region='Macedonia'), dict(mint='Alexandria'), dict(authority='Alexander'),
                       dict(denomination='Drachm'), dict(metal='AV Gold'), dict(date_1=-134),
                       dict(date_2=-300), dict(date_1=-550, date_1_text='550 BC'),
                       dict(date_1_text='454 BC / 453 BC'), dict(date_1_text=''),
                       dict(date_1=-390, date_1_text='390 BC')):
            if change == dict(date_1_text=''):
                self.assertEqual(e.calculate(dict(COIN, **change), INPUTS, NOW)['wage_days'], 4)
                continue
            with self.subTest(change=change):
                record = dict(COIN, **change)
                self.assertIsNone(e.calculate(record, INPUTS, NOW)['wage_days'])
                self.assertIsNone(e.researched_fineness(record))
        result = e.calculate(COIN, dict(INPUTS, cpi={}), NOW)
        self.assertEqual(result['wage_days'], 4)
        self.assertIsNone(result['wage_usd'])

    def test_gold_and_silver_units_purity_and_conflicts(self):
        for metal, symbol in (('AV', 'XAU'), ('Gold', 'XAU'), ('AR Silver', 'XAG')):
            record = dict(COIN, metal=metal, weight='17.15 g')
            result = e.calculate(record, INPUTS, NOW)
            self.assertAlmostEqual(result['metal_value'], 17.15 / 31.1034768 * INPUTS['quotes'][symbol]['price'])
        for metal in ('AV Silver', 'AR Gold', 'Gold plated', 'EL Electrum', 'BL Billon', 'AE Bronze', 'AR 22k'):
            self.assertIsNone(e.calculate(dict(COIN, metal=metal), INPUTS, NOW)['metal_value'], metal)
        for weight in (None, 0, -1, 'NaN', 'Infinity', '17.15 oz', '17.15 AV', True):
            self.assertIsNone(e.calculate(dict(COIN, weight=weight), INPUTS, NOW)['metal_value'])
        record = dict(COIN, metal='AV Gold 22k')
        self.assertAlmostEqual(e.calculate(record, INPUTS, NOW)['metal_value'], 17.15 * 22 / 24 / 31.1034768 * 4000)

    def test_recorded_estimate_provenance_and_identity_must_remain_consistent(self):
        record = dict(COIN, **e.researched_fineness(COIN))
        result = e.calculate(record, INPUTS, NOW)
        self.assertAlmostEqual(result['metal_value'], 17.15 * .99 / 31.1034768 * 50)
        self.assertIn('Published type estimate; specimen unassayed', result['metal_basis'])
        self.assertIn(e.ATHENS_FINENESS_URL, [source['url'] for source in result['sources']])
        self.assertIsNone(e.calculate(dict(record, authority='Other authority'), INPUTS, NOW)['metal_value'])
        self.assertIsNone(e.calculate(dict(record, fineness_source=''), INPUTS, NOW)['metal_value'])
        self.assertIsNone(e.calculate(dict(record, fineness=1.1), INPUTS, NOW)['metal_value'])
        self.assertIsNotNone(e.calculate(dict(record, weight=16), INPUTS, NOW)['metal_value'])

    def test_quote_date_and_unavailable_inputs_are_visible(self):
        data = deepcopy(INPUTS)
        data['quotes']['XAG']['updated_at'] = (NOW - timedelta(days=3)).isoformat()
        result = e.calculate(COIN, data, NOW)
        self.assertIn('Stale', result['quote_status'])
        self.assertIn('2026-11-06', result['data_dates'][-1])
        self.assertIsNotNone(result['metal_value'])
        for quote in ({}, dict(price=50, updated_at='garbage'), dict(price=float('nan'), updated_at=NOW.isoformat()),
                      dict(price=50, updated_at=(NOW + timedelta(hours=1)).isoformat())):
            self.assertIsNone(e.calculate(COIN, dict(INPUTS, quotes={'XAG':quote}), NOW)['metal_value'])

    def test_public_quote_parser_and_partial_failure_retain_original_timestamp(self):
        valid = dict(symbol='XAU', currency='USD', exchangeRate=1, price=4000, updatedAt=NOW.isoformat())
        self.assertEqual(p.parse_quote(valid, 'XAU', NOW)['price'], 4000)
        for change in (dict(symbol='XAG'), dict(currency='EUR'), dict(exchangeRate=1.2), dict(exchangeRate=True),
                       dict(price=-1), dict(price=True), dict(price=float('inf')),
                       dict(updatedAt='2026-11-09'), dict(updatedAt=(NOW + timedelta(hours=1)).isoformat())):
            with self.assertRaises(ValueError):
                p.parse_quote(dict(valid, **change), 'XAU', NOW)
        folder = tempfile.mkdtemp()
        original = dict(version=1, quotes=deepcopy(INPUTS['quotes']))
        Path(folder, 'precious-metals.json').write_text(json.dumps(original))
        def provider(symbol):
            if symbol == 'XAG':
                raise OSError('Synthetic public quote outage')
            return dict(symbol=symbol, currency='USD', exchangeRate=1, price=4100, updatedAt=datetime.now(timezone.utc).isoformat())
        with patch.object(p, '_read', side_effect=provider):
            p.refresh(folder)
        actual = p.snapshot(folder)
        self.assertEqual(actual['quotes']['XAG'], original['quotes']['XAG'])
        self.assertEqual(actual['quotes']['XAU']['price'], 4100)

    def test_ten_minute_cache_does_not_start_duplicate_background_fetches(self):
        folder = tempfile.mkdtemp()
        Path(folder, 'precious-metals.json').write_text(json.dumps(dict(version=1, quotes={},
            checked_at=datetime.now(timezone.utc).isoformat())))
        with patch.dict(os.environ, COIN_ECONOMICS_REFRESH='1'), patch.object(p.threading.Thread, 'start') as start:
            p.request_refresh(folder)
            start.assert_not_called()
            Path(folder, 'precious-metals.json').unlink()
            with patch.object(p, 'snapshot', return_value=dict(version=1, quotes={})), patch.object(p, '_attempts', {}):
                p.request_refresh(folder); p.request_refresh(folder)
            self.assertEqual(start.call_count, 1)
        p._active.discard(str(Path(folder).resolve()))


class CoinRouteTests(unittest.TestCase):
    def setUp(self):
        self.context = stuff.app.app_context(); self.context.push()
        self.db = stuff.get_db()
        values = dict(COIN, id='synthetic-economics-coin', status='Own', image_1='synthetic.jpg')
        self.db.execute('INSERT OR REPLACE INTO coins (' + ','.join(values) + ') VALUES ('
                        + ','.join('?' for _ in values) + ')', list(values.values()))
        self.db.commit()
        self.client = stuff.app.test_client()

    def tearDown(self):
        self.context.pop()

    def row(self):
        return dict(self.db.execute("SELECT * FROM coins WHERE id='synthetic-economics-coin'").fetchone())

    def post(self, suffix, data):
        return self.client.post('/coins/synthetic-economics-coin/' + suffix, json=data)

    def test_view_and_quote_endpoint_never_modify_collection(self):
        before = self.row()
        page = self.client.get('/coins/synthetic-economics-coin').get_data(as_text=True)
        self.assertLess(page.index('id="coinEconomics"'), page.index('<div class="section-bar">Description</div>'))
        result = self.client.get('/coins/synthetic-economics-coin/economics')
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.get_json()['wage_display'], '≈ $743.17')
        self.assertEqual(before, self.row())
        self.assertEqual(self.client.get('/coins/missing/economics').status_code, 404)
        with patch.object(stuff, '_user_can_see_row', return_value=False):
            self.assertEqual(self.client.get('/coins/synthetic-economics-coin/economics').status_code, 404)

    def test_research_preview_then_explicit_save_persists_only_provenance_fields(self):
        before = self.row()
        response = self.post('fineness', dict(action='research'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(before, self.row())
        proposal = response.get_json()['proposal']
        response = self.post('fineness', dict(action='save', percent=99, basis='estimate', source=e.ATHENS_FINENESS_URL,
                                           expected_identity=proposal['fineness_identity'], expected_fineness=e.fineness_state(before)))
        self.assertEqual(response.status_code, 200)
        after = self.row()
        for field in before:
            if field not in (*e.FINENESS_FIELDS, 'fineness_identity', 'updated_at'):
                self.assertEqual(before[field], after[field], field)
        self.assertEqual(after['fineness'], .99)
        self.assertEqual(after['fineness_basis'], 'estimate')
        self.assertEqual(self.post('fineness', dict(action='research')).status_code, 409)

    def test_stale_identity_and_invalid_fineness_never_write(self):
        before = self.row()
        base = dict(action='save', percent=99, basis='estimate', source=e.ATHENS_FINENESS_URL,
                    expected_identity=e.identity(before), expected_fineness=e.fineness_state(before))
        for changes in (dict(percent=0), dict(percent=101), dict(percent='NaN'), dict(percent=True),
                        dict(source='javascript:alert(1)'), dict(source='https://user:pass@example.org'),
                        dict(basis='known'), dict(expected_identity='old identity'), dict(expected_fineness='stale values')):
            with self.subTest(changes=changes):
                self.assertIn(self.post('fineness', dict(base, **changes)).status_code, (400, 409))
                self.assertEqual(before, self.row())

    def test_check_proposes_without_writing_then_applies_verified_tuple_once(self):
        before = self.row()
        with patch.object(stuff, 'fetch_coin_specs', return_value={'fineness':.5, 'sources':'Synthetic unrelated model suggestion'}):
            response = self.post('lookup-specs', {})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json()['filled']['fineness'], .99)
        self.assertIn('specimen unassayed', response.get_json()['sources'])
        self.assertIsNone(self.row()['fineness'])
        self.assertEqual(self.post('apply-lookup-specs', {'updates':{'fineness':.5}}).get_json()['updated'], 0)
        applied = self.post('apply-lookup-specs', {'updates':{'fineness':.99}})
        self.assertEqual(applied.status_code, 200)
        self.assertEqual(self.row()['fineness'], .99)
        self.assertEqual(self.row()['fineness_source'], e.ATHENS_FINENESS_URL)
        after = self.row()
        self.assertEqual(self.post('apply-lookup-specs', {'updates':{'fineness':.99}}).get_json()['updated'], 0)
        self.assertEqual(after, self.row())
        for field in ('price', 'weight', 'metal', 'notes', 'image_1', 'status'):
            self.assertEqual(before[field], after[field])

    def test_changed_type_cannot_apply_old_research(self):
        self.db.execute("UPDATE coins SET authority='Other authority' WHERE id='synthetic-economics-coin'")
        self.db.commit()
        before = self.row()
        self.assertEqual(self.post('apply-lookup-specs', {'updates':{'fineness':.99}}).get_json()['updated'], 0)
        self.assertEqual(self.post('fineness', {'action':'research'}).status_code, 422)
        self.assertEqual(before, self.row())

    def test_apply_rejects_category_reader_and_hidden_coin_without_any_write(self):
        self.db.execute("INSERT OR REPLACE INTO users (id, email, display_name, role, categories) "
                        "VALUES ('synthetic-coin-reader', 'coin-reader@example.org', 'Synthetic reader', 'viewer', 'coins')")
        self.db.commit()
        before = self.row()
        url = '/coins/synthetic-economics-coin/apply-lookup-specs'
        updates = {'updates': {'fineness': .99, 'weight': 18}}
        headers = {'Cf-Access-Authenticated-User-Email': 'coin-reader@example.org'}
        # This user can view this category, so a category-only gate would not
        # protect either the newly researched purity or the other selected edits.
        self.assertEqual(self.client.get('/coins/synthetic-economics-coin/economics', headers=headers).status_code, 200)
        self.assertEqual(self.client.post(url, json=updates, headers=headers).status_code, 403)
        self.assertEqual(before, self.row())
        with patch.object(stuff, '_user_can_see_row', return_value=False):
            self.assertEqual(self.client.post(url, json=updates).status_code, 404)
        self.assertEqual(before, self.row())
        self.assertEqual(self.client.post('/coins/missing/apply-lookup-specs', json=updates).status_code, 404)

    def test_apply_rechecks_row_visibility_under_fineness_write_lock(self):
        before = self.row()
        with patch.object(stuff, '_user_can_see_row', side_effect=[True, False]):
            response = self.post('apply-lookup-specs', {'updates': {'fineness': .99}})
        self.assertEqual(response.status_code, 404)
        self.assertFalse(self.db.in_transaction)
        self.assertEqual(before, self.row())


if __name__ == '__main__':
    unittest.main()
