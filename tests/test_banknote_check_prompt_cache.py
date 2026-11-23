"""Optional prompt-caching layout for banknote Check (BANKNOTE_CHECK_PROMPT_CACHE=1).

The default request is unchanged. With the flag on, the fixed instructions are
one cache_control system block (identical for every note, cut from the default
prompt itself) and each note's photos, dealer text, saved fields and catalogue
research instructions follow in the user message. Both layouts produce the
same Check result from the same model reply. No network and no paid calls."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-check-cache-')
for name in ('ANTHROPIC_API_KEY', 'PERPLEXITY_API_KEY', 'OPENAI_API_KEY', 'BANKNOTE_CHECK_PROMPT_CACHE'):
    os.environ.pop(name, None)
for name in ('EBAY_SYNC_WORKER', 'BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER', 'MARKET_LABEL_WORKER'):
    os.environ[name] = '0'

import app as stuff
import enrichment

IMAGE = {'label': 'front', 'data': 'aGk=', 'media_type': 'image/jpeg'}
ANSWER = {'country': 'France', 'denomination': '10 Livres', 'issuer': 'Domaines Nationaux', 'date_1': 1792,
          'pick_number': 'P-A66b', 'lettering': None, 'lettering_translation': None,
          'catalogue_research': {'identity': {'match': 'unresolved'}, 'fields': {}},
          'direct_evidence': {}, 'purchase_evidence': {}, 'sources': 'note images'}


def reply(usage=None):
    text = json.dumps(ANSWER)
    return SimpleNamespace(stop_reason='end_turn', content=[SimpleNamespace(type='text', text=text)],
                           usage=SimpleNamespace(**(usage or {'input_tokens': 9000, 'output_tokens': 400})),
                           model_dump=lambda: {'content': [{'type': 'text', 'text': text}]})


def note(**changes):
    row = dict(id='n1', country='France', denomination='10 Livres', description='France 10 livres assignat, 1792.',
               notes='PMG 64 EPQ')
    row.update(changes)
    return row


class CheckPromptCacheLayout(unittest.TestCase):
    def setUp(self):
        enrichment.reset()
        self.client = MagicMock()
        self.client.messages.create.side_effect = lambda **kwargs: reply()
        patches = [patch('anthropic.Anthropic', return_value=self.client),
                   patch.object(stuff, '_require_anthropic_key', return_value='synthetic'),
                   patch.object(stuff, 'anthropic_lookup_model', return_value='fixture-model'),
                   patch.object(stuff, '_banknote_check_vision_images', return_value=[IMAGE])]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def check(self, flag, row=None):
        self.client.messages.create.reset_mock()
        with patch.dict(os.environ, {'BANKNOTE_CHECK_PROMPT_CACHE': '1'} if flag else {}, clear=False):
            if not flag:
                os.environ.pop('BANKNOTE_CHECK_PROMPT_CACHE', None)
            result = stuff.fetch_banknote_specs(row or note())
        return result, self.client.messages.create.call_args_list[0].kwargs

    def test_default_request_is_unchanged(self):
        _, request = self.check(False)
        self.assertNotIn('system', request)
        text = request['messages'][0]['content'][-1]['text']
        self.assertTrue(text.startswith('You are extracting structured catalogue fields'))
        self.assertIn('France 10 livres assignat, 1792.', text)
        self.assertIn('\nRules:\n0. Audit EVERY target field', text)

    def test_cached_layout_moves_only_the_fixed_instructions_into_a_cacheable_block(self):
        _, legacy = self.check(False)
        _, cached = self.check(True)
        system = cached['system']
        self.assertEqual(len(system), 1)
        self.assertEqual(system[0]['cache_control'], {'type': 'ephemeral'})
        instructions = system[0]['text']
        user = cached['messages'][0]['content']
        self.assertEqual([block['type'] for block in user], ['text', 'image', 'text'], 'photos first, then the note')
        per_note = user[-1]['text']
        for private in ('France 10 livres assignat, 1792.', 'PMG 64 EPQ', '- country: France'):
            self.assertNotIn(private, instructions)
            self.assertIn(private, per_note)
        self.assertNotIn('\nRules:\n0.', per_note)
        # Same instruction text as the default prompt, pointed at the user message.
        legacy_text = legacy['messages'][0]['content'][-1]['text']
        restored = (instructions
                    .replace("images in the user message (front/back", "images above (front/back", 1)
                    .replace("own text in the user message —", "own text below —", 1))
        head, rules = restored.split('\n\nRules:\n', 1)
        self.assertTrue(legacy_text.startswith(head + '\n'))
        self.assertIn('Rules:\n' + rules, legacy_text)
        self.assertTrue(per_note.endswith(stuff.banknote_catalog_lookup.prompt(note())))
        for field in ('- slab_number:', '- lettering_translation:', '- obv_rev:', '"sources":'):
            self.assertIn(field, instructions)

    def test_the_cached_prefix_is_identical_for_every_note(self):
        _, first = self.check(True, note())
        _, second = self.check(True, note(id='n2', country='Ceylon', denomination='1 Rupee',
                                          description='Ceylon 1 rupee 1942, King George VI.', notes=''))
        self.assertEqual(first['system'], second['system'])
        self.assertEqual(first['tools'], second['tools'])
        self.assertNotEqual(first['messages'], second['messages'])

    def test_both_layouts_produce_the_same_check_result(self):
        legacy, _ = self.check(False)
        cached, _ = self.check(True)
        self.assertEqual(legacy, cached)

    def test_cache_reads_are_metered(self):
        self.client.messages.create.side_effect = lambda **kwargs: reply(
            {'input_tokens': 900, 'output_tokens': 400, 'cache_creation_input_tokens': 0,
             'cache_read_input_tokens': 4100})
        self.check(True)
        self.assertEqual(enrichment.usage_snapshot()['banknote-check']['cache_read_tokens'], 4100)

    def test_any_layout_mismatch_falls_back_to_the_default(self):
        self.assertIsNone(stuff._banknote_check_cached_layout('no marker here', 'dealer', 'known', 'extra'))
        prompt = ('You are extracting...\n\n' + stuff._BANKNOTE_CHECK_IMAGES_LINE + ' — x\n'
                  + stuff._BANKNOTE_CHECK_DEALER_LINE + 'OTHER TEXT')
        self.assertIsNone(stuff._banknote_check_cached_layout(prompt, 'dealer', 'known', 'extra'))


if __name__ == '__main__':
    unittest.main(verbosity=1)
