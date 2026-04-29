#!/usr/bin/env python3
"""Import rows from Watch.csv into watches table, skipping watches already present.

Dedupe key: (reference, case_num, movement_num). Safe to re-run.
"""

import csv
import io
import os
import sqlite3
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'stuffapp.db')
CSV_PATH = os.path.join(os.path.dirname(__file__), 'Watch.csv')


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


def key_of(reference, case_num, movement_num):
    return ((reference or '').strip(), (case_num or '').strip(), (movement_num or '').strip())


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

existing = set()
for r in cur.execute("SELECT reference, case_num, movement_num FROM watches"):
    existing.add(key_of(r[0], r[1], r[2]))

inserted = 0
skipped_existing = 0
skipped_bad = 0

for row in load_rows():
    if len(row) < 38:
        skipped_bad += 1
        continue

    reference = clean(row[28])
    case_num  = clean(row[3])
    movement_num = clean(row[19])
    k = key_of(reference, case_num, movement_num)
    if k in existing:
        skipped_existing += 1
        continue
    if all(not x for x in k):
        skipped_bad += 1
        continue

    cur.execute('''
        INSERT INTO watches (
            id, brand, model, reference, metal, case_diameter,
            dial_color, case_num, movement_num, edition, year,
            calibre, movement_type, movement_origin,
            beat, reserve, complications, clasp_type,
            strap_material, strap_color,
            date, price, vendor, description,
            owner, property, status,
            created_at, updated_at
        ) VALUES (
            ?,?,?,?,?,?,
            ?,?,?,?,?,
            ?,?,?,
            ?,?,?,?,
            ?,?,
            ?,?,?,?,
            ?,?,?,
            datetime('now'), datetime('now')
        )
    ''', (
        str(uuid.uuid4()),
        clean(row[1]),          # brand
        clean(row[11]),         # model
        reference,
        clean(row[16]),         # metal
        parse_num(row[4]),      # case_diameter
        clean(row[12]),         # dial_color
        case_num,
        movement_num,
        clean(row[15]),         # edition
        parse_num(row[37], int),# year
        clean(row[2]),          # calibre
        clean(row[22]),         # movement_type
        clean(row[21]),         # movement_origin
        parse_num(row[0], int), # beat
        parse_num(row[13]),     # reserve
        clean(row[6]),          # complications
        clean(row[5]),          # clasp_type
        clean(row[35]),         # strap_material
        clean(row[34]),         # strap_color
        parse_date(row[10]),    # date
        parse_num(row[25]),     # price
        clean(row[36]),         # vendor
        clean(row[23]),         # description
        clean(row[24]),         # owner
        clean(row[27]),         # property
        clean(row[33]),         # status
    ))
    inserted += 1
    existing.add(k)

conn.commit()
conn.close()

print(f'Inserted: {inserted}')
print(f'Skipped (already in DB): {skipped_existing}')
print(f'Skipped (malformed/empty-key): {skipped_bad}')
