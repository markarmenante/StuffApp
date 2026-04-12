#!/usr/bin/env python3
"""Import Watches.csv into the StuffApp SQLite database."""

import csv, sqlite3, uuid, os
from datetime import datetime

# Column mapping (0-indexed):
# 0:  beat
# 1:  brand
# 2:  calibre
# 3:  case_num
# 4:  case_diameter
# 5:  clasp_type
# 6:  complications  (vertical-tab \x0b separated)
# 7:  date           (purchase date m/d/yyyy)
# 8:  model
# 9:  dial_color
# 10: movement_jewels
# 11: hertz          (calculated — skip)
# 12: lug_mm         (stored as e.g. "2020" = 20/20)
# 13: metal
# 14: movement_num
# 15: movement_origin (In-House / Ebauche / etc.)
# 16: movement_type  (Manual / Automatic)
# 17: notes
# 18: owner
# 19: price
# 20: property
# 21: reference
# 22: reserve        (power reserve hours)
# 23: primary_key    (skip)
# 24: service_date
# 25: status
# 26: strap_color
# 27: strap_material
# 28: vendor
# 29: year

DB_PATH  = os.path.join(os.path.dirname(__file__), 'stuffapp.db')
CSV_PATH = '/Users/markarmenante/Desktop/Watches.csv'

def parse_date(s):
    s = s.strip()
    if not s: return None
    for fmt in ('%m/%d/%Y', '%Y-%m-%d', '%m/%d/%y'):
        try: return datetime.strptime(s, fmt).strftime('%Y-%m-%d')
        except ValueError: pass
    return None

def parse_num(s, cast=float):
    s = s.strip().replace(',', '')
    try: return cast(s)
    except: return None

def clean(s):
    return s.strip().replace('\x0b', '\n').strip()

def parse_complications(s):
    """Convert vertical-tab-separated FileMaker list to comma-separated."""
    if not s: return ''
    parts = [p.strip() for p in s.replace('\x0b', ',').split(',') if p.strip()]
    return ','.join(parts)

conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()
cur.execute('DELETE FROM watches')

imported = skipped = 0

with open(CSV_PATH, newline='', encoding='utf-8-sig') as f:
    for row in csv.reader(f):
        if len(row) < 29:
            skipped += 1
            continue

        cur.execute('''
            INSERT INTO watches (
                id, beat, brand, calibre, case_num, case_diameter,
                clasp_type, complications, date, model, dial_color,
                movement_jewels, lug_mm, metal, movement_num,
                movement_origin, movement_type, notes, owner, price,
                property, reference, reserve, service_date, status,
                strap_color, strap_material, vendor, year,
                created_at, updated_at
            ) VALUES (
                ?,?,?,?,?,?,
                ?,?,?,?,?,
                ?,?,?,?,
                ?,?,?,?,?,
                ?,?,?,?,?,
                ?,?,?,?,
                datetime('now'), datetime('now')
            )
        ''', (
            str(uuid.uuid4()),
            parse_num(row[0], int),      # beat
            clean(row[1]),               # brand
            clean(row[2]),               # calibre
            clean(row[3]),               # case_num
            parse_num(row[4]),           # case_diameter
            clean(row[5]),               # clasp_type
            parse_complications(row[6]), # complications
            parse_date(row[7]),          # date
            clean(row[8]),               # model
            clean(row[9]),               # dial_color
            clean(row[10]),              # movement_jewels
            clean(row[12]),              # lug_mm
            clean(row[13]),              # metal
            clean(row[14]),              # movement_num
            clean(row[15]),              # movement_origin
            clean(row[16]),              # movement_type
            clean(row[17]),              # notes
            clean(row[18]),              # owner
            parse_num(row[19]),          # price
            clean(row[20]),              # property
            clean(row[21]),              # reference
            parse_num(row[22]),          # reserve
            parse_date(row[24]),         # service_date
            clean(row[25]),              # status
            clean(row[26]),              # strap_color
            clean(row[27]),              # strap_material
            clean(row[28]),              # vendor
            clean(row[29]) if len(row) > 29 else None,  # year
        ))
        imported += 1

conn.commit()
conn.close()
print(f'Done. Imported: {imported}, Skipped: {skipped}')
