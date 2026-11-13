"""Date coverage and durable jobs for additions to monetary-history tables."""
import hashlib
import json
import time
import uuid
from urllib.parse import urlparse


def merge_eras(existing, additions):
    """Keep established history intact, including issuer-gated overlapping bands."""
    result = list(existing)
    for era in additions:
        if not any(era[0] <= old[1] and old[0] <= era[1] for old in result):
            result.append(era)
    return tuple(sorted(result, key=lambda e: e[0]))


def missing_years(eras, years):
    return sorted({int(y) for y in years if y and
                   not any(e[0] <= int(y) <= e[1] for e in eras)})


def validate(data, years=(), existing=(), observed_sources=None):
    """Reject wrong-date, overlapping, unsourced or incomplete model additions."""
    title = str(data.get('title') or '').strip()
    eras = []
    for e in data.get('eras') or []:
        start, end = int(e['start']), int(e['end'])
        label, body = str(e.get('label') or '').strip(), str(e.get('body') or '').strip()
        if start < 1 or end > 2100 or start > end or not label or not body:
            raise RuntimeError('Invalid history period')
        eras.append([start, end, label, body])
    eras.sort(key=lambda e: e[0])
    if not title or not 1 <= len(eras) <= 12:
        raise RuntimeError('History response has no usable periods')
    if any(a[1] >= b[0] for a, b in zip(eras, eras[1:])):
        raise RuntimeError('New history periods overlap')
    if len(merge_eras(existing, eras)) != len(existing) + len(eras):
        raise RuntimeError('New history would overwrite an existing period')
    if missing_years(eras, years):
        raise RuntimeError('History response does not cover the missing note dates')
    sources = []
    for source in data.get('sources') or []:
        url = str(source.get('url') or '').strip()
        parsed = urlparse(url)
        if parsed.scheme in ('http', 'https') and parsed.hostname:
            if observed_sources is not None and url not in observed_sources:
                raise RuntimeError('History source was not returned by web research')
            sources.append({'title': str(source.get('title') or '').strip(), 'url': url})
    if not sources:
        raise RuntimeError('History response needs published sources')
    return {'title': title, 'eras': eras, 'sources': sources,
            'spellings': [str(s).strip().lower() for s in data.get('spellings') or [] if str(s).strip()]}


def init_schema(db):
    db.execute('''CREATE TABLE IF NOT EXISTS country_history_jobs (
        country_key TEXT PRIMARY KEY, request_key TEXT NOT NULL,
        token TEXT NOT NULL, state TEXT NOT NULL, attempts INTEGER NOT NULL,
        retry_after REAL NOT NULL DEFAULT 0, lease_until REAL NOT NULL DEFAULT 0,
        error TEXT)''')
    db.execute('''CREATE TABLE IF NOT EXISTS country_history_updates (
        token TEXT PRIMARY KEY, country_key TEXT NOT NULL,
        eras TEXT NOT NULL, sources TEXT NOT NULL, completed_at REAL NOT NULL)''')


def claim(db, key, years, existing, force=False):
    """One job per country across workers; expired leases can be recovered."""
    now = time.time()
    request_key = hashlib.sha256(json.dumps([sorted(years), existing], sort_keys=True).encode()).hexdigest()
    db.execute('BEGIN IMMEDIATE')
    try:
        old = db.execute('SELECT * FROM country_history_jobs WHERE country_key=?', (key,)).fetchone()
        if old and old['state'] == 'pending' and old['lease_until'] > now:
            db.rollback()
            return None
        attempts = old['attempts'] if old and old['request_key'] == request_key else 0
        if not force and old and old['request_key'] == request_key and (
                attempts >= 3 or old['retry_after'] > now):
            db.rollback()
            return None
        token = uuid.uuid4().hex
        db.execute('''INSERT OR REPLACE INTO country_history_jobs
            (country_key, request_key, token, state, attempts, retry_after, lease_until)
            VALUES (?, ?, ?, 'pending', ?, 0, ?)''',
                   (key, request_key, token, 1 if force else attempts + 1, now + 900))
        db.commit()
        return token
    except Exception:
        db.rollback()
        raise


def fail(db, key, token, error):
    # A delayed former worker must never change a replacement worker's job.
    db.execute('''UPDATE country_history_jobs SET state='failed', error=?,
        retry_after=?, lease_until=0 WHERE country_key=? AND token=?''',
               (str(error)[:500], time.time() + 60, key, token))
    db.commit()


def state(db, key):
    row = db.execute('SELECT * FROM country_history_jobs WHERE country_key=?', (key,)).fetchone()
    if row and ((row['state'] == 'pending' and row['lease_until'] > time.time())
                or (row['state'] == 'failed' and row['attempts'] < 3)):
        return 'pending'
    return 'missing'
