#!/usr/bin/env python3
"""Import rows from Coin.csv into coins table, skipping coin_ids that already exist.

Safe to re-run: existing records are never overwritten.
"""

import csv
import io
import os
import sqlite3
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'stuffapp.db')
CSV_PATH = os.path.join(os.path.dirname(__file__), 'Coin.csv')


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


def split_range(text):
    t = (text or '').strip()
    if ' - ' in t:
        a, b = t.split(' - ', 1)
        return a.strip(), b.strip()
    return t, ''


def load_rows():
    with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
        content = f.read().replace('\r', '\n')
    return [r for r in csv.reader(io.StringIO(content)) if any(c.strip() for c in r)]


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

existing_coin_ids = {row[0] for row in cur.execute("SELECT coin_id FROM coins WHERE coin_id IS NOT NULL AND coin_id != ''")}
existing_ids = {row[0].lower() for row in cur.execute("SELECT id FROM coins") if row[0]}

inserted = 0
skipped_existing = 0
skipped_bad = 0

for row in load_rows():
    if len(row) < 45:
        skipped_bad += 1
        continue
    coin_id = clean(row[1])
    csv_uuid = clean(row[29])
    # Dedupe: prefer coin_id, fall back to the CSV's UUID (col 29) for rows without coin_id (e.g. bullion)
    if coin_id:
        if coin_id in existing_coin_ids:
            skipped_existing += 1
            continue
        record_id = str(uuid.uuid4())
    else:
        if not csv_uuid:
            skipped_bad += 1
            continue
        if csv_uuid.lower() in existing_ids:
            skipped_existing += 1
            continue
        record_id = csv_uuid

    d1_text, _ = split_range(row[11])

    cur.execute('''
        INSERT INTO coins (
            id, coin_id, authority, print_field, notes,
            date_1, date_1_text, date_2, date_2_text,
            denomination, obv_rev, die_axis, grade, metal,
            mint, description, owner, price,
            property_name, purchase_date, coin_references,
            region, sheldon, size, status, strike, surface,
            vendor, weight,
            created_at, updated_at
        ) VALUES (
            ?,?,?,?,?,
            ?,?,?,?,
            ?,?,?,?,?,
            ?,?,?,?,
            ?,?,?,
            ?,?,?,?,?,?,
            ?,?,
            datetime('now'), datetime('now')
        )
    ''', (
        record_id,
        coin_id,
        clean(row[0]),
        clean(row[2]),
        clean(row[4]),
        parse_num(row[10], int),
        clean(d1_text) or None,
        parse_num(row[12], int),
        clean(row[13]),
        clean(row[14]),
        clean(row[15]),
        clean(row[17]),
        clean(row[18]),
        clean(row[20]),
        clean(row[21]),
        clean(row[24]),
        clean(row[27]),
        parse_num(row[28]),
        clean(row[31]),
        parse_date(row[32]),
        clean(row[34]),
        clean(row[35]),
        clean(row[36]),
        parse_num(row[38]),
        clean(row[39]),
        parse_num(row[40]),
        parse_num(row[41]),
        clean(row[43]),
        parse_num(row[44]),
    ))
    inserted += 1
    if coin_id:
        existing_coin_ids.add(coin_id)
    existing_ids.add(record_id.lower())

conn.commit()
conn.close()

print(f'Inserted: {inserted}')
print(f'Skipped (already in DB): {skipped_existing}')
print(f'Skipped (malformed row): {skipped_bad}')
