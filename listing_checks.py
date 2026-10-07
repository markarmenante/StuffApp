"""One successful source comparison per original listing; never edits item facts."""
import hashlib
import json
import time
import uuid

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
    return ' '.join(display(value).split()).casefold()


def validate_result(category, record, page_text, result):
    if not isinstance(result, dict) or not isinstance(result.get('comparisons'), list):
        raise ValueError('No structured comparison')
    comparisons, seen = [], set()
    for item in result['comparisons']:
        if not isinstance(item, dict):
            raise ValueError('Invalid comparison')
        field = item.get('field')
        quote, value = item.get('evidence'), item.get('listing_value')
        outcome = item.get('outcome')
        if (field not in FIELDS[category] or field in seen or outcome not in ('match', 'different', 'missing', 'uncertain')
                or not isinstance(quote, str) or not 3 <= len(quote) <= 600
                or not isinstance(value, str) or not 1 <= len(value) <= 300
                or normalized(quote) not in normalized(page_text)):
            raise ValueError('Comparison lacks valid source evidence')
        stored = display(record.get(field))
        if outcome == 'missing' and stored:
            raise ValueError('Stored field is not missing')
        if outcome == 'different' and normalized(stored) == normalized(value):
            outcome = 'match'
        seen.add(field)
        comparisons.append(dict(field=field, label=LABELS.get(field, field.replace('_', ' ').capitalize()),
                                stored=stored, listed=value, evidence=quote, outcome=outcome))
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


def report(db, category, record_id):
    key = 'coin_id' if category == 'coins' else 'banknote_id'
    row = db.execute(f'SELECT * FROM original_listing_checks WHERE {key}=?', (record_id,)).fetchone()
    if not row:
        return None
    comparisons = json.loads(row['result'] or '[]')
    differences = [c for c in comparisons if c['outcome'] != 'match']
    return dict(state=row['state'], dismissed=bool(row['dismissed']), differences=differences,
                compared=len(comparisons), token=token(row), checked_at=row['checked_at'])


def run_once(connect, fetch_page, analyze):
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
            # The model sees only the supported fields and the readable original listing.
            comparisons = validate_result(category, before, page_text,
                                          analyze(category, before, row['url'], page_text))
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
