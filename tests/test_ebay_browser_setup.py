import io
import json
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from flask import Flask, abort
import ebay_browser_setup


class BrowserSetupTests(unittest.TestCase):
    def setUp(self):
        self.owner=True
        app=Flask(__name__)
        ebay_browser_setup.register(app,lambda:None if self.owner else abort(403),lambda:dict(category='banknotes'))
        self.client=app.test_client()

    def get(self,path,origin='https://stuff.armenante.com'):
        return self.client.get(path,base_url=origin)

    def test_setup_uses_owner_context_and_is_not_available_on_other_tenants(self):
        with patch.object(ebay_browser_setup,'render_template',return_value='Setup') as render:
            self.assertEqual(self.get('/ebay/browser/setup').status_code,200)
            render.assert_called_once_with('ebay_browser_setup.html',category='banknotes')
        with patch.object(ebay_browser_setup,'render_template',return_value='Setup'):
            self.assertEqual(self.get('/ebay/browser/setup','http://stuff.armenante.com').status_code,200)
        self.assertEqual(self.get('/ebay/browser/setup','https://gerri.armenante.com').status_code,404)
        self.owner=False
        self.assertEqual(self.get('/ebay/browser/setup').status_code,403)
        self.assertEqual(self.get('/ebay/browser/download').status_code,403)

    def test_download_contains_only_allowlisted_runtime_files(self):
        response=self.get('/ebay/browser/download')
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertIn('stuffapp-ebay-browser.zip',response.headers['Content-Disposition'])
        with ZipFile(io.BytesIO(response.data)) as archive:
            self.assertEqual(set(archive.namelist()),{'browser-extension/'+name for name in ebay_browser_setup.RUNTIME_FILES})
            manifest=json.loads(archive.read('browser-extension/manifest.json'))
            self.assertIn('browser-extension/'+manifest['background']['service_worker'],archive.namelist())
            self.assertEqual(manifest['externally_connectable']['matches'],['https://stuff.armenante.com/*'])
            for name in archive.namelist():
                if name.endswith('.mjs'):
                    for dependency in re.findall(r"(?:from\s+|import\s*)['\"]\./([^'\"]+)['\"]",archive.read(name).decode()):
                        self.assertIn('browser-extension/'+dependency,archive.namelist())
        self.assertEqual(self.get('/ebay/browser/download','https://gerri.armenante.com').status_code,404)


if __name__=='__main__':unittest.main()
