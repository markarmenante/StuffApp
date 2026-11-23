"""Paid lookups are owner-only, like banknote Check and Market Scan (2026-11-23).

A viewer who can see a category gets the same 403 as banknote Check from the
watch, coin, art, recording, serial-scan and pedigree lookup routes; no
provider is called and no record changes. The pages render those controls
disabled (or not at all) for the viewer. No network and no paid calls."""
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-owner-lookups-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER', 'MARKET_LABEL_WORKER'):
    os.environ[name] = '0'

import app as stuff

VIEWER = {'Cf-Access-Authenticated-User-Email': 'synthetic-viewer@example.org'}
PAID_ROUTES = [
    '/watches/w1/lookup', '/watches/w1/value', '/watches/revalue',
    '/coins/c1/lookup-specs', '/coins/c1/history', '/coins/c1/context', '/coins/c1/context-perplexity',
    '/art/a1/lookup', '/recordings/r1/fetch-notes', '/banknotes/b1/scan-serial',
    '/coins/c1/pedigree/provenance/research', '/banknotes/b1/pedigree/rarity/research',
]
TABLES = {'watches': "INSERT INTO watches (id, brand, model) VALUES ('w1', 'F.P. Journe', 'Resonance')",
          'coins': "INSERT INTO coins (id, description, region, authority) VALUES ('c1', 'Syracuse tetradrachm', 'Sicily', 'Syracuse')",
          'art': "INSERT INTO art (id, artist, title) VALUES ('a1', 'Agnes Martin', 'Untitled #5')",
          'recordings': "INSERT INTO recordings (id, artist, title) VALUES ('r1', 'Bill Evans', 'Sunday at the Village Vanguard')",
          'banknotes': "INSERT INTO banknotes (id, cat_id, country, denomination, image_1) VALUES ('b1', 'B-1', 'France', '10 Livres', 'front.jpg')"}


class OwnerOnlyPaidLookups(unittest.TestCase):
    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        for table, insert in TABLES.items():
            self.db.execute(f'DELETE FROM {table}')
            self.db.execute(insert)
        self.db.execute("INSERT OR REPLACE INTO users (id, email, display_name, role, categories) VALUES "
                        "('synthetic-viewer', 'synthetic-viewer@example.org', 'Synthetic viewer', 'viewer', "
                        "'watches,coins,art,recordings,banknotes')")
        self.db.commit()
        self.client = stuff.app.test_client()
        self.provider = MagicMock()
        self.provider.messages.create.side_effect = AssertionError('a paid call was attempted')
        patches = [patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'synthetic', 'PERPLEXITY_API_KEY': 'synthetic'}),
                   patch('anthropic.Anthropic', return_value=self.provider),
                   patch('urllib.request.urlopen', side_effect=AssertionError('a paid call was attempted'))]
        self.opener = [p.start() for p in patches][2]
        for p in patches:
            self.addCleanup(p.stop)

    def tearDown(self):
        self.db.rollback()
        self.ctx.pop()

    def snapshot(self):
        return {table: [dict(row) for row in self.db.execute(f'SELECT * FROM {table} ORDER BY id')]
                for table in TABLES}

    def test_viewer_gets_the_same_403_as_banknote_check_and_nothing_is_billed_or_written(self):
        before = self.snapshot()
        reference = self.client.post('/banknotes/b1/lookup-specs', headers=VIEWER)
        self.assertEqual(reference.status_code, 403)
        for url in PAID_ROUTES:
            with self.subTest(url=url):
                response = self.client.post(url, headers=VIEWER, json={'field': 'region', 'brand': 'Journe'})
                self.assertEqual(response.status_code, 403)
                self.assertEqual(response.content_type, reference.content_type)
                self.assertEqual(response.get_data(), reference.get_data())
        self.provider.messages.create.assert_not_called()
        self.opener.assert_not_called()
        self.assertEqual(before, self.snapshot())

    def test_owner_still_reaches_every_route(self):
        stubs = {'fetch_watch_specs': {}, 'fetch_watch_valuation': {'value': None, 'results': '', 'fallback': False},
                 'fetch_coin_specs': {}, 'fetch_coin_history': {'markdown': 'x'}, 'fetch_art_lookup': {},
                 'fetch_recording_notes': {'notes': ''}, 'scan_banknote_serial': {'serial_number': None},
                 '_start_coin_context_job': ('started', 202), '_run_revaluation': None, '_run_pedigree_job': None}
        with patch.multiple(stuff, **{name: MagicMock(return_value=value) for name, value in stubs.items()}):
            for url in PAID_ROUTES:
                with self.subTest(url=url):
                    response = self.client.post(url, json={'field': 'region', 'brand': 'Journe'})
                    self.assertNotEqual(response.status_code, 403, response.get_data(as_text=True)[:200])

    def test_pages_disable_paid_controls_for_viewers_only(self):
        watch_viewer = self.client.get('/watches/w1', headers=VIEWER).get_data(as_text=True)
        watch_owner = self.client.get('/watches/w1').get_data(as_text=True)
        viewer_button = watch_viewer.split('id="valueBtn"', 1)[1].split('>', 1)[0]
        owner_button = watch_owner.split('id="valueBtn"', 1)[1].split('>', 1)[0]
        self.assertIn('disabled', viewer_button)
        self.assertNotIn('data-url', viewer_button)
        self.assertNotIn('disabled', owner_button)
        self.assertIn('/watches/w1/value', owner_button)
        self.assertNotIn('data-url="/watches/w1/lookup"', watch_viewer)
        self.assertIn('data-url="/watches/w1/lookup"', watch_owner)

        coin_viewer = self.client.get('/coins/c1', headers=VIEWER).get_data(as_text=True)
        coin_owner = self.client.get('/coins/c1').get_data(as_text=True)
        for ident in ('pdgProvResearch', 'pdgRarResearch'):
            viewer_tag = coin_viewer.split(f'id="{ident}"', 1)[1].split('>', 1)[0]
            owner_tag = coin_owner.split(f'id="{ident}"', 1)[1].split('>', 1)[0]
            self.assertIn('disabled', viewer_tag, ident)
            self.assertNotIn('disabled', owner_tag, ident)
        self.assertNotIn('coin-lookup-btn coin-check-all-btn', coin_viewer)
        self.assertIn('coin-lookup-btn coin-check-all-btn', coin_owner)


if __name__ == '__main__':
    unittest.main(verbosity=1)
