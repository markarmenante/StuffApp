"""Explicit Check reads exact sources, archives PDFs once, and does not invent paid amounts."""
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuff-check-sources-')
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuff
import banknote_check_sources as sources
import original_listings
import purchase_orders
import ebay_listing_captures

URL = 'https://www.ebay.com/itm/325643741723'
HTML = '<title>Tonga original banknote</title><h1>Tonga 1 Pound 1966 PMG 67 EPQ</h1><p>Serial D/1 53153. Sold.</p>'


def make_pdf(text):
    from reportlab.pdfgen.canvas import Canvas
    out = io.BytesIO()
    canvas = Canvas(out)
    canvas.drawString(35, 750, text)
    canvas.save()
    return out.getvalue()


class SourceCheckTests(unittest.TestCase):
    def setUp(self):
        self.ctx = stuff.app.app_context()
        self.ctx.push()
        self.db = stuff.get_db()
        self.id = self._testMethodName
        self.db.execute("INSERT INTO banknotes (id,country,denomination,price,size_width,size_height) "
                        "VALUES (?,'Tonga','1 Pound','$485',150,80)", (self.id,))
        self.db.commit()
        self.client = stuff.app.test_client()

    def tearDown(self):
        self.db.rollback()
        self.db.execute('DELETE FROM banknotes WHERE id=?', (self.id,))
        self.db.execute('DELETE FROM record_documents WHERE record_id=?', (self.id,))
        self.db.execute('DELETE FROM purchase_source_archives')
        self.db.execute('DELETE FROM original_listing_pages')
        self.db.execute('DELETE FROM ebay_order_items WHERE line_key LIKE ?', (self.id + '%',))
        self.db.execute('DELETE FROM original_image_assets')
        self.db.execute('DELETE FROM ebay_listing_captures')
        self.db.execute('DELETE FROM trimmed_image_sources')
        self.db.commit()
        self.ctx.pop()

    def note(self):
        return self.db.execute('SELECT * FROM banknotes WHERE id=?', (self.id,)).fetchone()

    def prepare(self):
        return sources.prepare(self.db, self.note(), stuff.UPLOAD_FOLDER, stuff._pdf_fonts)

    def add_listing(self):
        original_listings.add_source(self.db, 'banknotes', self.id, URL)
        self.db.commit()

    def invoice(self, text='Order receipt: Tonga 1 Pound. Unit price $485.00. Shipping $5.00. Tax $37.59. Total $527.59.'):
        filename = self.id + '.pdf'
        (Path(stuff.UPLOAD_FOLDER) / filename).write_bytes(make_pdf(text))
        self.db.execute("INSERT INTO record_documents (id,category,record_id,doc_set,position,title,filename) "
                        "VALUES (?,'banknotes',?,'main',0,'eBay Order Receipt',?)", (self.id, self.id, filename))
        self.db.commit()

    def test_missing_sources_are_not_guessed_from_vendor(self):
        with patch.object(sources.archives, 'fetch_bytes') as fetch:
            result = self.prepare()
        self.assertFalse(fetch.called)
        self.assertEqual(result['evidence'], [])
        self.assertEqual(len(result['warnings']), 2)

    def test_pasted_order_does_not_retry_private_pages(self):
        self.db.execute("UPDATE banknotes SET marketplace='eBay',order_number='12-34567-89012' WHERE id=?", (self.id,))
        self.db.commit()
        self.add_listing()
        with patch.object(sources.archives, 'fetch_bytes', side_effect=ValueError('sign in')) as fetch:
            result = self.prepare()
        self.assertEqual([c.args[0] for c in fetch.call_args_list], [URL])
        self.assertIn('12-34567-89012', ' '.join(result['warnings']))
        self.assertIn('signed-in browser', ' '.join(result['warnings']))

    def order(self, suffix='', title='Tonga 1 Pound 1966 PMG 67 EPQ', **values):
        self.db.execute("UPDATE banknotes SET order_number='12-34567-89012' WHERE id=?", (self.id,))
        item = dict(line_key=self.id + suffix, order_id='12-34567-89012',
                    item_id='325643741723' if not suffix else '325643741724', title=title,
                    seller='Example Dealer', quantity=1, attention='',
                    ordered_at='2026-10-07T12:10:00Z', delivery_status='Ordered', last_seen='now')
        item.update(values)
        self.db.execute('INSERT INTO ebay_order_items (' + ','.join(item) + ') VALUES (' + ','.join('?' for _ in item) + ')', list(item.values()))
        self.db.commit()

    def blank(self):
        self.db.execute('UPDATE banknotes SET country=NULL,denomination=NULL,price=NULL WHERE id=?', (self.id,))
        self.db.commit()

    def photo(self, url, folder):
        from PIL import Image
        import hashlib
        filename = ('front' if '/front/' in url else 'back') + '.png'
        path = Path(folder) / filename
        Image.new('RGB', (400, 200), '#418050').save(path)
        return dict(url=url, filename=filename, sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    width=400, height=200, saved_at=1)

    def gallery(self):
        return HTML + '''<script type="application/ld+json">{"@type":"Product","image":[
        "https://i.ebayimg.com/images/g/front/s-l1600.jpg",
        "https://i.ebayimg.com/images/g/back/s-l1600.jpg"]}</script>'''

    def test_order_number_alone_identifies_single_item_and_infers_ebay(self):
        self.blank()
        self.order()
        self.assertEqual(purchase_orders.order_reference(self.db, 'banknotes', self.note())['provider'], 'eBay')
        with patch.object(sources.archives, 'fetch_bytes', return_value=(HTML.encode(), 'text/html', URL)):
            result = self.prepare()
        self.assertEqual(result['purchase']['purchase_date'], '2026-10-07')
        self.assertIn('Tonga 1 Pound', sources.evidence_text(result))
        self.assertIn('synced purchase', sources.evidence_text(result))
        self.assertEqual(len(result['documents']), 1)

    def test_browser_capture_imports_photos_and_pdf_without_server_listing_access(self):
        self.blank()
        self.order()
        ebay_listing_captures.save(self.db, dict(url=URL, title='Tonga 1 Pound 1966 PMG 67 EPQ',
            text='Tonga 1 Pound 1966 PMG 67 EPQ. Serial D/1 53153. Sold.',
            images=['https://i.ebayimg.com/images/g/front/s-l1600.jpg',
                    'https://i.ebayimg.com/images/g/back/s-l1600.jpg']),
            [dict(item_id='325643741723', quantity=1)])
        self.db.commit()
        with patch.object(sources.archives, 'fetch_bytes', side_effect=ValueError('server denied')) as fetch, \
                patch.object(sources.listing_images, 'download', side_effect=self.photo):
            result = self.prepare()
        self.assertNotIn(URL, [c.args[0] for c in fetch.call_args_list])
        self.assertFalse(any('order.ebay.com' in c.args[0] for c in fetch.call_args_list))
        self.assertEqual(set(result['images']), {'image_1', 'image_2'})
        pdfs = [d for d in result['documents'] if d['filename'].endswith('.pdf')]
        self.assertEqual(len(pdfs), 1)
        self.assertIn('Serial D/1 53153', sources.pdf_text(Path(stuff.UPLOAD_FOLDER) / pdfs[0]['filename']))
        self.assertIn('No readable invoice', ' '.join(result['warnings']))

    def test_blank_multi_item_order_is_not_selected(self):
        self.blank()
        self.order()
        self.order('-two', 'Canada 2 Dollars 1954 PMG 64')
        self.assertIsNone(purchase_orders.ebay_item_for_order(self.db, 'banknotes', self.note()))
        self.db.execute("UPDATE banknotes SET country='Tonga',denomination='1 Pound' WHERE id=?", (self.id,))
        self.assertEqual(purchase_orders.ebay_item_for_order(self.db, 'banknotes', self.note())['line_key'], self.id)

    def test_wrong_identity_refund_quantity_or_bundle_is_not_imported(self):
        self.order()
        for changes in [dict(title='Canada 2 Dollars'), dict(attention='Refunded'), dict(quantity=2), dict(title='Tonga 1 Pound lot of 2 banknotes')]:
            with self.subTest(changes=changes):
                self.db.execute('UPDATE ebay_order_items SET ' + ','.join(k + '=?' for k in changes) + ' WHERE line_key=?', [*changes.values(), self.id])
                self.assertIsNone(purchase_orders.ebay_item_for_order(self.db, 'banknotes', self.note()))
                self.db.execute("UPDATE ebay_order_items SET title='Tonga 1 Pound 1966',attention='',quantity=1 WHERE line_key=?", (self.id,))

    def test_listing_images_are_documents_and_fill_empty_slots_once(self):
        self.add_listing()
        with patch.object(sources.archives, 'fetch_bytes', return_value=(self.gallery().encode(), 'text/html', URL)), \
                patch.object(sources.listing_images, 'download', side_effect=self.photo) as download:
            first, second = self.prepare(), self.prepare()
        self.assertEqual(set(first['images']), {'image_1', 'image_2'})
        self.assertEqual(second['images'], {})
        self.assertEqual(len(first['documents']), 3)
        self.assertEqual(first['documents'], second['documents'])
        self.assertEqual(download.call_count, 2)
        self.assertNotEqual(self.note()['image_1'], 'front.png')
        self.assertEqual((Path(stuff.UPLOAD_FOLDER) / self.note()['image_1']).read_bytes(), (Path(stuff.UPLOAD_FOLDER) / 'front.png').read_bytes())

    def test_original_downloads_do_not_replace_existing_photos(self):
        self.add_listing()
        self.db.execute("UPDATE banknotes SET image_1='manual-front.png',image_2='manual-back.png' WHERE id=?", (self.id,))
        self.db.commit()
        with patch.object(sources.archives, 'fetch_bytes', return_value=(self.gallery().encode(), 'text/html', URL)), \
                patch.object(sources.listing_images, 'download', side_effect=self.photo):
            result = self.prepare()
        self.assertEqual(result['images'], {})
        self.assertEqual(self.note()['image_1'], 'manual-front.png')
        self.assertEqual(len(result['documents']), 3)

    def test_failed_front_download_does_not_move_back_into_front_slot(self):
        self.add_listing()
        def download(url, folder):
            if '/front/' in url:
                raise ValueError('Unavailable')
            return self.photo(url, folder)
        with patch.object(sources.archives, 'fetch_bytes', return_value=(self.gallery().encode(), 'text/html', URL)), \
                patch.object(sources.listing_images, 'download', side_effect=download):
            result = self.prepare()
        self.assertEqual(set(result['images']), {'image_2'})
        self.assertFalse(self.note()['image_1'])
        self.assertEqual(len(result['documents']), 2)

    def test_cached_images_and_receipt_are_reused_without_private_fetch(self):
        self.order()
        self.add_listing()
        order_url = 'https://order.ebay.com/ord/show?orderId=12-34567-89012'
        pdf = make_pdf('Tonga 1 Pound, order 12-34567-89012. Unit price $485.00.')
        sources.save_pdf(self.db, self.id, order_url, 'eBay Order Receipt 12-34567-89012', 'order', pdf, stuff.UPLOAD_FOLDER)
        # Simulate an order archive captured before this new note was linked.
        self.db.execute('DELETE FROM banknote_source_archives WHERE banknote_id=?', (self.id,))
        self.db.execute('DELETE FROM record_documents WHERE record_id=?', (self.id,))
        sources.archives.enqueue(self.db, 'banknotes', self.id, URL, 'eBay Original Listing', 'listing')
        asset = self.photo('https://i.ebayimg.com/images/g/front/s-l1600.jpg', stuff.UPLOAD_FOLDER)
        sources.listing_images.save(self.db, URL, [asset])
        self.db.commit()
        with patch.object(sources.archives, 'fetch_bytes', side_effect=ValueError('blocked')) as fetch:
            result = self.prepare()
        self.assertEqual([c.args[0] for c in fetch.call_args_list], [URL])
        self.assertIn('image_1', result['images'])
        self.assertTrue(any(e['kind'] == 'invoice' and 'Unit price $485' in e['text'] for e in result['evidence']))
        self.assertEqual(len(result['documents']), 2)

    def test_check_receives_imported_photos_and_order_evidence_same_run(self):
        self.blank()
        self.order()
        with patch.object(sources.archives, 'fetch_bytes', return_value=(self.gallery().encode(), 'text/html', URL)), \
                patch.object(sources.listing_images, 'download', side_effect=self.photo), \
                patch.object(stuff, 'fetch_banknote_specs', return_value={'country':'Tonga','denomination':'1 Pound'}) as lookup, \
                patch.object(stuff, 'ensure_country_history'):
            response = self.client.post('/banknotes/' + self.id + '/lookup-specs')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertTrue(lookup.call_args.args[0]['image_1'])
        self.assertEqual(response.json['filled']['purchase_date'], '2026-10-07')
        self.assertEqual(response.json['filled']['vendor'], 'Example Dealer')
        self.assertEqual(set(response.json['images']), {'image_1', 'image_2'})
        self.assertEqual(len(response.json['documents']), 3)
        self.assertFalse(self.note()['country'])

    def crop(self, raw, expect_aspect=None, meta=None):
        from PIL import Image
        meta['quad'] = [[20, 50], [380, 50], [380, 190], [20, 190]]
        out = io.BytesIO()
        Image.open(io.BytesIO(raw)).crop((20, 50, 380, 190)).save(out, format='JPEG')
        return out.getvalue()

    def check_imports(self):
        with patch.object(sources.archives, 'fetch_bytes', return_value=(self.gallery().encode(), 'text/html', URL)), \
                patch.object(sources.listing_images, 'download', side_effect=self.photo), \
                patch.object(stuff, 'fetch_banknote_specs', return_value={'country': 'Tonga'}), \
                patch.object(stuff, 'ensure_country_history'):
            response = self.client.post('/banknotes/' + self.id + '/lookup-specs')
        self.assertEqual(response.status_code, 200, response.json)
        return response.json

    def test_check_crops_new_imports_once_and_preserves_document_originals(self):
        from PIL import Image
        self.add_listing()
        with patch.object(stuff, '_trim_slabbed_note_image', side_effect=self.crop) as trim:
            first = self.check_imports()
            names = [self.note()[field] for field in ('image_1', 'image_2')]
            second = self.check_imports()
        self.assertEqual(trim.call_count, 2)
        self.assertEqual(trim.call_args.kwargs['expect_aspect'], 150 / 80)
        self.assertEqual(second['images'], {})
        self.assertEqual(first['documents'], second['documents'])
        folder = Path(stuff.UPLOAD_FOLDER)
        for field, name, original in zip(('image_1', 'image_2'), names, ('front.png', 'back.png')):
            self.assertEqual(first['images'][field], '/uploads/' + name)
            self.assertEqual(self.note()[field], name)
            with Image.open(folder / name) as image:
                self.assertEqual(image.size, (360, 140))
            source = stuff._banknote_vision_source(name, self.db)
            self.assertNotEqual(source, name)
            self.assertEqual((folder / source).read_bytes(), (folder / original).read_bytes())
            self.assertTrue(self.db.execute('SELECT quad FROM trimmed_image_sources WHERE trimmed=?', (name,)).fetchone()['quad'])
            self.assertTrue(any(d['filename'] == original for d in first['documents']))
            with Image.open(folder / original) as image:
                self.assertEqual(image.size, (400, 200))

    def test_check_only_crops_empty_slot_beside_existing_manual_crop(self):
        self.add_listing()
        self.photo('https://i.ebayimg.com/images/g/front/s-l1600.jpg', stuff.UPLOAD_FOLDER)
        folder = Path(stuff.UPLOAD_FOLDER)
        manual = self.crop((folder / 'front.png').read_bytes(), meta={})
        (folder / 'manual.jpg').write_bytes(manual)
        self.db.execute("UPDATE banknotes SET image_1='manual.jpg' WHERE id=?", (self.id,))
        self.db.execute("INSERT INTO trimmed_image_sources (trimmed,source,quad) VALUES ('manual.jpg','front.png','manual geometry')")
        self.db.commit()
        with patch.object(stuff, '_trim_slabbed_note_image', side_effect=self.crop) as trim:
            result = self.check_imports()
        self.assertEqual(trim.call_count, 1)
        self.assertEqual(set(result['images']), {'image_2'})
        self.assertEqual(self.note()['image_1'], 'manual.jpg')
        self.assertEqual((folder / 'manual.jpg').read_bytes(), manual)
        self.assertEqual(self.db.execute("SELECT quad FROM trimmed_image_sources WHERE trimmed='manual.jpg'").fetchone()['quad'], 'manual geometry')

    def test_check_keeps_originals_when_crop_fails(self):
        self.add_listing()
        with patch.object(stuff, '_trim_slabbed_note_image', side_effect=[ValueError('detector unavailable'), None]):
            result = self.check_imports()
        folder = Path(stuff.UPLOAD_FOLDER)
        for field, original in zip(('image_1', 'image_2'), ('front.png', 'back.png')):
            self.assertEqual(result['images'][field], '/uploads/' + self.note()[field])
            self.assertEqual((folder / self.note()[field]).read_bytes(), (folder / original).read_bytes())
        self.assertEqual(len(result['documents']), 3)
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trimmed_image_sources').fetchone()[0], 0)

    def test_manual_crop_during_check_wins_over_inflight_detection(self):
        self.add_listing()
        before = set(Path(stuff.UPLOAD_FOLDER).glob('*.jpg'))
        def concurrent_crop(raw, **kwargs):
            self.db.execute("UPDATE banknotes SET image_1='new-manual.jpg' WHERE id=?", (self.id,))
            self.db.commit()
            return self.crop(raw, **kwargs)
        with patch.object(stuff, '_trim_slabbed_note_image', side_effect=concurrent_crop):
            result = self.check_imports()
        self.assertEqual(self.note()['image_1'], 'new-manual.jpg')
        self.assertEqual(result['images']['image_1'], '/uploads/new-manual.jpg')
        self.assertEqual(self.db.execute('SELECT COUNT(*) FROM trimmed_image_sources').fetchone()[0], 1)
        crops = set(Path(stuff.UPLOAD_FOLDER).glob('*.jpg')) - before
        mappings = {r[0] for r in self.db.execute('SELECT trimmed FROM trimmed_image_sources')}
        self.assertIn(self.note()['image_2'], mappings)
        self.assertEqual({p.name for p in crops}, {self.note()['image_2']})

    def test_source_only_record_can_reach_model(self):
        self.blank()
        note = dict(self.note(), size_width=None, size_height=None,
                    _check_sources={'evidence':[dict(title='Order',kind='purchase',url=URL,text='Tonga 1 Pound',saved=True)]})
        with patch.object(stuff, '_require_anthropic_key', side_effect=RuntimeError('Reached model')):
            with self.assertRaisesRegex(RuntimeError, 'Reached model'):
                stuff.fetch_banknote_specs(note)

    def test_new_banknote_location_default_preserves_existing_and_explicit(self):
        page = self.client.get('/banknotes/new').data.decode()
        self.assertRegex(page, r'value="Carpinteria"\s+selected')
        self.assertIsNone(self.note()['property_name'])
        for location, expected in [('', 'Carpinteria'), ('NY', 'NY')]:
            with patch.object(stuff, 'ensure_country_history'):
                response = self.client.post('/banknotes/new', data=dict(owner='Mark',status='Ordered',property_name=location,order_number='12-34567-89012'))
            self.assertEqual(response.status_code, 302, response.data)
            created = response.location.rstrip('/').split('/')[-1]
            row = self.db.execute('SELECT property_name,order_number FROM banknotes WHERE id=?', (created,)).fetchone()
            self.assertEqual(row['property_name'], expected)
            self.assertEqual(row['order_number'], '12-34567-89012')
            self.db.execute('DELETE FROM banknotes WHERE id=?', (created,))
            self.db.commit()

    def test_ambiguous_order_stops_before_model_or_downloads(self):
        self.blank()
        self.order()
        self.order('-two', 'Canada 2 Dollars 1954')
        with patch.object(stuff, 'fetch_banknote_specs') as model, patch.object(sources.archives, 'fetch_bytes') as fetch:
            response = self.client.post('/banknotes/' + self.id + '/lookup-specs')
        self.assertEqual(response.status_code, 409)
        model.assert_not_called()
        fetch.assert_not_called()
        self.assertFalse(self.note()['image_1'])

    def test_conflicting_listing_does_not_attach_new_order_receipt(self):
        self.order()
        original_listings.add_source(self.db, 'banknotes', self.id, 'https://www.ebay.com/itm/325643741724')
        self.db.commit()
        with patch.object(stuff, 'fetch_banknote_specs') as model, patch.object(sources.archives, 'fetch_bytes') as fetch:
            response = self.client.post('/banknotes/' + self.id + '/lookup-specs')
        self.assertEqual(response.status_code, 409)
        model.assert_not_called()
        fetch.assert_not_called()
        self.assertEqual(response.json['documents'], [])

    def test_downloadable_invoice_pdf_is_attached_and_checked_once(self):
        url = 'https://www.cngcoins.com/invoice/431062.pdf'
        sources.archives.enqueue(self.db, 'banknotes', self.id, url, 'CNG Invoice 431062', 'invoice')
        self.db.commit()
        pdf = make_pdf('CNG Invoice 431062. Tonga 1 Pound. Unit price $485.00. Shipping $5.00.')
        with patch.object(sources.archives, 'fetch_bytes', return_value=(pdf, 'application/pdf', url)):
            first, second = self.prepare(), self.prepare()
        self.assertEqual(len(first['documents']), 1)
        self.assertEqual(first['documents'], second['documents'])
        self.assertEqual((Path(stuff.UPLOAD_FOLDER) / first['documents'][0]['filename']).read_bytes(), pdf)
        self.assertIn('Unit price $485', first['evidence'][0]['text'])

    def test_image_only_invoice_is_saved_but_not_claimed_verified(self):
        url = 'https://www.cngcoins.com/invoice/431062.pdf'
        sources.archives.enqueue(self.db, 'banknotes', self.id, url, 'CNG Invoice 431062', 'invoice')
        self.db.commit()
        pdf = make_pdf('')
        with patch.object(sources.archives, 'fetch_bytes', return_value=(pdf, 'application/pdf', url)):
            result = self.prepare()
        self.assertEqual(len(result['documents']), 1)
        self.assertEqual(result['evidence'], [])
        self.assertIn('scanned PDF has no readable text', ' '.join(result['warnings']))

    def test_live_listing_pdf_attaches_once_and_check_refetches(self):
        self.add_listing()
        with patch.object(sources.archives, 'fetch_bytes', return_value=(HTML.encode(), 'text/html', URL)) as fetch:
            first, second = self.prepare(), self.prepare()
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(len(first['documents']), 1)
        self.assertEqual(first['documents'], second['documents'])
        self.assertIn('Serial D/1 53153', first['evidence'][0]['text'])
        self.assertFalse(first['evidence'][0]['saved'])
        self.assertTrue((Path(stuff.UPLOAD_FOLDER) / first['documents'][0]['filename']).read_bytes().startswith(b'%PDF-'))

    def test_blocked_source_uses_saved_pdf_without_claiming_live(self):
        self.add_listing()
        self.invoice()
        with patch.object(sources.archives, 'fetch_bytes', side_effect=ValueError('sign in')):
            result = self.prepare()
        self.assertTrue(result['evidence'][0]['saved'])
        self.assertIn('live source could not be read', ' '.join(result['warnings']))
        self.assertNotIn('No readable invoice', ' '.join(result['warnings']))

    def test_search_or_login_page_is_not_archived(self):
        self.add_listing()
        with patch.object(sources.archives, 'fetch_bytes', return_value=(b'<h1>Sign in to your account</h1>', 'text/html', URL)):
            result = self.prepare()
        self.assertEqual(result['documents'], [])
        self.assertEqual(result['evidence'], [])

    def test_scanned_or_missing_pdf_reports_incomplete(self):
        self.invoice('')
        result = self.prepare()
        self.assertIn('PDF text could not be read', ' '.join(result['warnings']))
        self.assertEqual(result['evidence'], [])

    def test_route_supplies_receipt_to_model_and_preserves_price(self):
        self.invoice()
        with patch.object(stuff, 'fetch_banknote_specs', return_value={
            'price': '$527.59', 'sources': 'Receipt', 'size_width': 150, 'size_height': 80,
        }) as lookup, patch.object(stuff, 'ensure_country_history'):
            response = self.client.post('/banknotes/' + self.id + '/lookup-specs')
        self.assertEqual(response.status_code, 200, response.json)
        supplied = lookup.call_args.args[0]['_check_sources']['evidence']
        self.assertIn('Unit price $485.00', supplied[0]['text'])
        self.assertNotIn('price', response.json['overwritten'])
        self.assertEqual(self.note()['price'], '$485')
        self.assertEqual(len(response.json['documents']), 1)

    def test_quoted_unit_price_can_be_reviewed_but_not_silently_applied(self):
        self.invoice()
        self.db.execute("UPDATE banknotes SET price='$400' WHERE id=?", (self.id,))
        self.db.commit()
        with patch.object(stuff, 'fetch_banknote_specs', return_value={
            'price': '$485.00', 'purchase_evidence': {'price': 'Unit price $485.00'},
        }), patch.object(stuff, 'ensure_country_history'):
            response = self.client.post('/banknotes/' + self.id + '/lookup-specs')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['overwritten']['price']['new'], '$485')
        self.assertEqual(self.note()['price'], '$400')

    def test_order_host_cannot_redirect_to_arbitrary_host(self):
        self.assertTrue(sources.archives.safe_remote('https://order.ebay.com/ord/show?orderId=23-15242-04872'))
        self.assertFalse(sources.archives.safe_remote('https://order.ebay.com.evil.test/receipt.pdf'))
        self.assertFalse(sources.archives.safe_remote('https://order.ebay.com@localhost/receipt.pdf'))

    def test_order_total_or_unrelated_quote_is_not_a_unit_price(self):
        self.invoice()
        for quote in ('Unit price $485.00', 'Total $527.59.'):
            with patch.object(stuff, 'fetch_banknote_specs', return_value={
                'price': '$527.59', 'purchase_evidence': {'price': quote},
            }), patch.object(stuff, 'ensure_country_history'):
                response = self.client.post('/banknotes/' + self.id + '/lookup-specs')
            self.assertEqual(response.status_code, 200, response.json)
            self.assertNotIn('price', response.json['overwritten'])

    def test_receipt_time_placed_verifies_purchase_date(self):
        self.invoice('Order info. Time placed Oct 7, 2026 at 12:10 PM. Tonga 1 Pound. Unit price $485.00.')
        with patch.object(stuff, 'fetch_banknote_specs', return_value={
            'purchase_date': '2026-10-07',
            'purchase_evidence': {'purchase_date': 'Time placed Oct 7, 2026 at 12:10 PM'},
        }), patch.object(stuff, 'ensure_country_history'):
            response = self.client.post('/banknotes/' + self.id + '/lookup-specs')
        self.assertEqual(response.status_code, 200, response.json)
        self.assertEqual(response.json['filled']['purchase_date'], '2026-10-07')


if __name__ == '__main__':
    unittest.main()
