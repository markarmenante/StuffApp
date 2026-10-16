"""Exact-gallery side selection and bounded image-only payload regressions."""
from copy import deepcopy
import hashlib
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import banknote_photo_sides as sides
from PIL import Image


class PhotoSidesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = Path(self.tmp.name)
        self.assets = []
        self.meaning = {}
        for number, side in enumerate(('front', 'front', 'back', 'back')):
            filename = f'gallery-{number}.png'
            Image.new('RGB', (500, 300), (40 + number * 30, 90, 140)).save(self.folder / filename)
            self.assets.append(dict(filename=filename, position=number))
            self.meaning[filename] = side

    def decision(self, photos):
        readings = [dict(id=p['id'], side=self.meaning.get(p['filename'], 'unknown'), confidence='high',
                         complete_note=True, same_note=True, reason='Different printed note design') for p in photos]
        chosen = {}
        for p, reading in zip(photos, readings):
            if p['gallery']:
                chosen.setdefault(reading['side'], p['id'])
        return dict(photos=readings, front=chosen.get('front'), back=chosen.get('back'),
                    pair_verified=bool(chosen.get('front') and chosen.get('back')), pair_reason='Opposite designs of the same note')

    def select(self, **kwargs):
        return sides.select(self.assets, self.folder, kwargs.pop('classify', self.decision), **kwargs)

    def test_front_front_back_back_examines_all_and_chooses_different_sides(self):
        classify = Mock(side_effect=self.decision)
        result = self.select(classify=classify)
        self.assertEqual(len(classify.call_args.args[0]), 4)
        self.assertEqual(result['images']['image_1']['position'], 0)
        self.assertEqual(result['images']['image_2']['position'], 2)

    def test_later_reverse_after_first_four_is_considered(self):
        for asset in self.assets:
            self.meaning[asset['filename']] = 'front'
        filename = 'later.png'
        Image.new('RGB',(500,300),'yellow').save(self.folder / filename)
        self.assets.append(dict(filename=filename,position=4))
        self.meaning[filename] = 'back'
        self.assertEqual(self.select()['images']['image_2']['position'], 4)

    def test_gallery_can_be_reverse_first(self):
        self.assets.reverse()
        result = self.select()
        self.assertEqual(result['images']['image_1']['position'], 1)
        self.assertEqual(result['images']['image_2']['position'], 3)

    def test_identical_content_deduplicated_not_a_second_side(self):
        self.assets = [self.assets[0],dict(self.assets[0],position=1)]
        spy = Mock(side_effect=self.decision)
        result = self.select(classify=spy)
        self.assertEqual(len(spy.call_args.args[0]), 1)
        self.assertEqual(set(result['images']), {'image_1'})

    def test_only_front_keeps_reverse_empty(self):
        for asset in self.assets:
            self.meaning[asset['filename']] = 'front'
        result = self.select()
        self.assertEqual(set(result['images']), {'image_1'})
        self.assertTrue(result['warnings'])

    def test_existing_correct_pair_unchanged(self):
        result = self.select(existing={'image_1':'gallery-0.png','image_2':'gallery-2.png'})
        self.assertEqual(result['images'], {})

    def test_existing_duplicate_is_warned_but_never_replaced(self):
        result = self.select(existing={'image_1':'gallery-0.png','image_2':'gallery-1.png'})
        self.assertEqual(result['images'], {})
        self.assertTrue(result['warnings'])

    def test_mapped_manual_crop_is_not_repaired(self):
        result = self.select(existing={'image_1':'gallery-0.png','image_2':'gallery-1.png'})
        self.assertEqual(result['images'], {})

    def test_unrelated_manual_photo_does_not_gain_a_guessed_partner(self):
        Image.new('RGB',(500,300),'black').save(self.folder/'manual.png')
        result = self.select(existing={'image_1':'manual.png'})
        self.assertEqual(result['images'], {})
        self.assertTrue(result['warnings'])

    def test_saved_reverse_in_front_slot_is_not_duplicated(self):
        result = self.select(existing={'image_1':'gallery-2.png'})
        self.assertEqual(result['images'], {})

    def test_correct_manual_front_is_preserved_and_missing_reverse_filled(self):
        result = self.select(existing={'image_1':'manual-crop.jpg'}, resolve_original=lambda name:'gallery-0.png')
        self.assertEqual(set(result['images']), {'image_2'})

    def test_malformed_or_incomplete_model_result_never_imports(self):
        mutations = [lambda d:d.update(photos=[]), lambda d:d['photos'].append(d['photos'][0]),
                     lambda d:d['photos'][0].update(id='photo-999'), lambda d:d.update(front='photo-99'),
                     lambda d:d.update(back=d['front']), lambda d:d.update(pair_verified=False),
                     lambda d:d['photos'][2].update(confidence='medium'),
                     lambda d:d['photos'][2].update(side='both'), lambda d:d['photos'][2].update(complete_note=False),
                     lambda d:d['photos'][2].update(same_note=False), lambda d:d['photos'][2].update(same_note='true'),
                     lambda d:d['photos'][2].update(reason='')]
        for change in mutations:
            def classify(photos):
                data=self.decision(photos);change(data);return data
            result=self.select(classify=classify)
            self.assertEqual(result['images'],{},str(change))
            self.assertTrue(result['warnings'])
        self.assertEqual(self.select(classify=lambda photos:'not json')['images'],{})

    def test_no_key_or_provider_failure_preserves_every_image(self):
        for classifier in (None, Mock(side_effect=RuntimeError('No API key'))):
            result=self.select(classify=classifier,existing={'image_1':'gallery-0.png'})
            self.assertEqual(result['images'],{})
            self.assertTrue(result['warnings'])

    def test_blank_reverse_is_allowed_when_confidently_same_note(self):
        # The verifier's judgement of a blank sheet is explicit, never inferred
        # from absence of OCR or from a holder back label.
        self.assertIn('image_2',self.select()['images'])

    def test_payload_is_bounded_images_and_generic_ids_only(self):
        photos=[dict(id='photo-0',filename='gallery-0.png',gallery=True)]
        original=(self.folder/'gallery-0.png').read_bytes()
        content=sides.vision_content(photos,self.folder)
        self.assertEqual([b['type'] for b in content],['text','image','text'])
        self.assertEqual(content[0]['text'],'photo-0 GALLERY')
        self.assertNotIn(str(self.folder),str(content))
        self.assertNotIn('gallery-0.png',str(content))
        self.assertLess(len(content[1]['source']['data']),700_000)
        self.assertEqual((self.folder/'gallery-0.png').read_bytes(),original)
        with self.assertRaises(ValueError):
            sides.vision_content([dict(id='photo-0',filename='../private.png',gallery=True)],self.folder)

    def test_max_gallery_is_bounded_without_an_extra_network_call(self):
        self.assets=self.assets*20
        classify=Mock(side_effect=self.decision)
        self.select(classify=classify)
        self.assertEqual(classify.call_count,1)
        self.assertLessEqual(len(classify.call_args.args[0]),sides.MAX_GALLERY+2)


if __name__ == '__main__':
    unittest.main()
