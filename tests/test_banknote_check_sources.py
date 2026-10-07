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


if __name__ == '__main__':
    unittest.main()
