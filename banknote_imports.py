"""Durable exact-order drafts, isolated from the live collection until release.

Batch/item identity is relational. Editable fields are a versioned draft document;
source facts, original-photo assets and accepted Check evidence are separate.
No GET starts research, changes a draft or releases an item.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import threading
import time
from urllib.parse import quote, urlencode
import uuid

import banknote_catalog_lookup
import banknote_catalog_proposals
import banknote_photo_sides
import ebay_listing_captures
import ebay_mail
import ebay_matching
import ebay_purchase_prices
import listing_images
import original_listings
import source_documents

MAX_ITEMS = 25
CHECK_TTL = 300
_CHECK_SLOTS = threading.BoundedSemaphore(2)
PHOTO_SIDE_WARNINGS = (
    'Front and back could not both be confirmed from the listing. Existing photos and all originals were retained; choose the missing or uncertain side manually.',
    'Listing-photo sides could not be verified. Existing photos and all originals were retained; run Check again or choose the photos manually.',
)
_ORDER = re.compile(r'\d{2}-\d{5}-\d{5}')
_MULTIPLE = r'(?:[2-9]\d*|1\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|twenty|hundred)'
_BUNDLE = re.compile(r'\b(?:set|bundle)\s*(?:of\s*)?'+_MULTIPLE+r'\b|\blot\s+of\s+'+_MULTIPLE+r'\b|\bpair of\b|\b'+_MULTIPLE+r'\s+(?:consecutive\s+)?(?:serial\s+)?(?:notes|banknotes)\b', re.I)
_DIMENSIONS = re.compile(r'(?<![\w.])\d+(?:[.,]\d+)?\s*(?:(?:mm|cm|inches|inch|in)\s*)?[x×]\s*\d+(?:[.,]\d+)?\s*(?:mm|cm|inches|inch|in)\b', re.I)
_MULTIPACK = re.compile(r'(?<![\w./-])'+_MULTIPLE+r'\s*[x×](?=\s|\d|$)|(?<!\w)[x×]\s*'+_MULTIPLE+r'\b', re.I)
_AUTO_AMBIGUOUS = re.compile(r'\b(?:set|bundle|pair|assortment|assorted|coins?|stamps?|medals?|empty|holder only)\b|\blot\s+(?:of\s+)?(?:notes|banknotes)\b|\bcollection\s+of\s+(?:\w+\s+){0,4}(?:notes|banknotes)\b|\b(?:notes|banknotes)\s+collection\b', re.I)
_NOTE_TITLE = re.compile(r'\b(?:banknotes?|paper money|PMG|Friedberg)\b|\bPick\s*[#-]?\s*\d', re.I)
_NON_NOTE_TITLE = re.compile(r'\b(?:books?|cameras?|lenses|lens|albums?|posters?|postcards?)\b', re.I)
_LISTING_PREVIEW_URL = re.compile(r'https://i\.ebayimg\.com/images/g/[\w~-]+/s-l\d+\.(?:jpg|jpeg|png|webp)', re.ASCII)
_INSPECTION_ATTENTION = frozenset(('multiple items; shipment or delivery not confirmed',))
_REVIEW_LOCKED_FIELDS = ('price','vendor','purchase_date','status')
_INSPECTION_FIELDS = frozenset(('country','municipality','issue_type','issuer','official',
    'denomination','series','pick_number','other_catalog','printer','signatures','serial_number',
    'watermark','material','date_1','date_2','date_1_text','date_2_text','size_width','size_height',
    'grade','grade_numeric','grading_authority','slab_number','grade_condition','grade_modifier',
    'lettering','lettering_translation','obv_rev','condition','notes'))


class ImportProblem(ValueError):
    def __init__(self, message, *, code=None, item=None):
        super().__init__(message)
        self.code = code
        self.item = item

    def payload(self):
        result = {'error': str(self)}
        if self.code:
            result['code'] = self.code
        if self.item is not None:
            result['item'] = self.item
        return result


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def init_schema(db):
    db.executescript('''
    CREATE TABLE IF NOT EXISTS banknote_import_batches (
        id TEXT PRIMARY KEY, account_name TEXT NOT NULL, order_id TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'queued', request_id TEXT, message TEXT NOT NULL DEFAULT '',
        snapshot_json TEXT NOT NULL DEFAULT '[]', auto_single INTEGER NOT NULL DEFAULT 0,
        created_at REAL NOT NULL, updated_at REAL NOT NULL,
        UNIQUE(account_name,order_id));
    CREATE TABLE IF NOT EXISTS banknote_import_items (
        id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES banknote_import_batches(id),
        account_name TEXT NOT NULL, line_key TEXT NOT NULL, item_id TEXT NOT NULL,
        source_json TEXT NOT NULL, source_digest TEXT NOT NULL, fields_json TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'draft', revision INTEGER NOT NULL DEFAULT 1,
        released_record_id TEXT, existing_record_id TEXT, existing_snapshot_json TEXT,
        manual_photos_json TEXT NOT NULL DEFAULT '{}',
        note_identity_json TEXT NOT NULL DEFAULT '{}',
        retry_photos INTEGER NOT NULL DEFAULT 0,
        warning TEXT NOT NULL DEFAULT '',
        check_state TEXT NOT NULL DEFAULT 'idle', check_token TEXT, check_expires REAL NOT NULL DEFAULT 0,
        check_message TEXT NOT NULL DEFAULT '', checked_at REAL,
        created_at REAL NOT NULL, updated_at REAL NOT NULL,
        UNIQUE(account_name,line_key), UNIQUE(batch_id,item_id));
    CREATE INDEX IF NOT EXISTS banknote_import_items_batch ON banknote_import_items(batch_id,state);
    CREATE TABLE IF NOT EXISTS banknote_import_assets (
        item_id TEXT NOT NULL REFERENCES banknote_import_items(id), source_url TEXT NOT NULL,
        filename TEXT NOT NULL, sha256 TEXT NOT NULL, width INTEGER, height INTEGER,
        position INTEGER NOT NULL, PRIMARY KEY(item_id,source_url));
    CREATE TABLE IF NOT EXISTS banknote_import_image_edits (
        filename TEXT PRIMARY KEY, item_id TEXT NOT NULL REFERENCES banknote_import_items(id),
        field TEXT NOT NULL CHECK(field IN ('image_1','image_2')),
        base_filename TEXT NOT NULL, source_filename TEXT NOT NULL,
        quad_json TEXT NOT NULL, sha256 TEXT NOT NULL, created_at REAL NOT NULL);
    CREATE INDEX IF NOT EXISTS banknote_import_image_edits_item
        ON banknote_import_image_edits(item_id,field);
    CREATE TABLE IF NOT EXISTS banknote_import_preview_jobs (
        item_id TEXT PRIMARY KEY REFERENCES banknote_import_items(id),
        source_digest TEXT NOT NULL, capture_digest TEXT NOT NULL, revision INTEGER NOT NULL,
        state TEXT NOT NULL, token TEXT, expires REAL NOT NULL DEFAULT 0,
        message TEXT NOT NULL DEFAULT '', updated_at REAL NOT NULL);
    CREATE TABLE IF NOT EXISTS banknote_import_photo_previews (
        item_id TEXT NOT NULL REFERENCES banknote_import_items(id), source_url TEXT NOT NULL,
        source_digest TEXT NOT NULL, capture_digest TEXT NOT NULL,
        source_filename TEXT NOT NULL, source_sha256 TEXT NOT NULL,
        filename TEXT NOT NULL, sha256 TEXT NOT NULL, quad_json TEXT NOT NULL,
        position INTEGER NOT NULL, PRIMARY KEY(item_id,source_url,source_digest,capture_digest));
    CREATE TABLE IF NOT EXISTS banknote_import_evidence (
        item_id TEXT NOT NULL REFERENCES banknote_import_items(id), field TEXT NOT NULL,
        value_json TEXT NOT NULL, proof_json TEXT NOT NULL, accepted_at REAL NOT NULL,
        identity_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(item_id,field));
    ''')
    if 'auto_single' not in {row[1] for row in db.execute('PRAGMA table_info(banknote_import_batches)')}:
        db.execute('ALTER TABLE banknote_import_batches ADD COLUMN auto_single INTEGER NOT NULL DEFAULT 0')
    if 'identity_json' not in {row[1] for row in db.execute('PRAGMA table_info(banknote_import_evidence)')}:
        db.execute("ALTER TABLE banknote_import_evidence ADD COLUMN identity_json TEXT NOT NULL DEFAULT '{}'")
    columns={row[1] for row in db.execute('PRAGMA table_info(banknote_import_items)')}
    for name in ('existing_record_id','existing_snapshot_json'):
        if name not in columns:db.execute('ALTER TABLE banknote_import_items ADD COLUMN '+name+' TEXT')
    if 'manual_photos_json' not in columns:
        db.execute("ALTER TABLE banknote_import_items ADD COLUMN manual_photos_json TEXT NOT NULL DEFAULT '{}'")
    if 'note_identity_json' not in columns:
        db.execute("ALTER TABLE banknote_import_items ADD COLUMN note_identity_json TEXT NOT NULL DEFAULT '{}'")
    if 'retry_photos' not in columns:
        db.execute('ALTER TABLE banknote_import_items ADD COLUMN retry_photos INTEGER NOT NULL DEFAULT 0')


def _account(db):
    row = db.execute('SELECT account_name FROM ebay_purchase_account WHERE id=1').fetchone()
    if not row or not row[0]:
        raise ImportProblem('Connect and verify eBay Purchases before importing an order.')
    return row[0].strip().lower()


def _batch(db, batch_id):
    row = db.execute('SELECT * FROM banknote_import_batches WHERE id=?', (batch_id,)).fetchone()
    if not row or row['account_name'] != _account(db):
        raise ImportProblem('This import is unavailable for the connected eBay account.')
    return dict(row)


def _item(db, batch_id, item_id):
    batch = _batch(db, batch_id)
    row = db.execute('SELECT * FROM banknote_import_items WHERE id=? AND batch_id=?', (item_id,batch_id)).fetchone()
    if not row:
        raise ImportProblem('This draft is no longer available.')
    return batch, dict(row)


def source_identity(item):
    return {key:item.get(key) for key in ('order_id','item_id','title','seller','quantity')}


def _digest(item):
    return hashlib.sha256(_json(source_identity(item)).encode()).hexdigest()


def _bundle_title(title):
    # A checkout quantity of one can still buy several physical notes. Remove
    # explicitly labelled measurements before interpreting "3 x" or "x 3".
    return bool(_BUNDLE.search(title) or _MULTIPACK.search(_DIMENSIONS.sub(' ',title)))


def _reason(item):
    if item.get('ignored'):
        return 'This purchase was excluded from eBay order matching. Review it before importing.'
    if item.get('quantity') != 1 or _bundle_title(item.get('title') or ''):
        return 'This purchase contains multiple notes or units. Separate exact item identification is needed before release.'
    if item.get('attention'):
        return 'This purchase needs review: ' + str(item['attention'])[:300]
    return ''


def _existing_matches(db,source):
    return db.execute('''SELECT n.* FROM banknotes n JOIN banknote_original_listings s ON s.banknote_id=n.id
        WHERE n.order_number=? AND s.url=? AND COALESCE(n.marketplace,'') IN ('','eBay')''',
        (source['order_id'],'https://www.ebay.com/itm/'+source['item_id'])).fetchall()


def begin(db, order_number, refresh=False):
    number = str(order_number or '').strip()
    if not _ORDER.fullmatch(number):
        raise ImportProblem('Enter the eBay order number, for example 12-12345-12345.')
    if not ebay_mail.configured():
        raise ImportProblem('The eBay purchase reader is not configured for this collection.')
    account = _account(db)
    now = time.time()
    db.execute('BEGIN IMMEDIATE')
    try:
        existing = db.execute('SELECT * FROM banknote_import_batches WHERE account_name=? AND order_id=?', (account,number)).fetchone()
        if not existing:
            # Entering a sibling seller order from an already imported checkout
            # resumes that review instead of manufacturing an empty second batch.
            existing = db.execute('''SELECT b.* FROM banknote_import_batches b
                JOIN banknote_import_items i ON i.batch_id=b.id
                WHERE b.account_name=? AND json_extract(i.source_json,'$.order_id')=?
                AND b.state IN ('review','complete') LIMIT 1''',(account,number)).fetchone()
        if existing and existing['state'] in ('review','complete') and not refresh:
            db.execute('UPDATE banknote_import_batches SET auto_single=1 WHERE id=?',(existing['id'],))
            db.commit()
            return existing['id']
        # Retry must recover even when the Mac stopped polling after claiming
        # the order. Use the reader's session-aware expiry before its busy guard.
        import ebay_purchase_lookup
        ebay_purchase_lookup.expire(db)
        if existing and existing['request_id']:
            request = db.execute("SELECT q.*,s.expires_at FROM ebay_purchase_requests q LEFT JOIN ebay_purchase_request_sessions s ON s.request_id=q.id WHERE q.id=?", (existing['request_id'],)).fetchone()
            if request and request['status'] in ('queued','reading') and (request['expires_at'] or request['requested_at']+120) > now:
                db.execute('UPDATE banknote_import_batches SET auto_single=1 WHERE id=?',(existing['id'],))
                db.commit()
                return existing['id']
        paused = db.execute('SELECT enabled FROM ebay_mail_connection WHERE id=1').fetchone()
        if paused and not paused[0]:
            raise ImportProblem('Purchase updates are paused. Resume them in eBay Orders before importing.')
        batch_id = existing['id'] if existing else uuid.uuid4().hex
        if existing:
            number=existing['order_id']
        request_id = uuid.uuid4().hex
        # A fresh import MUST read the complete exact order; a cached single
        # Purchases card may omit collapsed siblings and is not membership proof.
        old = db.execute('SELECT id,status FROM ebay_purchase_requests WHERE order_id=?', (number,)).fetchone()
        if old and old['status']=='reading':
            raise ImportProblem('A previous Check is reading this order. Let it finish, then retry Import order.')
        if old and old['status'] in ('queued','reading'):
            request_id = old['id']
        else:
            if old:
                db.execute('DELETE FROM ebay_purchase_request_sessions WHERE request_id=?', (old['id'],))
            db.execute('''INSERT INTO ebay_purchase_requests(id,order_id,requested_at,status,message)
                VALUES(?,?,?,'queued',?) ON CONFLICT(order_id) DO UPDATE SET id=excluded.id,
                requested_at=excluded.requested_at,status=excluded.status,message=excluded.message''',
                (request_id,number,now,'Reading all purchased items from this exact eBay order…'))
            db.execute('INSERT INTO ebay_purchase_request_sessions(request_id,expires_at) VALUES(?,?)', (request_id,now+600))
        db.execute('''INSERT INTO banknote_import_batches(id,account_name,order_id,request_id,created_at,updated_at,auto_single)
            VALUES(?,?,?,?,?,?,1) ON CONFLICT(account_name,order_id) DO UPDATE SET request_id=excluded.request_id,
            state='queued',message='',auto_single=1,updated_at=excluded.updated_at''', (batch_id,account,number,request_id,now,now))
        db.commit()
        return batch_id
    except Exception:
        db.rollback()
        raise


def materialize(db, account, order_id, items, request_id):
    """Called inside authenticated complete's transaction with exact membership."""
    if not 1 <= len(items) <= MAX_ITEMS or len({item['item_id'] for item in items}) != len(items):
        raise ImportProblem('The order contains unsupported or ambiguous item quantities.')
    batch = db.execute("SELECT * FROM banknote_import_batches WHERE account_name=? AND order_id=? AND request_id=? AND state='queued'",
                       (account.lower(),order_id,request_id)).fetchone()
    if not batch:
        return None
    now = time.time()
    membership = [[item['order_id'],item['item_id']] for item in items]
    for item in items:
        stored = db.execute('SELECT * FROM ebay_order_items WHERE order_id=? AND item_id=?', (item['order_id'],item['item_id'])).fetchall()
        if len(stored) != 1:
            raise ImportProblem('The exact purchased item is ambiguous.')
        source = dict(stored[0])
        prior = db.execute('SELECT * FROM banknote_import_items WHERE account_name=? AND line_key=?',
                           (account.lower(),source['line_key'])).fetchone()
        if prior and prior['batch_id'] != batch['id']:
            raise ImportProblem('These items already have an Order review. Open that existing review instead of importing again.')
        linked = db.execute('SELECT banknote_id FROM banknote_ebay_links WHERE line_key=?', (source['line_key'],)).fetchone()
        reason = _reason(source)
        recovery=None
        if not linked:
            matches=_existing_matches(db,source)
            bound_id=prior['existing_record_id'] if prior else None
            unlinked=len(matches)==1 and not db.execute('SELECT 1 FROM banknote_ebay_links WHERE banknote_id=?',(matches[0]['id'],)).fetchone()
            if bound_id:
                # Explicit refresh can rebase this SAME recovery target after
                # edits, but can never silently switch to a different record.
                if unlinked and matches[0]['id']==bound_id:
                    recovery=dict(matches[0])
                else:
                    reason='The existing recovery record no longer matches this exact order and listing, or is already linked. Review it before release.'
            elif unlinked and all(banknote_catalog_lookup.is_blank(matches[0][field])
                    for field in ('country','denomination','pick_number','other_catalog')):
                recovery=dict(matches[0])
            elif matches:
                reason='This exact purchased listing already has a collection record. Review its existing record before creating another.'
        fields = dict(description=source['title'],vendor=source['seller'],purchase_date=(source.get('ordered_at') or '')[:10],
                      order_number=source['order_id'],marketplace='eBay',status='Ordered',owner='Mark',property_name='Carpinteria')
        paid = ebay_purchase_prices.for_item(db,source)
        if paid:
            fields['price'] = paid['price']
        if recovery:
            fields.update({key:value for key,value in recovery.items() if key not in
                ('id','cat_id','banknote_id','created_at','updated_at','specs_searched_at') and not banknote_catalog_lookup.is_blank(value)})
        state = 'released' if linked else 'blocked' if reason else 'draft'
        db.execute('''INSERT INTO banknote_import_items(id,batch_id,account_name,line_key,item_id,source_json,
            source_digest,fields_json,state,released_record_id,warning,created_at,updated_at)
            VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(account_name,line_key) DO NOTHING''',
            (uuid.uuid4().hex,batch['id'],account.lower(),source['line_key'],source['item_id'],_json(source),
             _digest(source),_json(fields),state,linked[0] if linked else None,reason,now,now))
        if recovery:
            db.execute('UPDATE banknote_import_items SET existing_record_id=?,existing_snapshot_json=? WHERE account_name=? AND line_key=?',
                       (recovery['id'],_json(recovery),account.lower(),source['line_key']))
        if prior:
            # A new explicit source refresh updates verified membership/source
            # facts. Draft edits stay, except occupied live recovery values are
            # refreshed and protected rather than being overwritten on release.
            refreshed_fields=json.loads(prior['fields_json'])
            if recovery:
                previous=json.loads(prior['existing_snapshot_json'] or '{}')
                for key,value in previous.items():
                    if (not banknote_catalog_lookup.is_blank(value) and banknote_catalog_lookup.is_blank(recovery.get(key))
                            and (refreshed_fields.get(key)==value or
                                 _image_edits(db,prior,refreshed_fields).get(key,{}).get('base_filename')==value)):
                        # A deliberately cleared live value must not return
                        # through its old, read-only recovery copy.
                        refreshed_fields.pop(key,None)
                crops=_preserved_image_edits(db,prior,refreshed_fields,recovery)
                refreshed_fields.update({key:value for key,value in recovery.items() if key not in
                    ('id','cat_id','banknote_id','created_at','updated_at','specs_searched_at') and not banknote_catalog_lookup.is_blank(value)})
                refreshed_fields.update(crops)
            # A newly captured exact receipt fills the saved draft immediately;
            # ordinary edits and occupied recovery values remain authoritative.
            if paid and banknote_catalog_lookup.is_blank(refreshed_fields.get('price')):
                refreshed_fields['price']=paid['price']
            db.execute('''UPDATE banknote_import_items SET source_json=?,source_digest=?,warning=?,
                fields_json=?,state=?,released_record_id=?,revision=revision+1,check_state='idle',check_token=NULL,check_expires=0,updated_at=?
                WHERE account_name=? AND line_key=? AND state!='released' ''',
                (_json(source),_digest(source),reason,_json(refreshed_fields),state,linked[0] if linked else None,now,account.lower(),source['line_key']))
    # Membership comes only from this complete response, never historical rows.
    for old in db.execute('SELECT id,item_id,state,source_json FROM banknote_import_items WHERE batch_id=?', (batch['id'],)).fetchall():
        if [json.loads(old['source_json'])['order_id'],old['item_id']] not in membership and old['state'] != 'released':
            db.execute("UPDATE banknote_import_items SET state='blocked',warning=?,revision=revision+1,updated_at=? WHERE id=?",
                       ('This item is absent from the latest complete order snapshot; it cannot be released.',now,old['id']))
    pending = db.execute("SELECT COUNT(*) FROM banknote_import_items WHERE batch_id=? AND state!='released'", (batch['id'],)).fetchone()[0]
    db.execute('UPDATE banknote_import_batches SET state=?,snapshot_json=?,message=?,updated_at=? WHERE id=?',
               ('review' if pending else 'complete',_json(membership),'Review each purchased item before adding it to the collection.',now,batch['id']))
    return batch['id']


_EXISTING_UNVERSIONED_FIELDS = frozenset(('banknote_id', 'updated_at', 'specs_searched_at'))
_EXISTING_DRAFT_EXCLUDED_FIELDS = _EXISTING_UNVERSIONED_FIELDS | {'id', 'cat_id', 'created_at'}


def _existing_record_version(record):
    return hashlib.sha256(_json({key: value for key, value in record.items()
        if key not in _EXISTING_UNVERSIONED_FIELDS}).encode()).hexdigest()


def _existing_record_changes(existing, current):
    return [dict(field=key, before=value, current=current.get(key))
            for key, value in existing.items()
            if key not in _EXISTING_UNVERSIONED_FIELDS and current.get(key) != value]


def _listing_preview_sources(db, row, source):
    """Expose captured public images for viewing without accepting source status.

    This read-only fallback never downloads, retains, selects or classifies a
    photograph. Check and release keep their stricter source-status guards.
    """
    if row['state'] not in ('draft', 'blocked'):
        return []
    try:
        batch = _batch(db, row['batch_id'])
        membership = json.loads(batch['snapshot_json'])
    except (ImportProblem, ValueError, TypeError):
        return []
    if (not isinstance(membership, list) or batch['state'] not in ('review', 'complete')
            or row['account_name'] != batch['account_name']
            or source.get('item_id') != row['item_id']
            or _digest(source) != row['source_digest']
            or [source.get('order_id'), row['item_id']] not in membership):
        return []
    stored = db.execute('SELECT * FROM ebay_order_items WHERE order_id=? AND item_id=?',
                        (source.get('order_id'), row['item_id'])).fetchall()
    if len(stored) != 1:
        return []
    current = dict(stored[0])
    if (current['line_key'] != row['line_key'] or _digest(current) != row['source_digest']
            or current['quantity'] != 1 or current['ignored']
            or current['attention'].startswith('Multiple purchase rows')):
        return []
    now = time.time()
    capture = db.execute('SELECT images_json FROM ebay_listing_captures WHERE url=? '
                         'AND captured_at>? AND captured_at<=?',
                         ('https://www.ebay.com/itm/' + row['item_id'],
                          now - ebay_listing_captures.MAX_AGE, now + 60)).fetchone()
    if not capture:
        return []
    try:
        urls = json.loads(capture['images_json'])
    except (ValueError, TypeError):
        return []
    if (not isinstance(urls, list) or len(urls) > 24
            or any(not isinstance(url, str) or len(url) > 2048
                   or not _LISTING_PREVIEW_URL.fullmatch(url) for url in urls)):
        return []
    return [dict(url=url, source_url=url, position=position, preview=True, selectable=False)
            for position, url in enumerate(dict.fromkeys(urls))]


def _preview_digest(photos):
    return hashlib.sha256(_json([photo['source_url'] for photo in photos]).encode()).hexdigest()


def _preview_context(db,batch,row):
    """Exact photo identity is independent of permission to accept the purchase."""
    source=json.loads(row['source_json'])
    photos=_listing_preview_sources(db,row,source)
    existing=json.loads(row['existing_snapshot_json'] or '{}')
    if (row['state']!='blocked' or not photos or _bundle_title(source.get('title') or '')
            or any(existing.get(field) for field in ('image_1','image_2'))
            or db.execute('SELECT 1 FROM banknote_import_assets WHERE item_id=?',(row['id'],)).fetchone()):
        raise ImportProblem('No exact listing previews are available to crop for this item.')
    return photos,_preview_digest(photos)


def _listing_previews(db,row,source):
    photos=_listing_preview_sources(db,row,source)
    capture_digest=_preview_digest(photos)
    cached={entry['source_url']:dict(entry) for entry in db.execute(
        'SELECT * FROM banknote_import_photo_previews WHERE item_id=? AND source_digest=? AND capture_digest=?',
        (row['id'],row['source_digest'],capture_digest))}
    for photo in photos:
        saved=cached.get(photo['source_url'])
        if saved:
            route=f"/banknotes/imports/{row['batch_id']}/items/{row['id']}/preview/{photo['position']}"
            photo.update(url=route+'?v='+saved['sha256'],original_url=route+'?original=1',local_preview=True)
    return photos


def claim_previews(db,batch_id,item_id,*,retry=False):
    """Claim only the two review-card previews; never select photos or accept a purchase."""
    db.execute('BEGIN IMMEDIATE')
    try:
        batch,row=_item(db,batch_id,item_id)
        photos,capture_digest=_preview_context(db,batch,row)
        job=db.execute('SELECT * FROM banknote_import_preview_jobs WHERE item_id=?',(item_id,)).fetchone()
        matching=bool(job and job['source_digest']==row['source_digest'] and job['capture_digest']==capture_digest
                      and job['revision']==row['revision'])
        if matching and job['state']=='queued' and job['expires']>time.time():
            # A queued token is durable work, not proof a process still owns it.
            # Resume/startup can reattach it; run_previews claims it atomically.
            db.commit();return job['token']
        # An expired queued lease still represents requested work. Issue a new
        # token below after the same source checks, even if old crops are cached.
        if matching and job['state']!='queued' and ((job['state']=='checking' and job['expires']>time.time()) or not retry):
            db.commit();return None
        cached={entry['source_url']:entry for entry in db.execute(
            'SELECT * FROM banknote_import_photo_previews WHERE item_id=? AND source_digest=? AND capture_digest=?',
            (item_id,row['source_digest'],capture_digest))}
        if not retry and not (matching and job['state']=='queued') and all(photo['source_url'] in cached and cached[photo['source_url']]['filename']!=cached[photo['source_url']]['source_filename']
               for photo in photos[:2]):
            db.commit();return None
        token=uuid.uuid4().hex
        db.execute('''INSERT INTO banknote_import_preview_jobs
            (item_id,source_digest,capture_digest,revision,state,token,expires,updated_at)
            VALUES(?,?,?,?,'queued',?,?,?) ON CONFLICT(item_id) DO UPDATE SET
            source_digest=excluded.source_digest,capture_digest=excluded.capture_digest,revision=excluded.revision,
            state='queued',token=excluded.token,expires=excluded.expires,message='',updated_at=excluded.updated_at''',
            (item_id,row['source_digest'],capture_digest,row['revision'],token,time.time()+1800,time.time()))
        db.commit();return token
    except Exception:
        db.rollback();raise


def pending_preview_batches(db):
    """Restart only explicitly queued previews, never replay an active crop."""
    return [row[0] for row in db.execute('''SELECT DISTINCT i.batch_id
        FROM banknote_import_preview_jobs j JOIN banknote_import_items i ON i.id=j.item_id
        JOIN banknote_import_batches b ON b.id=i.batch_id
        WHERE j.state='queued' AND i.state='blocked'
            AND i.account_name=? AND b.account_name=i.account_name
            AND j.source_digest=i.source_digest AND j.revision=i.revision
            AND b.state IN ('review','complete') LIMIT 25''',(_account(db),))]


def _validate_preview_job(db,batch_id,item_id,token):
    batch,row=_item(db,batch_id,item_id)
    photos,capture_digest=_preview_context(db,batch,row)
    job=db.execute('SELECT * FROM banknote_import_preview_jobs WHERE item_id=?',(item_id,)).fetchone()
    if (not job or job['token']!=token or job['expires']<=time.time() or job['revision']!=row['revision']
            or job['source_digest']!=row['source_digest'] or job['capture_digest']!=capture_digest):
        raise ImportProblem('The listing photos changed while cropping. Use Crop photos to retry.')
    return row,photos,capture_digest


def run_previews(connect,batch_id,item_id,token,folder,prepare_photo):
    db=connect();created=[]
    try:
        db.execute('BEGIN IMMEDIATE')
        job=db.execute('SELECT state,token FROM banknote_import_preview_jobs WHERE item_id=?',(item_id,)).fetchone()
        if not job or job['token']!=token or job['state']!='queued':
            db.rollback();return
        row,photos,capture_digest=_validate_preview_job(db,batch_id,item_id,token)
        db.execute("UPDATE banknote_import_preview_jobs SET state='checking',expires=? WHERE item_id=? AND token=?",
                   (time.time()+CHECK_TTL,item_id,token));db.commit()
        unchanged=False
        for photo in photos[:2]:
            cached=db.execute('''SELECT * FROM banknote_import_photo_previews
                WHERE item_id=? AND source_url=? AND source_digest=? AND capture_digest=?''',
                (item_id,photo['source_url'],row['source_digest'],capture_digest)).fetchone()
            if cached:
                source=cached['source_filename'];source_hash=cached['source_sha256']
            else:
                asset=listing_images.download(photo['source_url'],folder)
                # The downloader may return a content-addressed original already
                # used by a sibling or collection record. Only our UUID crop
                # outputs belong to this worker's cleanup list.
                source=asset['filename'];source_hash=asset['sha256']
            source_path=Path(folder)/source
            if source_path.name!=source or source_path.resolve().parent!=Path(folder).resolve():
                raise ImportProblem('The listing original is unavailable. Use Crop photos to retry.')
            raw=source_path.read_bytes()
            if hashlib.sha256(raw).hexdigest()!=source_hash:
                raise ImportProblem('The listing original changed. Refresh the eBay order before retrying.')
            # Retain the original before model work, without making it a selectable
            # draft asset or changing any purchase/draft fields.
            db.execute('BEGIN IMMEDIATE')
            _validate_preview_job(db,batch_id,item_id,token)
            db.execute('''INSERT OR IGNORE INTO banknote_import_photo_previews
                (item_id,source_url,source_digest,capture_digest,source_filename,source_sha256,filename,sha256,quad_json,position)
                VALUES(?,?,?,?,?,?,?,?,?,?)''',(item_id,photo['source_url'],row['source_digest'],capture_digest,
                source,source_hash,source,source_hash,'null',photo['position']))
            db.commit()
            try:
                crop=prepare_photo(raw,json.loads(row['fields_json']))
            except Exception:
                unchanged=True;continue
            if not crop:
                unchanged=True;continue
            filename=uuid.uuid4().hex+'.jpg';path=Path(folder)/filename
            created.append(path);path.write_bytes(crop['data'])
            db.execute('BEGIN IMMEDIATE')
            _validate_preview_job(db,batch_id,item_id,token)
            if hashlib.sha256(source_path.read_bytes()).hexdigest()!=source_hash:
                raise ImportProblem('The listing original changed while cropping. Use Crop photos to retry.')
            db.execute('''UPDATE banknote_import_photo_previews SET filename=?,sha256=?,quad_json=?
                WHERE item_id=? AND source_url=? AND source_filename=? AND source_digest=? AND capture_digest=?''',
                (filename,hashlib.sha256(crop['data']).hexdigest(),_json(crop.get('quad')),item_id,photo['source_url'],
                 source,row['source_digest'],capture_digest))
            db.commit()
        db.execute('BEGIN IMMEDIATE')
        _validate_preview_job(db,batch_id,item_id,token)
        message='Some listing photos were kept unchanged because their note edges could not be confirmed. Use Crop photos to retry.' if unchanged else ''
        db.execute('''UPDATE banknote_import_preview_jobs SET state=?,message=?,token=NULL,expires=0,updated_at=?
            WHERE item_id=? AND token=?''',('partial' if unchanged else 'done',message,time.time(),item_id,token));db.commit()
    except Exception as error:
        db.rollback()
        message=str(error) if isinstance(error,ImportProblem) else 'Listing photos could not finish cropping. Their originals were kept; use Crop photos to retry.'
        db.execute('''UPDATE banknote_import_preview_jobs SET state='failed',message=?,token=NULL,expires=0,updated_at=?
            WHERE item_id=? AND token=?''',(message,time.time(),item_id,token));db.commit()
    finally:
        for path in created:
            retained=db.execute('SELECT 1 FROM banknote_import_photo_previews WHERE filename=? OR source_filename=?',
                                (path.name,path.name)).fetchone()
            if not retained:path.unlink(missing_ok=True)
        db.close()


def preview_file(db,batch_id,item_id,position,folder,*,original=False):
    batch,row=_item(db,batch_id,item_id)
    photos=_listing_preview_sources(db,row,json.loads(row['source_json']))
    photo=next((photo for photo in photos if photo['position']==position),None)
    if not photo:raise ImportProblem('This listing preview is unavailable.')
    saved=db.execute('''SELECT * FROM banknote_import_photo_previews WHERE item_id=? AND source_url=?
        AND source_digest=? AND capture_digest=?''',(item_id,photo['source_url'],row['source_digest'],_preview_digest(photos))).fetchone()
    if not saved:raise ImportProblem('This listing preview is unavailable.')
    filename=saved['source_filename'] if original else saved['filename'];path=Path(folder)/filename
    expected=saved['source_sha256'] if original else saved['sha256']
    if (path.name!=filename or path.resolve().parent!=Path(folder).resolve() or not path.is_file()
            or hashlib.sha256(path.read_bytes()).hexdigest()!=expected):
        raise ImportProblem('This listing preview is unavailable.')
    return filename


def _public_item(db, row):
    row = dict(row)
    source = json.loads(row['source_json'])
    fields = json.loads(row['fields_json'])
    released_record = None
    if row['state'] == 'released' and row['released_record_id']:
        released_record = db.execute('SELECT * FROM banknotes WHERE id=?',
                                     (row['released_record_id'],)).fetchone()
        if released_record:
            # Review history keeps its original draft and purchase evidence;
            # its displayed fields follow subsequent edits to the real note.
            fields.update({key: value for key, value in dict(released_record).items()
                           if key not in ('id', 'cat_id', 'created_at', 'updated_at')})
    check_state, message = row['check_state'],row['check_message']
    if check_state == 'checking' and row['check_expires'] <= time.time():
        check_state,message='failed','Check was interrupted or expired. Your draft was kept; press Check to retry.'
    warnings = [v for v in (row['warning'],message if check_state in ('failed','partial') else '') if v]
    editable=can_edit(db,row)
    photos = [dict(url='/uploads/'+asset['filename'],filename=asset['filename'],selectable=editable,source_url=asset['source_url'],position=asset['position'])
              for asset in db.execute('SELECT * FROM banknote_import_assets WHERE item_id=? ORDER BY position', (row['id'],))]
    existing_changes = []
    existing_version = None
    if row.get('existing_record_id'):
        existing=json.loads(row['existing_snapshot_json'])
        live=db.execute('SELECT * FROM banknotes WHERE id=?',(row['existing_record_id'],)).fetchone()
        if row['state']=='draft' and live:
            existing_changes=_existing_record_changes(existing,dict(live))
            existing_version=_existing_record_version(dict(live))
        saved=[dict(url='/uploads/'+existing[field],filename=existing[field],selectable=False,source_url='',position=index)
               for index,field in enumerate(('image_1','image_2')) if existing.get(field)]
        photos=saved+[photo for photo in photos if photo['url'] not in {p['url'] for p in saved}]
    if not photos:
        photos = _listing_previews(db, row, source)
    preview_job=db.execute('SELECT * FROM banknote_import_preview_jobs WHERE item_id=?',(row['id'],)).fetchone()
    if preview_job and (row['state']!='blocked' or preview_job['source_digest']!=row['source_digest']
            or preview_job['revision']!=row['revision'] or not photos or any(not photo.get('preview') for photo in photos)
            or preview_job['capture_digest']!=_preview_digest(photos)):
        preview_job=None
    preview_state=preview_job['state'] if preview_job else 'idle'
    preview_message=preview_job['message'] if preview_job else ''
    if preview_job and preview_state in ('queued','checking') and preview_job['expires']<=time.time():
        preview_state,preview_message='failed','Photo cropping was interrupted. Use Crop photos to retry.'
    if preview_state in ('failed','partial') and preview_message:warnings.append(preview_message)
    evidence = [json.loads(proof['proof_json']) | {'field':proof['field'],'value':json.loads(proof['value_json'])}
                for proof in db.execute('SELECT * FROM banknote_import_evidence WHERE item_id=? ORDER BY field', (row['id'],))]
    paid=ebay_purchase_prices.for_item(db,source)
    purchase=dict(price=paid['price'] if paid else None,vendor=source['seller'],purchase_date=(source.get('ordered_at') or '')[:10])
    preserved_fields=[key for key,value in json.loads(row['existing_snapshot_json'] or '{}').items()
                      if not banknote_catalog_lookup.is_blank(value)]
    collection_url = None
    if released_record:
        collection_url = '/banknotes/' + quote(row['released_record_id'], safe='') + '?' + urlencode(
            {'report_back': f"/banknotes/imports/{row['batch_id']}"})
    return dict(id=row['id'],state=row['state'],revision=row['revision'],fields=fields,title=source['title'],
                listing_url='https://www.ebay.com/itm/'+row['item_id'],order_number=source['order_id'],
                detail_url=f"/banknotes/imports/{row['batch_id']}/items/{row['id']}",
                collection_url=collection_url,
                released_record_id=row['released_record_id'],existing_record_id=row.get('existing_record_id'),photos=photos,check_state=check_state,
                existing_record_changes=existing_changes,existing_record_version=existing_version,
                existing_record_url='/banknotes/'+row['existing_record_id'] if row.get('existing_record_id') else None,
                check_message=message,warnings=warnings,evidence=evidence,purchase=purchase,preserved_fields=preserved_fields,
                manual_photos=json.loads(row.get('manual_photos_json') or '{}'),
                preview_state=preview_state,can_check=can_check(db,row),can_edit=editable,can_release=editable,
                locked_fields=list(_REVIEW_LOCKED_FIELDS) if row['state']=='blocked' else [],
                image_sources={field:edit['source_filename'] for field,edit in _image_edits(db,row,fields).items()})


def _single_item(db,batch):
    """Complete checkout cardinality, never a filtered banknote/pending count."""
    if not batch.get('auto_single') or batch['state'] not in ('review','complete'):
        return None
    membership=json.loads(batch['snapshot_json'])
    rows=db.execute('SELECT * FROM banknote_import_items WHERE batch_id=?',(batch['id'],)).fetchall()
    if len(membership)!=1 or len(rows)!=1:
        return None
    row=dict(rows[0])
    if membership != [[json.loads(row['source_json'])['order_id'],row['item_id']]]:
        return None
    return row


def _single_ready(db,batch,row):
    if row['state']!='draft' or row['check_state'] not in ('done','partial') or row['warning']:
        return False
    source=_validate_source(db,batch,row)
    fields=json.loads(row['fields_json'])
    # Positive banknote identity is separate from complete enrichment. A known
    # note may keep a blank catalogue field or uncertain photo side in its normal
    # editor; an unknown item or a potentially mixed lot still needs review.
    if _AUTO_AMBIGUOUS.search(source['title']):
        return False
    identified=(all(str(fields.get(key) or '').strip() for key in ('country','denomination'))
                and any(str(fields.get(key) or '').strip() for key in ('pick_number','other_catalog','issue_type')))
    if not (_NOTE_TITLE.search(source['title']) or identified):
        return False
    paid=ebay_purchase_prices.for_item(db,source)
    if paid and fields.get('price')!=paid['price']:
        return False
    return True


def finish_single(db,batch_id,folder,create):
    """Finish an explicitly requested, proven single-banknote import once.

    This is called only by POST processing or its Check worker, never a GET.
    The existing release transaction repeats every guard under its write lock.
    """
    batch=_batch(db,batch_id)
    row=_single_item(db,batch)
    if not row or not _single_ready(db,batch,row):
        return None
    return release(db,batch_id,[dict(id=row['id'],revision=row['revision'])],folder,create,automatic_single=True)


def collection_check_warning(db,record):
    """Show only unresolved import enrichment warnings in the ordinary editor."""
    row=db.execute("SELECT check_message,checked_at FROM banknote_import_items WHERE released_record_id=? AND state='released' AND check_state IN ('partial','failed') ORDER BY checked_at DESC LIMIT 1",(record['id'],)).fetchone()
    if not row or not row['check_message']:
        return ''
    completed=dict(record).get('specs_searched_at')
    if completed:
        from datetime import datetime, timezone
        try:
            if datetime.fromisoformat(completed.replace('Z','+00:00')).replace(tzinfo=timezone.utc).timestamp() >= (row['checked_at'] or 0):
                return ''
        except (TypeError,ValueError):pass
    return row['check_message']


def status(db,batch_id):
    batch = _batch(db,batch_id)
    state,message=batch['state'],batch['message']
    if state == 'queued':
        request = db.execute('SELECT * FROM ebay_purchase_requests WHERE id=?',(batch['request_id'],)).fetchone()
        if request:
            import ebay_purchase_lookup
            progress=ebay_purchase_lookup.snapshot(request,ebay_purchase_lookup.session_for(db,request['id']))
            state=progress['status'] if progress['status'] in ('failed','sign_in_required','challenge_required') else 'queued'
            message=progress['message']
            if progress.get('expires_at',0) < time.time():
                state,message='failed','This order read expired. Keep the Today Mac awake, then retry the import.'
    items=[_public_item(db,row) for row in db.execute('SELECT * FROM banknote_import_items WHERE batch_id=? ORDER BY created_at,item_id',(batch_id,))]
    single=_single_item(db,batch)
    processing_single=False
    completion_url=None
    if single:
        if single['state']=='released' and items[0].get('collection_url') and not single['warning']:
            try:
                source=_validate_source(db,batch,single)
                if not _AUTO_AMBIGUOUS.search(source['title']):
                    completion_url='/banknotes/'+quote(single['released_record_id'],safe='')
            except ImportProblem:pass
        elif single['state']=='draft' and not single['warning']:
            processing_single=single['check_state'] in ('idle','queued','checking')
            if single['check_state'] in ('done','partial'):
                try:processing_single=_single_ready(db,batch,single)
                except ImportProblem:processing_single=False
            if single['check_state']=='checking' and single['check_expires']<=time.time():
                processing_single=False
    return dict(id=batch_id,order_number=batch['order_id'],state=state,message=message,items=items,
                processing_single=processing_single,completion_url=completion_url,
                pending_count=sum(item['state']!='released' for item in items),
                url=f'/banknotes/imports/{batch_id}',status_url=f'/banknotes/imports/{batch_id}/status')


def _validate_source(db,batch,row):
    if batch['state'] not in ('review','complete'):
        raise ImportProblem('Wait for the fresh order read to finish before checking or releasing this draft.')
    if [json.loads(row['source_json'])['order_id'],row['item_id']] not in json.loads(batch['snapshot_json']):
        raise ImportProblem('This item is absent from the verified order snapshot.')
    if row['account_name'] != _account(db):
        raise ImportProblem('The connected eBay account changed; the draft was kept.')
    saved=json.loads(row['source_json'])
    matches=db.execute('SELECT * FROM ebay_order_items WHERE order_id=? AND item_id=?',
                       (saved['order_id'],row['item_id'])).fetchall()
    if len(matches)!=1:
        raise ImportProblem('This purchase identity is ambiguous or unavailable. Refresh the order review.')
    source=matches[0]
    if (source['line_key']!=row['line_key'] or _digest(dict(source)) != row['source_digest']
            or source['ordered_at'] != saved.get('ordered_at')):
        raise ImportProblem('The purchased item details changed. Review the order again before releasing it.')
    reason=_reason(dict(source))
    if reason:
        raise ImportProblem(reason)
    return dict(source)


def _review_note_title(title):
    """Recognize a note's Pick shorthand without broadening automatic imports."""
    if _NOTE_TITLE.search(title):return True
    if _NON_NOTE_TITLE.search(title):return False
    profile=ebay_matching.profile(title)
    picks=profile['catalogs'].get('p',set())
    denominations=profile['denominations']
    if len(picks)!=1 or len(denominations)!=1 or next(iter(denominations))[0]<=0:
        return False
    # A bare asking price beside a product/SKU token is not a face value.
    without_catalog=ebay_matching.CATALOG_RE.sub(' ',title)
    # The shared matching parser intentionally discards punctuation. A signed
    # negative face value must not become positive proof of a banknote here.
    if re.search(r'(?<!\w)[-−]'+ebay_matching.NUMBER+r'\s*(?:'+ebay_matching.UNIT_RE+r')\b',without_catalog,re.I):return False
    if not re.search(r'\b(?:'+ebay_matching.UNIT_RE+r')\b',without_catalog,re.I):return False
    without_prices=re.sub(r'[$£]\s*'+ebay_matching.NUMBER,' ',without_catalog)
    if ebay_matching.denominations(without_prices)!=denominations:return False
    # The shared parser intentionally ignores malformed references and collapses
    # repeated values. Review eligibility must not turn those into one note.
    starts=list(re.finditer(r'\b(?:pk|p)(?=\d|[\s.#?/_-]|$)',title,re.I))
    matches=[match for match in ebay_matching.CATALOG_RE.finditer(title)
             if match[1].lower() in ('p','pk')]
    if len(starts)!=1 or len(matches)!=1 or starts[0].start()!=matches[0].start():return False
    match=matches[0];tail=title[match.end():]
    if (tail and not re.match(r'[\s.,;:)\]]',tail)
            or re.match(r'\s*(?:[/~]|[-–—]\s*\w|(?:and|or|to)\s+[a-z]?\d)',tail,re.I)):
        return False
    return True


def _review_title_ambiguous(title):
    """Reject explicit contradictory identities without requiring known units."""
    # Repeated written units joined as separate values are explicit ambiguity,
    # even when the matching vocabulary does not know that currency yet.
    if re.search(r'\b'+ebay_matching.NUMBER+r'\s+([^\W\d_]+(?:\s+[^\W\d_]+){0,3}?)\s*(?:and|or|to|[&/,;–—])\s*'
                 +ebay_matching.NUMBER+r'\s+\1\b',title,re.I):return True
    denominations=ebay_matching.denominations(title)
    if len(denominations)>1 or any(amount<=0 for amount,_ in denominations):return True
    if re.search(r'(?<!\w)[-−]'+ebay_matching.NUMBER+r'\s*(?:'+ebay_matching.UNIT_RE+r')\b',
                 ebay_matching.CATALOG_RE.sub(' ',title),re.I):return True
    starts=list(re.finditer(r'\b(?:pk|p)(?=\d|[\s.#?/_-]|$)',title,re.I))
    matches=[match for match in ebay_matching.CATALOG_RE.finditer(title) if match[1].lower() in ('p','pk')]
    if len(starts)>1 or len(starts)!=len(matches):return True
    if matches:
        if starts[0].start()!=matches[0].start():return True
        tail=title[matches[0].end():]
        if (tail and not re.match(r'[\s.,;:)\]]',tail)
                or re.match(r'\s*(?:[/~]|[-–—]\s*\w|(?:and|or|to)\s+[a-z]?\d)',tail,re.I)):
            return True
    return False


def _review_purchase_source(db,batch,row):
    """Validate an exact quantity-one purchase before explicit inspection.

    A title vocabulary match is not required to inspect its originals. Known
    non-note objects, bundles and every other purchase blocker remain excluded.
    """
    source=json.loads(row['source_json'])
    membership=json.loads(batch['snapshot_json'])
    if (row['state']!='blocked' or row['existing_record_id']
            or batch['state'] not in ('review','complete') or not isinstance(membership,list)
            or row['account_name']!=batch['account_name'] or row['account_name']!=_account(db)
            or source.get('item_id')!=row['item_id'] or _digest(source)!=row['source_digest']
            or [source.get('order_id'),row['item_id']] not in membership
            or source.get('attention','').lower() not in _INSPECTION_ATTENTION
            or row['warning']!=_reason(source) or _NON_NOTE_TITLE.search(source.get('title') or '')
            or _review_title_ambiguous(source.get('title') or '')
            or _AUTO_AMBIGUOUS.search(source.get('title') or '') or _bundle_title(source.get('title') or '')):
        raise ImportProblem('This purchase needs its exact item identity reviewed before editing or release.')
    matches=db.execute('SELECT * FROM ebay_order_items WHERE order_id=? AND item_id=?',
                       (source.get('order_id'),row['item_id'])).fetchall()
    if len(matches)!=1:
        raise ImportProblem('This purchase identity is ambiguous. Refresh the order review.')
    current=dict(matches[0])
    if (current['line_key']!=row['line_key'] or _digest(current)!=row['source_digest']
            or current['ordered_at']!=source.get('ordered_at')
            or current['attention'].lower() not in _INSPECTION_ATTENTION
            or _reason(current)!=row['warning'] or current['quantity']!=1 or current['ignored']
            or _existing_matches(db,source)
            or db.execute('SELECT 1 FROM banknote_ebay_links WHERE line_key=?',(row['line_key'],)).fetchone()):
        raise ImportProblem('This purchase identity changed or already has a collection record. Refresh the order review.')
    return current


def _identity_capture_digest(capture):
    # Retained identity survives time passing and a timestamp-only refresh, but
    # never a change to the listing evidence on which the classifier relied.
    return hashlib.sha256(_json({key:capture[key] for key in ('url','title','text','images_json')}).encode()).hexdigest()


def _identity_asset(asset):
    return {key:asset[key] for key in ('source_url','filename','sha256')}


def _valid_note_identity(db,row,proof=None):
    """Validate server-owned proof against current source, capture and assets."""
    try:
        proof=json.loads(row['note_identity_json']) if proof is None else proof
        if (not isinstance(proof,dict) or proof.get('version')!=1
                or proof.get('source_digest')!=row['source_digest']):return False
        capture=db.execute('SELECT * FROM ebay_listing_captures WHERE url=?',
            ('https://www.ebay.com/itm/'+row['item_id'],)).fetchone()
        if not capture or proof.get('capture_digest')!=_identity_capture_digest(capture):return False
        urls=json.loads(capture['images_json'])
        originals=proof.get('originals')
        pair=proof.get('pair')
        if (not isinstance(originals,list) or not isinstance(pair,dict)
                or set(pair)!=set(('image_1','image_2')) or len(originals)!=len(urls)
                or {asset['source_url'] for asset in originals}!=set(urls)):
            return False
        current={asset['source_url']:_identity_asset(asset) for asset in db.execute(
            'SELECT * FROM banknote_import_assets WHERE item_id=?',(row['id'],))}
        if any(current.get(asset['source_url'])!=asset for asset in originals):return False
        if any(asset not in originals for asset in pair.values()):return False
        return (pair['image_1']['filename']!=pair['image_2']['filename']
                and pair['image_1']['sha256']!=pair['image_2']['sha256'])
    except (KeyError,TypeError,ValueError):
        return False


def _review_source(db,batch,row):
    """Editing/release requires a recognized title or retained photo identity."""
    source=_review_purchase_source(db,batch,row)
    if not _review_note_title(source.get('title') or '') and not _valid_note_identity(db,row):
        raise ImportProblem('Use Check to verify that the original photos show one banknote before editing or release.')
    return source


def can_edit(db,row):
    if row['state']=='draft':return True
    if row['state']!='blocked':return False
    try:
        _review_source(db,_batch(db,row['batch_id']),row)
        return True
    except ImportProblem:return False


def _editable_source(db,batch,row):
    if row['state']=='blocked':return _review_source(db,batch,row)
    if row['state']!='draft':raise ImportProblem('This item is no longer an editable draft.',code='draft_changed')
    return _validate_source(db,batch,row)


def _inspection_context(db,batch,row):
    """Bind explicit inspection to fresh evidence for an exact purchase."""
    _review_purchase_source(db,batch,row)
    if not _listing_preview_sources(db,row,json.loads(row['source_json'])):
        raise ImportProblem('Refresh the exact listing evidence before checking this note.')
    capture=db.execute('SELECT * FROM ebay_listing_captures WHERE url=?',
                       ('https://www.ebay.com/itm/'+row['item_id'],)).fetchone()
    # Bind all evidence read by Check, not just gallery URLs. A newer capture
    # must never lend its identity to an older in-flight model response.
    return hashlib.sha256(_json(dict(capture)).encode()).hexdigest()


def can_check(db,row):
    if row['state']=='draft':return True
    if row['state']!='blocked':return False
    try:
        _inspection_context(db,_batch(db,row['batch_id']),row)
        return True
    except ImportProblem:return False


def _check_context(db,batch,row):
    if row['state']=='blocked':
        capture_digest=_inspection_context(db,batch,row)
        source=_review_purchase_source(db,batch,row)
    else:
        if row['state']!='draft':raise ImportProblem('This item is no longer an editable draft.')
        source=_validate_source(db,batch,row)
        capture=db.execute('SELECT * FROM ebay_listing_captures WHERE url=?',
                           ('https://www.ebay.com/itm/'+row['item_id'],)).fetchone()
        capture_digest=hashlib.sha256(_json(dict(capture) if capture else None).encode()).hexdigest()
    # Normal Check needs the same evidence binding as warning-only inspection.
    # Receipt corrections can arrive while the provider is running without
    # changing a draft revision or the purchased listing's identity.
    return (row['state'],capture_digest,_json(ebay_purchase_prices.for_item(db,source)))


def _check_active(row):
    return row['check_state']=='queued' or (row['check_state']=='checking' and row['check_expires']>time.time())


def save(db,batch_id,item_id,revision,updates,normalize):
    if type(revision) is not int or not isinstance(updates,dict) or not updates:
        raise ImportProblem('Save requires the current draft revision and edited fields.')
    normalized=normalize(updates)
    db.execute('BEGIN IMMEDIATE')
    try:
        batch,row=_item(db,batch_id,item_id)
        if row['state'] not in ('draft','blocked') or row['revision']!=revision:
            raise ImportProblem('This draft changed or was released. Reload it before saving.', code='draft_changed')
        if _check_active(row):
            raise ImportProblem('Wait for Check to finish before editing this draft. Your saved values were kept.')
        if row['state']=='blocked':
            _review_source(db,batch,row)
            if any(field in normalized for field in _REVIEW_LOCKED_FIELDS):
                raise ImportProblem('Price, seller, purchase date and status remain tied to the verified purchase while this item needs review.')
        existing=json.loads(row['existing_snapshot_json'] or '{}')
        if any(not banknote_catalog_lookup.is_blank(existing.get(key)) and
               str(value or '').strip()!=str(existing[key] or '').strip() for key,value in normalized.items()):
            raise ImportProblem('Existing record values are preserved. Open the existing record to change them, then refresh this review.')
        fields=json.loads(row['fields_json']);fields.update(normalized)
        db.execute('UPDATE banknote_import_items SET fields_json=?,revision=revision+1,updated_at=? WHERE id=?',(_json(fields),time.time(),item_id))
        db.commit()
    except Exception:
        db.rollback();raise
    return _public_item(db,db.execute('SELECT * FROM banknote_import_items WHERE id=?',(item_id,)).fetchone())


def refresh_existing(db,batch_id,item_id,revision,existing_record_version):
    """Accept reviewed current values from the same exact unfinished record.

    This updates only the saved draft and its baseline. It does not fetch eBay,
    run Check, release anything, or write the existing collection record.
    """
    if type(revision) is not int or not isinstance(existing_record_version,str) or not existing_record_version:
        raise ImportProblem('Review the current collection values before refreshing this draft.')
    db.execute('BEGIN IMMEDIATE')
    try:
        batch,row=_item(db,batch_id,item_id)
        source=_validate_source(db,batch,row)
        if row['state']!='draft' or row['revision']!=revision:
            raise ImportProblem('This draft changed or was released. Review its latest saved values.',code='draft_changed')
        if _check_active(row):
            raise ImportProblem('Wait for Check to finish before refreshing the existing record.')
        if not row['existing_record_id']:
            raise ImportProblem('This draft does not complete an existing collection record.')
        matches=_existing_matches(db,source)
        if len(matches)!=1 or matches[0]['id']!=row['existing_record_id']:
            raise ImportProblem('The existing record no longer uniquely matches this exact order and listing. Open the existing record to review it.')
        if db.execute('SELECT 1 FROM banknote_ebay_links WHERE line_key=? OR banknote_id=?',
                (row['line_key'],row['existing_record_id'])).fetchone():
            raise ImportProblem('This purchased item or its existing record is already linked. Open the existing record to review its purchase link.')
        current=dict(matches[0])
        if _existing_record_version(current)!=existing_record_version:
            raise ImportProblem('The collection record changed again. Review its current values before refreshing the draft.',
                                code='existing_record_changed',item=_public_item(db,row))
        previous=json.loads(row['existing_snapshot_json'] or '{}')
        fields=json.loads(row['fields_json'])
        for key,value in previous.items():
            if (key not in _EXISTING_DRAFT_EXCLUDED_FIELDS and not banknote_catalog_lookup.is_blank(value)
                    and banknote_catalog_lookup.is_blank(current.get(key)) and
                    (fields.get(key)==value or _image_edits(db,row,fields).get(key,{}).get('base_filename')==value)):
                fields.pop(key,None)
        crops=_preserved_image_edits(db,row,fields,current)
        fields.update({key:value for key,value in current.items()
                       if key not in _EXISTING_DRAFT_EXCLUDED_FIELDS and not banknote_catalog_lookup.is_blank(value)})
        fields.update(crops)
        db.execute('''UPDATE banknote_import_items SET fields_json=?,existing_snapshot_json=?,
            revision=revision+1,updated_at=? WHERE id=?''',(_json(fields),_json(current),time.time(),item_id))
        db.commit()
    except Exception:
        db.rollback();raise
    return _public_item(db,db.execute('SELECT * FROM banknote_import_items WHERE id=?',(item_id,)).fetchone())


def _image_edits(db,row,fields):
    """Only a display crop saved for this exact draft side may replace it."""
    result={}
    for field in ('image_1','image_2'):
        edit=db.execute('SELECT * FROM banknote_import_image_edits WHERE item_id=? AND field=? AND filename=?',
                        (row['id'],field,fields.get(field))).fetchone()
        if edit:result[field]=dict(edit)
    return result


def _preserved_image_edits(db,row,fields,current):
    previous=json.loads(row['existing_snapshot_json'] or '{}')
    return {field:fields[field] for field,edit in _image_edits(db,row,fields).items()
            if current.get(field)==edit['base_filename'] or
            (banknote_catalog_lookup.is_blank(current.get(field)) and banknote_catalog_lookup.is_blank(previous.get(field)))}


def _draft_image(db,batch_id,item_id,field,folder,revision=None,trimmed=None):
    if field not in ('image_1','image_2'):
        raise ImportProblem('Unknown image field.')
    batch,row=_item(db,batch_id,item_id)
    _editable_source(db,batch,row)
    if revision is not None and row['revision']!=revision:
        raise ImportProblem('This draft changed or was released. Reopen the photo editor.',code='draft_changed')
    if _check_active(row):
        raise ImportProblem('Wait for Check to finish before editing draft photos.')
    fields=json.loads(row['fields_json']);filename=fields.get(field)
    if not filename or (trimmed is not None and filename!=trimmed):
        raise ImportProblem('This draft photograph changed. Reopen the photo editor.',code='draft_changed')
    root=Path(folder).resolve()
    def available(name):
        return isinstance(name,str) and Path(name).name==name and (root/name).resolve().parent==root and (root/name).is_file()
    if not available(filename):raise ImportProblem('The saved draft photograph is unavailable.')
    edit=_image_edits(db,row,fields).get(field)
    existing=json.loads(row['existing_snapshot_json'] or '{}')
    if row.get('existing_record_id'):
        live=db.execute('SELECT * FROM banknotes WHERE id=?',(row['existing_record_id'],)).fetchone()
        if not live or live[field]!=existing.get(field):
            raise ImportProblem('The collection photograph changed. Review its current version before editing the draft.',
                                code='existing_record_changed',item=_public_item(db,row))
    if edit:
        source,quad,base=edit['source_filename'],json.loads(edit['quad_json']),edit['base_filename']
    else:
        asset=db.execute('SELECT 1 FROM banknote_import_assets WHERE item_id=? AND filename=?',(item_id,filename)).fetchone()
        if not asset and existing.get(field)!=filename:
            raise ImportProblem('That photograph does not belong to this draft.')
        source,quad,base=filename,None,filename
        original=db.execute('SELECT source,quad FROM trimmed_image_sources WHERE trimmed=?',(filename,)).fetchone()
        if original and available(original['source']):
            source=original['source']
            try:quad=json.loads(original['quad']) if original['quad'] else None
            except ValueError:quad=None
    if not available(source):raise ImportProblem('The original draft photograph is unavailable.')
    return row,dict(trimmed=filename,source=source,quad=quad,base_filename=base)


def image_info(db,batch_id,item_id,field,folder,revision=None,trimmed=None):
    return _draft_image(db,batch_id,item_id,field,folder,revision,trimmed)


def crop_image(db,batch_id,item_id,field,folder,revision,trimmed,quad,render):
    """Save a new draft crop, retaining original bytes and collection state."""
    if type(revision) is not int or not isinstance(trimmed,str) or not trimmed:
        raise ImportProblem('Reopen the photo editor before saving this crop.')
    created=None
    db.execute('BEGIN IMMEDIATE')
    try:
        row,info=_draft_image(db,batch_id,item_id,field,folder,revision,trimmed)
        output,width,height,corners=render(Path(folder)/info['source'],quad)
        filename=uuid.uuid4().hex+'.jpg';created=Path(folder)/filename
        created.write_bytes(output)
        encoded_quad=_json(corners)
        db.execute("""INSERT INTO banknote_import_image_edits
            (filename,item_id,field,base_filename,source_filename,quad_json,sha256,created_at)
            VALUES(?,?,?,?,?,?,?,?)""",
            (filename,item_id,field,info['base_filename'],info['source'],encoded_quad,hashlib.sha256(output).hexdigest(),time.time()))
        db.execute('INSERT INTO trimmed_image_sources(trimmed,source,quad) VALUES(?,?,?)',
                   (filename,info['source'],encoded_quad))
        fields=json.loads(row['fields_json']);fields[field]=filename
        selected=json.loads(row['manual_photos_json'] or '{}');selected[field]=filename
        db.execute("""UPDATE banknote_import_items SET fields_json=?,manual_photos_json=?,
            revision=revision+1,updated_at=? WHERE id=?""",(_json(fields),_json(selected),time.time(),item_id))
        db.commit()
    except Exception:
        db.rollback()
        if created:created.unlink(missing_ok=True)
        raise
    item=_public_item(db,db.execute('SELECT * FROM banknote_import_items WHERE id=?',(item_id,)).fetchone())
    return dict(ok=True,item=item,url='/uploads/'+filename,width=width,height=height)


def _manually_selected_pair(fields,selected):
    return all(fields.get(field) and selected.get(field)==fields[field] for field in ('image_1','image_2'))


def select_photo(db,batch_id,item_id,revision,field,filename,folder):
    """Select a retained original for a draft slot; never alter collection photos."""
    if (type(revision) is not int or field not in ('image_1','image_2') or not isinstance(filename,str)
            or not filename or Path(filename).name!=filename):
        raise ImportProblem('Choose a saved draft photograph and its front or back side.')
    db.execute('BEGIN IMMEDIATE')
    try:
        batch,row=_item(db,batch_id,item_id)
        _editable_source(db,batch,row)
        if row['revision']!=revision:
            raise ImportProblem('This draft changed or was released. Reload it before choosing a photo.',code='draft_changed')
        if _check_active(row):
            raise ImportProblem('Wait for Check to finish before choosing draft photos.')
        existing=json.loads(row['existing_snapshot_json'] or '{}')
        if not banknote_catalog_lookup.is_blank(existing.get(field)):
            raise ImportProblem('This photo already belongs to the existing record and is preserved. Open that record to change it.')
        asset=db.execute('SELECT * FROM banknote_import_assets WHERE item_id=? AND filename=?',(item_id,filename)).fetchone()
        root=Path(folder).resolve();path=root/filename
        if (not asset or path.resolve().parent!=root or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']):
            raise ImportProblem('That photograph is not an available original for this draft.')
        fields=json.loads(row['fields_json']);other='image_2' if field=='image_1' else 'image_1'
        if fields.get(other):
            other_path=root/fields[other]
            other_edit=_image_edits(db,row,fields).get(other)
            other_name=other_edit['source_filename'] if other_edit else fields[other]
            other_path=root/other_name
            other_asset=db.execute('SELECT sha256 FROM banknote_import_assets WHERE item_id=? AND filename=?',(item_id,other_name)).fetchone()
            other_hash=other_asset['sha256'] if other_asset else (
                hashlib.sha256(other_path.read_bytes()).hexdigest() if other_path.resolve().parent==root and other_path.is_file() else None)
            if fields[other]==filename or other_name==filename or (other_hash and other_hash==asset['sha256']):
                raise ImportProblem('Choose different photographs for the front and back.')
        fields[field]=filename
        selected=json.loads(row['manual_photos_json'] or '{}');selected[field]=filename
        message=row['check_message'];state=row['check_state']
        if _manually_selected_pair(fields,selected):
            for warning in PHOTO_SIDE_WARNINGS:message=message.replace(warning,'')
            message=' '.join(message.split())
            if state=='partial' and not message:state='done'
        db.execute('''UPDATE banknote_import_items SET fields_json=?,manual_photos_json=?,
            revision=revision+1,check_state=?,check_message=?,updated_at=? WHERE id=?''',
            (_json(fields),_json(selected),state,message,time.time(),item_id))
        db.commit()
    except Exception:
        db.rollback();raise
    return _public_item(db,db.execute('SELECT * FROM banknote_import_items WHERE id=?',(item_id,)).fetchone())


def _source_inputs(db,row,fields,folder,classify):
    source=json.loads(row['source_json']);url='https://www.ebay.com/itm/'+row['item_id']
    evidence=[dict(kind='purchase',title='Verified eBay purchase',url='https://order.ebay.com/ord/show?orderId='+source['order_id'],
                   text=f"Order number: {source['order_id']}\nItem ID: {source['item_id']}\nItem: {source['title']}\nSeller: {source['seller']}\nPurchase date: {(source.get('ordered_at') or '')[:10]}",saved=True)]
    purchase=dict(vendor=source['seller'],purchase_date=(source.get('ordered_at') or '')[:10])
    warnings=[]
    paid=ebay_purchase_prices.for_item(db,source)
    if paid:
        evidence.append(dict(kind='order',title='Exact paid item amount',url=paid['source_url'],text=paid['evidence'],authenticated=True,saved=False))
        if not str(fields.get('price') or '').strip():purchase['price']=paid['price']
    else:warnings.append('The exact paid item amount is unavailable. Shipping, tax and order totals were not substituted.')
    capture=db.execute('SELECT * FROM ebay_listing_captures WHERE url=? AND captured_at>?',(url,time.time()-ebay_listing_captures.MAX_AGE)).fetchone()
    assets=[dict(asset) for asset in db.execute('SELECT * FROM banknote_import_assets WHERE item_id=? ORDER BY position',(row['id'],))]
    if capture:
        evidence.append(dict(kind='listing',title=capture['title'],url=url,text=capture['text'],saved=True))
        known={a['source_url']:a for a in assets};deadline=time.monotonic()+30
        for position,image_url in enumerate(json.loads(capture['images_json'])[:24]):
            if image_url in known or time.monotonic()>deadline:continue
            try:
                asset=listing_images.download(image_url,folder)
                assets.append(dict(asset,source_url=image_url,position=position))
            except Exception:warnings.append('An exact listing photograph could not be downloaded. Retry Check when the source is available.')
    else:warnings.append('The exact listing photos and description are unavailable. Retry the order read; your draft details were kept.')
    def original(filename):
        saved=db.execute('SELECT source FROM trimmed_image_sources WHERE trimmed=?',(filename,)).fetchone()
        return saved['source'] if saved else filename
    current_urls=set(json.loads(capture['images_json'])) if capture else set()
    needs_identity=row['state']=='blocked' and not _review_note_title(source.get('title') or '')
    # Retained originals remain available for review, but a refreshed listing
    # must not promote a removed photo into an empty side. Existing selected
    # images still enter the classifier separately as saved references.
    inspected=[asset for asset in assets if asset['source_url'] in current_urls]
    chosen=banknote_photo_sides.select(inspected,folder,classify,existing=fields,resolve_original=original)
    warnings.extend(chosen['warnings'])
    photos={field:asset['filename'] for field,asset in chosen['images'].items() if not fields.get(field)}
    identity={}
    pair=chosen.get('verified_pair',{})
    if (needs_identity and capture and set(pair)=={'image_1','image_2'}
            and {asset['source_url'] for asset in inspected}==current_urls
            and len(inspected)==len(current_urls)):
        identity=dict(version=1,source_digest=row['source_digest'],
            capture_digest=_identity_capture_digest(capture),
            originals=[_identity_asset(asset) for asset in inspected],
            pair={field:_identity_asset(asset) for field,asset in pair.items()})
    vision_images=[dict(filename=asset['filename'],sha256=asset['sha256'],
                        label='Additional verified photograph of the same note (holder/label evidence)')
                   for asset in chosen['evidence_images'] if asset['source_url'] in current_urls]
    return dict(evidence=evidence,reports=['Exact order item isolated from sibling purchases.'],warnings=warnings,
                documents=[],images={},vision_images=vision_images,purchase=purchase,
                purchase_price_fill_only=True,purchase_price_blocked=not bool(paid),
                _note_identity=identity,_current_gallery=inspected),assets,photos


def _verify_original_assets(assets,folder):
    root=Path(folder).resolve()
    for asset in assets:
        path=root/asset['filename']
        if (path.name!=asset['filename'] or path.resolve().parent!=root or not path.is_file()
                or hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']):
            raise ImportProblem('An original listing photo changed while checking. Your draft was kept; retry Check.')


def _saved_preview_crop(db,row,asset,folder,*,retry=False):
    if retry:return None
    photos=_listing_preview_sources(db,row,json.loads(row['source_json']))
    cached=db.execute('''SELECT * FROM banknote_import_photo_previews WHERE item_id=? AND source_url=?
        AND source_digest=? AND capture_digest=? AND source_sha256=? AND filename!=source_filename''',
        (row['id'],asset['source_url'],row['source_digest'],_preview_digest(photos),asset['sha256'])).fetchone()
    if not cached:return None
    path=Path(folder)/cached['filename']
    if path.name!=cached['filename'] or path.resolve().parent!=Path(folder).resolve() or not path.is_file():return None
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=cached['sha256']:return None
    return dict(data=raw,quad=json.loads(cached['quad_json']))


def _uncropped_draft_photos(db,row,fields,assets,*,retry_automatic=False):
    """Check retries originals; explicit Crop photos may replace automatic crops."""
    selected=json.loads(row['manual_photos_json'] or '{}')
    existing=json.loads(row['existing_snapshot_json'] or '{}')
    originals={asset['filename'] for asset in assets}
    result={}
    for field in ('image_1','image_2'):
        filename=fields.get(field)
        if (not filename or selected.get(field)
                or not banknote_catalog_lookup.is_blank(existing.get(field))):
            continue
        edit=db.execute('''SELECT source_filename FROM banknote_import_image_edits
            WHERE item_id=? AND field=? AND filename=?''',(row['id'],field,filename)).fetchone()
        trimmed=db.execute('SELECT source FROM trimmed_image_sources WHERE trimmed=?',(filename,)).fetchone()
        if retry_automatic:
            original=edit['source_filename'] if edit else trimmed['source'] if trimmed else filename
            if original in originals:result[field]=original
        elif filename in originals and not trimmed and not edit:
            result[field]=filename
    return result


def queue_photo_retries(db,batch_id):
    """Make an order-level retry durable before its provider slot becomes free."""
    db.execute('BEGIN IMMEDIATE')
    try:
        batch=_batch(db,batch_id)
        rows=db.execute("SELECT * FROM banknote_import_items WHERE batch_id=? AND state IN ('draft','blocked') LIMIT 25",(batch_id,)).fetchall()
        for row in rows:
            if row['check_state']=='checking' and row['check_expires']>time.time():continue
            try:_check_context(db,batch,row)
            except ImportProblem:continue
            fields=json.loads(row['fields_json'])
            assets=[dict(asset) for asset in db.execute('SELECT * FROM banknote_import_assets WHERE item_id=?',(row['id'],))]
            if all(fields.get(field) for field in ('image_1','image_2')) and not _uncropped_draft_photos(db,row,fields,assets,retry_automatic=True):continue
            db.execute("UPDATE banknote_import_items SET check_state='queued',retry_photos=1,check_token=NULL,check_expires=0 WHERE id=?",
                       (row['id'],))
        db.commit()
    except Exception:
        db.rollback();raise


def queue_inspection_checks(db,batch_id):
    """Persist every eligible Check requested by import/resume before dispatch."""
    db.execute('BEGIN IMMEDIATE')
    try:
        batch=_batch(db,batch_id)
        for row in db.execute("SELECT * FROM banknote_import_items WHERE batch_id=? AND state IN ('draft','blocked') AND check_state='idle' LIMIT 25",(batch_id,)).fetchall():
            try:_check_context(db,batch,row)
            except ImportProblem:continue
            db.execute("UPDATE banknote_import_items SET check_state='queued' WHERE id=?",(row['id'],))
        db.commit()
    except Exception:
        db.rollback();raise


def run_check(connect,batch_id,item_id,revision,token,folder,classify,evaluate,prepare_photo=None,*,retry_uncropped=False):
    db=connect()
    created=[]
    retained=set()
    committed=False
    checkpointed=False
    try:
        batch,row=_item(db,batch_id,item_id)
        context=_check_context(db,batch,row)
        inspection=row['state']=='blocked'
        needs_identity=inspection and not _review_note_title(json.loads(row['source_json']).get('title') or '')
        fields=json.loads(row['fields_json'])
        prepared,assets,photos=_source_inputs(db,row,fields,folder,classify)
        _verify_original_assets(assets,folder)
        if inspection:
            prepared.update(purchase={},purchase_price_blocked=True,
                evidence=[entry for entry in prepared['evidence'] if entry['kind']=='listing'])
        retry_automatic=bool(row['retry_photos'])
        retries=_uncropped_draft_photos(db,row,fields,assets,retry_automatic=retry_automatic) if retry_uncropped or retry_automatic else {}
        photos.update(retries)
        # Save source photographs before the slower catalogue call. A provider
        # failure or restart must not discard the already captured originals.
        db.execute('BEGIN IMMEDIATE')
        batch,current=_item(db,batch_id,item_id)
        current_context=_check_context(db,batch,current)
        if current_context!=context or current['revision']!=revision or current['check_token']!=token or current['check_expires']<=time.time():
            raise ImportProblem('This draft Check expired. The draft was kept; press Check again.')
        for asset in assets:
            db.execute('''INSERT OR IGNORE INTO banknote_import_assets(item_id,source_url,filename,sha256,width,height,position)
                VALUES(?,?,?,?,?,?,?)''',(item_id,asset['source_url'],asset['filename'],asset['sha256'],asset.get('width'),asset.get('height'),asset['position']))
        db.commit()
        current_gallery=prepared.pop('_current_gallery',[])
        identity=prepared.pop('_note_identity',{})
        if needs_identity and not _valid_note_identity(db,row,identity):
            raise ImportProblem('The original photos could not verify one banknote with a clear front and back. No draft fields or selected photos were changed; refresh the listing evidence and retry Check.')
        note={column[1]:None for column in db.execute('PRAGMA table_info(banknotes)')}
        note.update(fields);note.update(photos);note.update(id=item_id,_check_sources=prepared)
        if inspection:
            # Uncertain sides must not suppress the original holder evidence.
            # These temporary inputs never become selected display photographs.
            used={note.get(field) for field in ('image_1','image_2') if note.get(field)}
            for field in ('image_1','image_2'):
                if not note.get(field):
                    current_urls={entry['source_url'] for entry in current_gallery}
                    candidate=next((asset['filename'] for asset in assets if asset['source_url'] in current_urls and asset['filename'] not in used),None)
                    if candidate:
                        note[field]=candidate;used.add(candidate);note['_inspection_unassigned_photos']=True
        result=evaluate(note,prepared)
        _verify_original_assets(assets,folder)
        if inspection:
            result=dict(result,filled={field:value for field,value in result.get('filled',{}).items()
                                      if field in _INSPECTION_FIELDS})
        def publish(outgoing_photos,display_edits,expected_images,*,final):
            nonlocal revision
            db.execute('BEGIN IMMEDIATE')
            batch,current=_item(db,batch_id,item_id)
            current_context=_check_context(db,batch,current)
            if (current_context!=context or current['revision']!=revision or current['check_token']!=token or current['check_expires']<=time.time()):
                raise ImportProblem('The draft changed while Check was running. Your edits were kept; press Check again.')
            _verify_original_assets(assets,folder)
            if needs_identity and not _valid_note_identity(db,current,identity):
                raise ImportProblem('The verified note photos or listing changed while Check was running. Your draft was kept; retry Check.')
            current_fields=json.loads(current['fields_json'])
            filled={} if checkpointed else result.get('filled',{})
            applied=set()
            for field,value in {**outgoing_photos,**filled}.items():
                retry_crop=(field in display_edits and field in expected_images
                            and current_fields.get(field)==expected_images[field])
                if field in note and (banknote_catalog_lookup.is_blank(current_fields.get(field)) or retry_crop):
                    current_fields[field]=value
                    applied.add(field)
            for field,edit in display_edits.items():
                if current_fields.get(field)!=edit['filename']:
                    continue
                db.execute('''INSERT INTO banknote_import_image_edits
                    (filename,item_id,field,base_filename,source_filename,quad_json,sha256,created_at)
                    VALUES(?,?,?,?,?,?,?,?)''',(edit['filename'],item_id,field,edit['source'],edit['source'],
                    edit['quad'],edit['sha256'],time.time()))
                db.execute('INSERT INTO trimmed_image_sources(trimmed,source,quad) VALUES(?,?,?)',
                    (edit['filename'],edit['source'],edit['quad']))
                retained.add(edit['filename'])
            proofs={field:proof for field,proof in result.get('catalogue',{}).get('fields',{}).items()
                    if field in filled and current_fields.get(field)==proof.get('value')
                    and (not inspection or field in applied)}
            if proofs:
                current_fields['note_references_research']=banknote_catalog_proposals.append_reference_notes(
                    current_fields.get('note_references_research'),proofs,banknote_catalog_lookup.identity_snapshot(current_fields),time.strftime('%Y-%m-%d',time.gmtime()))
                for field,proof in proofs.items():
                    db.execute('''INSERT OR REPLACE INTO banknote_import_evidence
                        (item_id,field,value_json,proof_json,accepted_at,identity_json) VALUES(?,?,?,?,?,?)''',
                        (item_id,field,_json(proof['value']),_json(proof),time.time(),_json(banknote_catalog_lookup.identity_snapshot(current_fields))))
            for asset in assets:
                db.execute('''INSERT OR IGNORE INTO banknote_import_assets(item_id,source_url,filename,sha256,width,height,position)
                    VALUES(?,?,?,?,?,?,?)''',(item_id,asset['source_url'],asset['filename'],asset['sha256'],asset.get('width'),asset.get('height'),asset['position']))
            warnings=list(dict.fromkeys(prepared['warnings']+[result['lookup_error']] if result.get('lookup_error') else prepared['warnings']))
            missing=[label for field,label in (('country','country'),('denomination','denomination'))
                     if banknote_catalog_lookup.is_blank(current_fields.get(field))]
            if all(banknote_catalog_lookup.is_blank(current_fields.get(field)) for field in ('pick_number','other_catalog')):
                missing.append('catalogue number')
            if missing:
                warnings.append('Check could not confirm '+', '.join(missing)+'. Review the listing and original photos or retry Check.')
            if _manually_selected_pair(current_fields,json.loads(current['manual_photos_json'] or '{}')):
                warnings=[warning for warning in warnings if warning not in PHOTO_SIDE_WARNINGS]
            db.execute('''UPDATE banknote_import_items SET fields_json=?,note_identity_json=?,revision=revision+1,updated_at=? WHERE id=?''',
                (_json(current_fields),_json(identity) if needs_identity else current['note_identity_json'],time.time(),item_id))
            if final:
                db.execute('''UPDATE banknote_import_items SET check_state=?,check_message=?,retry_photos=0,
                    check_token=NULL,check_expires=0,checked_at=? WHERE id=?''',
                    ('partial' if warnings else 'done',' '.join(warnings),time.time(),item_id))
            else:
                db.execute('''UPDATE banknote_import_items SET check_message=?,check_expires=? WHERE id=?''',
                    ('Note details saved; preparing display crops.',time.time()+CHECK_TTL,item_id))
            db.commit()
            revision+=1
            return current_fields

        # Optional crop latency must not erase completed identification. The
        # checkpoint retains the active token and advances its revision, so a
        # refresh/new writer still invalidates only the remaining crop work.
        expected_images=publish(photos,{}, {},final=False)
        checkpointed=True
        # Vision reads the full saved originals first. Display preparation is
        # for newly selected empty slots or an explicit retry of an untouched
        # original. Accepted crops, manual choices and collection photos stay put.
        # Detection runs outside the write lock; publication below still checks
        # the draft revision/token. A stale result cannot replace newer edits.
        display_edits={}
        if prepare_photo:
            crop_note={**note,**result.get('filled',{})}
            for field,source in list(photos.items()):
                active=db.execute('SELECT revision,check_token,check_expires FROM banknote_import_items WHERE id=?',(item_id,)).fetchone()
                if (not active or active['revision']!=revision or active['check_token']!=token
                        or active['check_expires']<=time.time()):
                    raise ImportProblem('Automatic cropping was interrupted; the saved note details and originals were kept. Retry Crop photos.')
                try:
                    raw=(Path(folder)/source).read_bytes()
                    asset=next(asset for asset in assets if asset['filename']==source)
                    if hashlib.sha256(raw).hexdigest()!=asset['sha256']:
                        raise ValueError('Source image changed')
                    crop=_saved_preview_crop(db,row,asset,folder,retry=retry_automatic) or prepare_photo(raw,crop_note)
                    if not crop:continue
                    filename=uuid.uuid4().hex+'.jpg';path=Path(folder)/filename
                    created.append(path);path.write_bytes(crop['data'])
                    display_edits[field]=dict(filename=filename,source=source,
                        quad=_json(crop.get('quad')),sha256=hashlib.sha256(crop['data']).hexdigest())
                    photos[field]=filename
                except Exception:
                    prepared['warnings'].append('An imported photo could not be cropped; its original was retained.')
        publish(photos,display_edits,expected_images,final=True)
        committed=True
    except Exception as error:
        db.rollback()
        message=str(error) if isinstance(error,ImportProblem) else 'Check could not finish. Your saved draft was kept; retry Check.'
        state='failed'
        if checkpointed:
            state='partial'
            message='The note details and original photos were saved, but automatic cropping did not finish. Use Crop photos to retry.'
        db.execute("UPDATE banknote_import_items SET check_state=?,check_message=?,check_token=NULL,check_expires=0 WHERE id=? AND check_token=?",
                   (state,message,item_id,token));db.commit()
    finally:
        db.close()
        for path in created:
            if not committed or path.name not in retained:path.unlink(missing_ok=True)


def claim_check(db,batch_id,item_id,revision):
    if type(revision) is not int:raise ImportProblem('Check requires the current draft revision.')
    db.execute('BEGIN IMMEDIATE')
    try:
        batch,row=_item(db,batch_id,item_id)
        _check_context(db,batch,row)
        if row['revision']!=revision:raise ImportProblem('The draft changed. Reload it before checking.',code='draft_changed')
        if row['check_state']=='checking' and row['check_expires']>time.time():
            db.commit();return None
        token=uuid.uuid4().hex
        db.execute("UPDATE banknote_import_items SET check_state='checking',check_message='',check_token=?,check_expires=? WHERE id=?",(token,time.time()+CHECK_TTL,item_id))
        db.commit();return token
    except Exception:db.rollback();raise


def release(db,batch_id,selected,folder,create,*,automatic_single=False):
    if not isinstance(selected,list) or not 1<=len(selected)<=MAX_ITEMS:raise ImportProblem('Select the draft notes to release.')
    if any(not isinstance(entry,dict) or not isinstance(entry.get('id'),str) or type(entry.get('revision')) is not int for entry in selected):
        raise ImportProblem('Release requires exact drafts and their current revisions.')
    if len({entry['id'] for entry in selected})!=len(selected):raise ImportProblem('A draft was selected more than once.')
    copies=[];released=[]
    db.execute('BEGIN IMMEDIATE')
    try:
        batch=_batch(db,batch_id)
        if automatic_single:
            single=_single_item(db,batch)
            same_item=bool(single and len(selected)==1 and selected[0]['id']==single['id'])
            already_finished=bool(same_item and single['state']=='released' and single['released_record_id']
                and db.execute('SELECT 1 FROM banknotes WHERE id=?',(single['released_record_id'],)).fetchone())
            if not already_finished and (not same_item
                    or selected[0]['revision']!=single['revision'] or not _single_ready(db,batch,single)):
                raise ImportProblem('This order needs review before it can be added to the collection.')
        for entry in selected:
            _,row=_item(db,batch_id,entry['id'])
            if row['state']=='released':
                released.append(dict(id=row['id'],record_id=row['released_record_id']));continue
            if row['state'] not in ('draft','blocked') or row['revision']!=entry['revision']:raise ImportProblem('A selected draft changed. Review the latest version before release.',code='draft_changed')
            if _check_active(row):raise ImportProblem('Wait for Check to finish before releasing this draft.')
            source=_editable_source(db,batch,row)
            _verify_original_assets([dict(asset) for asset in db.execute(
                'SELECT * FROM banknote_import_assets WHERE item_id=?',(row['id'],))],folder)
            linked=db.execute('SELECT banknote_id FROM banknote_ebay_links WHERE line_key=?',(row['line_key'],)).fetchone()
            if linked:raise ImportProblem('This purchased item was already added to the collection. Refresh the review list.')
            fields=json.loads(row['fields_json'])
            fields['order_number']=source['order_id'];fields['marketplace']='eBay'
            if row['state']=='blocked':
                # Explicit review accepts this exact note into the collection,
                # never delivery or ownership. Preserve the warning and retain
                # the existing authenticated item-price authority.
                paid=ebay_purchase_prices.for_item(db,source)
                fields.update(status='Ordered',price=paid['price'] if paid else '',
                              vendor=source['seller'],purchase_date=(source.get('ordered_at') or '')[:10])
            image_edits=_image_edits(db,row,fields)
            existing=None
            if not row['existing_record_id'] and _existing_matches(db,source):
                raise ImportProblem('This exact purchased listing now has a collection record. Refresh the order review before release; no duplicate was created.')
            if row['existing_record_id']:
                live=db.execute('SELECT * FROM banknotes WHERE id=?',(row['existing_record_id'],)).fetchone()
                existing=json.loads(row['existing_snapshot_json'])
                if not live:
                    raise ImportProblem('The existing banknote is unavailable. Review the collection before release.')
                if _existing_record_changes(existing,dict(live)):
                    raise ImportProblem('The existing banknote changed since import. Its fields and photographs were kept; review the changes before release.',
                                        code='existing_record_changed',item=_public_item(db,row))
                if db.execute('SELECT 1 FROM banknote_ebay_links WHERE banknote_id=?',(live['id'],)).fetchone():
                    raise ImportProblem('The existing banknote is already linked to a purchased item. Review its order link before release.')
                if not db.execute('SELECT 1 FROM banknote_original_listings WHERE banknote_id=? AND url=?',
                        (live['id'],'https://www.ebay.com/itm/'+source['item_id'])).fetchone():
                    raise ImportProblem('The existing banknote listing changed. Review it before release.')
                crops=_preserved_image_edits(db,row,fields,existing)
                fields.update({key:value for key,value in existing.items() if not banknote_catalog_lookup.is_blank(value)})
                fields.update(crops)
                image_edits={field:edit for field,edit in image_edits.items() if field in crops}
            for field in ('image_1','image_2'):
                if fields.get(field):
                    if existing and existing.get(field)==fields[field]:continue
                    asset=db.execute('SELECT * FROM banknote_import_assets WHERE item_id=? AND filename=?',(row['id'],fields[field])).fetchone()
                    path=Path(folder)/fields[field]
                    edit=image_edits.get(field)
                    if ((not asset and not edit) or path.name!=fields[field] or path.resolve().parent!=Path(folder).resolve()
                            or not path.is_file()):raise ImportProblem('A draft photograph is unavailable; check the draft before releasing it.')
                    if edit and hashlib.sha256(path.read_bytes()).hexdigest()!=edit['sha256']:
                        raise ImportProblem('The saved draft crop changed on disk. Reopen its photo editor before release.')
                    filename=uuid.uuid4().hex+path.suffix;destination=Path(folder)/filename
                    shutil.copyfile(path,destination);copies.append(destination);fields[field]=filename
                    transform=db.execute('SELECT source,quad FROM trimmed_image_sources WHERE trimmed=?',(path.name,)).fetchone()
                    if transform:
                        db.execute('INSERT INTO trimmed_image_sources(trimmed,source,quad) VALUES(?,?,?)',
                                   (filename,transform['source'],transform['quad']))
            ident=create(db,fields,existing,image_overrides=tuple(image_edits))
            if automatic_single and row['check_state']=='done' and row['checked_at']:
                from datetime import datetime, timezone
                checked=datetime.fromtimestamp(row['checked_at'],timezone.utc).replace(tzinfo=None).isoformat()
                db.execute('UPDATE banknotes SET specs_searched_at=? WHERE id=?',(checked,ident))
                record=db.execute('SELECT * FROM banknotes WHERE id=?',(ident,)).fetchone()
                original_listings.listing_checks.clear_failed_after_check(db,'banknotes',record,
                    ['https://www.ebay.com/itm/'+source['item_id']])
            identity=banknote_catalog_lookup.identity_snapshot(fields)
            proofs={proof['field']:json.loads(proof['proof_json']) for proof in db.execute(
                'SELECT * FROM banknote_import_evidence WHERE item_id=?',(row['id'],))
                if json.loads(proof['identity_json'])==identity and json.loads(proof['value_json'])==fields.get(proof['field'])}
            if proofs:
                proposal=banknote_catalog_proposals.create(db,ident,identity,proofs)
                banknote_catalog_proposals.mark_accepted(db,proposal,{field:proof['value'] for field,proof in proofs.items()})
            db.execute('INSERT INTO banknote_ebay_links(banknote_id,line_key,matched_by,matched_at) VALUES(?,?,?,?)',(ident,row['line_key'],'manual',time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
            url='https://www.ebay.com/itm/'+source['item_id'];original_listings.add_source(db,'banknotes',ident,url)
            source_documents.enqueue(db,'banknotes',ident,url,'eBay Original Listing','listing')
            source_documents.enqueue(db,'banknotes',ident,'https://order.ebay.com/ord/show?orderId='+source['order_id'],'eBay Order Receipt '+source['order_id'],'order')
            for asset in db.execute('SELECT * FROM banknote_import_assets WHERE item_id=? ORDER BY position',(row['id'],)).fetchall():
                db.execute('INSERT OR IGNORE INTO original_image_assets(url,filename,sha256,width,height,saved_at) VALUES(?,?,?,?,?,?)',
                           (asset['source_url'],asset['filename'],asset['sha256'],asset['width'],asset['height'],time.time()))
                db.execute('INSERT OR IGNORE INTO original_listing_image_sources(listing_url,image_url,position) VALUES(?,?,?)',(url,asset['source_url'],asset['position']))
            listing_images.attach_saved(db,'banknotes',ident,url)
            db.execute("UPDATE banknote_import_items SET state='released',released_record_id=?,revision=revision+1,updated_at=? WHERE id=?",(ident,time.time(),row['id']))
            released.append(dict(id=row['id'],record_id=ident))
        pending=db.execute("SELECT COUNT(*) FROM banknote_import_items WHERE batch_id=? AND state!='released'",(batch_id,)).fetchone()[0]
        db.execute('UPDATE banknote_import_batches SET state=?,updated_at=? WHERE id=?',('review' if pending else 'complete',time.time(),batch_id))
        db.commit()
    except Exception:
        db.rollback()
        for path in copies:path.unlink(missing_ok=True)
        raise
    other_pending=db.execute("SELECT 1 FROM banknote_import_batches WHERE account_name=? AND id!=? AND state!='complete' LIMIT 1",
                             (batch['account_name'],batch_id)).fetchone()
    next_url=f'/banknotes/imports/{batch_id}' if pending else '/banknotes/imports/new' if other_pending else '/banknotes'
    return dict(ok=True,released=released,pending_count=pending,next_url=next_url)
