"""Shared document scan service for every collection type.

One place reads uploaded and archived documents:

* ``pdf_text`` extracts the text layer of a receipt, invoice or saved listing
  PDF with the purchase-evidence limits (size, pages, text length, minimum
  readable text). Results are memoised by the document's sha256, so the same
  saved receipt is not re-parsed for every Check and every original-listing
  comparison.
* ``is_pdf`` recognises a PDF by its bytes (and an optional MIME type).
* ``render_first_page`` renders a PDF's first page at the size its consumer
  needs (thumbnails), instead of a fixed 2x page render.

No model is called here: purchase evidence stays literal text, and image-only
PDFs are reported as unreadable rather than guessed.
"""
from collections import OrderedDict
import hashlib
import threading
from pathlib import Path

MAX_BYTES = 12_000_000
MAX_PAGES = 30
MAX_CHARS = 60000
MIN_CHARS = 40

_MEMO = OrderedDict()
_MEMO_LOCK = threading.Lock()
_MEMO_MAX = 64


def is_pdf(data, mime=None):
    """True for PDF bytes; with a MIME type, only the PDF/octet-stream types."""
    if not isinstance(data, (bytes, bytearray)) or not data.startswith(b'%PDF-'):
        return False
    return mime is None or mime in ('application/pdf', 'application/octet-stream')


def _read(source):
    if isinstance(source, (bytes, bytearray)):
        if len(source) > MAX_BYTES:
            raise ValueError('PDF is too large for this check')
        return bytes(source)
    path = Path(source)
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('PDF is too large for this check')
    return path.read_bytes()


def _extract(data):
    import pypdfium2 as pdfium
    with pdfium.PdfDocument(data) as pdf:
        if len(pdf) > MAX_PAGES:
            raise ValueError('PDF exceeds the 30-page check limit')
        parts = []
        for page in pdf:
            try:
                text = page.get_textpage()
                try:
                    parts.append(text.get_text_range())
                finally:
                    text.close()
            finally:
                page.close()
    result = '\n'.join(parts).strip()
    if len(result) > MAX_CHARS:
        raise ValueError('PDF text exceeds the check limit')
    if len(result) < MIN_CHARS:
        raise ValueError('PDF has no readable text; a text-readable invoice is needed')
    return result


def pdf_text(source):
    """Text of a PDF path or bytes, with the purchase-evidence limits.

    Raises ValueError with the same messages the banknote Check has always
    reported (too large, page limit, text limit, no readable text)."""
    data = _read(source)
    digest = hashlib.sha256(data).hexdigest()
    with _MEMO_LOCK:
        hit = _MEMO.get(digest)
        if hit is not None:
            _MEMO.move_to_end(digest)
    if hit is not None:
        if isinstance(hit, ValueError):
            raise ValueError(str(hit))
        return hit
    try:
        result = _extract(data)
    except ValueError as error:
        result = error
    with _MEMO_LOCK:
        _MEMO[digest] = result
        while len(_MEMO) > _MEMO_MAX:
            _MEMO.popitem(last=False)
    if isinstance(result, ValueError):
        raise ValueError(str(result))
    return result


def clear_memo():
    with _MEMO_LOCK:
        _MEMO.clear()


def render_first_page(path, max_edge):
    """PIL image of page 1, rendered so its long edge is about 1.5x max_edge.

    The thumbnail path previously rendered every page at scale 2.0 (a letter
    page becomes 1224x1584 pixels) and then shrank it to 320 pixels."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(str(path))
    try:
        page = doc[0]
        try:
            width, height = page.get_size()
            longest = max(width, height) or 1.0
            scale = min(2.0, max(0.25, 1.5 * max_edge / longest))
            bitmap = page.render(scale=scale)
            return bitmap.to_pil()
        finally:
            page.close()
    finally:
        doc.close()
