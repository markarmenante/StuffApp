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
_BUNDLE = re.compile(r'\b(?:lot|set|bundle|pair)\s*(?:of\s*)?[2-9]\d*\b|\bpair of\b|\b[2-9]\d*\s+(?:consecutive\s+)?(?:serial\s+)?(?:notes|banknotes)\b', re.I)


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
        snapshot_json TEXT NOT NULL DEFAULT '[]', created_at REAL NOT NULL, updated_at REAL NOT NULL,
        UNIQUE(account_name,order_id));
    CREATE TABLE IF NOT EXISTS banknote_import_items (
        id TEXT PRIMARY KEY, batch_id TEXT NOT NULL REFERENCES banknote_import_batches(id),
        account_name TEXT NOT NULL, line_key TEXT NOT NULL, item_id TEXT NOT NULL,
        source_json TEXT NOT NULL, source_digest TEXT NOT NULL, fields_json TEXT NOT NULL,
        state TEXT NOT NULL DEFAULT 'draft', revision INTEGER NOT NULL DEFAULT 1,
        released_record_id TEXT, existing_record_id TEXT, existing_snapshot_json TEXT,
        manual_photos_json TEXT NOT NULL DEFAULT '{}',
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
    CREATE TABLE IF NOT EXISTS banknote_import_evidence (
        item_id TEXT NOT NULL REFERENCES banknote_import_items(id), field TEXT NOT NULL,
        value_json TEXT NOT NULL, proof_json TEXT NOT NULL, accepted_at REAL NOT NULL,
        identity_json TEXT NOT NULL DEFAULT '{}',
        PRIMARY KEY(item_id,field));
    ''')
    if 'identity_json' not in {row[1] for row in db.execute('PRAGMA table_info(banknote_import_evidence)')}:
        db.execute("ALTER TABLE banknote_import_evidence ADD COLUMN identity_json TEXT NOT NULL DEFAULT '{}'")
    columns={row[1] for row in db.execute('PRAGMA table_info(banknote_import_items)')}
    for name in ('existing_record_id','existing_snapshot_json'):
        if name not in columns:db.execute('ALTER TABLE banknote_import_items ADD COLUMN '+name+' TEXT')
    if 'manual_photos_json' not in columns:
        db.execute("ALTER TABLE banknote_import_items ADD COLUMN manual_photos_json TEXT NOT NULL DEFAULT '{}'")


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


def _reason(item):
    if item.get('ignored'):
        return 'This purchase was excluded from eBay order matching. Review it before importing.'
    if item.get('quantity') != 1 or _BUNDLE.search(item.get('title') or ''):
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
            db.commit()
            return existing['id']
        if existing and existing['request_id']:
            request = db.execute("SELECT q.*,s.expires_at FROM ebay_purchase_requests q LEFT JOIN ebay_purchase_request_sessions s ON s.request_id=q.id WHERE q.id=?", (existing['request_id'],)).fetchone()
            if request and request['status'] in ('queued','reading') and (request['expires_at'] or request['requested_at']+120) > now:
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
        db.execute('''INSERT INTO banknote_import_batches(id,account_name,order_id,request_id,created_at,updated_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(account_name,order_id) DO UPDATE SET request_id=excluded.request_id,
            state='queued',message='',updated_at=excluded.updated_at''', (batch_id,account,number,request_id,now,now))
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
    photos = [dict(url='/uploads/'+asset['filename'],filename=asset['filename'],selectable=True,source_url=asset['source_url'],position=asset['position'])
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
                image_sources={field:edit['source_filename'] for field,edit in _image_edits(db,row,fields).items()})


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
    return dict(id=batch_id,order_number=batch['order_id'],state=state,message=message,items=items,
                pending_count=sum(item['state']!='released' for item in items),
                url=f'/banknotes/imports/{batch_id}',status_url=f'/banknotes/imports/{batch_id}/status')


def _validate_source(db,batch,row):
    if batch['state'] not in ('review','complete'):
        raise ImportProblem('Wait for the fresh order read to finish before checking or releasing this draft.')
    if [json.loads(row['source_json'])['order_id'],row['item_id']] not in json.loads(batch['snapshot_json']):
        raise ImportProblem('This item is absent from the verified order snapshot.')
    if row['account_name'] != _account(db):
        raise ImportProblem('The connected eBay account changed; the draft was kept.')
    source=db.execute('SELECT * FROM ebay_order_items WHERE line_key=?',(row['line_key'],)).fetchone()
    if not source or _digest(dict(source)) != row['source_digest']:
        raise ImportProblem('The purchased item details changed. Review the order again before releasing it.')
    reason=_reason(dict(source))
    if reason:
        raise ImportProblem(reason)
    return dict(source)


def save(db,batch_id,item_id,revision,updates,normalize):
    if type(revision) is not int or not isinstance(updates,dict) or not updates:
        raise ImportProblem('Save requires the current draft revision and edited fields.')
    normalized=normalize(updates)
    db.execute('BEGIN IMMEDIATE')
    try:
        batch,row=_item(db,batch_id,item_id)
        if row['state']!='draft' or row['revision']!=revision:
            raise ImportProblem('This draft changed or was released. Reload it before saving.', code='draft_changed')
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
        if row['check_state']=='checking' and row['check_expires']>time.time():
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
    """Only a crop explicitly saved for this exact draft side may replace it."""
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
    _validate_source(db,batch,row)
    if row['state']!='draft' or (revision is not None and row['revision']!=revision):
        raise ImportProblem('This draft changed or was released. Reopen the photo editor.',code='draft_changed')
    if row['check_state']=='checking' and row['check_expires']>time.time():
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
        _validate_source(db,batch,row)
        if row['state']!='draft' or row['revision']!=revision:
            raise ImportProblem('This draft changed or was released. Reload it before choosing a photo.',code='draft_changed')
        if row['check_state']=='checking' and row['check_expires']>time.time():
            raise ImportProblem('Wait for Check to finish before choosing draft photos.')
        existing=json.loads(row['existing_snapshot_json'] or '{}')
        if not banknote_catalog_lookup.is_blank(existing.get(field)):
            raise ImportProblem('This photo already belongs to the existing record and is preserved. Open that record to change it.')
        asset=db.execute('SELECT * FROM banknote_import_assets WHERE item_id=? AND filename=?',(item_id,filename)).fetchone()
        root=Path(folder).resolve();path=root/filename
        if not asset or path.resolve().parent!=root or not path.is_file():
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
    chosen=banknote_photo_sides.select(assets,folder,classify,existing=fields)
    warnings.extend(chosen['warnings'])
    photos={field:asset['filename'] for field,asset in chosen['images'].items() if not fields.get(field)}
    return dict(evidence=evidence,reports=['Exact order item isolated from sibling purchases.'],warnings=warnings,
                documents=[],images={},purchase=purchase,purchase_price_fill_only=True,purchase_price_blocked=not bool(paid)),assets,photos


def run_check(connect,batch_id,item_id,revision,token,folder,classify,evaluate):
    db=connect()
    try:
        batch,row=_item(db,batch_id,item_id)
        _validate_source(db,batch,row)
        fields=json.loads(row['fields_json'])
        prepared,assets,photos=_source_inputs(db,row,fields,folder,classify)
        # Save source photographs before the slower catalogue call. A provider
        # failure or restart must not discard the already captured originals.
        db.execute('BEGIN IMMEDIATE')
        batch,current=_item(db,batch_id,item_id)
        _validate_source(db,batch,current)
        if current['state']!='draft' or current['check_token']!=token or current['check_expires']<=time.time():
            raise ImportProblem('This draft Check expired. The draft was kept; press Check again.')
        for asset in assets:
            db.execute('''INSERT OR IGNORE INTO banknote_import_assets(item_id,source_url,filename,sha256,width,height,position)
                VALUES(?,?,?,?,?,?,?)''',(item_id,asset['source_url'],asset['filename'],asset['sha256'],asset.get('width'),asset.get('height'),asset['position']))
        db.commit()
        note={column[1]:None for column in db.execute('PRAGMA table_info(banknotes)')}
        note.update(fields);note.update(photos);note.update(id=item_id,_check_sources=prepared)
        result=evaluate(note,prepared)
        db.execute('BEGIN IMMEDIATE')
        batch,current=_item(db,batch_id,item_id)
        _validate_source(db,batch,current)
        if (current['state']!='draft' or current['revision']!=revision or current['check_token']!=token or current['check_expires']<=time.time()):
            raise ImportProblem('The draft changed while Check was running. Your edits were kept; press Check again.')
        current_fields=json.loads(current['fields_json'])
        for field,value in {**photos,**result.get('filled',{})}.items():
            if field in note and banknote_catalog_lookup.is_blank(current_fields.get(field)):
                current_fields[field]=value
        proofs={field:proof for field,proof in result.get('catalogue',{}).get('fields',{}).items()
                if field in result.get('filled',{}) and current_fields.get(field)==proof.get('value')}
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
        if _manually_selected_pair(current_fields,json.loads(current['manual_photos_json'] or '{}')):
            warnings=[warning for warning in warnings if warning not in PHOTO_SIDE_WARNINGS]
        db.execute('''UPDATE banknote_import_items SET fields_json=?,revision=revision+1,check_state=?,check_message=?,
            check_token=NULL,check_expires=0,checked_at=?,updated_at=? WHERE id=?''',
            (_json(current_fields),'partial' if warnings else 'done',' '.join(warnings),time.time(),time.time(),item_id))
        db.commit()
    except Exception as error:
        db.rollback()
        message=str(error) if isinstance(error,ImportProblem) else 'Check could not finish. Your saved draft was kept; retry Check.'
        db.execute("UPDATE banknote_import_items SET check_state='failed',check_message=?,check_token=NULL,check_expires=0 WHERE id=? AND check_token=?",
                   (message,item_id,token));db.commit()
    finally:db.close()


def claim_check(db,batch_id,item_id,revision):
    if type(revision) is not int:raise ImportProblem('Check requires the current draft revision.')
    db.execute('BEGIN IMMEDIATE')
    try:
        batch,row=_item(db,batch_id,item_id)
        _validate_source(db,batch,row)
        if row['state']!='draft' or row['revision']!=revision:raise ImportProblem('The draft changed. Reload it before checking.',code='draft_changed')
        if row['check_state']=='checking' and row['check_expires']>time.time():
            db.commit();return None
        token=uuid.uuid4().hex
        db.execute("UPDATE banknote_import_items SET check_state='checking',check_message='',check_token=?,check_expires=? WHERE id=?",(token,time.time()+CHECK_TTL,item_id))
        db.commit();return token
    except Exception:db.rollback();raise


def release(db,batch_id,selected,folder,create):
    if not isinstance(selected,list) or not 1<=len(selected)<=MAX_ITEMS:raise ImportProblem('Select the draft notes to release.')
    if any(not isinstance(entry,dict) or not isinstance(entry.get('id'),str) or type(entry.get('revision')) is not int for entry in selected):
        raise ImportProblem('Release requires exact drafts and their current revisions.')
    if len({entry['id'] for entry in selected})!=len(selected):raise ImportProblem('A draft was selected more than once.')
    copies=[];released=[]
    db.execute('BEGIN IMMEDIATE')
    try:
        batch=_batch(db,batch_id)
        for entry in selected:
            _,row=_item(db,batch_id,entry['id'])
            if row['state']=='released':
                released.append(dict(id=row['id'],record_id=row['released_record_id']));continue
            if row['state']!='draft' or row['revision']!=entry['revision']:raise ImportProblem('A selected draft changed. Review the latest version before release.',code='draft_changed')
            if row['check_state']=='checking' and row['check_expires']>time.time():raise ImportProblem('Wait for Check to finish before releasing this draft.')
            source=_validate_source(db,batch,row)
            linked=db.execute('SELECT banknote_id FROM banknote_ebay_links WHERE line_key=?',(row['line_key'],)).fetchone()
            if linked:raise ImportProblem('This purchased item was already added to the collection. Refresh the review list.')
            fields=json.loads(row['fields_json'])
            fields['order_number']=source['order_id'];fields['marketplace']='eBay'
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
