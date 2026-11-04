"""Temporary provider errors recover inside Check's original time budget."""
import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-provider-recovery-')
for key in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY'):
    os.environ.pop(key, None)
import anthropic
try:
    import httpx2 as httpx
except ImportError:
    import httpx
import app as stuff


def provider_error(status, headers=None):
    response = httpx.Response(status, headers=headers or {},
        request=httpx.Request('POST', 'https://api.anthropic.com/v1/messages'))
    return anthropic.APIStatusError('private response body', response=response,
        body={'private': 'purchase details and credentials must not be logged'})


def response(data, stop='end_turn'):
    content = [SimpleNamespace(type='text', text=json.dumps(data))]
    return SimpleNamespace(stop_reason=stop, content=content,
        model_dump=lambda: {'content': [{'type': 'text', 'text': json.dumps(data)}]})


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.now = 100.0
        self.sleep = Mock(side_effect=self.advance)
        self.client = Mock()
        self.clock = patch.object(stuff.time, 'monotonic', side_effect=lambda: self.now)
        self.clock.start()
        self.addCleanup(self.clock.stop)
        sleeper = patch.object(stuff.time, 'sleep', self.sleep)
        sleeper.start()
        self.addCleanup(sleeper.stop)

    def advance(self, seconds):
        self.now += seconds

    def call(self, deadline=135):
        return stuff._banknote_provider_create(self.client, stage='photo-sides',
            deadline=deadline, model='configured-model', messages=[], max_tokens=5000)

    def test_temporary_status_recovers_once_with_remaining_timeout(self):
        for status in (408, 409, 429, 500, 503, 529):
            with self.subTest(status=status):
                self.now = 100
                self.client.reset_mock()
                self.sleep.reset_mock()
                expected = object()
                self.client.messages.create.side_effect = [provider_error(status), expected]
                self.assertIs(self.call(), expected)
                self.assertEqual(self.client.messages.create.call_count, 2)
                self.sleep.assert_called_once()
                self.assertLess(self.client.messages.create.call_args.kwargs['timeout'], 35)

    def test_connection_error_retries_but_second_failure_stops(self):
        error = anthropic.APIConnectionError(request=httpx.Request('POST', 'https://api.anthropic.com'))
        self.client.messages.create.side_effect = error
        with self.assertRaises(anthropic.APIConnectionError):
            self.call()
        self.assertEqual(self.client.messages.create.call_count, 2)

    def test_auth_invalid_request_and_unknown_failure_do_not_retry(self):
        for error in (provider_error(400), provider_error(401), provider_error(403),
                      provider_error(404), ValueError('private invalid output')):
            with self.subTest(error=type(error).__name__):
                self.client.reset_mock()
                self.sleep.reset_mock()
                self.client.messages.create.side_effect = error
                with self.assertRaises(type(error)):
                    self.call()
                self.assertEqual(self.client.messages.create.call_count, 1)
                self.sleep.assert_not_called()

    def test_retry_after_is_honored_without_extending_deadline(self):
        self.client.messages.create.side_effect = [provider_error(429, {'retry-after': '3'}), 'ok']
        self.assertEqual(self.call(), 'ok')
        self.sleep.assert_called_once_with(3)
        self.assertEqual(self.client.messages.create.call_args.kwargs['timeout'], 32)

    def test_long_or_invalid_retry_delay_and_provider_veto_do_not_retry(self):
        for headers in ({'retry-after': '120'}, {'retry-after': 'NaN'},
                        {'retry-after': 'invalid'}, {'x-should-retry': 'false'}):
            with self.subTest(headers=headers):
                self.client.reset_mock()
                self.sleep.reset_mock()
                self.client.messages.create.side_effect = provider_error(429, headers)
                with self.assertRaises(anthropic.APIStatusError):
                    self.call()
                self.assertEqual(self.client.messages.create.call_count, 1)
                self.sleep.assert_not_called()

    def test_slow_first_failure_does_not_restart_full_budget(self):
        def slow_failure(**kwargs):
            self.advance(34)
            raise provider_error(503)
        self.client.messages.create.side_effect = slow_failure
        with self.assertRaises(anthropic.APIStatusError):
            self.call()
        self.assertEqual(self.client.messages.create.call_count, 1)
        self.sleep.assert_not_called()

    def test_expired_deadline_never_calls_provider(self):
        with self.assertRaises(TimeoutError):
            self.call(deadline=99)
        self.client.messages.create.assert_not_called()

    def test_diagnostics_keep_stage_status_and_type_not_private_content(self):
        self.client.messages.create.side_effect = provider_error(401)
        with self.assertLogs(stuff.app.logger, level='WARNING') as logged:
            with self.assertRaises(anthropic.APIStatusError):
                self.call()
        text = '\n'.join(logged.output)
        self.assertIn('photo-sides', text)
        self.assertIn('401', text)
        self.assertIn('APIStatusError', text)
        for value in ('private response', 'purchase details', 'credentials', 'https://'):
            self.assertNotIn(value, text)

    def test_wrapped_import_exception_logs_original_cause_without_private_message(self):
        try:
            try:
                raise provider_error(503)
            except Exception as cause:
                raise RuntimeError('private purchase text') from cause
        except RuntimeError as error:
            with self.assertLogs(stuff.app.logger, level='WARNING') as logged:
                stuff._log_banknote_check_error('import-identification', error)
        text = '\n'.join(logged.output)
        self.assertIn('APIStatusError', text)
        self.assertIn('503', text)
        self.assertNotIn('private', text)

    def test_recovered_selection_preserves_manual_crop_and_all_originals(self):
        import hashlib
        from PIL import Image
        with tempfile.TemporaryDirectory() as folder:
            assets = []
            for index, color in enumerate(('red', 'blue')):
                path = Path(folder) / f'original-{index}.png'
                Image.new('RGB', (100, 60), color).save(path)
                assets.append(dict(filename=path.name, sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
            decision = dict(photos=[dict(id=f'photo-{i}', side=side, confidence='high',
                complete_note=True, same_note=True, reason='Opposite complete designs')
                for i, side in enumerate(('front', 'back'))], front='photo-0', back='photo-1',
                pair_verified=True, pair_reason='Same exact note')
            self.client.messages.create.side_effect = [provider_error(529), response(decision)]
            with patch('anthropic.Anthropic', return_value=self.client), \
                    patch.object(stuff, 'UPLOAD_FOLDER', folder), \
                    patch.object(stuff, '_require_anthropic_key', return_value='test-key'), \
                    patch.object(stuff, 'anthropic_lookup_model', return_value='configured-model'):
                selected = stuff.banknote_photo_sides.select(assets, folder,
                    stuff._classify_banknote_listing_photos, existing={'image_1': 'manual-crop.jpg'},
                    resolve_original=lambda _: 'original-0.png')
            self.assertEqual(set(selected['images']), {'image_2'})
            self.assertEqual(selected['images']['image_2']['filename'], 'original-1.png')
            self.assertFalse(selected['warnings'])
            for asset in assets:
                self.assertEqual(hashlib.sha256((Path(folder) / asset['filename']).read_bytes()).hexdigest(), asset['sha256'])

    def test_real_classifier_retries_transport_but_not_invalid_decision(self):
        for outputs, attempts in (([provider_error(529), response({'photos': []})], 2),
                                  ([response({'photos': []}, 'max_tokens')], 1)):
            with self.subTest(attempts=attempts), \
                    patch('anthropic.Anthropic', return_value=self.client) as factory, \
                    patch.object(stuff, '_require_anthropic_key', return_value='test-key'), \
                    patch.object(stuff, 'anthropic_lookup_model', return_value='configured-model'), \
                    patch.object(stuff.banknote_photo_sides, 'vision_content', return_value=[]):
                self.client.reset_mock()
                self.client.messages.create.side_effect = outputs
                if attempts == 2:
                    self.assertEqual(stuff._classify_banknote_listing_photos([]), {'photos': []})
                else:
                    with self.assertRaises(ValueError):
                        stuff._classify_banknote_listing_photos([])
                self.assertEqual(self.client.messages.create.call_count, attempts)
                self.assertEqual(factory.call_args.kwargs['max_retries'], 0)

    def test_specs_retry_and_search_continuation_share_original_budget(self):
        note = dict(description='Isle of Man 5 Pounds 2015')
        def respond(**kwargs):
            self.advance(2)
            if self.client.messages.create.call_count == 1:
                raise provider_error(503)
            return response({}, 'pause_turn' if self.client.messages.create.call_count == 2 else 'end_turn')
        self.client.messages.create.side_effect = respond
        with patch('anthropic.Anthropic', return_value=self.client), \
                patch.object(stuff, '_require_anthropic_key', return_value='test-key'), \
                patch.object(stuff, 'anthropic_lookup_model', return_value='configured-model'), \
                patch.object(stuff, '_banknote_check_vision_images', return_value=[]):
            stuff.fetch_banknote_specs(note)
        self.assertEqual(self.client.messages.create.call_count, 3)
        timeouts = [call.kwargs['timeout'] for call in self.client.messages.create.call_args_list]
        self.assertEqual(timeouts, sorted(timeouts, reverse=True))
        self.assertEqual(timeouts[0], 75)
        self.assertLess(timeouts[-1], 72)


if __name__ == '__main__':
    unittest.main()
