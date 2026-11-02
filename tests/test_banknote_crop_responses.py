"""Crop analysis must leave output room for a model's final JSON verdict."""
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='stuff-crop-responses-')
for key in ('BANKNOTE_IMPORT_WORKER','ORIGINAL_LISTING_WORKER','EBAY_SYNC_WORKER'):
    os.environ[key]='0'
os.environ.pop('ANTHROPIC_API_KEY',None)
import app as stuff
from PIL import Image


class CropResponses(unittest.TestCase):
    def setUp(self):
        self.client=Mock()
        self.image=Image.new('RGB',(800,400),(240,235,220))

    def response(self,text,stop='end_turn'):
        return SimpleNamespace(stop_reason=stop,content=[
            SimpleNamespace(type='thinking',thinking=''),
            SimpleNamespace(type='text',text=text)])

    def analyze(self,function,response):
        # Simulate the production failure: a small response cap is exhausted
        # by thinking, before even the tiny verdict's text can be returned.
        def create(**kwargs):
            if kwargs['max_tokens']<1024:
                return SimpleNamespace(stop_reason='max_tokens',content=[SimpleNamespace(type='thinking',thinking='')])
            return response
        self.client.messages.create.side_effect=create
        with patch.dict(os.environ,{'ANTHROPIC_API_KEY':'synthetic-key'}), \
                patch('anthropic.Anthropic',return_value=self.client), \
                patch.object(stuff,'anthropic_lookup_model',return_value='synthetic-model'):
            return function(self.image)

    def test_verdict_survives_thinking_before_final_json(self):
        self.assertIs(self.analyze(stuff._vision_crop_verdict,self.response('{"good":true}')),True)
        self.client.messages.create.assert_called_once()

    def test_negative_and_unreadable_verdicts_do_not_authorize_crop(self):
        for text,expected in (('{"good":false}',False),('{"good":"true"}',None),('',None)):
            with self.subTest(text=text):
                self.assertIs(self.analyze(stuff._vision_crop_verdict,self.response(text)),expected)

    def test_truncated_parseable_verdict_is_still_inconclusive(self):
        self.assertIsNone(self.analyze(stuff._vision_crop_verdict,self.response('{"good":true}','max_tokens')))

    def test_geometry_keeps_its_image_coordinate_contract(self):
        result=self.analyze(stuff._note_geometry_scan,self.response(
            '{"note":[[80,80],[720,80],[720,360],[80,360]],"holder":true,"label":true}'))
        self.assertEqual(result['quad'],((100,200),(900,200),(900,900),(100,900)))
        self.assertTrue(result['holder']);self.assertTrue(result['label'])
        self.client.messages.create.assert_called_once()

    def test_truncated_geometry_is_not_a_seed(self):
        self.assertIsNone(self.analyze(stuff._note_geometry_scan,self.response(
            '{"note":[[80,80],[720,80],[720,360],[80,360]]}','max_tokens')))


if __name__=='__main__':unittest.main()
