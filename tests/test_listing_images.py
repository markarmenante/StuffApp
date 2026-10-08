"""Original source photos remain separate from edited collection images."""
import hashlib
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
import listing_images as photos
import original_listings
import source_documents

URL = 'https://www.vcoins.com/en/stores/kirk_davis/45/product/kroton/1560122/Default.aspx'
FRONT = 'https://images.vcoins.com/product_image/45/9/original.jpg'
BACK = 'https://images.vcoins.com/product_image/45/B/back.jpg'
HTML = '<h1>BRUTTIUM, Kroton. AR Stater (7.71g).</h1><script>SetImageZoom("' + FRONT + '");</script>'


def jpeg(size=(1600, 800), color='red'):
    out = BytesIO()
    Image.new('RGB', size, color).save(out, 'JPEG', quality=94)
    return out.getvalue()


class ListingImagesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.folder = Path(self.tmp.name) / 'uploads'
        self.path = Path(self.tmp.name) / 'test.db'
        self.db = self.connect()
        for category in ('coins', 'banknotes'):
            self.db.execute(f'CREATE TABLE {category} (id TEXT PRIMARY KEY,cat_id TEXT,image_1 TEXT,image_2 TEXT,updated_at TEXT)')
            self.db.execute(f"INSERT INTO {category} VALUES ('item','C081','front-edited.jpg','back-edited.jpg','before')")
        self.db.execute("CREATE TABLE record_documents (id TEXT PRIMARY KEY,category TEXT,record_id TEXT,doc_set TEXT DEFAULT 'main',position INTEGER,title TEXT,filename TEXT)")
        original_listings.init_schema(self.db)
        for category in ('coins', 'banknotes'):
            original_listings.add_source(self.db, category, 'item', URL)
            source_documents.enqueue(self.db, category, 'item', URL, 'Original Listing', 'listing')
        self.db.execute("UPDATE original_listing_pages SET state='available'")
        self.db.commit()

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        return db

    def tearDown(self):
        self.db.close()
        self.tmp.cleanup()

    def test_vcoins_original_gallery_not_preview_related_product_or_logo(self):
        html = HTML + '<a onclick="SetImageZoom(\'' + BACK + '\')">Back</a>'
        html += '<meta property="og:image" content="' + FRONT.replace('/9/', '/9/6/') + '">'
        html += '<img src="https://images.vcoins.com/product_image/45/other.jpg">'
        html += '<script type="application/ld+json">' + json.dumps({'@type': 'Product', 'url': URL.replace('1560122', '99999'), 'image': 'https://images.vcoins.com/product_image/45/related.jpg'}) + '</script>'
        self.assertEqual(photos.image_urls(html, URL), [FRONT, BACK])

    def test_structured_gallery_only_for_exact_ebay_and_cng_product(self):
        for url in ('https://www.ebay.com/itm/123456789012', 'https://www.cngcoins.com/Coin.aspx?CoinID=123'):
            image = 'https://i.ebayimg.com/images/g/ABC/s-l1600.jpg' if 'ebay' in url else 'https://www.cngcoins.com/photos/123.jpg'
            html = '<h1>Original ancient silver tetradrachm</h1><script type="application/ld+json">'
            html += json.dumps({'@graph': [{'@type': 'Product', 'url': url, 'image': [image]},
                                          {'@type': 'Product', 'url': URL, 'image': BACK}]}) + '</script>'
            self.assertEqual(photos.image_urls(html, url), [image])

    def test_unsafe_and_decorative_urls_excluded(self):
        for url in ('http://images.vcoins.com/p.jpg', 'https://localhost/p.jpg',
                    'https://images.vcoins.com.evil.test/p.jpg', 'https://images.vcoins.com:8443/p.jpg',
                    'https://u:p@images.vcoins.com/p.jpg', 'https://images.vcoins.com/pixel.gif',
                    'https://images.vcoins.com/logo.png', 'https://images.vcoins.com/photo.svg'):
            self.assertEqual(photos.image_urls(HTML.replace(FRONT, url), URL), [])

    def test_cng_enlargement_link_and_ebay_thumbnail_variants(self):
        cng = 'https://www.cngcoins.com/Coin.aspx?CoinID=394565'
        html = '<h1>Ancient silver stater from Kroton</h1><a onclick="return ShowImage(\'/photos/enlarged/577810.jpg\')"><image src="/photos/big/577810.jpg"></a>'
        self.assertEqual(photos.image_urls(html, cng), ['https://www.cngcoins.com/photos/enlarged/577810.jpg'])
        ebay = 'https://www.ebay.com/itm/123456789012'
        image = 'https://i.ebayimg.com/images/g/AAA/s-l1600.jpg'
        html = '<h1>Japan 10 Yen Original Banknote</h1>'
        html += '<script type="application/ld+json">' + json.dumps({'@type': 'Product', 'image': image}) + '</script>'
        html += '<meta property="og:image" content="' + image.replace('1600','500') + '">'
        self.assertEqual(photos.image_urls(html, ebay), [image])

    def test_unreadable_or_redirected_listing_not_archived(self):
        for body, final in (('<h1>Sign in to your account</h1>', URL), (HTML, URL.replace('1560122','999999'))):
            with self.assertRaises(ValueError):
                photos.image_urls(body, URL, final)

    def test_download_preserves_exact_original_bytes_and_dimensions(self):
        data = jpeg()
        with patch.object(source_documents, 'fetch_bytes', return_value=(data, 'image/jpeg', FRONT)) as fetch:
            asset = photos.download(FRONT, self.folder)
            again = photos.download(FRONT, self.folder)
        self.assertEqual((asset['width'],asset['height']), (1600,800))
        self.assertEqual((self.folder / asset['filename']).read_bytes(), data)
        self.assertEqual(asset['sha256'], hashlib.sha256(data).hexdigest())
        self.assertEqual(asset['filename'], again['filename'])
        self.assertEqual(len(list(self.folder.iterdir())), 1)
        fetch.assert_called_with(FRONT, source_documents.IMAGE_HOSTS, photos.MAX_BYTES)

    def test_download_rejects_html_tiny_and_invalid_images(self):
        for data, mime in ((b'<h1>Sign in</h1>', 'text/html'), (b'not an image', 'image/jpeg'),
                           (jpeg((1,1)), 'image/jpeg')):
            with patch.object(source_documents, 'fetch_bytes', return_value=(data,mime,FRONT)):
                with self.assertRaises(Exception):
                    photos.download(FRONT, self.folder)
        self.assertFalse(self.folder.exists())

    def test_save_adds_once_both_categories_without_replacing_any_images_or_documents(self):
        with patch.object(source_documents, 'fetch_bytes', return_value=(jpeg(),'image/jpeg',FRONT)):
            asset = photos.download(FRONT, self.folder)
        self.db.execute("INSERT INTO record_documents VALUES ('old','coins','item','main',0,'Invoice','old.pdf')")
        with self.db:
            self.assertEqual(photos.save(self.db, URL, [asset]), 2)
            self.assertEqual(photos.save(self.db, URL, [asset]), 0)
        for category in ('coins', 'banknotes'):
            row = self.db.execute(f'SELECT image_1,image_2 FROM {category}').fetchone()
            self.assertEqual(tuple(row), ('front-edited.jpg','back-edited.jpg'))
            docs = self.db.execute('SELECT * FROM record_documents WHERE category=? ORDER BY position', (category,)).fetchall()
            self.assertEqual(docs[-1]['title'], 'VCoins Original Listing Image 1 - C081')
            self.assertEqual(docs[-1]['filename'], asset['filename'])
        self.assertEqual(self.db.execute("SELECT filename FROM record_documents WHERE id='old'").fetchone()[0], 'old.pdf')

    def test_shared_image_bytes_do_not_create_duplicate_documents(self):
        with patch.object(source_documents, 'fetch_bytes', return_value=(jpeg(),'image/jpeg',FRONT)):
            front, back = photos.download(FRONT, self.folder), photos.download(BACK, self.folder)
        with self.db:
            photos.save(self.db, URL, [front,back])
        self.assertEqual(self.db.execute('SELECT count(*) FROM record_documents').fetchone()[0], 2)

    def test_changed_listing_association_is_not_given_old_listing_photos(self):
        with patch.object(source_documents, 'fetch_bytes', return_value=(jpeg(),'image/jpeg',FRONT)):
            asset = photos.download(FRONT, self.folder)
        self.db.execute('DELETE FROM coin_original_listings')
        with self.db:
            self.assertEqual(photos.save(self.db, URL, [asset]), 1)
        self.assertFalse(self.db.execute("SELECT 1 FROM record_documents WHERE category='coins'").fetchone())

    def test_worker_retries_failures_then_completes_once(self):
        def fetch(url, *args):
            return (HTML.encode(), 'text/html', URL) if url == URL else (jpeg(), 'image/jpeg', FRONT)
        with patch.object(source_documents, 'fetch_bytes', side_effect=ValueError('blocked')):
            self.assertTrue(photos.run_once(self.connect, self.folder))
        row = self.db.execute('SELECT * FROM original_listing_image_scans').fetchone()
        self.assertIsNone(row['completed_at'])
        self.assertGreater(row['next_attempt'], time.time())
        with self.db:
            self.db.execute('UPDATE original_listing_image_scans SET next_attempt=0')
        with patch.object(source_documents, 'fetch_bytes', side_effect=fetch) as calls:
            self.assertTrue(photos.run_once(self.connect, self.folder))
            self.assertFalse(photos.run_once(self.connect, self.folder))
        self.assertEqual(calls.call_count, 2)
        self.assertIsNotNone(self.db.execute('SELECT completed_at FROM original_listing_image_scans').fetchone()[0])
        self.assertEqual(self.db.execute('SELECT count(*) FROM record_documents').fetchone()[0], 2)

    def test_partial_download_keeps_original_gallery_positions(self):
        html = HTML + '<a onclick="SetImageZoom(\'' + BACK + '\')">Back</a>'
        def fetch(url, *args):
            if url == URL: return html.encode(), 'text/html', URL
            if url == FRONT: raise ValueError('Temporarily blocked')
            return jpeg(), 'image/jpeg', BACK
        with patch.object(source_documents, 'fetch_bytes', side_effect=fetch):
            photos.run_once(self.connect, self.folder)
        self.assertEqual(self.db.execute('SELECT position FROM original_listing_image_sources').fetchone()[0], 1)
        self.assertIn('Image 2', self.db.execute('SELECT title FROM record_documents').fetchone()[0])
        self.assertIsNone(self.db.execute('SELECT completed_at FROM original_listing_image_scans').fetchone()[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
