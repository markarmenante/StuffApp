"""Purchase evidence for an explicit banknote Check, never a similar-item search."""
from pathlib import Path
import re
import time
import uuid

import original_listings as listings
import source_documents as archives


def pdf_text(path):
    import pypdfium2 as pdfium
    if path.stat().st_size > 12_000_000:
        raise ValueError('PDF is too large for this check')
    with pdfium.PdfDocument(str(path)) as pdf:
        if len(pdf) > 30:
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
        if len(result) > 60000:
            raise ValueError('PDF text exceeds the check limit')
        if len(result) < 40:
            raise ValueError('PDF has no readable text; a text-readable invoice is needed')
        return result


def save_pdf(db, record_id, url, title, kind, pdf, folder):
    """Attach once per source; preserve existing PDFs and user-edited document titles."""
    if not pdf.startswith(b'%PDF-'):
        raise ValueError('Not a PDF')
    archives.enqueue(db, 'banknotes', record_id, url, title, kind)
    current = db.execute('SELECT filename FROM purchase_source_archives WHERE url=?', (url,)).fetchone()
    if not current:
        raise ValueError('Unsupported purchase source')
    filename = current['filename']
    if filename and Path(filename).name != filename:
        raise ValueError('Invalid archive filename')
    if not filename or not (Path(folder) / filename).is_file():
        filename = filename or 'source_' + uuid.uuid4().hex + '.pdf'
        path = Path(folder) / filename
        path.write_bytes(pdf)
        try:
            db.execute('UPDATE purchase_source_archives SET filename=?,saved_at=?,lease_until=0 WHERE url=?',
                       (filename, time.time(), url))
            archives.attach_saved(db)
            db.commit()
        except Exception:
            db.rollback()
            path.unlink(missing_ok=True)
            raise
    else:
        archives.attach_saved(db)
        db.commit()
    return filename


def prepare(db, record, folder, fonts):
    record = dict(record)
    record_id = record['id']
    evidence, reports, warnings = [], [], []
    sources = []
    row = db.execute('SELECT url FROM banknote_original_listings WHERE banknote_id=?', (record_id,)).fetchone()
    url = row['url'] if row else listings.candidate(db, 'banknotes', record)
    if url:
        listings.add_source(db, 'banknotes', record_id, url)
        vendor = listings.exact_listing(url)[1]
        title = f"{vendor} Original Listing - {record.get('cat_id') or ''} - {record.get('country') or ''} {record.get('denomination') or ''}".strip()
        sources.append(dict(url=url, title=title, kind='listing'))
        db.commit()
    else:
        warnings.append('Original listing is not linked. Add the exact listing URL to References as "Listing: URL".')

    for row in db.execute('SELECT a.url,a.title,a.kind FROM banknote_source_archives l '
                          'JOIN purchase_source_archives a ON a.url=l.url WHERE l.banknote_id=?', (record_id,)):
        if row['kind'] != 'listing' and not row['url'].startswith('/uploads/'):
            sources.append(dict(row))
    for row in db.execute('SELECT i.order_id FROM banknote_ebay_links l JOIN ebay_order_items i '
                          'ON i.line_key=l.line_key WHERE l.banknote_id=?', (record_id,)):
        if re.fullmatch(r'\d{2}-\d{5}-\d{5}', row['order_id'] or ''):
            sources.append(dict(url='https://order.ebay.com/ord/show?orderId=' + row['order_id'],
                                title='eBay Order Receipt ' + row['order_id'], kind='order'))

    seen_urls, live_filenames = set(), set()
    for source in sources[:6]:
        url, kind, title = source['url'], source['kind'], source['title']
        if url in seen_urls:
            continue
        seen_urls.add(url)
        try:
            data, mime, final = archives.fetch_bytes(url, limit=2_000_000 if kind == 'listing' else 12_000_000)
            if data.startswith(b'%PDF-') and mime in ('application/pdf', 'application/octet-stream'):
                # Validate/extract before attaching: malformed or scanned-only files cannot verify fields.
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.pdf') as temp:
                    temp.write(data)
                    temp.flush()
                    text = pdf_text(Path(temp.name))
                pdf = data
            elif kind == 'listing':
                html = data.decode('utf-8', errors='replace')
                if listings.page_state(url, 200, html, final) != 'available':
                    raise ValueError('Original listing is unavailable or requires sign-in')
                parser = listings.PageText()
                parser.feed(html)
                text = ' '.join(' '.join(parser.text).split())[:60000]
                pdf = archives.source_pdf(html, url, title, fonts)
                now = time.time()
                db.execute("UPDATE original_listing_pages SET state='available',checked_at=?,next_check_at=? WHERE url=?",
                           (now, now + listings.FRESH_SECONDS, url))
            else:
                raise ValueError('Invoice or receipt requires a signed-in browser or an uploaded PDF')
            filename = save_pdf(db, record_id, url, title, kind, pdf, folder)
            live_filenames.add(filename)
            if sum(len(e['text']) for e in evidence) + len(text) > 120000:
                warnings.append(title + ': PDF saved, but source text exceeds this check limit.')
                continue
            evidence.append(dict(title=title, kind=kind, url=url, text=text, saved=False))
            reports.append(title + ': live source checked; PDF in Documents.')
        except Exception:
            db.rollback()
            warnings.append(title + ': live source could not be read; any saved PDF will be checked below.')

    docs = db.execute("SELECT title,filename FROM record_documents WHERE category='banknotes' AND record_id=? "
                      "AND doc_set='main' ORDER BY position,created_at,id", (record_id,)).fetchall()
    seen_files = set(live_filenames)
    for doc in docs:
        filename = doc['filename'] or ''
        if filename in seen_files or not filename.lower().endswith('.pdf'):
            continue
        seen_files.add(filename)
        title = doc['title'] or 'Saved document'
        if len(evidence) >= 8:
            warnings.append(title + ': not checked because the eight-source limit was reached.')
            continue
        try:
            if Path(filename).name != filename:
                raise ValueError('Invalid file')
            text = pdf_text(Path(folder) / filename)
            if sum(len(e['text']) for e in evidence) + len(text) > 120000:
                warnings.append(title + ': source text exceeds this check limit.')
                continue
            kind = 'invoice' if re.search(r'invoice|receipt|\border\b', title, re.I) else 'document'
            evidence.append(dict(title=title, kind=kind, url='/uploads/' + filename, text=text, saved=True))
            reports.append(title + ': saved PDF checked.')
        except Exception:
            warnings.append(title + ': PDF text could not be read; its fields are not verified.')
    if not any(e['kind'] in ('order', 'invoice') for e in evidence):
        warnings.append('No readable invoice or order receipt found. Purchase amount and date are not verified against a receipt.')
    return dict(evidence=evidence, reports=reports, warnings=warnings,
                documents=[dict(d) for d in docs])


def evidence_text(prepared):
    return '\n\n'.join(f"SOURCE: {e['title']} ({'saved PDF' if e['saved'] else 'live source'})\nURL: {e['url']}\n{e['text']}"
                       for e in prepared.get('evidence', []))
