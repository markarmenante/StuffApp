"""One successful source comparison per original listing; never edits item facts."""
import hashlib
import json
import re
import time
import unicodedata
import uuid
from pathlib import Path

COMMON_FIELDS = ('denomination', 'date_1', 'date_2', 'grade', 'grading_authority',
                 'grade_modifier', 'slab_number', 'price')
FIELDS = {
    'coins': COMMON_FIELDS + ('region', 'authority', 'metal', 'mint', 'weight', 'size', 'die_axis'),
    'banknotes': COMMON_FIELDS + ('country', 'issuer', 'series', 'pick_number', 'other_catalog',
                                  'serial_number', 'material', 'grade_numeric', 'size_width', 'size_height'),
}
LABELS = {'date_1': 'Date from', 'date_2': 'Date to', 'slab_number': 'Certificate',
          'grading_authority': 'Grading service', 'grade_modifier': 'Grade designation',
          'size': 'Diameter', 'die_axis': 'Die axis', 'pick_number': 'Pick number'}


def snapshot(category, record):
    return {field: dict(record).get(field) for field in FIELDS[category]}


def display(value):
    return '' if value is None else str(value)


def normalized(value):
    return ' '.join(unicodedata.normalize('NFKC', display(value)).split()).casefold()


def same_value(stored, listed):
    return bool(normalized(stored)) and normalized(stored) == normalized(listed)


def differences(comparisons):
    # Also suppress identical-value warnings in checks saved before validation was tightened.
    return [c for c in comparisons if c['outcome'] != 'match' and not c.get('resolution')
            and not same_value(c.get('stored'), c.get('listed'))]


def proposed_value(category, item):
    field, value = item.get('field'), display(item.get('listed')).strip()
    if field not in FIELDS[category] or not value or len(value) > 300:
        return None
    if field in ('date_1', 'date_2'):
        match = re.fullmatch(r'(-?\d{1,4})\s*(BC|BCE|AD|CE)?(?:\s*\([^\n]*\))?', value, re.I)
        if not match:
            return None
        year = int(match[1])
        return str(-abs(year) if (match[2] or '').upper() in ('BC', 'BCE') else year)
    units = {'weight': r'g|gm|grams?', 'size': r'mm', 'size_width': r'mm',
             'size_height': r'mm', 'grade_numeric': r'', 'die_axis': r'h|hours?'}
    if field in units:
        match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*(?:' + units[field] + r')?', value, re.I)
        return match[1] if match else None
    return value


def current_comparisons(category, record, row, parse_price=None):
    result = []
    for saved in json.loads(row['result'] or '[]'):
        item = dict(saved)
        if row['record_snapshot']:
            item['stored'] = display(dict(record).get(item['field']))
        proposed = proposed_value(category, item)
        item['update_value'] = proposed
        equal = same_value(item['stored'], proposed)
        if item['field'] == 'price' and parse_price:
            native, listed = parse_price(item['stored']), parse_price(item['listed'])
            equal = native[1] is not None and native == listed
        if equal:
            item['outcome'] = 'match'
        elif saved['outcome'] == 'match' and item['stored'] != saved.get('stored'):
            item['outcome'] = 'different' if item['stored'] else 'missing'
        result.append(item)
    return result


def purchase_sources(db, category, record_id, folder):
    from banknote_check_sources import pdf_text
    import source_documents
    table, key = source_documents.TABLES[category]
    evidence = []
    for row in db.execute(f'SELECT a.url,a.title,a.filename FROM {table} l '
                          f'JOIN purchase_source_archives a ON a.url=l.url WHERE l.{key}=? '
                          "AND a.kind IN ('order','invoice') AND a.filename IS NOT NULL ORDER BY a.url LIMIT 6",
                          (record_id,)):
        filename = row['filename']
        if Path(filename).name != filename:
            continue
        try:
            text = pdf_text(Path(folder) / filename)
            if sum(len(e['text']) for e in evidence) + len(text) <= 90000:
                evidence.append(dict(url=row['url'], title=row['title'], text=text))
        except Exception:
            # An unreadable receipt must not prevent checking the listing's other fields.
            continue
    return evidence


def validate_result(category, record, page_text, result, sources=(), parse_price=None):
    if not isinstance(result, dict) or not isinstance(result.get('comparisons'), list):
        raise ValueError('No structured comparison')
    comparisons, seen = [], set()
    for item in result['comparisons']:
        if not isinstance(item, dict):
            raise ValueError('Invalid comparison')
        field = item.get('field')
        quote, value = item.get('evidence'), item.get('listing_value')
        outcome = item.get('outcome')
        source = next((s for s in sources if s['url'] == item.get('source_url')), None) if field == 'price' else None
        evidence_text = source['text'] if source else page_text
        if (field not in FIELDS[category] or field in seen or outcome not in ('match', 'different', 'missing', 'uncertain')
                or not isinstance(quote, str) or not 3 <= len(quote) <= 600
                or not isinstance(value, str) or not 1 <= len(value) <= 300
                or normalized(quote) not in normalized(evidence_text)):
            raise ValueError('Comparison lacks valid source evidence')
        stored = display(record.get(field))
        if outcome == 'missing' and stored:
            raise ValueError('Stored field is not missing')
        if same_value(stored, value):
            outcome = 'match'
        seen.add(field)
        if field == 'price' and source:
            identity = item.get('item_title')
            if (not parse_price or not isinstance(identity, str) or len(identity) < 16
                    or normalized(identity) not in normalized(quote)
                    or normalized(identity) not in normalized(page_text)
                    or normalized(value) not in normalized(quote)
                    or re.search(r'\b(?:order total|subtotal|shipping|tax|converted|exchange rate)\b', quote, re.I)
                    or not re.search(r'[\u20ac\u00a3\u00a5$]|\b[A-Z]{3}\b', value)):
                continue
            currency, amount = parse_price(value)
            if currency is None or amount is None or amount <= 0:
                continue
            outcome = ('missing' if not stored else 'match' if parse_price(stored) == (currency, amount)
                       else 'different')
        elif field == 'price' and (outcome == 'uncertain'
                or re.search(r'\b(?:asking|estimate|best offer|hammer)\b', quote + ' ' + value, re.I)
                or not re.search(r'\b(?:paid|order total|amount charged|purchase (?:price|total)|invoice total)\b', quote, re.I)):
            continue
        comparisons.append(dict(field=field, label=LABELS.get(field, field.replace('_', ' ').capitalize()),
                                stored=stored, listed=value, evidence=quote, outcome=outcome))
        if source:
            comparisons[-1].update(source_label=source['title'], source_url=source['url'])
    if not comparisons:
        raise ValueError('Listing contained no verifiable fields')
    return comparisons


def token(row):
    return hashlib.sha256(json.dumps([row['id'], row['url'], row['checked_at'], row['result']],
                                     sort_keys=True).encode()).hexdigest()


def ensure(db, category, record_id, url):
    key = 'coin_id' if category == 'coins' else 'banknote_id'
    db.execute(f'INSERT INTO original_listing_checks (id,{key},url) VALUES (?,?,?) '
               f'ON CONFLICT({key}) DO NOTHING', (str(uuid.uuid4()), record_id, url))
    db.execute(f"UPDATE original_listing_checks SET url=?,state='pending',attempts=0,next_attempt=0,"
               "lease_until=0,checked_at=NULL,dismissed=0,record_snapshot=NULL,result=NULL "
               f"WHERE {key}=? AND url<>?", (url, record_id, url))


def report(db, category, record_id, parse_price=None):
    key = 'coin_id' if category == 'coins' else 'banknote_id'
    row = db.execute(f'SELECT * FROM original_listing_checks WHERE {key}=?', (record_id,)).fetchone()
    if not row:
        return None
    record = db.execute(f'SELECT * FROM {category} WHERE id=?', (record_id,)).fetchone()
    if not record:
        return None
    comparisons = current_comparisons(category, record, row, parse_price)
    current_token = hashlib.sha256((token(row) + json.dumps(comparisons, sort_keys=True)).encode()).hexdigest()
    price = next((c for c in comparisons if c['field'] == 'price' and c.get('source_label')), None)
    return dict(state=row['state'], dismissed=bool(row['dismissed']), differences=differences(comparisons),
                compared=len(comparisons), token=current_token, checked_at=row['checked_at'], price=price)


def resolve(db, category, record_id, field, action, value=None):
    key = 'coin_id' if category == 'coins' else 'banknote_id'
    row = db.execute(f'SELECT * FROM original_listing_checks WHERE {key}=?', (record_id,)).fetchone()
    comparisons = json.loads(row['result'])
    for item in comparisons:
        if item['field'] == field:
            item.update(resolution=action, resolved_at=time.time())
            if action == 'updated':
                item['applied_value'] = value
    db.execute('UPDATE original_listing_checks SET result=? WHERE id=?', (json.dumps(comparisons), row['id']))


def run_once(connect, fetch_page, analyze, upload_folder=None, parse_price=None):
    db = connect()
    try:
        now = time.time()
        lease = now + 300
        db.execute('BEGIN IMMEDIATE')
        row = db.execute("SELECT c.* FROM original_listing_checks c JOIN original_listing_pages p ON p.url=c.url "
                         "WHERE c.state IN ('pending','failed') AND c.attempts<3 AND c.next_attempt<=? "
                         "AND c.lease_until<? AND p.state='available' AND p.checked_at>=? "
                         "ORDER BY c.next_attempt LIMIT 1", (now, now, now - 86400)).fetchone()
        if not row:
            db.rollback()
            return False
        category = 'coins' if row['coin_id'] else 'banknotes'
        record_id = row['coin_id'] or row['banknote_id']
        record = db.execute(f'SELECT * FROM {category} WHERE id=?', (record_id,)).fetchone()
        before = snapshot(category, record)
        db.execute('UPDATE original_listing_checks SET lease_until=?,attempts=attempts+1 WHERE id=?',
                   (lease, row['id']))
        db.commit()
        try:
            state, page_text = fetch_page(row['url'])
            if state != 'available':
                raise ValueError('Original listing is not readable')
            sources = purchase_sources(db, category, record_id, upload_folder) if upload_folder else []
            result = (analyze(category, before, row['url'], page_text, sources) if sources
                      else analyze(category, before, row['url'], page_text))
            comparisons = validate_result(category, before, page_text,
                                          result, sources, parse_price)
            db.execute('BEGIN IMMEDIATE')
            current = db.execute(f'SELECT * FROM {category} WHERE id=?', (record_id,)).fetchone()
            if not current:
                db.rollback()
                return True
            if snapshot(category, current) != before:
                db.execute("UPDATE original_listing_checks SET state='pending',lease_until=0,attempts=0,next_attempt=? "
                           'WHERE id=? AND url=? AND lease_until=?', (time.time() + 60, row['id'], row['url'], lease))
            else:
                db.execute("UPDATE original_listing_checks SET state='checked',checked_at=?,lease_until=0,"
                           'record_snapshot=?,result=? WHERE id=? AND url=? AND lease_until=?',
                           (time.time(), json.dumps(before), json.dumps(comparisons), row['id'], row['url'], lease))
            db.commit()
        except Exception:
            db.rollback()
            with db:
                db.execute("UPDATE original_listing_checks SET state='failed',lease_until=0,next_attempt=? "
                           'WHERE id=? AND url=? AND lease_until=?',
                           (time.time() + 3600, row['id'], row['url'], lease))
        return True
    finally:
        db.close()
