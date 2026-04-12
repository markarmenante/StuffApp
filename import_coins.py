#!/usr/bin/env python3
"""Import Coins.csv into the StuffApp SQLite database."""

import csv
import sqlite3
import uuid
import os
from datetime import datetime

# Column mapping (0-indexed):
# 0: mint
# 1: region
# 2: authority
# 3: date_1 (integer, negative = BC)
# 4: coin_id (e.g. "C 1")
# 5: print_field (e.g. "Single")
# 6: coin_age (calculated — skip)
# 7: notes (condition/grade notes)
# 8: date range text (e.g. "480 BC - 440 BC")
# 9: date_2 (integer, negative = BC)
# 10: denomination
# 11: obv_rev (obverse/reverse description, e.g. "Sea turtle, head in profile")
# 12: die_axis
# 13: grade
# 14: metal
# 15: description (full catalog description)
# 16: price
# 17: property_name
# 18: purchase_date (m/d/yyyy)
# 19: coin_references (pedigree/references)
# 20: sheldon
# 21: size (mm)
# 22: status
# 23: strike
# 24: surface
# 25: vendor
# 26: weight (g)

DB_PATH = os.path.join(os.path.dirname(__file__), 'stuffapp.db')
CSV_PATH = '/Users/markarmenante/Desktop/Coins.csv'

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
    s = s.strip().replace(',', '')
    try:
        return cast(s)
    except (ValueError, TypeError):
        return None

def split_date_text(text):
    """Split '480 BC - 440 BC' → ('480 BC', '440 BC')"""
    text = text.strip()
    if ' - ' in text:
        parts = text.split(' - ', 1)
        return parts[0].strip(), parts[1].strip()
    return text, ''

def clean(s):
    """Strip whitespace and vertical-tab characters FileMaker sometimes exports."""
    return s.strip().replace('\x0b', '\n').strip()

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

# Clear existing coin data
cur.execute('DELETE FROM coins')

imported = 0
skipped = 0

with open(CSV_PATH, newline='', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    for row in reader:
        if len(row) < 27:
            skipped += 1
            continue

        date_text_1, date_text_2 = split_date_text(clean(row[8]))

        cur.execute('''
            INSERT INTO coins (
                id, coin_id, mint, region, authority,
                date_1, date_1_text, date_2, date_2_text,
                denomination, obv_rev, die_axis, grade, metal,
                description, price, property_name, purchase_date,
                coin_references, sheldon, size, status,
                strike, surface, vendor, weight,
                notes, print_field,
                created_at, updated_at
            ) VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?,
                datetime('now'), datetime('now')
            )
        ''', (
            str(uuid.uuid4()),
            clean(row[4]),                      # coin_id
            clean(row[0]),                      # mint
            clean(row[1]),                      # region
            clean(row[2]),                      # authority
            parse_num(row[3], int),             # date_1
            date_text_1,                        # date_1_text
            parse_num(row[9], int),             # date_2
            date_text_2,                        # date_2_text
            clean(row[10]),                     # denomination
            clean(row[11]),                     # obv_rev
            clean(row[12]),                     # die_axis
            clean(row[13]),                     # grade
            clean(row[14]),                     # metal
            clean(row[15]),                     # description
            parse_num(row[16]),                 # price
            clean(row[17]),                     # property_name
            parse_date(row[18]),                # purchase_date
            clean(row[19]),                     # coin_references
            clean(row[20]),                     # sheldon
            parse_num(row[21]),                 # size
            clean(row[22]),                     # status
            parse_num(row[23]),                 # strike
            parse_num(row[24]),                 # surface
            clean(row[25]),                     # vendor
            parse_num(row[26]),                 # weight
            clean(row[7]),                      # notes
            clean(row[5]),                      # print_field
        ))
        imported += 1

conn.commit()
conn.close()

print(f'Done. Imported: {imported}, Skipped: {skipped}')
