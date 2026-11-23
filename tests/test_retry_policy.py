"""Shared retry policy at the app's paid call sites (2026-11-23).

Only failures that cannot have been billed or are safe to repeat are retried
(a connection failure without a response, 429, 529, 500/502/503). A timeout is
never repeated: it makes exactly one paid call. Each call site keeps its own
exhaustion result, and every Anthropic client is built with SDK retries off.
Providers are stubbed: no network and no paid calls."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-retry-policy-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER', 'MARKET_LABEL_WORKER'):
    os.environ[name] = '0'

import anthropic
try:
    import httpx2 as httpx
except ImportError:
    import httpx

import app as stuff
import enrichment

REQUEST = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')


class Row(dict):
    """A sparse record: unset columns read as None, like a fresh database row."""
    def __missing__(self, key):
        return None


def timeout():
    return anthropic.APITimeoutError(request=REQUEST)


def status(code, cls=anthropic.APIStatusError):
    return cls('provider said no', body=None, response=httpx.Response(code, request=REQUEST))


def reply(payload):
    return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=json.dumps(payload))],
                           usage=SimpleNamespace(input_tokens=10, output_tokens=5),
                           model_dump=lambda: {'content': [{'type': 'text', 'text': json.dumps(payload)}]})


class RetryPolicyAtCallSites(unittest.TestCase):
    def setUp(self):
        enrichment.reset()
        self.client = MagicMock()
        patches = [patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic'}),
                   patch('anthropic.Anthropic', return_value=self.client),
                   patch.object(stuff, 'anthropic_lookup_model', return_value='fixture-model'),
                   patch('time.sleep')]
        started = [p.start() for p in patches]
        self.factory, self.sleep = started[1], started[3]
        for p in patches:
            self.addCleanup(p.stop)
        self.addCleanup(enrichment.reset)

    def outcomes(self, *items):
        self.client.messages.create.side_effect = list(items)

    def calls(self):
        return self.client.messages.create.call_count

    def assert_sdk_retries_off(self):
        self.assertTrue(self.factory.call_args_list)
        for call in self.factory.call_args_list:
            self.assertEqual(call.kwargs.get('max_retries'), 0, call)

    def art(self):
        return {'artist': 'Agnes Martin', 'title': 'Untitled #5', 'year': 1998, 'medium': 'Acrylic', 'vendor': ''}

    def test_art_lookup_timeout_is_one_paid_call_with_the_old_message(self):
        self.outcomes(timeout(), reply({'artist_notes': 'late'}))
        with self.assertRaisesRegex(RuntimeError, '^Lookup failed after retries: '):
            stuff.fetch_art_lookup(self.art())
        self.assertEqual(self.calls(), 1)
        self.sleep.assert_not_called()
        self.assert_sdk_retries_off()

    def test_art_lookup_overload_then_success(self):
        self.outcomes(status(529), status(503), reply({'artist_notes': 'Painter of grids.', 'object_notes': None}))
        self.assertEqual(stuff.fetch_art_lookup(self.art())['artist_notes'], 'Painter of grids.')
        self.assertEqual(self.calls(), 3)

    def test_coin_specs_rejected_request_is_not_repeated_and_raises_unchanged(self):
        self.outcomes(status(400, anthropic.BadRequestError))
        with self.assertRaises(anthropic.BadRequestError):
            stuff.fetch_coin_specs(Row(description='Syracuse tetradrachm'), provider='anthropic')
        self.assertEqual(self.calls(), 1)

    def test_coin_specs_timeout_gets_the_friendly_message(self):
        self.outcomes(timeout(), reply({}))
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            stuff.fetch_coin_specs(Row(description='Syracuse tetradrachm'), provider='anthropic')
        self.assertEqual(self.calls(), 1)

    def test_watch_value_rate_limits_exhaust_with_the_old_message(self):
        watch = {'brand': 'F.P. Journe', 'model': 'Chronometre Bleu', 'reference': '', 'year': None,
                 'metal': 'Tantalum', 'description': '', 'dial_color': None, 'edition': None, 'calibre': None,
                 'case_diameter': None, 'price': None}
        self.outcomes(*[status(429, anthropic.RateLimitError)] * 3)
        with self.assertRaisesRegex(RuntimeError, '^Rate limited after retries: '):
            stuff.fetch_watch_valuation_anthropic(watch)
        self.assertEqual(self.calls(), 3)
        self.assertEqual(self.sleep.call_count, 2)
        self.assertTrue(all(c.args[0] <= 30 for c in self.sleep.call_args_list), 'backoff is bounded')

    def test_serial_scan_timeout_is_one_paid_call(self):
        self.outcomes(timeout())
        image = {'label': 'front', 'data': 'aGk=', 'media_type': 'image/jpeg'}
        with patch.object(stuff, '_load_vision_images', return_value=[image]), \
                patch.object(stuff, '_banknote_vision_source', side_effect=lambda name, db=None: name):
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                stuff.scan_banknote_serial({'image_1': 'front.jpg', 'image_2': None})
        self.assertEqual(self.calls(), 1)

    def test_pedigree_research_never_repeats_a_timeout(self):
        self.outcomes(timeout(), reply({}))
        with self.assertRaisesRegex(RuntimeError, 'timed out'):
            stuff._pedigree_model_call('provenance', 'coins', 'Trace this coin.', [])
        self.assertEqual(self.calls(), 1)
        self.assert_sdk_retries_off()

    def test_background_generation_keeps_two_app_retries_but_not_for_timeouts(self):
        self.outcomes(status(529), reply({'title': 'Atlantis', 'spellings': [], 'eras': [], 'sources': []}))
        try:
            stuff.generate_country_eras('Atlantis')
        except Exception:
            pass   # the fixture history is not a valid answer; only the call count matters
        self.assertEqual(self.calls(), 2)
        self.client.messages.create.reset_mock()
        self.outcomes(timeout(), reply({}))
        with self.assertRaises(anthropic.APITimeoutError):
            stuff.generate_country_eras('Atlantis')
        self.assertEqual(self.calls(), 1)
        self.assert_sdk_retries_off()


if __name__ == '__main__':
    unittest.main(verbosity=1)
