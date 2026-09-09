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


# Paper-quality designations: PMG's EPQ and PCGS's PPQ both ride with the
# grade, from dealer text and from the scan (vision) result alike.
_ppq_note = {'description': 'Iran 100 Rials 1971 P-86b PCGS Currency 64 PPQ Very Choice New'}
_ppq = stuffapp._banknote_description_fields(_ppq_note)
assert _ppq.get('grade_modifier') == 'PPQ', _ppq
assert _ppq.get('grading_authority') == 'PCGS Currency', _ppq
assert _ppq.get('grade_numeric') == 64, _ppq
_epq = stuffapp._banknote_description_fields({'description': 'PMG 66 EPQ ★ Gem Uncirculated'})
assert _epq.get('grade_modifier') == 'EPQ★', _epq
_plain = stuffapp._banknote_description_fields({'description': 'PMG 58 Choice About Unc'})
assert _plain.get('grade_modifier') is None, _plain
for raw, want in (('PPQ', 'PPQ'), ('ppq star', 'PPQ★'), ('64 PPQ★', 'PPQ★'),
                  ('EPQ', 'EPQ'), ('EPQ★', 'EPQ★'), ('★', '★'), ('plus', '+'), ('', None)):
    got = stuffapp._coerce_banknote_spec('grade_modifier', raw)
    assert got == want, (raw, got, want)
print('banknote EPQ/PPQ OK')


# Every paper-money grading service: authority spelling, numeric grade,
# paper-quality designation, problem-note wording, and the "New" scale.
_svc = stuffapp._banknote_description_fields
cases = [
    ('PMG 66 EPQ Gem Uncirculated',                 'PMG',           66, 'EPQ',  None,       'Gem UNC'),
    ('Paper Money Guaranty 30 NET pinholes',        'PMG',           30, None,   'Net',      None),
    ('PCGS Banknote 58 PPQ Choice About Unc',       'PCGS Banknote', 58, 'PPQ',  None,       'cAU'),
    ('PCGS Currency Apparent Very Fine 30, tear',   'PCGS Currency', 30, None,   'Apparent', 'VF'),
    ('PCGS Currency Very Choice New 64 PPQ',        'PCGS Currency', 64, 'PPQ',  None,       'Choice UNC'),
    ('Legacy Currency Grading 67 PPQ Superb Gem New', 'Legacy',      67, 'PPQ',  None,       'Superb Gem UNC'),
    ('CGA Gem Uncirculated 66',                     'CGA',           66, None,   None,       'Gem UNC'),
    ('P-86b PMG Gem Unc 65 Exceptional Paper Quality', 'PMG',        65, 'EPQ',  None,       'Gem UNC'),
    ('PCGS Banknote Details 20 Very Good, ink',     'PCGS Banknote', 20, None,   'Details',  'VG'),
]
for text, auth, num, mod, cond, grade in cases:
    got = _svc({'description': text})
    assert got.get('grading_authority') == auth, (text, got)
    assert got.get('grade_numeric') == num, (text, got)
    assert got.get('grade_modifier') == mod, (text, got)
    if cond:
        assert str(got.get('grade_condition', '')).startswith(cond), (text, got)
    else:
        assert not got.get('grade_condition'), (text, got)
    if grade:
        assert got.get('grade') == grade, (text, got)
# The Pick number never becomes the grade: "P-64 PMG" is Pick 64.
got = _svc({'description': 'Iran P-64 PMG Choice Unc 63 EPQ'})
assert got.get('grade_numeric') == 63 and got.get('pick_number') == 'P-64', got
for raw, want in (('pcgs currency', 'PCGS Currency'), ('PCGS Bank Note', 'PCGS Banknote'),
                  ('LCG', 'Legacy'), ('Legacy Currency Grading', 'Legacy'),
                  ('paper money guaranty', 'PMG'), ('pcgs', 'PCGS'), ('ngc', 'NGC'), ('', None)):
    got = stuffapp.normalize_banknote_grading_authority(raw)
    assert got == want, (raw, got, want)
assert stuffapp._coerce_banknote_spec('grading_authority', 'PCGS Currency') == 'PCGS Currency'
assert stuffapp._coerce_banknote_spec('grade_modifier', 'Premium Paper Quality') == 'PPQ'
assert stuffapp.banknote_grader_profile('pmg')['paper_quality'] == 'EPQ'
assert stuffapp.banknote_grader_profile('Legacy')['paper_quality'] == 'PPQ'
for phrase, want in (('Very Choice New 64', 'Choice UNC'), ('Superb Gem New 67', 'Superb Gem UNC'),
                     ('About New 55', 'aAU'), ('Choice About New 58', 'cAU'), ('New 62', 'UNC'),
                     ('Gem New', 'Gem UNC')):
    got = stuffapp.banknote_grade_value_list_match(phrase)
    assert got == want, (phrase, got, want)
print('banknote grading services OK')
