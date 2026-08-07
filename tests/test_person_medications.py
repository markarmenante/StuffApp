"""Characterization tests pinning person_medications behavior.

These lock the current medication save/read/clear round-trip so the
person_medications helpers can later be consolidated onto the
spec-driven property_slot machinery without silently changing what gets
written to the (health) records. Run: .venv/bin/python this-file.
"""
import os, sys, sqlite3, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-meds-')

import app as stuffapp

SLOTS = stuffapp.PERSON_MEDICATION_SLOTS


def fresh_db():
    db = sqlite3.connect(':memory:')
    stuffapp._configure_db_connection(db)
    # persons carries the legacy med_* slot columns + updated_at/prescriptions.
    legacy = []
    for pfx in stuffapp.PERSON_MEDICATION_FIELD_COLUMNS:
        legacy += [f'{pfx}_{i} TEXT' for i in range(1, SLOTS + 1)]
    db.execute(
        "CREATE TABLE persons (id TEXT PRIMARY KEY, updated_at TEXT, "
        "prescriptions TEXT, " + ", ".join(legacy) + ")")
    db.execute(
        "CREATE TABLE person_medications ("
        "id TEXT PRIMARY KEY, person_id TEXT NOT NULL, position INTEGER NOT NULL, "
        "med_type TEXT, name TEXT, active_ingredients TEXT, dose TEXT, "
        "directions TEXT, note TEXT, created_at TEXT, updated_at TEXT, "
        "UNIQUE(person_id, position))")
    db.execute("INSERT INTO persons (id) VALUES ('p1')")
    db.commit()
    return db


# 1. Set a field → a position-1 row with that value, canonical column names.
db = fresh_db()
assert stuffapp._update_person_medication_field(db, 'p1', 'med_name_1', 'Aspirin')
pos = stuffapp._person_medications_by_position(db, 'p1')
assert set(pos) == {1} and pos[1]['name'] == 'Aspirin', pos

# 2. Add more fields to the same slot → upsert, one row, all values present.
stuffapp._update_person_medication_field(db, 'p1', 'med_dose_1', '100mg')
stuffapp._update_person_medication_field(db, 'p1', 'med_type_1', 'NSAID')
pos = stuffapp._person_medications_by_position(db, 'p1')
assert len(pos) == 1, pos
assert (pos[1]['name'], pos[1]['dose'], pos[1]['med_type']) == ('Aspirin', '100mg', 'NSAID'), pos[1]

# 3. Legacy columns on persons are synced back.
r = db.execute("SELECT med_name_1, med_dose_1, med_type_1 FROM persons WHERE id='p1'").fetchone()
assert (r['med_name_1'], r['med_dose_1'], r['med_type_1']) == ('Aspirin', '100mg', 'NSAID'), tuple(r)

# 4. Edit a field in place.
stuffapp._update_person_medication_field(db, 'p1', 'med_name_1', 'Ibuprofen')
pos = stuffapp._person_medications_by_position(db, 'p1')
assert pos[1]['name'] == 'Ibuprofen', pos[1]

# 5. Clearing every field removes the slot row entirely.
for f in ('med_name_1', 'med_dose_1', 'med_type_1'):
    stuffapp._update_person_medication_field(db, 'p1', f, '')
assert stuffapp._person_medications_by_position(db, 'p1') == {}, 'row should be gone'

# 6. _replace_person_medications writes rows in order, skips empty ones.
db = fresh_db()
stuffapp._replace_person_medications(db, 'p1', [
    {'position': 2, 'name': 'Med B', 'dose': '2'},
    {'position': 1, 'name': 'Med A', 'dose': '1'},
    {'position': 3, 'name': '', 'dose': ''},   # empty → skipped
])
pos = stuffapp._person_medications_by_position(db, 'p1')
assert set(pos) == {1, 2}, pos
assert pos[1]['name'] == 'Med A' and pos[2]['name'] == 'Med B', pos

# 7. Invalid / out-of-range field names are rejected, no write.
db = fresh_db()
assert stuffapp._update_person_medication_field(db, 'p1', 'not_a_field', 'x') is False
assert stuffapp._update_person_medication_field(
    db, 'p1', f'med_name_{SLOTS + 1}', 'x') is False
assert stuffapp._person_medications_by_position(db, 'p1') == {}

print('PERSON_MEDICATIONS CHARACTERIZATION OK')
