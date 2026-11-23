"""Shared enrichment plumbing: fingerprints, replay, single-flight, durable
content cache, generation cooldowns, metering, vision fitting and the
Perplexity transport. No network and no paid calls."""
import base64
import io
import json
import os
import sqlite3
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY', 'ENRICHMENT_REPLAY_SECONDS'):
    os.environ.pop(name, None)

from PIL import Image

import enrichment


def text_response(text, stop='end_turn', **usage):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type='text', text=text)],
                           usage=SimpleNamespace(**usage))


class Base(unittest.TestCase):
    def setUp(self):
        enrichment.reset()
        self.path = tempfile.mktemp(suffix='.db')

        def connect():
            db = sqlite3.connect(self.path)
            db.row_factory = sqlite3.Row
            return db
        self.connect = connect
        db = connect()
        enrichment.init_schema(db)
        db.commit()
        db.close()
        enrichment.configure(connect)

    def tearDown(self):
        enrichment.configure(None)
        enrichment.reset()

    def query(self, sql):
        db = self.connect()
        try:
            return db.execute(sql).fetchall()
        finally:
            db.close()


class FingerprintTests(Base):
    def test_stable_across_key_order_and_sensitive_to_content(self):
        a = enrichment.fingerprint('coin-specs', {'model': 'm', 'messages': [{'role': 'user', 'content': 'x'}]})
        b = enrichment.fingerprint('coin-specs', {'messages': [{'content': 'x', 'role': 'user'}], 'model': 'm'})
        self.assertEqual(a, b)
        self.assertNotEqual(a, enrichment.fingerprint('coin-specs', {'model': 'm', 'messages': 'y'}))
        self.assertNotEqual(a, enrichment.fingerprint('art-lookup', {'model': 'm', 'messages': [{'role': 'user', 'content': 'x'}]}))

    def test_sdk_objects_and_bytes_are_hashable(self):
        block = MagicMock()
        block.model_dump.return_value = {'type': 'text', 'text': 'paused'}
        self.assertEqual(enrichment.fingerprint('k', [block]), enrichment.fingerprint('k', [{'type': 'text', 'text': 'paused'}]))
        self.assertIsInstance(enrichment.fingerprint('k', {'raw': b'\x00\x01'}), str)


class ReplayTests(Base):
    def test_repeated_identical_request_makes_one_paid_call(self):
        calls = []

        def paid():
            calls.append(1)
            return text_response('{"value": 1}')
        payload = {'model': 'm', 'messages': [{'role': 'user', 'content': 'same record'}]}
        first = enrichment.replay('coin-specs', payload, paid, accept=enrichment.anthropic_completed)
        second = enrichment.replay('coin-specs', dict(payload), paid, accept=enrichment.anthropic_completed)
        self.assertEqual(len(calls), 1, 'the identical second request must not pay again')
        self.assertIs(first, second)
        self.assertEqual(enrichment.usage_snapshot()['coin-specs']['replayed'], 1)

    def test_changed_request_failure_and_rejected_result_still_call(self):
        calls = []

        def paid(text='{"v": 1}', stop='end_turn'):
            calls.append(text)
            return text_response(text, stop)
        enrichment.replay('art-lookup', {'q': 'a'}, paid, accept=enrichment.anthropic_completed)
        enrichment.replay('art-lookup', {'q': 'b'}, paid, accept=enrichment.anthropic_completed)
        self.assertEqual(len(calls), 2, 'a changed record is a new request')
        # An unfinished turn is never stored.
        enrichment.replay('art-lookup', {'q': 'c'}, lambda: paid('', 'max_tokens'), accept=enrichment.anthropic_completed)
        enrichment.replay('art-lookup', {'q': 'c'}, lambda: paid('', 'max_tokens'), accept=enrichment.anthropic_completed)
        self.assertEqual(len(calls), 4)

        def failing():
            calls.append('error')
            raise RuntimeError('provider failed')
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                enrichment.replay('art-lookup', {'q': 'd'}, failing)
        self.assertEqual(calls.count('error'), 2, 'failures are never replayed')

    def test_window_expires_and_can_be_disabled(self):
        calls = []
        with patch.object(enrichment.time, 'time', return_value=1000.0):
            enrichment.replay('watch-specs', {'q': 1}, lambda: calls.append(1) or ('{}', 'x'))
        with patch.object(enrichment.time, 'time', return_value=1000.0 + enrichment.REPLAY_TTL + 1):
            enrichment.replay('watch-specs', {'q': 1}, lambda: calls.append(1) or ('{}', 'x'))
        self.assertEqual(len(calls), 2)
        with patch.dict(os.environ, {'ENRICHMENT_REPLAY_SECONDS': '0'}):
            enrichment.replay('watch-specs', {'q': 2}, lambda: calls.append(1) or 1)
            enrichment.replay('watch-specs', {'q': 2}, lambda: calls.append(1) or 1)
        self.assertEqual(len(calls), 4)


class SingleFlightTests(Base):
    def test_concurrent_identical_requests_share_one_call(self):
        started, release, calls, results = threading.Event(), threading.Event(), [], []

        def slow():
            calls.append(1)
            started.set()
            release.wait(5)
            return 'answer'
        leader = threading.Thread(target=lambda: results.append(enrichment.single_flight('k', slow, 'banknote-check')))
        leader.start()
        self.assertTrue(started.wait(5))
        followers = [threading.Thread(target=lambda: results.append(enrichment.single_flight('k', slow, 'banknote-check')))
                     for _ in range(3)]
        for thread in followers:
            thread.start()
        time.sleep(0.1)
        release.set()
        for thread in [leader] + followers:
            thread.join(5)
        self.assertEqual(calls, [1])
        self.assertEqual(results, ['answer'] * 4)
        self.assertEqual(enrichment.usage_snapshot()['banknote-check']['joined'], 3)
        # Once finished, a later request runs again (no replay here).
        enrichment.single_flight('k', lambda: calls.append(2) or 'again')
        self.assertEqual(calls, [1, 2])

    def test_errors_reach_every_waiter(self):
        started, release = threading.Event(), threading.Event()
        errors = []

        def boom():
            started.set()
            release.wait(5)
            raise ValueError('provider down')

        def run():
            try:
                enrichment.single_flight('e', boom)
            except ValueError as error:
                errors.append(str(error))
        threads = [threading.Thread(target=run)]
        threads[0].start()
        started.wait(5)
        threads.append(threading.Thread(target=run))
        threads[1].start()
        time.sleep(0.1)
        release.set()
        for thread in threads:
            thread.join(5)
        self.assertEqual(errors, ['provider down', 'provider down'])


class DurableCacheTests(Base):
    def test_accepted_results_survive_process_state_and_rejected_ones_do_not(self):
        calls = []

        def classify():
            calls.append(1)
            return {'front': 'photo-0', 'back': 'photo-1'}
        payload = {'photos': [['photo-0', 'a' * 64, True]]}
        enrichment.remember('banknote-photo-sides', payload, classify, accept=lambda d: True, ttl=3600)
        enrichment.reset()   # a restart: only the database remembers
        again = enrichment.remember('banknote-photo-sides', payload, classify, accept=lambda d: True, ttl=3600)
        self.assertEqual(calls, [1])
        self.assertEqual(again, {'front': 'photo-0', 'back': 'photo-1'})
        stored = self.query('SELECT kind FROM ai_result_cache')
        self.assertEqual([row['kind'] for row in stored], ['banknote-photo-sides'])

        other = {'photos': [['photo-0', 'b' * 64, True]]}
        enrichment.remember('banknote-photo-sides', other, classify, accept=lambda d: False, ttl=3600)
        enrichment.remember('banknote-photo-sides', other, classify, accept=lambda d: False, ttl=3600)
        self.assertEqual(len(calls), 3, 'uncertain results are asked again')

    def test_expired_entries_are_recomputed(self):
        calls = []
        now = time.time()
        with patch.object(enrichment.time, 'time', return_value=now):
            enrichment.remember('k', {'x': 1}, lambda: calls.append(1) or {'v': 1}, accept=lambda d: True, ttl=60)
            enrichment.remember('k', {'x': 1}, lambda: calls.append(1) or {'v': 1}, accept=lambda d: True, ttl=60)
        with patch.object(enrichment.time, 'time', return_value=now + 61):
            enrichment.remember('k', {'x': 1}, lambda: calls.append(1) or {'v': 1}, accept=lambda d: True, ttl=60)
        self.assertEqual(len(calls), 2)


class CooldownTests(Base):
    def test_backoff_grows_and_clears(self):
        self.assertFalse(enrichment.cooldown_active('state-names:atlantis'))
        enrichment.record_failure('state-names:atlantis', 'state-names', RuntimeError('unusable response: 14 eras'))
        self.assertTrue(enrichment.cooldown_active('state-names:atlantis'))
        row = self.query('SELECT * FROM ai_generation_failures')[0]
        self.assertEqual(row['failures'], 1)
        self.assertAlmostEqual(row['retry_after'] - row['last_failed_at'], enrichment.COOLDOWN_STEPS[0], delta=1)
        enrichment.record_failure('state-names:atlantis', 'state-names', RuntimeError('again'))
        row = self.query('SELECT * FROM ai_generation_failures')[0]
        self.assertEqual(row['failures'], 2)
        self.assertAlmostEqual(row['retry_after'] - row['last_failed_at'], enrichment.COOLDOWN_STEPS[1], delta=1)
        self.assertEqual(enrichment.failures_snapshot()[0]['job_key'], 'state-names:atlantis')
        enrichment.clear_failure('state-names:atlantis')
        self.assertFalse(enrichment.cooldown_active('state-names:atlantis'))

    def test_without_a_database_nothing_blocks(self):
        enrichment.configure(None)
        enrichment.record_failure('era-supplement:x', 'era-supplement', RuntimeError('x'))
        self.assertFalse(enrichment.cooldown_active('era-supplement:x'))


class MeteringTests(Base):
    def test_client_meters_usage_and_passes_everything_through(self):
        inner = MagicMock()
        inner.messages.create.return_value = text_response(
            'ok', input_tokens=1200, output_tokens=300, cache_read_input_tokens=0,
            cache_creation_input_tokens=0, server_tool_use=SimpleNamespace(web_search_requests=2))
        with patch('anthropic.Anthropic', return_value=inner) as factory:
            client = enrichment.anthropic_client('coin-specs', api_key='k', timeout=240.0)
            factory.assert_called_once_with(api_key='k', timeout=240.0, max_retries=0)
            client.messages.create(model='m', max_tokens=10, messages=[])
            client.close()
        inner.close.assert_called_once()
        row = enrichment.usage_snapshot()['coin-specs']
        self.assertEqual((row['calls'], row['input_tokens'], row['output_tokens'], row['web_searches']), (1, 1200, 300, 2))

    def test_errors_are_counted_and_raised(self):
        inner = MagicMock()
        inner.messages.create.side_effect = RuntimeError('529')
        client = enrichment.MeteredClient(inner, 'banknote-check')
        with self.assertRaises(RuntimeError):
            client.messages.create(model='m')
        self.assertEqual(enrichment.usage_snapshot()['banknote-check']['errors'], 1)

    def test_mock_usage_never_breaks_a_call(self):
        enrichment.record_call('x', 'anthropic', MagicMock(), MagicMock())
        self.assertEqual(enrichment.usage_snapshot()['x']['input_tokens'], 0)


try:
    import httpx2 as httpx
except ImportError:   # older SDKs
    import httpx
import anthropic
import socket

REQUEST = httpx.Request('POST', 'https://api.anthropic.com/v1/messages')


def status_error(status, headers=None):
    return anthropic.APIStatusError('provider said no', body=None,
                                    response=httpx.Response(status, headers=headers or {}, request=REQUEST))


class RetryPolicyTests(Base):
    def test_classifier_per_error_class(self):
        cases = {
            'connection refused before a response': (anthropic.APIConnectionError(request=REQUEST), True),
            'SDK timeout': (anthropic.APITimeoutError(request=REQUEST), False),
            'socket timeout': (TimeoutError('timed out'), False),
            'urllib timeout before a response': (urllib.error.URLError(socket.timeout('timed out')), False),
            'urllib connection refused': (urllib.error.URLError(ConnectionRefusedError()), True),
            'invalid output': (ValueError('bad json'), False),
        }
        for status in (429, 500, 502, 503, 529):
            cases[f'HTTP {status}'] = (status_error(status), True)
            cases[f'Perplexity HTTP {status}'] = (urllib.error.HTTPError('u', status, 'x', {}, None), True)
        for status in (400, 401, 403, 404, 408, 409, 413, 504):
            cases[f'HTTP {status}'] = (status_error(status), False)
            cases[f'Perplexity HTTP {status}'] = (urllib.error.HTTPError('u', status, 'x', {}, None), False)
        cases['provider veto'] = (status_error(529, {'x-should-retry': 'false'}), False)
        for label, (error, expected) in cases.items():
            with self.subTest(label):
                self.assertIs(enrichment.retryable(error), expected)

    def metered(self, retries, *outcomes):
        inner = MagicMock()
        inner.messages.create.side_effect = list(outcomes)
        return inner, enrichment.MeteredClient(inner, 'country-history', retries=retries)

    def test_a_timeout_makes_exactly_one_paid_call(self):
        inner, client = self.metered(2, anthropic.APITimeoutError(request=REQUEST), text_response('late'))
        with patch('time.sleep') as sleep:
            with self.assertRaises(anthropic.APITimeoutError):
                client.messages.create(model='m', max_tokens=10, messages=[])
        self.assertEqual(inner.messages.create.call_count, 1)
        sleep.assert_not_called()
        self.assertEqual(enrichment.usage_snapshot()['country-history']['calls'], 1)

    def test_unbilled_failures_retry_with_bounded_backoff(self):
        inner, client = self.metered(2, status_error(529, {'retry-after': '120'}),
                                     anthropic.APIConnectionError(request=REQUEST), text_response('ok'))
        with patch('time.sleep') as sleep:
            result = client.messages.create(model='m', max_tokens=10, messages=[])
        self.assertEqual(result.content[0].text, 'ok')
        self.assertEqual(inner.messages.create.call_count, 3)
        self.assertEqual([c.args[0] for c in sleep.call_args_list], [30.0, 20.0],
                         'Retry-After is honoured but bounded; then base * attempt')

    def test_completed_and_rejected_requests_are_not_repeated(self):
        for error in (status_error(400), status_error(401), status_error(408), status_error(504), ValueError('x')):
            with self.subTest(type(error).__name__, status=getattr(error, 'status_code', None)):
                inner, client = self.metered(2, error)
                with patch('time.sleep'):
                    with self.assertRaises(type(error)):
                        client.messages.create(model='m', max_tokens=10, messages=[])
                self.assertEqual(inner.messages.create.call_count, 1)

    def test_exhaustion_keeps_the_call_sites_result(self):
        attempts = []

        def send():
            attempts.append(1)
            raise status_error(503)
        with patch('time.sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Lookup failed after retries'):
                enrichment.call_with_retries(send, attempts=3,
                                             give_up=lambda e: RuntimeError(f'Lookup failed after retries: {e}'))
        self.assertEqual(len(attempts), 3)
        with self.assertRaises(anthropic.APITimeoutError):   # give_up may decline: original error re-raised
            enrichment.call_with_retries(lambda: (_ for _ in ()).throw(anthropic.APITimeoutError(request=REQUEST)),
                                         attempts=3, give_up=lambda e: None)

    def test_deadline_and_strict_retry_after(self):
        calls = []

        def send():
            calls.append(1)
            raise status_error(429, {'retry-after': '8'})
        with patch('time.sleep') as sleep:
            with self.assertRaises(anthropic.APIStatusError):
                enrichment.call_with_retries(send, attempts=2, base=1.0, cap=float('inf'), deadline=10.0,
                                             reserve=5, strict_retry_after=True, clock=lambda: 0.0)
        self.assertEqual((len(calls), sleep.call_count), (1, 0), '8 s wait would leave under 5 s')
        calls.clear()
        with patch('time.sleep') as sleep:
            with self.assertRaises(anthropic.APIStatusError):
                enrichment.call_with_retries(lambda: calls.append(1) or (_ for _ in ()).throw(
                    status_error(429, {'retry-after': 'soon'})), attempts=2, strict_retry_after=True)
        self.assertEqual(len(calls), 1, 'an unreadable Retry-After vetoes the strict retry')


class ModelAliasTests(Base):
    def test_alias_cache_is_per_key_and_expires(self):
        self.assertIsNone(enrichment.cached_model_alias('sonnet', 'key-a'))
        enrichment.remember_model_alias('sonnet', 'key-a', 'claude-sonnet-x')
        self.assertEqual(enrichment.cached_model_alias('sonnet', 'key-a'), 'claude-sonnet-x')
        self.assertIsNone(enrichment.cached_model_alias('sonnet', 'key-b'))
        with patch.object(enrichment.time, 'time', return_value=time.time() + enrichment.ALIAS_TTL + 5):
            self.assertIsNone(enrichment.cached_model_alias('sonnet', 'key-a'))


def encode(image, fmt):
    out = io.BytesIO()
    image.save(out, format=fmt)
    return out.getvalue()


class VisionFitTests(unittest.TestCase):
    def test_small_images_pass_through_byte_for_byte(self):
        raw = encode(Image.new('RGB', (1200, 800), 'red'), 'JPEG')
        data, media = enrichment.fit_vision_image(raw, 'image/jpeg')
        self.assertEqual(base64.b64decode(data), raw)
        self.assertEqual(media, 'image/jpeg')

    def test_large_images_are_bounded_to_the_api_edge_in_their_own_format(self):
        for fmt, media in (('JPEG', 'image/jpeg'), ('PNG', 'image/png'), ('WEBP', 'image/webp')):
            with self.subTest(fmt=fmt):
                raw = encode(Image.new('RGB', (4000, 3000), 'blue'), fmt)
                data, out_media = enrichment.fit_vision_image(raw, media)
                self.assertEqual(out_media, media)
                with Image.open(io.BytesIO(base64.b64decode(data))) as image:
                    self.assertEqual(max(image.size), 1568)
                    self.assertEqual(image.size, (1568, 1176))

    def test_unreadable_bytes_are_returned_unchanged(self):
        data, media = enrichment.fit_vision_image(b'not an image', 'image/jpeg')
        self.assertEqual(base64.b64decode(data), b'not an image')
        self.assertEqual(media, 'image/jpeg')

    def test_edge_is_configurable(self):
        raw = encode(Image.new('RGB', (3000, 1000), 'green'), 'JPEG')
        with patch.dict(os.environ, {'ANTHROPIC_VISION_MAX_EDGE': '2000'}):
            data, _ = enrichment.fit_vision_image(raw, 'image/jpeg')
        with Image.open(io.BytesIO(base64.b64decode(data))) as image:
            self.assertEqual(max(image.size), 2000)


class FakeHTTP:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


class PerplexityTransportTests(Base):
    BODY = {'model': 'sonar-pro', 'messages': [{'role': 'user', 'content': 'specs'}], 'max_tokens': 10}

    def test_success_is_metered(self):
        answer = {'choices': [{'message': {'content': ' {"metal": "Steel"} '}}],
                  'usage': {'prompt_tokens': 50, 'completion_tokens': 20}}
        with patch('urllib.request.urlopen', return_value=FakeHTTP(answer)) as opener:
            data, text = enrichment.perplexity_chat('key', self.BODY, 'watch-specs')
        self.assertEqual(text, '{"metal": "Steel"}')
        self.assertEqual(json.loads(opener.call_args.args[0].data), self.BODY)
        row = enrichment.usage_snapshot()['watch-specs']
        self.assertEqual((row['calls'], row['input_tokens'], row['output_tokens']), (1, 50, 20))

    def test_rate_limit_retries_with_unchanged_semantics(self):
        answer = {'choices': [{'message': {'content': 'ok'}}]}
        limited = urllib.error.HTTPError('u', 429, 'slow down', {'retry-after': '12'}, None)
        waits = []
        with patch('urllib.request.urlopen', side_effect=[limited, FakeHTTP(answer)]):
            _, text = enrichment.perplexity_chat('key', self.BODY, 'watch-value', sleep=waits.append)
        self.assertEqual((text, waits), ('ok', [12]))

    def test_client_errors_are_not_retried(self):
        bad = urllib.error.HTTPError('u', 400, 'bad', {}, io.BytesIO(b'schema rejected'))
        with patch('urllib.request.urlopen', side_effect=[bad]) as opener:
            with self.assertRaisesRegex(RuntimeError, 'Perplexity HTTP 400'):
                enrichment.perplexity_chat('key', self.BODY, 'watch-specs', sleep=lambda s: None)
        self.assertEqual(opener.call_count, 1)

    def test_timeouts_make_exactly_one_paid_call(self):
        for error, raised in ((urllib.error.URLError(socket.timeout('timed out')), RuntimeError),
                              (TimeoutError('The read operation timed out'), TimeoutError)):
            with self.subTest(type(error).__name__):
                answer = {'choices': [{'message': {'content': 'late'}}]}
                with patch('urllib.request.urlopen', side_effect=[error, FakeHTTP(answer)]) as opener:
                    with self.assertRaises(raised):
                        enrichment.perplexity_chat('key', self.BODY, 'watch-specs', sleep=lambda s: None)
                self.assertEqual(opener.call_count, 1)

    def test_connection_failures_and_overload_retry_then_give_up_with_the_old_message(self):
        refused = urllib.error.URLError(ConnectionRefusedError())
        busy = urllib.error.HTTPError('u', 503, 'busy', {}, None)
        waits = []
        with patch('urllib.request.urlopen', side_effect=[refused, busy, busy]) as opener:
            with self.assertRaisesRegex(RuntimeError, '^Lookup failed after retries'):
                enrichment.perplexity_chat('key', self.BODY, 'watch-specs', sleep=waits.append)
        self.assertEqual((opener.call_count, waits), (3, [10.0, 20.0]))
        gateway = urllib.error.HTTPError('u', 504, 'gateway timeout', {}, io.BytesIO(b'upstream timed out'))
        with patch('urllib.request.urlopen', side_effect=[gateway]) as opener:
            with self.assertRaisesRegex(RuntimeError, 'Perplexity HTTP 504'):
                enrichment.perplexity_chat('key', self.BODY, 'watch-specs', sleep=waits.append)
        self.assertEqual(opener.call_count, 1)


if __name__ == '__main__':
    unittest.main(verbosity=1)
