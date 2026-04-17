#!/usr/bin/env python3
"""Import remaining CSVs into the StuffApp SQLite database.

CSVs live next to this script. Each CSV has FileMaker-style columns in roughly
alphabetical order (no headers, CR line terminators). Per-file mappings are
derived from inspecting sample rows and matching values against the schema.
"""

import csv
import io
import os
import sqlite3
import uuid
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'stuffapp.db')
BASE = os.path.dirname(__file__)


def parse_date(s):
    s = (s or '').strip()
    if not s:
        return None
    # Many rows have "m/d/YYYY h:m:s AM/PM" — take the date part only
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


def clean(s):
    return (s or '').replace('\x0b', '\n').strip() or None


def load_csv(filename):
    path = os.path.join(BASE, filename)
    with open(path, 'r', encoding='utf-8-sig') as f:
        content = f.read().replace('\r', '\n')
    rows = [r for r in csv.reader(io.StringIO(content)) if any(c.strip() for c in r)]
    return rows


def new_id(val):
    v = (val or '').strip()
    if len(v) >= 8:
        return v
    return str(uuid.uuid4())


conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

totals = {}

# ---------------- CAMERAS ----------------
cur.execute('DELETE FROM cameras')
for row in load_csv('Camera.csv'):
    if len(row) < 21:
        continue
    cur.execute('''
        INSERT INTO cameras (id, make, model, digital_film, film_size, lens_mount,
            megapixels, sensor, serial_number, date, price, vendor, notes,
            owner, property, status, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
    ''', (
        new_id(row[15]), clean(row[7]), clean(row[9]), clean(row[4]),
        clean(row[5]), clean(row[6]), parse_num(row[8]), clean(row[17]),
        clean(row[18]), parse_date(row[3]), parse_num(row[14]), clean(row[20]),
        clean(row[12]), clean(row[13]), clean(row[16]), clean(row[19]),
    ))
totals['cameras'] = cur.rowcount if False else None
totals['cameras'] = conn.execute('SELECT COUNT(*) FROM cameras').fetchone()[0]

# ---------------- LENSES ----------------
# Col 9 mixes status/property. If value looks like a known status keep in status,
# else treat as property. Col 11 → status if non-empty (overrides).
STATUS_TOKENS = {'Own', 'Owned', 'Sold', 'Gifted', 'Lost', 'Consigned', 'Stolen', 'Damaged'}
cur.execute('DELETE FROM lenses')
for row in load_csv('Lens.csv'):
    if len(row) < 13:
        continue
    col9 = clean(row[9]) or ''
    col11 = clean(row[11]) or ''
    if col11:
        status, prop = col11, col9
    elif col9 in STATUS_TOKENS:
        status, prop = col9, None
    else:
        status, prop = None, col9
    length = parse_num(row[3])
    length_end = clean(row[7])
    notes_extra = None
    if length_end and length and str(int(length)) != length_end:
        notes_extra = f'Focal range: {int(length)}-{length_end}mm'
    cur.execute('''
        INSERT INTO lenses (id, make, model, mount, aperture, filter_size, length,
            serial_number, date, price, vendor, notes, property, status,
            created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
    ''', (
        str(uuid.uuid4()), clean(row[4]), clean(row[5]), clean(row[6]),
        parse_num(row[0]), parse_num(row[2]), length,
        clean(row[10]), parse_date(row[1]), parse_num(row[8]), clean(row[12]),
        notes_extra, prop or None, status or None,
    ))
totals['lenses'] = conn.execute('SELECT COUNT(*) FROM lenses').fetchone()[0]

# ---------------- PENS ----------------
cur.execute('DELETE FROM pens')
for row in load_csv('Pen.csv'):
    if len(row) < 12:
        continue
    cur.execute('''
        INSERT INTO pens (id, make, model, type, action, nib, cartridge, reservoir,
            date, price, vendor, notes, property, status,
            created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
    ''', (
        str(uuid.uuid4()), clean(row[2]), clean(row[3]), clean(row[10]),
        None, clean(row[4]), clean(row[0]), clean(row[8]),
        parse_date(row[1]), parse_num(row[6]), clean(row[11]), clean(row[5]),
        clean(row[7]), clean(row[9]),
    ))
totals['pens'] = conn.execute('SELECT COUNT(*) FROM pens').fetchone()[0]

# ---------------- RECORDINGS ----------------
cur.execute('DELETE FROM recordings')
for row in load_csv('Recording.csv'):
    if len(row) < 25:
        continue
    cur.execute('''
        INSERT INTO recordings (id, title, artist, type, genre, genre_2, year_recorded,
            speed, sound, like_field, number_position, other, date, vendor, notes,
            owner, property, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
    ''', (
        new_id(row[23]), clean(row[10]), clean(row[0]), clean(row[11]),
        clean(row[2]), clean(row[3]), clean(row[13]),
        clean(row[9]), clean(row[8]), clean(row[18]),
        parse_num(row[21], int), clean(row[5]), parse_date(row[1]),
        clean(row[12]), clean(row[6]), clean(row[22]), clean(row[7]),
    ))
totals['recordings'] = conn.execute('SELECT COUNT(*) FROM recordings').fetchone()[0]

# ---------------- RIFLES ----------------
cur.execute('DELETE FROM rifles')
for row in load_csv('Rifle.csv'):
    if len(row) < 17:
        continue
    cur.execute('''
        INSERT INTO rifles (id, make, model, caliber, serial_number, date, price,
            vendor, notes, owner, property, status,
            created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
    ''', (
        new_id(row[12]), clean(row[5]), clean(row[6]), clean(row[0]),
        clean(row[14]), parse_date(row[4]), parse_num(row[11]),
        clean(row[16]), clean(row[9]), clean(row[10]),
        clean(row[13]), clean(row[15]),
    ))
totals['rifles'] = conn.execute('SELECT COUNT(*) FROM rifles').fetchone()[0]

# ---------------- VEHICLES ----------------
cur.execute('DELETE FROM vehicles')
for row in load_csv('Vehicle.csv'):
    if len(row) < 7:
        continue
    cur.execute('''
        INSERT INTO vehicles (id, make, model, state, tags, vin, year,
            created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,datetime('now'),datetime('now'))
    ''', (
        str(uuid.uuid4()), clean(row[1]), clean(row[2]), clean(row[3]),
        clean(row[4]), clean(row[5]), parse_num(row[6], int),
    ))
totals['vehicles'] = conn.execute('SELECT COUNT(*) FROM vehicles').fetchone()[0]

# ---------------- PROPERTIES ----------------
cur.execute('DELETE FROM properties')
for row in load_csv('Property.csv'):
    if len(row) < 26:
        continue
    cur.execute('''
        INSERT INTO properties (id, name, short_name, type, address, year_built,
            ein, llc, wifi, alarm_company, alarm_account, alarm_code_1,
            alarm_password, alarm_phone, alarm_notes, date, price, notes, status,
            archive, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
    ''', (
        new_id(row[19]), clean(row[16]), clean(row[20]), clean(row[22]),
        clean(row[0]), parse_num(row[25], int),
        clean(row[12]), clean(row[13]), clean(row[1]),
        clean(row[3]), clean(row[2]), clean(row[2]),
        clean(row[5]), clean(row[6]), clean(row[4]),
        parse_date(row[11]), parse_num(row[18]), clean(row[17]), clean(row[21]),
        clean(row[23]),
    ))
totals['properties'] = conn.execute('SELECT COUNT(*) FROM properties').fetchone()[0]

# ---------------- PERSONS ----------------
cur.execute('DELETE FROM persons')
for row in load_csv('Person.csv'):
    if len(row) < 34:
        continue
    # Combine leftover document/banking text into notes
    extras = []
    for label, idx in (
        ('License', 18),
        ('Passport', 8),
        ('Health card', 10),
        ('Medicare', 13),
        ('Bank', 27),
        ('Wire', 28),
    ):
        v = clean(row[idx])
        if v:
            extras.append(f'{label}: {v}')
    notes = '\n\n'.join(extras) if extras else None

    cur.execute('''
        INSERT INTO persons (id, name, birth_date, blood_type, home_address,
            phone, ssn, primary_care_physician, prescriptions, health_notes,
            spouse_name_and_phone, notes, created_at, updated_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'),datetime('now'))
    ''', (
        new_id(row[23]), clean(row[17]), parse_date(row[0]), clean(row[1]),
        clean(row[5]), clean(row[20]), clean(row[26]),
        clean(row[22]), clean(row[21]), clean(row[4]),
        clean(row[24]), notes,
    ))
totals['persons'] = conn.execute('SELECT COUNT(*) FROM persons').fetchone()[0]

conn.commit()
conn.close()

for t, n in totals.items():
    print(f'{t:12s} {n}')
