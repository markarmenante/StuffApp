#!/usr/bin/env python3
"""Upsert Recording.csv into recordings.

Behaviour:
- Match rows by CSV UUID (col 23) against recordings.id.
- For existing rows: overwrite a column only when the CSV value is
  non-blank (preserves any manual edits made in-app).
- For rows whose CSV UUID isn't in the DB: INSERT as a new record.
- Reports counts: updated, filled, inserted, skipped.

Safe to re-run. No DELETE.
"""
import csv
import io
import os
import sqlite3
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE, 'stuffapp.db')
CSV_PATH = os.path.join(BASE, 'Recording.csv')


def clean(s):
    return (s or '').replace('\x0b', '\n').strip() or None


def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    s = s.split(' ')[0]
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y', '%d/%m/%Y'):
        try:
            return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError:
            continue
    return None


def parse_num(s, cast=float):
    s = (s or '').strip().replace(',', '').replace('$', '')
    try:
        return cast(s)
    except (ValueError, TypeError):
        return None


def load_csv():
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        content = f.read().replace('\r', '\n')
    return [r for r in csv.reader(io.StringIO(content)) if any(c.strip() for c in r)]


# (db_column, csv_value_builder)
# Each builder converts a CSV row into the intended column value.
FIELD_MAP = [
    ('title',           lambda r: clean(r[10])),
    ('artist',          lambda r: clean(r[0])),
    ('type',            lambda r: clean(r[11])),
    ('genre',           lambda r: clean(r[2])),
    ('genre_2',         lambda r: clean(r[3])),
    ('year_recorded',   lambda r: clean(r[13])),
    ('speed',           lambda r: clean(r[9])),
    ('sound',           lambda r: clean(r[8])),
    ('like_field',      lambda r: clean(r[18])),
    ('number_position', lambda r: parse_num(r[21], int)),
    ('other',           lambda r: clean(r[5])),
    ('date',            lambda r: parse_date(r[1])),
    ('price',           lambda r: parse_num(r[6])),
    ('vendor',          lambda r: clean(r[12])),
    ('notes',           lambda r: clean(r[4])),
    ('owner',           lambda r: clean(r[22])),
    ('property',        lambda r: clean(r[7])),
]


def main():
    rows = load_csv()
    print(f'CSV rows: {len(rows)}')

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    updated = filled_cols = inserted = skipped = 0
    now = datetime.utcnow().isoformat()

    for row in rows:
        if len(row) < 24:
            skipped += 1
            continue
        uid = (row[23] or '').strip()
        if not uid:
            skipped += 1
            continue

        csv_vals = {col: fn(row) for col, fn in FIELD_MAP}

        existing = cur.execute(
            "SELECT * FROM recordings WHERE lower(id) = lower(?)", (uid,)
        ).fetchone()

        if existing:
            to_set = {}
            for col, new_val in csv_vals.items():
                if new_val in (None, ''):
                    continue
                old_val = existing[col]
                old_normed = '' if old_val is None else str(old_val).strip()
                new_normed = str(new_val).strip()
                if old_normed != new_normed:
                    to_set[col] = new_val
            if to_set:
                assigns = ', '.join(f'{c} = ?' for c in to_set) + ', updated_at = ?'
                cur.execute(
                    f'UPDATE recordings SET {assigns} WHERE lower(id) = lower(?)',
                    list(to_set.values()) + [now, uid],
                )
                updated += 1
                filled_cols += len(to_set)
        else:
            cols = ['id'] + list(csv_vals.keys()) + ['created_at', 'updated_at']
            placeholders = ','.join(['?'] * len(cols))
            cur.execute(
                f'INSERT INTO recordings ({",".join(cols)}) VALUES ({placeholders})',
                [uid] + list(csv_vals.values()) + [now, now],
            )
            inserted += 1

    conn.commit()
    total = cur.execute('SELECT COUNT(*) FROM recordings').fetchone()[0]
    conn.close()

    print(f'Updated:  {updated} (columns filled: {filled_cols})')
    print(f'Inserted: {inserted}')
    print(f'Skipped:  {skipped}')
    print(f'DB total: {total}')


if __name__ == '__main__':
    main()
