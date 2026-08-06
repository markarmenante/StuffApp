"""Unit tests for consolidated helpers — pin behavior equivalence."""
import os, sys, sqlite3, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-helpers-')

import app as stuffapp


def _coins_db(ids):
    db = sqlite3.connect(':memory:')
    stuffapp._configure_db_connection(db)
    db.execute("CREATE TABLE coins (id INTEGER PRIMARY KEY, cat_id TEXT)")
    for i, cid in enumerate(ids, 1):
        db.execute("INSERT INTO coins (id, cat_id) VALUES (?, ?)", (i, cid))
    return db


# next_cat_id is the coins-with-'C' case of next_serial_cat_id.
for ids in ([], ['C001'], ['C001', 'C002', 'C010'], ['C007', 'X1', None]):
    db = _coins_db(ids)
    a = stuffapp.next_cat_id(db)
    b = stuffapp.next_serial_cat_id(db, 'coins', 'C')
    assert a == b, (ids, a, b)
    # Legacy dead args must not change the result.
    assert stuffapp.next_cat_id(db, 'carp', 1990) == b, (ids, 'legacy-args')
print('next_cat_id EQUIVALENCE OK')


# _table_cols returns the column-name set for a table.
db = sqlite3.connect(':memory:')
stuffapp._configure_db_connection(db)
db.execute("CREATE TABLE t (a INTEGER, b TEXT, c REAL)")
assert stuffapp._table_cols(db, 't') == {'a', 'b', 'c'}
assert stuffapp._table_cols(db, 'nope') == set()
print('_table_cols OK')

# _restore_docs_from_slots rebuilds JSON only for empty rows, from slot cols.
db = sqlite3.connect(':memory:')
stuffapp._configure_db_connection(db)
db.execute("CREATE TABLE persons (id INTEGER PRIMARY KEY, id_documents TEXT, "
           "id_doc_3 TEXT, id_doc_3_title TEXT, id_doc_4 TEXT, id_doc_4_title TEXT, "
           "updated_at TEXT)")
# row 1: empty JSON, two slot docs (one titled, one default-titled)
db.execute("INSERT INTO persons VALUES (1, '', 'a.pdf', 'Passport', 'b.pdf', '', NULL)")
# row 2: JSON already populated → must be skipped
db.execute("INSERT INTO persons VALUES (2, '[{\"title\":\"x\",\"filename\":\"z.pdf\"}]', "
           "'c.pdf', 'Card', NULL, NULL, NULL)")
# row 3: no slot files → nothing to restore
db.execute("INSERT INTO persons VALUES (3, '', NULL, NULL, NULL, NULL, NULL)")
db.commit()
cols = stuffapp._table_cols(db, 'persons')
rows = db.execute("SELECT * FROM persons").fetchall()
sources = [(f'id_doc_{i}', f'id_doc_{i}_title', f'ID Doc {i}') for i in range(3, 5)]

# Stub storage: capture the (record_id, docs) the helper would persist,
# so we test its selection/build logic independent of record_documents.
captured = []
_orig = stuffapp._docs_update
stuffapp._docs_update = lambda db, table, rid, docs, col, now: captured.append((rid, docs))
try:
    n = stuffapp._restore_docs_from_slots(
        db, 'persons', cols, rows, 'id_documents', sources)
    # Missing JSON column → 0, no crash, no writes.
    n_missing = stuffapp._restore_docs_from_slots(
        db, 'persons', cols, rows, 'nope', sources)
finally:
    stuffapp._docs_update = _orig

assert n == 1, n                        # only row 1 restored
assert n_missing == 0, n_missing
assert len(captured) == 1 and captured[0][0] == 1, captured
assert captured[0][1] == [{'title': 'Passport', 'filename': 'a.pdf'},
                          {'title': 'ID Doc 4', 'filename': 'b.pdf'}], captured
print('_restore_docs_from_slots OK')

print('ALL HELPER TESTS PASSED')
