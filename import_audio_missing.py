#!/usr/bin/env python3
"""Import rows from Audio.csv into the audio table, skipping rows already present.

Dedupe key: CSV UUID in column 9. Safe to re-run.
"""

import csv
import io
import os
import sqlite3
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'stuffapp.db')
CSV_PATH = os.path.join(os.path.dirname(__file__), 'Audio.csv')


def parse_date(s):
    s = (s or '').strip().split(' ')[0]
    if not s:
        return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y'):
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


def clean(s):
    return (s or '').replace('\x0b', '\n').strip() or None


def load_rows():
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        content = f.read().replace('\r', '\n')
    return [r for r in csv.reader(io.StringIO(content)) if any(c.strip() for c in r)]


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

existing_ids = {(row[0] or '').lower() for row in cur.execute("SELECT id FROM audio")}

inserted = 0
skipped_existing = 0
skipped_bad = 0
now = datetime.utcnow().isoformat()

for row in load_rows():
    if len(row) < 14:
        skipped_bad += 1
        continue
    csv_uuid = clean(row[9])
    if not csv_uuid:
        skipped_bad += 1
        continue
    if csv_uuid.lower() in existing_ids:
        skipped_existing += 1
        continue

    cur.execute('''
        INSERT INTO audio (
            id, make, model, type, date, price, vendor, notes, property,
            created_at, updated_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
    ''', (
        csv_uuid,
        clean(row[0]),
        clean(row[4]),
        clean(row[12]),
        parse_date(row[3]),
        parse_num(row[8]),
        clean(row[13]),
        clean(row[7]),
        clean(row[10]),
        now, now,
    ))
    inserted += 1
    existing_ids.add(csv_uuid.lower())

conn.commit()
conn.close()

print(f'Inserted: {inserted}')
print(f'Skipped (already in DB): {skipped_existing}')
print(f'Skipped (malformed): {skipped_bad}')
