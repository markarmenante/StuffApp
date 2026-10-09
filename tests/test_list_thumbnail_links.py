"""Collection thumbnails are native detail links and keep upload targets."""
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit, parse_qs
from html.parser import HTMLParser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-list-links-')
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuff


class ListLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.rows = {}
        self.row = None
        self.feed(html.decode())

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if 'item-row' in classes:
            self.row = dict(attrs, thumbs=[])
            self.rows[attrs['id']] = self.row
        elif 'item-thumb' in classes and self.row is not None:
            self.row['thumbs'].append(dict(attrs, tag=tag))


class ThumbnailLinkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ctx = stuff.app.app_context()
        cls.ctx.push()
        db = stuff.get_db()
        for category, info in stuff.CATEGORIES.items():
            if category == 'persons':
                continue
            db.execute(f"INSERT INTO {info['table']} (id,{info['image_field']}) VALUES (?,?)",
                       ('thumb-link-' + category, 'example.jpg'))
        db.commit()
        cls.client = stuff.app.test_client()

    @classmethod
    def tearDownClass(cls):
        cls.ctx.pop()

    def test_each_collection_image_links_to_same_detail_as_row(self):
        for category in stuff.CATEGORIES:
            if category == 'persons':
                continue
            with self.subTest(category=category), patch.object(stuff, 'ensure_country_history'):
                response = self.client.get('/' + category + '?filter=all')
                self.assertEqual(response.status_code, 200)
                row = ListLinks(response.data).rows.get('item-thumb-link-' + category)
                self.assertIsNotNone(row)
                thumbs = row['thumbs']
                self.assertEqual(len(thumbs), 2 if category in ('coins', 'banknotes') else 1)
                for thumb in thumbs:
                    self.assertEqual(thumb['tag'], 'a')
                    self.assertEqual(thumb['href'], row['data-href'])
                    self.assertTrue(thumb.get('aria-label'))
                    self.assertEqual(urlsplit(thumb['href']).path, '/' + category + '/thumb-link-' + category)
                    self.assertTrue(thumb.get('data-upload-url'))
                if len(thumbs) == 2:
                    self.assertEqual(thumbs[1]['data-field'], 'image_2')

    def test_banknote_thumbnail_preserves_history_preference(self):
        with patch.object(stuff, 'ensure_country_history'):
            parsed = ListLinks(self.client.get('/banknotes?history=0').data)
        thumb = parsed.rows['item-thumb-link-banknotes']['thumbs'][0]
        self.assertEqual(parse_qs(urlsplit(thumb['href']).query)['history'], ['0'])


if __name__ == '__main__':
    unittest.main()
