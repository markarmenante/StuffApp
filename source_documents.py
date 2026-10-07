"""One-time PDF source archives, attached without replacing existing documents."""
from datetime import datetime, timezone
from html import escape
from io import BytesIO
from pathlib import Path
import re
import time
from urllib.parse import urlsplit, urljoin, unquote
from urllib.request import Request, build_opener
from urllib.error import HTTPError
import uuid

TABLES = {'coins': ('coin_source_archives', 'coin_id'),
          'banknotes': ('banknote_source_archives', 'banknote_id')}
HOSTS = {'vcoins.com', 'www.vcoins.com', 'cngcoins.com', 'www.cngcoins.com',
         'ebay.com', 'www.ebay.com', 'order.ebay.com', 'ma-shops.com', 'www.ma-shops.com'}
IMAGE_HOSTS = HOSTS | {'images.vcoins.com', 'images.cngcoins.com', 'i.ebayimg.com',
                       'img.ma-shops.com'}


def safe_remote(url, hosts=HOSTS):
    try:
        parts = urlsplit(url)
        return (parts.scheme == 'https' and parts.hostname in hosts and not parts.username
                and not parts.password and parts.port in (None, 443)
                and not re.search(r'[\x00-\x20\\]', url))
    except (ValueError, TypeError):
        return False


def enqueue(db, category, record_id, url, title, kind):
    if category not in TABLES or kind not in ('listing', 'invoice', 'order'):
        return
    if not safe_remote(url) and not re.fullmatch(r'/uploads/[^/]+\.pdf', url, re.I):
        return
    table, key = TABLES[category]
    db.execute('INSERT INTO purchase_source_archives (url,title,kind) VALUES (?,?,?) '
               'ON CONFLICT(url) DO NOTHING', (url, title, kind))
    db.execute(f'INSERT INTO {table} ({key},url) VALUES (?,?) ON CONFLICT DO NOTHING', (record_id, url))


def fetch_bytes(url, hosts=HOSTS, limit=2000000):
    from original_listings import NoRedirect
    if not safe_remote(url, hosts):
        raise ValueError('Unsupported source host')
    initial = urlsplit(url).hostname
    opener = build_opener(NoRedirect())
    for _ in range(4):
        try:
            with opener.open(Request(url, headers={'User-Agent':'Mozilla/5.0'}), timeout=10) as response:
                data = response.read(limit + 1)
                if len(data) > limit:
                    raise ValueError('Source too large')
                return data, response.headers.get_content_type(), url
        except HTTPError as error:
            if error.code not in (301,302,303,307,308):
                raise
            target = urljoin(url, error.headers.get('Location', ''))
            if not safe_remote(target, hosts) or urlsplit(target).hostname.removeprefix('www.') != initial.removeprefix('www.'):
                raise ValueError('Unexpected source redirect')
            url = target
    raise ValueError('Too many source redirects')


def source_pdf(html, url, title, fonts):
    from original_listings import PageText, page_state
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
    from PIL import Image as PILImage
    if page_state(url, 200, html, url) != 'available':
        raise ValueError('Cannot archive an unreadable listing')

    class ArchiveText(PageText):
        def __init__(self):
            super().__init__()
            self.image = None
            self.product_started = False
            self.product_finished = False
        def handle_starttag(self, tag, attrs):
            super().handle_starttag(tag, attrs)
            attrs = dict(attrs)
            if tag == 'meta' and (attrs.get('property') or attrs.get('name')) == 'og:image':
                self.image = urljoin(url, attrs.get('content', ''))
            if urlsplit(url).hostname in ('vcoins.com', 'www.vcoins.com'):
                if tag == 'h1' and not self.product_started:
                    self.text = []
                    self.product_started = True
                if attrs.get('id', '').endswith('_pnlProductsRelated'):
                    self.product_finished = True
            if tag in ('p','br','div','tr','li','h1','h2','h3'):
                self.text.append('\n')
        def handle_data(self, data):
            if not self.product_finished:
                super().handle_data(data)

    parsed = ArchiveText()
    parsed.feed(html)
    text = '\n'.join(' '.join(line.split()) for line in ' '.join(parsed.text).splitlines())
    regular, bold, _ = fonts()
    style = ParagraphStyle('SourceBody', fontName=regular, fontSize=9, leading=13,
                           spaceAfter=5, splitLongWords=True)
    heading = ParagraphStyle('SourceTitle', parent=style, fontName=bold, fontSize=15, leading=19, spaceAfter=10)
    small = ParagraphStyle('SourceMeta', parent=style, fontSize=8, leading=11, textColor='#555555')
    story = [Paragraph(escape(title), heading),
             Paragraph('Source: ' + escape(url), small),
             Paragraph('Saved ' + datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC'), small),
             Paragraph('Readable source copy. Page text is preserved, not summarized; web navigation may be included.', small),
             Spacer(1,12)]
    if parsed.image and safe_remote(parsed.image, IMAGE_HOSTS):
        try:
            data, kind, _ = fetch_bytes(parsed.image, IMAGE_HOSTS, 8000000)
            if not kind.startswith('image/'):
                raise ValueError('Not an image')
            im = PILImage.open(BytesIO(data))
            if im.width * im.height > 30000000 or min(im.size) < 120:
                raise ValueError('Image dimensions unsupported')
            im.thumbnail((1800,1800))
            clean = BytesIO()
            im.convert('RGB').save(clean, 'JPEG', quality=92)
            clean.seek(0)
            scale = min(480/im.width,280/im.height,1)
            story.extend([Image(clean,width=im.width*scale,height=im.height*scale),Spacer(1,12)])
        except Exception:
            pass  # Source text remains useful if a CDN does not permit image access.
    for line in text.splitlines():
        if line.strip():
            story.append(Paragraph(escape(line), style))
    output = BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4, rightMargin=40, leftMargin=40,
                            topMargin=38,bottomMargin=38,title=title,author='Source archive')
    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont(regular,8)
        canvas.drawRightString(A4[0]-40,22,str(document.page))
        canvas.restoreState()
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()


def attach_saved(db):
    for category, (table, key) in TABLES.items():
        for row in db.execute(f'SELECT l.{key} AS record_id,a.* FROM {table} l '
                               'JOIN purchase_source_archives a ON a.url=l.url '
                               'WHERE l.attached=0 AND a.filename IS NOT NULL').fetchall():
            if not db.execute('SELECT 1 FROM record_documents WHERE category=? AND record_id=? AND filename=?',
                              (category,row['record_id'],row['filename'])).fetchone():
                position = db.execute("SELECT COALESCE(MAX(position),-1)+1 FROM record_documents "
                                       "WHERE category=? AND record_id=? AND doc_set='main'",
                                       (category,row['record_id'])).fetchone()[0]
                db.execute("INSERT INTO record_documents (id,category,record_id,doc_set,position,title,filename) "
                           "VALUES (?,?,?,'main',?,?,?)",
                           (str(uuid.uuid4()),category,row['record_id'],position,row['title'],row['filename']))
                db.execute(f'UPDATE {category} SET updated_at=? WHERE id=?',
                           (datetime.now(timezone.utc).isoformat(),row['record_id']))
            db.execute(f'UPDATE {table} SET attached=1 WHERE {key}=? AND url=?', (row['record_id'],row['url']))


def run_once(connect, upload_folder, fonts):
    from original_listings import page_state
    db = connect()
    path = None
    try:
        now, lease = time.time(), time.time()+180
        db.execute('BEGIN IMMEDIATE')
        attach_saved(db)
        row = db.execute('SELECT * FROM purchase_source_archives a WHERE filename IS NULL AND attempts<3 '
                         'AND next_attempt<=? AND lease_until<? AND '
                         '(EXISTS(SELECT 1 FROM coin_source_archives l WHERE l.url=a.url) OR '
                         'EXISTS(SELECT 1 FROM banknote_source_archives l WHERE l.url=a.url)) LIMIT 1',
                         (now,now)).fetchone()
        if not row:
            db.commit()
            return False
        db.execute('UPDATE purchase_source_archives SET lease_until=?,attempts=attempts+1 WHERE url=?', (lease,row['url']))
        db.commit()
        try:
            if row['url'].startswith('/uploads/'):
                filename = unquote(row['url'].removeprefix('/uploads/'))
                if Path(filename).name != filename or not (Path(upload_folder)/filename).is_file():
                    raise ValueError('Saved invoice is missing')
                with (Path(upload_folder)/filename).open('rb') as file:
                    if file.read(5) != b'%PDF-':
                        raise ValueError('Saved source is not PDF')
            else:
                data, mime, final = fetch_bytes(row['url'], limit=12000000 if row['kind'] != 'listing' else 2000000)
                if data.startswith(b'%PDF-') and mime in ('application/pdf','application/octet-stream'):
                    pdf = data
                else:
                    html = data.decode('utf-8',errors='replace')
                    if row['kind'] == 'listing':
                        if page_state(row['url'],200,html,final) != 'available':
                            raise ValueError('Listing is not readable')
                    else:
                        # Login-required invoice pages must be archived through the signed-in browser.
                        raise ValueError('Invoice is not a downloadable PDF')
                    pdf = source_pdf(html,row['url'],row['title'],fonts)
                filename = 'source_' + uuid.uuid4().hex + '.pdf'
                path = Path(upload_folder)/filename
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_bytes(pdf)
            db.execute('BEGIN IMMEDIATE')
            saved = db.execute('UPDATE purchase_source_archives SET filename=?,saved_at=?,lease_until=0 '
                               'WHERE url=? AND lease_until=?', (filename,time.time(),row['url'],lease)).rowcount
            if saved:
                attach_saved(db)
                path = None
            db.commit()
        except Exception:
            db.rollback()
            with db:
                db.execute('UPDATE purchase_source_archives SET next_attempt=?,lease_until=0 '
                           'WHERE url=? AND lease_until=?', (time.time()+3600,row['url'],lease))
        return True
    finally:
        if path:
            path.unlink(missing_ok=True)
        db.close()
