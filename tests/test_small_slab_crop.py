"""Small full sheets need original paper geometry and affirmative validation."""
import base64
import io
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-small-slab-')
for key in ('BANKNOTE_IMPORT_WORKER', 'ORIGINAL_LISTING_WORKER', 'EBAY_SYNC_WORKER'):
    os.environ[key] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)
import app as stuff


def slab(note_size=(450, 300)):
    image = Image.new('RGB', (1600, 1000), (15, 15, 15))
    draw = ImageDraw.Draw(image)
    draw.rectangle((300, 60, 1300, 190), fill=(235, 235, 235))
    draw.text((340, 100), 'PCGS BANKNOTE 64', fill=(20, 20, 20))
    width, height = note_size
    left, top = (1600 - width) // 2, 300
    draw.rectangle((left, top, left + width, top + height), fill=(240, 233, 211))
    draw.rectangle((left + 20, top + 20, left + width - 20, top + height - 20),
                   outline=(65, 45, 45), width=3)
    for x in range(left + 30, left + width - 25, 7):
        draw.line((x, top + 30, x, top + height - 30), fill=(85, 55, 50), width=2)
    return image


class SmallSlabCropTests(unittest.TestCase):
    def test_small_sheet_validator_receives_the_original_photo(self):
        image = slab()

        def compare(candidate, *, original):
            self.assertIs(original, image)
            self.assertIsNot(candidate, original)
            self.assertLess(candidate.width * candidate.height,
                            original.width * original.height * 0.15)
            return True

        with patch.object(stuff, '_vision_crop_verdict', side_effect=compare) as verdict:
            self.assertIsNotNone(stuff._trim_small_slab_note(image))
        verdict.assert_called_once()

    def test_validator_transmits_original_then_candidate_with_comparison_prompt(self):
        source = slab()
        candidate = Image.new('RGB', (408, 347), (240, 233, 211))
        response = SimpleNamespace(stop_reason='end_turn')
        create = Mock(return_value=response)
        provider = SimpleNamespace(Anthropic=Mock(return_value=SimpleNamespace(
            messages=SimpleNamespace(create=create))))
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-no-network'}), \
                patch.dict(sys.modules, {'anthropic': provider}), \
                patch.object(stuff, 'anthropic_lookup_model', return_value='test-model'), \
                patch.object(stuff, '_message_text', return_value='{"good": true}'):
            self.assertIs(stuff._vision_crop_verdict(candidate, original=source), True)
            self.assertIs(stuff._vision_crop_verdict(candidate), True)

        compared = create.call_args_list[0].kwargs['messages'][0]['content']
        images = [part for part in compared if part['type'] == 'image']
        self.assertEqual(len(images), 2)
        decoded = [Image.open(io.BytesIO(base64.b64decode(part['source']['data'])))
                   for part in images]
        self.assertEqual(decoded[0].size, source.size,
                         'Keep the 1600px original readable when paper margins are very narrow')
        self.assertEqual(decoded[1].size, candidate.size)
        prompt = ' '.join(part['text'] for part in compared if part['type'] == 'text')
        self.assertIn('Compare', prompt)
        self.assertIn('ORIGINAL', prompt)
        self.assertIn('naturally', prompt)
        self.assertIn('uncertainty', prompt)

        standalone = create.call_args_list[1].kwargs['messages'][0]['content']
        self.assertEqual(sum(part['type'] == 'image' for part in standalone), 1)
        standalone_prompt = ' '.join(part['text'] for part in standalone if part['type'] == 'text')
        self.assertIn('full paper', standalone_prompt)
        self.assertNotIn('Compare', standalone_prompt)

    def test_original_paper_quad_validates_and_records_inset_source_coordinates(self):
        image = slab()
        meta = {}
        with patch.object(stuff, '_vision_crop_verdict', return_value=True) as verdict:
            result = stuff._trim_small_slab_note(image, expect_aspect=1.5, meta=meta)
        self.assertIsNotNone(result)
        crop = Image.open(io.BytesIO(result))
        self.assertAlmostEqual(crop.width, 446, delta=4)
        self.assertAlmostEqual(crop.height, 296, delta=4)
        self.assertEqual(meta['engine'], 'small-paper-quad')
        self.assertEqual(len(meta['quad']), 4)
        self.assertGreater(meta['quad'][0][0], 575)
        self.assertGreater(meta['quad'][0][1], 300)
        self.assertLess(meta['quad'][2][0], 1025)
        self.assertLess(meta['quad'][2][1], 600)
        verdict.assert_called_once()

    def test_unavailable_or_negative_validator_never_approves_small_crop(self):
        for verdict in (None, False):
            with self.subTest(verdict=verdict), \
                    patch.object(stuff, '_vision_crop_verdict', return_value=verdict):
                meta = {}
                self.assertIsNone(stuff._trim_small_slab_note(slab(), meta=meta))
                self.assertEqual(meta, {})

    def test_hard_metrics_cannot_be_overruled_by_validator(self):
        for failure in ('design touches the frame edge', 'dark top band', 'aspect 20% off'):
            with self.subTest(failure=failure), \
                    patch.object(stuff, '_note_crop_metrics', return_value=[failure]), \
                    patch.object(stuff, '_vision_crop_verdict', return_value=True) as verdict:
                self.assertIsNone(stuff._trim_small_slab_note(slab()))
                verdict.assert_not_called()

    def test_soft_metrics_still_require_affirmative_validator(self):
        with patch.object(stuff, '_note_crop_metrics', return_value=['ink fills only 9%']), \
                patch.object(stuff, '_vision_crop_verdict', return_value=True):
            self.assertIsNotNone(stuff._trim_small_slab_note(slab()))

    def test_blank_watermark_inside_large_sheet_is_not_a_small_note(self):
        image = slab((900, 600))
        # A pale blank panel lies inside the design of a much larger note.
        ImageDraw.Draw(image).rectangle((400, 370, 720, 680), fill=(250, 245, 228))
        with patch.object(stuff, '_vision_crop_verdict', return_value=True) as verdict:
            self.assertIsNone(stuff._trim_small_slab_note(image))
            verdict.assert_not_called()

    def test_outside_area_window_is_left_to_existing_pipeline(self):
        for size in ((250, 180), (900, 600)):
            with self.subTest(size=size), \
                    patch.object(stuff, '_vision_crop_verdict', return_value=True) as verdict:
                self.assertIsNone(stuff._trim_small_slab_note(slab(size)))
                verdict.assert_not_called()

    def test_small_sheet_is_checked_before_seeded_and_cleanup_paths(self):
        image = slab()
        source = io.BytesIO()
        image.save(source, format='PNG')
        meta = {}
        with patch.object(stuff, '_warm_paper_on_light_holder_quad', return_value=None), \
                patch.object(stuff, '_paper_on_dark_backdrop_quad', return_value=None), \
                patch.object(stuff, '_vision_crop_verdict', return_value=True), \
                patch.object(stuff, '_trim_note_v2', side_effect=AssertionError('seeded path')), \
                patch.object(stuff, '_trim_note_cv_cascade', side_effect=AssertionError('cleanup path')):
            self.assertIsNotNone(stuff._trim_slabbed_note_image(source.getvalue(), meta=meta))
        self.assertEqual(meta['engine'], 'small-paper-quad')


if __name__ == '__main__':
    unittest.main()
