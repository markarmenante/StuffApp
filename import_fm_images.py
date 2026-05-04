#!/usr/bin/env python3
"""
Import FileMaker-exported images into StuffApp.

Expects files in the source folder named like:
  Watch_<UUID>_ImageObv.jpg
  Coin_<UUID>_Image1.png
  Person_<UUID>_HeadShot.jpg
  ...

Maps them to the correct SQLite table/column and copies into uploads/.
"""

import os
import sys
import uuid
import shutil
import sqlite3
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'stuffapp.db')
UPLOAD_DIR = os.path.join(BASE_DIR, 'uploads')

# FileMaker export name -> (sqlite_table, sqlite_column)
#
# Receipt mappings deliberately removed for the categories whose
# receipt → documents migration completed (Watch, Coin, Pen, Art,
# Rifle). Routing a FileMaker `<table>_<uuid>_Receipt.<ext>` back
# into the legacy receipt column would re-populate the very field
# the migration NULLed and the next boot's
# _migrate_receipt_into_documents would faithfully re-create the
# phantom Receipt-titled docs entry. Files matching the dropped
# keys hit the "No mapping" skip branch in main(). Real receipts
# should be uploaded via the dynamic docs UI on the record page.
# Recordings keeps its Receipt mapping because the migration was
# never run for it (the FM-era receipt slot historically held
# cover-image data and migrating would corrupt the docs JSON).
# Mirrors FM_FIELD_MAP in app.py — kept in lockstep on every change.
FIELD_MAP = {
    # Watches
    ('Watch', 'ImageObv'):       ('watches', 'image_obv'),
    ('Watch', 'ImageRev'):       ('watches', 'image_rev'),
    ('Watch', 'Document'):       ('watches', 'document'),
    # Coins
    ('Coin', 'Image1'):          ('coins', 'image_1'),
    ('Coin', 'Image2'):          ('coins', 'image_2'),
    ('Coin', 'Document1'):       ('coins', 'document_1'),
    ('Coin', 'Document2'):       ('coins', 'document_2'),
    # Cameras
    ('Camera', 'Image'):         ('cameras', 'image'),
    # Lenses
    ('Lens', 'Image'):           ('lenses', 'image'),
    # Pens
    ('Pen', 'Image'):            ('pens', 'image'),
    # Art
    ('Art', 'Image'):            ('art', 'image'),
    # Vehicles
    ('Vehicle', 'Image'):        ('vehicles', 'image'),
    ('Vehicle', 'Registration'): ('vehicles', 'registration'),
    ('Vehicle', 'Insurance'):    ('vehicles', 'insurance'),
    ('Vehicle', 'Invoice'):      ('vehicles', 'invoice'),
    # Recordings
    ('Recording', 'Image'):      ('recordings', 'image'),
    ('Recording', 'Receipt'):    ('recordings', 'receipt'),
    # Rifles
    ('Rifle', 'Image'):          ('rifles', 'image'),
    # Credit Cards
    ('CreditCard', 'ImageFront'): ('credit_cards', 'image_front'),
    ('CreditCard', 'ImageBack'):  ('credit_cards', 'image_back'),
    # Properties
    ('Property', 'Image'):       ('properties', 'image'),
    # Persons
    ('Person', 'HeadShot'):       ('persons', 'head_shot'),
    ('Person', 'Image1'):         ('persons', 'image_1'),
    ('Person', 'Image7'):         ('persons', 'image_7'),
    ('Person', 'Image9'):         ('persons', 'image_9'),
    ('Person', 'LicenseObverse'): ('persons', 'license_obverse'),
    ('Person', 'LicenseReverse'): ('persons', 'license_reverse'),
    ('Person', 'HealthCardObv'):  ('persons', 'health_card_obv'),
    ('Person', 'HealthCardRev'):  ('persons', 'health_card_rev'),
    ('Person', 'Passport'):       ('persons', 'passport'),
    ('Person', 'GlobalEntry'):    ('persons', 'global_entry'),
    ('Person', 'EyePrescription'):('persons', 'eye_prescription'),
    ('Person', 'Medicare'):       ('persons', 'medicare'),
}


def parse_filename(filename):
    """
    Parse 'Watch_<UUID>_ImageObv.jpg' -> ('Watch', uuid, 'ImageObv', '.jpg')
    FileMaker UUIDs look like: 3F2504E0-4F89-11D3-9A0C-0305E82C3301
    """
    name, ext = os.path.splitext(filename)
    parts = name.split('_', 2)  # Table_UUID_FieldName
    if len(parts) < 3:
        return None

    table = parts[0]
    # The UUID may contain underscores if FM formatted differently,
    # but the field name is the last segment after the UUID
    remainder = parts[1] + '_' + parts[2]

    # Try to find the UUID boundary — FM UUIDs are 36 chars with hyphens
    # or 32 hex chars. Try splitting on last underscore working backwards.
    for i in range(len(remainder) - 1, -1, -1):
        if remainder[i] == '_':
            pk = remainder[:i]
            field = remainder[i + 1:]
            # Validate it looks like a UUID
            clean = pk.replace('-', '')
            if len(clean) >= 16 and all(c in '0123456789abcdefABCDEF' for c in clean):
                return (table, pk, field, ext)

    return None


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <fm_images_folder>")
        sys.exit(1)

    src_dir = sys.argv[1]
    if not os.path.isdir(src_dir):
        print(f"Error: {src_dir} is not a directory")
        sys.exit(1)

    os.makedirs(UPLOAD_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row

    files = [f for f in os.listdir(src_dir) if not f.startswith('.')]
    print(f"Found {len(files)} files in {src_dir}")

    imported = 0
    skipped = 0
    errors = []

    for fname in sorted(files):
        parsed = parse_filename(fname)
        if not parsed:
            errors.append(f"  Could not parse: {fname}")
            skipped += 1
            continue

        table_prefix, pk, field_name, ext = parsed
        key = (table_prefix, field_name)

        if key not in FIELD_MAP:
            errors.append(f"  No mapping for: {table_prefix}.{field_name} ({fname})")
            skipped += 1
            continue

        sql_table, sql_column = FIELD_MAP[key]

        # Verify the record exists
        row = db.execute(f"SELECT id FROM {sql_table} WHERE id = ?", (pk,)).fetchone()
        if not row:
            errors.append(f"  No record {pk} in {sql_table} ({fname})")
            skipped += 1
            continue

        # Copy file to uploads with UUID name
        new_name = f"{uuid.uuid4().hex}{ext.lower()}"
        src = os.path.join(src_dir, fname)
        dst = os.path.join(UPLOAD_DIR, new_name)
        shutil.copy2(src, dst)

        # Update database
        db.execute(f"UPDATE {sql_table} SET {sql_column} = ? WHERE id = ?", (new_name, pk))
        imported += 1

    db.commit()
    db.close()

    print(f"\nDone: {imported} images imported, {skipped} skipped")
    if errors:
        print(f"\nDetails ({len(errors)} issues):")
        for e in errors[:20]:
            print(e)
        if len(errors) > 20:
            print(f"  ... and {len(errors) - 20} more")


if __name__ == '__main__':
    main()
