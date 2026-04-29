#!/usr/bin/env python3
"""Resync coins.region and coins.mint from Coin.csv (cols 35 and 21).

Earlier imports swapped these two columns for some rows. Safe to re-run.
Matches DB rows by coin_id when present, else by CSV UUID (col 29).
"""

import csv
import io
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), 'stuffapp.db')
CSV_PATH = os.path.join(os.path.dirname(__file__), 'Coin.csv')


def clean(s):
    return (s or '').replace('\x0b', '\n').strip() or None


with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
    content = f.read().replace('\r', '\n')
rows = [r for r in csv.reader(io.StringIO(content)) if any(c.strip() for c in r)]

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

updated = 0
by_coin_id = 0
by_uuid = 0
not_found = 0

for row in rows:
    if len(row) < 45:
        continue
    coin_id = clean(row[1])
    csv_uuid = clean(row[29])
    mint = clean(row[21])
    region = clean(row[35])

    if coin_id:
        r = cur.execute("UPDATE coins SET mint = ?, region = ? WHERE coin_id = ?",
                        (mint, region, coin_id))
        if r.rowcount:
            updated += r.rowcount
            by_coin_id += r.rowcount
            continue

    if csv_uuid:
        r = cur.execute("UPDATE coins SET mint = ?, region = ? WHERE lower(id) = lower(?)",
                        (mint, region, csv_uuid))
        if r.rowcount:
            updated += r.rowcount
            by_uuid += r.rowcount
            continue

    not_found += 1

conn.commit()
conn.close()

print(f'Updated: {updated}  (by coin_id: {by_coin_id}, by uuid: {by_uuid})')
print(f'CSV rows with no matching DB record: {not_found}')
