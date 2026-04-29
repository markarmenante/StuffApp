#!/usr/bin/env python3
"""Import Art.csv into the StuffApp SQLite database."""

import csv
import io
import sqlite3
import uuid
import os
from datetime import datetime

# Column mapping (0-indexed, no header row, CR line terminators):
# 0:  artist
# 1:  date (purchase date, m/d/yyyy)
# 2:  dimensions
# 3:  location (room / spot within property)
# 4:  medium
# 5:  notes
# 6:  owner
# 7:  price
# 8:  property
# 9:  title
# 10: vendor
# 11: year
# 12: status

DB_PATH = os.path.join(os.path.dirname(__file__), 'stuffapp.db')
CSV_PATH = os.path.join(os.path.dirname(__file__), 'Art.csv')


def parse_date(s):
    s = s.strip()
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
    return (s or '').replace('\x0b', '\n').strip()


with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
    content = f.read().replace('\r', '\n')

reader = csv.reader(io.StringIO(content))
rows = [r for r in reader if any(c.strip() for c in r)]

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()
cur.execute('DELETE FROM art')

imported = 0
skipped = 0

for row in rows:
    if len(row) < 13:
        skipped += 1
        continue

    cur.execute('''
        INSERT INTO art (
            id, artist, date, dimensions, location, medium, notes,
            owner, price, property, title, vendor, year, status,
            created_at, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?,
            datetime('now'), datetime('now')
        )
    ''', (
        str(uuid.uuid4()),
        clean(row[0]),
        parse_date(row[1]),
        clean(row[2]),
        clean(row[3]),
        clean(row[4]),
        clean(row[5]),
        clean(row[6]),
        parse_num(row[7]),
        clean(row[8]),
        clean(row[9]),
        clean(row[10]),
        parse_num(row[11], int),
        clean(row[12]),
    ))
    imported += 1

conn.commit()
conn.close()

print(f'Done. Imported: {imported}, Skipped: {skipped}')
