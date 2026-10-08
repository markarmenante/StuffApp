"""Purchase evidence for an explicit banknote Check, never a similar-item search."""
from pathlib import Path
import re
import time
import uuid
import shutil
from datetime import datetime, timezone
from urllib.parse import urlsplit

import original_listings as listings
import source_documents as archives
import purchase_orders
import listing_images


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


def save_pdf(db, record_id, url, title, kind, pdf, folder, category='banknotes'):
    """Attach once per source; preserve existing PDFs and user-edited document titles."""
    if not pdf.startswith(b'%PDF-'):
        raise ValueError('Not a PDF')
    archives.enqueue(db, category, record_id, url, title, kind)
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


def listing_photos(db, category, record_id, url, folder, html=None, final=None):
    """Keep originals in Documents; fill only empty display-photo slots."""
    if category not in archives.TABLES:
        raise ValueError('Unsupported category')
    warnings = []
    if html is not None:
        assets = []
        deadline = time.monotonic() + 35
        urls = listing_images.image_urls(html, url, final)
        if not urls:
            warnings.append('No downloadable original photos were found on this listing.')
        for position, image_url in enumerate(urls):
            if time.monotonic() > deadline:
                warnings.append('Additional listing images remain to be downloaded; run Check again.')
                break
            try:
                asset = db.execute('SELECT * FROM original_image_assets WHERE url=?', (image_url,)).fetchone()
                if asset and (Path(folder) / asset['filename']).is_file():
                    asset = dict(asset)
                else:
                    asset = listing_images.download(image_url, folder)
                assets.append(dict(asset, position=position))
            except Exception:
                warnings.append('An original listing image could not be downloaded.')
        listing_images.save(db, url, assets)
    listing_images.attach_saved(db, category, record_id, url)
    photos = db.execute('SELECT s.position,a.filename FROM original_listing_image_sources s '
                       'JOIN original_image_assets a ON a.url=s.image_url WHERE s.listing_url=? '
                       'ORDER BY s.position', (url,)).fetchall()
    images = {}
    for photo in photos:
        if photo['position'] not in (0, 1):
            continue
        field = 'image_' + str(photo['position'] + 1)
        current = db.execute(f'SELECT {field} FROM {category} WHERE id=?', (record_id,)).fetchone()
        if not current or current[field] or Path(photo['filename']).name != photo['filename']:
            continue
        source = Path(folder) / photo['filename']
        if not source.is_file():
            continue
        filename = uuid.uuid4().hex + source.suffix
        destination = Path(folder) / filename
        shutil.copyfile(source, destination)
        saved = db.execute(f"UPDATE {category} SET {field}=?,updated_at=? WHERE id=? AND ({field} IS NULL OR {field}='')",
                           (filename, datetime.now(timezone.utc).isoformat(), record_id)).rowcount
        if saved:
            images[field] = '/uploads/' + filename
        else:
            destination.unlink(missing_ok=True)
    db.commit()
    return images, warnings


def prepare(db, record, folder, fonts, category='banknotes'):
    if category not in archives.TABLES:
        raise ValueError('Unsupported category')
    record = dict(record)
    record_id = record['id']
    evidence, reports, warnings = [], [], []
    images, purchase = {}, {}
    sources = []
    order = purchase_orders.order_reference(db, category, record)
    item = purchase_orders.ebay_item_for_order(db, category, record)
    if item:
        text = f"Order number: {item['order_id']}\nItem ID: {item['item_id']}\nItem: {item['title']}\nSeller: {item['seller']}\nPurchase date: {(item['ordered_at'] or '')[:10]}"
        purchase = dict(vendor=item['seller'], purchase_date=(item['ordered_at'] or '')[:10])
        evidence.append(dict(title='eBay Purchases ' + item['order_id'], kind='purchase',
                             url='https://order.ebay.com/ord/show?orderId=' + item['order_id'], text=text, saved=True))
        reports.append('Exact purchased item identified from eBay Purchases.')
    elif record.get('order_number') and order['provider'] == 'eBay':
        warnings.append('This order has not been uniquely matched in the synced eBay Purchases. Sync Purchases or add the exact item listing; multi-item orders need identifying details.')
    if record.get('order_number') and order['url'] and not order['url'].startswith('/uploads/'):
        sources.append(dict(url=order['url'], kind=order['kind'],
                            title=f"{order['provider']} {order['kind'].title()} {order['number']}"))
    table, key, _ = listings.TABLES[category]
    row = db.execute(f'SELECT url FROM {table} WHERE {key}=?', (record_id,)).fetchone()
    entered_listing = 'https://www.ebay.com/itm/' + item['item_id'] if item else None
    conflict = bool(row and entered_listing and row['url'] != entered_listing)
    unresolved = category == 'banknotes' and order['provider'] == 'eBay' and not item and not row and bool(
        db.execute('SELECT 1 FROM ebay_order_items WHERE order_id=? LIMIT 1', (record.get('order_number'),)).fetchone())
    if conflict or unresolved:
        reason = ('The pasted order identifies a different listing from the one already linked. Confirm the item before replacing its sources.'
                  if conflict else 'This order does not identify one unambiguous banknote. Check the country, denomination and serial or certificate number before importing it.')
        warnings.append(reason)
        docs = db.execute("SELECT title,filename FROM record_documents WHERE category=? AND record_id=? AND doc_set='main' ORDER BY position,created_at,id", (category, record_id)).fetchall()
        return dict(evidence=[], reports=[], warnings=warnings, documents=[dict(d) for d in docs], images={}, purchase={}, blocked=reason)
    if record.get('order_number') and order['url']:
        # Reuse the exact receipt already captured by the signed-in browser,
        # including a shared order PDF that belongs to several purchased items.
        archived = db.execute('SELECT filename FROM purchase_source_archives WHERE url=?', (order['url'],)).fetchone()
        if archived:
            archives.enqueue(db, category, record_id, order['url'],
                             f"{order['provider']} {order['kind'].title()} {order['number']}", order['kind'])
            archives.attach_saved(db)
            db.commit()
    url = entered_listing or (row['url'] if row else listings.candidate(db, category, record))
    if url:
        listings.add_source(db, category, record_id, url)
        vendor = listings.exact_listing(url)[1]
        identity = item['title'] if item else ' '.join(str(record.get(f) or '') for f in ('country', 'region', 'denomination')).strip()
        title = ' - '.join(p for p in (vendor + ' Original Listing', record.get('cat_id'), identity) if p)
        archives.enqueue(db, category, record_id, url, title, 'listing')
        sources.append(dict(url=url, title=title, kind='listing'))
        db.commit()
    else:
        warnings.append('Original listing is not linked. Add the exact listing URL to References as "Listing: URL".')

    archive_table, archive_key = archives.TABLES[category]
    for row in db.execute(f'SELECT a.url,a.title,a.kind FROM {archive_table} l '
                          f'JOIN purchase_source_archives a ON a.url=l.url WHERE l.{archive_key}=?', (record_id,)):
        if row['kind'] != 'listing' and not row['url'].startswith('/uploads/'):
            sources.append(dict(row))
    linked_orders = db.execute('SELECT i.order_id FROM banknote_ebay_links l JOIN ebay_order_items i '
                              'ON i.line_key=l.line_key WHERE l.banknote_id=?', (record_id,)) if category == 'banknotes' else []
    for row in linked_orders:
        if record.get('order_number') and row['order_id'] != record['order_number']:
            continue
        if re.fullmatch(r'\d{2}-\d{5}-\d{5}', row['order_id'] or ''):
            sources.append(dict(url='https://order.ebay.com/ord/show?orderId=' + row['order_id'],
                                title='eBay Order Receipt ' + row['order_id'], kind='order'))

    seen_urls, live_filenames = set(), set()
    for source in sources[:6]:
        url, kind, title = source['url'], source['kind'], source['title']
        if url in seen_urls:
            continue
        seen_urls.add(url)
        parts = urlsplit(url)
        private_order = kind in ('order', 'invoice') and (
            parts.hostname == 'order.ebay.com' or
            (parts.hostname in ('www.vcoins.com', 'vcoins.com') and '/myaccount/' in parts.path.lower()))
        if private_order:
            saved = db.execute('SELECT filename FROM purchase_source_archives WHERE url=?', (url,)).fetchone()
            if not saved or not saved['filename'] or not (Path(folder) / saved['filename']).is_file():
                warnings.append(title + ': PDF not yet available from the signed-in browser. Check will not retry private order pages or bypass access limits.')
            continue
        if kind == 'listing':
            found, problems = listing_photos(db, category, record_id, url, folder)
            images.update(found)
            warnings.extend(problems)
        try:
            data, mime, final = archives.fetch_bytes(url, limit=2_000_000 if kind == 'listing' else 12_000_000)
            if data.startswith(b'%PDF-') and mime in ('application/pdf', 'application/octet-stream'):
                # Keep image-only receipts too, but never claim their text was checked.
                import tempfile
                with tempfile.NamedTemporaryFile(suffix='.pdf') as temp:
                    temp.write(data)
                    temp.flush()
                    try:
                        text = pdf_text(Path(temp.name))
                    except ValueError as error:
                        if not str(error).startswith('PDF has no readable text'):
                            raise
                        filename = save_pdf(db, record_id, url, title, kind, data, folder, category)
                        live_filenames.add(filename)
                        reports.append(title + ': original PDF saved in Documents.')
                        warnings.append(title + ': scanned PDF has no readable text; its fields are not verified.')
                        continue
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
                try:
                    found, problems = listing_photos(db, category, record_id, url, folder, html, final)
                    images.update(found)
                    warnings.extend(problems)
                except Exception:
                    db.rollback()
                    warnings.append('Original listing photos could not all be saved; the listing PDF is still being attached.')
            else:
                raise ValueError('Invoice or receipt requires a signed-in browser or an uploaded PDF')
            filename = save_pdf(db, record_id, url, title, kind, pdf, folder, category)
            live_filenames.add(filename)
            if sum(len(e['text']) for e in evidence) + len(text) > 120000:
                warnings.append(title + ': PDF saved, but source text exceeds this check limit.')
                continue
            evidence.append(dict(title=title, kind=kind, url=url, text=text, saved=False))
            reports.append(title + ': live source checked; PDF in Documents.')
        except Exception:
            db.rollback()
            warnings.append(title + ': live source could not be read; any saved PDF will be checked below.')

    docs = db.execute("SELECT title,filename FROM record_documents WHERE category=? AND record_id=? "
                      "AND doc_set='main' ORDER BY position,created_at,id", (category, record_id)).fetchall()
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
                documents=[dict(d) for d in docs], images=images, purchase=purchase)


def evidence_text(prepared):
    return '\n\n'.join(f"SOURCE: {e['title']} ({'synced purchase' if e['kind'] == 'purchase' else 'saved PDF' if e['saved'] else 'live source'})\nURL: {e['url']}\n{e['text']}"
                       for e in prepared.get('evidence', []))
