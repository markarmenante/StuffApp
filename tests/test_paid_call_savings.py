"""Paid-call savings through the shared enrichment layer, end to end in the app.

Every provider is stubbed: no network, no paid call. Covers the explicit
lookup replay (watch/art), photo-side content caching (conclusive only),
the state-name and era-map failure backoffs, the country-history year index,
bounded vision images, model-alias caching and the owner usage report."""
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
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-paid-calls-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY', 'ENRICHMENT_REPLAY_SECONDS'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER', 'MARKET_LABEL_WORKER'):
    os.environ[name] = '0'

from PIL import Image

import app as stuff
import banknote_photo_sides
import enrichment


class FakeHTTP:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return json.dumps(self.payload).encode()


def anthropic_reply(payload, stop='end_turn'):
    return SimpleNamespace(stop_reason=stop, content=[SimpleNamespace(type='text', text=json.dumps(payload))],
                           usage=SimpleNamespace(input_tokens=900, output_tokens=200))


WATCH_SPECS = {key: None for key in stuff.WATCH_SPECS_RESPONSE_SCHEMA['required']}
WATCH_SPECS.update(metal='Steel', case_diameter=38.0, sources='synthetic catalogue page')


class PaidCallSavingsTests(unittest.TestCase):
    def setUp(self):
        enrichment.reset()
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        for table in ('watches', 'art', 'banknotes', 'ai_result_cache', 'ai_generation_failures',
                      'country_eras', 'country_state_names', 'country_history_jobs', 'era_supplements'):
            self.db.execute('DELETE FROM ' + table)
        self.db.commit()
        stuff._generated_country_eras(force=True)
        stuff._generated_state_names(force=True)
        stuff._COUNTRY_HISTORY_INFLIGHT.clear()
        stuff._STATE_NAMES_INFLIGHT.clear()
        stuff._ERA_SUPPLEMENT_INFLIGHT.clear()
        self.client = stuff.app.test_client()

    def tearDown(self):
        self.db.rollback()
        self.ctx.pop()
        enrichment.reset()

    # ── explicit lookups ───────────────────────────────────────────────
    def add_watch(self, ident='w1', reference='1300.3'):
        self.db.execute("INSERT INTO watches (id, brand, model, reference) VALUES (?, 'F.P. Journe', 'Chronometre Bleu', ?)",
                        (ident, reference))
        self.db.commit()

    def test_repeated_identical_watch_lookup_makes_one_paid_call(self):
        """A lookup re-clicked after Cloudflare's 100 s cap returns the stored answer."""
        self.add_watch()
        answer = {'choices': [{'message': {'content': json.dumps(WATCH_SPECS)}}],
                  'citations': ['https://example.org/journe'], 'usage': {'prompt_tokens': 800, 'completion_tokens': 300}}
        with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'synthetic'}), \
                patch('urllib.request.urlopen', return_value=FakeHTTP(answer)) as provider:
            first = self.client.post('/watches/w1/lookup')
            second = self.client.post('/watches/w1/lookup')
        self.assertEqual(first.status_code, 200, first.get_json())
        self.assertEqual(second.status_code, 200, second.get_json())
        self.assertEqual(provider.call_count, 1, 'the identical second lookup must not be billed')
        strip = lambda data: {k: v for k, v in data.items() if k != 'specs_searched_at'}
        self.assertEqual(strip(first.get_json()), strip(second.get_json()))
        self.assertEqual(first.get_json()['filled'], {'case_diameter': 38.0, 'metal': 'Steel'})
        usage = enrichment.usage_snapshot()['watch-specs']
        self.assertEqual((usage['calls'], usage['replayed']), (1, 1))

    def test_changed_watch_or_failed_lookup_asks_again(self):
        self.add_watch()
        answer = {'choices': [{'message': {'content': json.dumps(WATCH_SPECS)}}]}
        with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'synthetic'}), \
                patch('urllib.request.urlopen', return_value=FakeHTTP(answer)) as provider:
            self.client.post('/watches/w1/lookup')
            self.db.execute("UPDATE watches SET reference='1300.3 Bleu' WHERE id='w1'")
            self.db.commit()
            self.client.post('/watches/w1/lookup')
        self.assertEqual(provider.call_count, 2, 'a changed record is a new request')

        import urllib.error
        rejected = urllib.error.HTTPError('u', 400, 'bad', {}, io.BytesIO(b'bad schema'))
        with patch.dict(os.environ, {'PERPLEXITY_API_KEY': 'synthetic'}), \
                patch('urllib.request.urlopen', side_effect=[rejected, FakeHTTP(answer)]) as provider:
            self.add_watch('w2', 'Resonance')
            self.assertEqual(self.client.post('/watches/w2/lookup').status_code, 503)
            self.assertEqual(self.client.post('/watches/w2/lookup').status_code, 200)
        self.assertEqual(provider.call_count, 2, 'a failed lookup is never replayed')

    def test_repeated_identical_art_lookup_uses_one_anthropic_call(self):
        self.db.execute("INSERT INTO art (id, artist, title, year, medium) VALUES ('a1', 'Agnes Martin', 'Untitled #5', 1998, 'Acrylic')")
        self.db.commit()
        client = MagicMock()
        client.messages.create.return_value = anthropic_reply(
            {'artist_notes': 'Painter of grids.', 'object_notes': 'A late work.'})
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic'}), \
                patch('anthropic.Anthropic', return_value=client), \
                patch.object(stuff, 'anthropic_lookup_model', return_value='fixture-model'):
            art = self.db.execute("SELECT * FROM art WHERE id='a1'").fetchone()
            first = stuff.fetch_art_lookup(art)
            second = stuff.fetch_art_lookup(art)
            request = client.messages.create.call_args.kwargs
        self.assertEqual(client.messages.create.call_count, 1)
        self.assertEqual(first, second)
        self.assertNotIn('replay_kind', request, 'the replay hook never reaches the provider')
        self.assertEqual(enrichment.usage_snapshot()['art-lookup']['replayed'], 1)

    # ── photo sides ────────────────────────────────────────────────────
    def photos(self, *colors):
        out = []
        for index, color in enumerate(colors):
            name = f'sides-{color}-{index}.jpg'
            Image.new('RGB', (300, 150), color).save(os.path.join(stuff.UPLOAD_FOLDER, name))
            out.append(dict(id=f'photo-{index}', filename=name, gallery=True))
        return out

    @staticmethod
    def decision(confidence='high'):
        return dict(photos=[dict(id='photo-0', side='front', confidence=confidence, complete_note=True, same_note=True,
                                 reason='portrait side'),
                            dict(id='photo-1', side='back', confidence=confidence, complete_note=True, same_note=True,
                                 reason='vignette side')],
                    front='photo-0', back='photo-1', pair_verified=True, pair_reason='opposite designs')

    def test_conclusive_photo_sides_are_classified_once_uncertain_ones_again(self):
        client = MagicMock()
        client.messages.create.return_value = anthropic_reply(self.decision())
        photos = self.photos('red', 'blue')
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic'}), \
                patch('anthropic.Anthropic', return_value=client), \
                patch.object(stuff, 'anthropic_lookup_model', return_value='fixture-model'):
            first = stuff._classify_banknote_listing_photos(photos)
            enrichment.reset()   # survives a restart: the cache is in the database
            second = stuff._classify_banknote_listing_photos([dict(p) for p in photos])
            self.assertEqual(client.messages.create.call_count, 1)
            self.assertEqual(first, second)
            result = banknote_photo_sides.select(
                [dict(filename=p['filename']) for p in photos], stuff.UPLOAD_FOLDER,
                stuff._classify_banknote_listing_photos)
            self.assertEqual(set(result['images']), {'image_1', 'image_2'})

            client.messages.create.reset_mock()
            client.messages.create.return_value = anthropic_reply(self.decision('medium'))
            uncertain = self.photos('green', 'yellow')
            stuff._classify_banknote_listing_photos(uncertain)
            stuff._classify_banknote_listing_photos(uncertain)
        self.assertEqual(client.messages.create.call_count, 2, '"run Check again" re-asks for uncertain sides')

    def test_conclusive_predicate_rejects_partial_decisions(self):
        photos = [dict(id='photo-0', gallery=True), dict(id='photo-1', gallery=True), dict(id='photo-2', gallery=False)]
        good = self.decision()
        good['photos'].append(dict(id='photo-2', side='front', confidence='high', complete_note=True, same_note=True,
                                   reason='saved reference'))
        self.assertTrue(banknote_photo_sides.conclusive(good, photos))
        for change in (dict(back=None), dict(front='photo-2'), dict(pair_verified=False), dict(back='photo-0')):
            self.assertFalse(banknote_photo_sides.conclusive(dict(good, **change), photos), change)
        missing = dict(good, photos=good['photos'][:2])
        self.assertFalse(banknote_photo_sides.conclusive(missing, photos))
        stranger = json.loads(json.dumps(good))
        stranger['photos'][2]['same_note'] = False
        self.assertFalse(banknote_photo_sides.conclusive(stranger, photos))

    # ── background generations triggered by page views ─────────────────
    def wait_for(self, inflight):
        deadline = time.time() + 5
        while inflight and time.time() < deadline:
            time.sleep(0.02)

    def test_failed_state_names_wait_out_a_backoff_instead_of_billing_every_view(self):
        self.db.execute("INSERT INTO banknotes (id, cat_id, country, date_1, status) VALUES ('n1', 'B-1', 'Synthetic Atoll', 1950, 'Own')")
        self.db.commit()
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic'}), \
                patch.object(stuff, 'generate_state_names', side_effect=RuntimeError('unusable response: 14 eras')) as names, \
                patch.object(stuff, 'generate_country_eras', side_effect=RuntimeError('no JSON in response')):
            for _ in range(3):
                self.assertEqual(self.client.get('/banknotes').status_code, 200)
                self.wait_for(stuff._STATE_NAMES_INFLIGHT)
            self.assertEqual(names.call_count, 1, 'list views no longer re-bill a failing generation')
            stuff._backfill_country_histories()      # a reboot respects it too
            self.assertEqual(names.call_count, 1)
            stuff.ensure_state_names('Synthetic Atoll', force=True)   # explicit Retry
            self.wait_for(stuff._STATE_NAMES_INFLIGHT)
            self.assertEqual(names.call_count, 2)
        row = self.db.execute("SELECT failures FROM ai_generation_failures WHERE job_key LIKE 'state-names:%'").fetchone()
        self.assertEqual(row['failures'], 1, 'a forced retry starts a fresh backoff')

    def test_failed_era_drawing_is_not_recommissioned_by_every_map_view(self):
        query = {'year': 1941, 'lat': 37.98, 'lng': 23.72, 'polity': 'Occupied Greece', 'place': 'Athens'}
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic'}), \
                patch.object(stuff, 'generate_era_supplement', side_effect=RuntimeError('drawing does not cover the pin')) as draw:
            first = self.client.get('/api/era-supplements', query_string=query).get_json()
            self.wait_for(stuff._ERA_SUPPLEMENT_INFLIGHT)
            views = [self.client.get('/api/era-supplements', query_string=query).get_json() for _ in range(3)]
        self.assertTrue(first['pending'])
        self.assertEqual([view['pending'] for view in views], [False] * 3)
        self.assertEqual(draw.call_count, 1)

    # ── country-history year index ─────────────────────────────────────
    def brute_force_years(self, key):
        years = set()
        for row in self.db.execute('SELECT country, issuer, series, date_1, date_1_text FROM banknotes WHERE country IS NOT NULL'):
            country = stuff.banknote_catalog.collection_country(*(row[f] for f in ('country', 'date_1', 'issuer', 'series')))
            if (stuff._country_key(country) or stuff._country_slug(country)) == key:
                year = stuff._note_year(row)
                if year and 1 <= year <= stuff.datetime.utcnow().year:
                    years.add(year)
        return sorted(years)

    def test_year_index_matches_the_full_scan_and_tracks_commits(self):
        notes = [('France', 1792, None), ('Ceylon', 1950, None), ('Germany', 1923, 'Notgeld'),
                 ('Synthetic Atoll', 1955, None), ('China (Manchukuo)', 1938, None), ('France', None, '1793')]
        for index, (country, year, series) in enumerate(notes):
            self.db.execute('INSERT INTO banknotes (id, cat_id, country, date_1, series) VALUES (?, ?, ?, ?, ?)',
                            (f'y{index}', f'B-{index}', country, year, series))
        self.db.commit()
        keys = {stuff._country_key(c) or stuff._country_slug(c) for c, _, _ in notes}
        for key in keys:
            self.assertEqual(stuff._country_history_years(key), self.brute_force_years(key), key)
        with patch.object(stuff, '_country_key', wraps=stuff._country_key) as classify:
            for key in keys:
                stuff._country_history_years(key)
        self.assertEqual(classify.call_count, 0, 'unchanged data is not rescanned')
        other = sqlite3.connect(stuff.DATABASE)
        other.execute("INSERT INTO banknotes (id, cat_id, country, date_1) VALUES ('y9', 'B-9', 'France', 1800)")
        other.commit()
        other.close()
        self.assertIn(1800, stuff._country_history_years('france'))
        self.assertEqual(stuff._country_history_years('france'), self.brute_force_years('france'))

    # ── vision images, model aliases, usage report ─────────────────────
    def test_vision_images_are_bounded_and_small_ones_untouched(self):
        big, small = 'vision-big.jpg', 'vision-small.jpg'
        Image.new('RGB', (4032, 3024), 'navy').save(os.path.join(stuff.UPLOAD_FOLDER, big), quality=95)
        Image.new('RGB', (900, 400), 'tan').save(os.path.join(stuff.UPLOAD_FOLDER, small))
        images = stuff._load_vision_images([(big, 'front'), (small, 'back')])
        with Image.open(io.BytesIO(base64.b64decode(images[0]['data']))) as sent:
            self.assertEqual(sent.size, (1568, 1176))
        self.assertEqual(images[0]['media_type'], 'image/jpeg')
        with open(os.path.join(stuff.UPLOAD_FOLDER, small), 'rb') as source:
            self.assertEqual(base64.b64decode(images[1]['data']), source.read())

    def test_model_alias_is_resolved_once(self):
        models = {'data': [{'id': 'claude-sonnet-fixture', 'display_name': 'Claude Sonnet'}]}
        with patch('urllib.request.urlopen', return_value=FakeHTTP(models)) as api:
            first = stuff.resolve_anthropic_lookup_model('synthetic', 'auto-sonnet')
            second = stuff.resolve_anthropic_lookup_model('synthetic', 'auto-sonnet')
        self.assertEqual((first, second, api.call_count), ('claude-sonnet-fixture',) * 2 + (1,))
        with patch('urllib.request.urlopen', side_effect=OSError('offline')):
            self.assertEqual(stuff.resolve_anthropic_lookup_model('other-key', 'auto-haiku'), 'claude-haiku-4-5-20251001')
        with patch('urllib.request.urlopen', return_value=FakeHTTP({'data': [{'id': 'claude-haiku-new'}]})) as api:
            self.assertEqual(stuff.resolve_anthropic_lookup_model('other-key', 'auto-haiku'), 'claude-haiku-new')
        self.assertEqual(api.call_count, 1, 'a fallback answer is never cached')

    def test_owner_usage_report(self):
        enrichment.record_call('coin-specs', 'anthropic', 'm', anthropic_reply({}))
        report = self.client.get('/admin/ai-usage')
        self.assertEqual(report.status_code, 200)
        data = report.get_json()
        rows = {row['kind']: row for row in data['kinds']}
        self.assertEqual(rows['coin-specs']['calls'], 1)
        self.assertIn('banknote-check', rows)
        self.assertEqual(data['replay_seconds'], enrichment.REPLAY_TTL)
        self.assertEqual(report.headers['Cache-Control'], 'private, no-store')


if __name__ == '__main__':
    unittest.main(verbosity=1)
