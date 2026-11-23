"""Shared document scan service: PDF text limits, memo, sniffing, thumbnails."""
import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas

import banknote_check_sources
import document_scan

RECEIPT = 'Item number: 123456789012  Price: US $45.00  Serial D/1 53153  Order 12-34567-89012'


def pdf_bytes(pages=1, text=RECEIPT):
    out = io.BytesIO()
    doc = canvas.Canvas(out, pagesize=letter)
    for _ in range(pages):
        if text:
            doc.drawString(72, 720, text)
        doc.showPage()
    doc.save()
    return out.getvalue()


class DocumentScanTests(unittest.TestCase):
    def setUp(self):
        document_scan.clear_memo()
        self.folder = Path(tempfile.mkdtemp(prefix='doc-scan-'))

    def write(self, name, data):
        path = self.folder / name
        path.write_bytes(data)
        return path

    def test_text_from_path_or_bytes_and_the_compatibility_entry_point(self):
        data = pdf_bytes()
        path = self.write('receipt.pdf', data)
        self.assertIn('Serial D/1 53153', document_scan.pdf_text(path))
        self.assertEqual(document_scan.pdf_text(data), document_scan.pdf_text(path))
        self.assertIn('Serial D/1 53153', banknote_check_sources.pdf_text(path))

    def test_the_same_document_is_parsed_once(self):
        data = pdf_bytes()
        first = self.write('a.pdf', data)
        copy = self.write('b.pdf', data)
        with patch.object(document_scan, '_extract', wraps=document_scan._extract) as extract:
            document_scan.pdf_text(first)
            document_scan.pdf_text(copy)
            document_scan.pdf_text(data)
        self.assertEqual(extract.call_count, 1, 'identical bytes share one parse')

    def test_limits_keep_their_messages(self):
        with self.assertRaisesRegex(ValueError, '^PDF has no readable text; a text-readable invoice is needed$'):
            document_scan.pdf_text(self.write('scan.pdf', pdf_bytes(text='')))
        with self.assertRaisesRegex(ValueError, '^PDF exceeds the 30-page check limit$'):
            document_scan.pdf_text(self.write('long.pdf', pdf_bytes(pages=31)))
        big = self.write('big.pdf', b'%PDF-' + b'0' * (document_scan.MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, '^PDF is too large for this check$'):
            document_scan.pdf_text(big)
        # A memoised failure repeats the same message.
        with self.assertRaisesRegex(ValueError, 'no readable text'):
            document_scan.pdf_text(pdf_bytes(text=''))

    def test_pdf_sniffing(self):
        self.assertTrue(document_scan.is_pdf(b'%PDF-1.7 ...'))
        self.assertTrue(document_scan.is_pdf(b'%PDF-1.7', 'application/pdf'))
        self.assertTrue(document_scan.is_pdf(b'%PDF-1.7', 'application/octet-stream'))
        self.assertFalse(document_scan.is_pdf(b'%PDF-1.7', 'text/html'))
        self.assertFalse(document_scan.is_pdf(b'<html>', 'application/pdf'))
        self.assertFalse(document_scan.is_pdf(None))

    def test_thumbnail_render_is_sized_for_its_consumer(self):
        path = self.write('page.pdf', pdf_bytes())
        image = document_scan.render_first_page(path, 320)
        self.assertEqual(max(image.size), 480, 'about 1.5x the 320 px thumbnail, not a 2x page render')


if __name__ == '__main__':
    unittest.main(verbosity=1)
