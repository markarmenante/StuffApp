"""Sanity test: banknote list order groups territories under modern nations."""
import os, sys, sqlite3, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
# Point the app at a throwaway DB so import-time hooks can't touch anything real.
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-test-')

import app as stuffapp

# In-memory DB with just the columns the banknotes ORDER BY touches.
db = sqlite3.connect(':memory:')
stuffapp._configure_db_connection(db)
db.execute("""CREATE TABLE banknotes (
    id INTEGER PRIMARY KEY, country TEXT, municipality TEXT, series TEXT,
    issuer TEXT, official TEXT, lettering TEXT, lettering_translation TEXT,
    other_catalog TEXT, description TEXT, condition TEXT, denomination TEXT,
    date_1 INTEGER)""")

rows = [
    # (country, series, denomination, date_1) — mirrors the screenshot
    ('Belize', '', '50 Dollars', 2021),
    ('British East Africa', '', '1 Shilling', 1943),
    ('British East Africa', '', '20 Shillings', 1956),
    ('British Honduras', '', '2 Dollars', 1973),
    ('Cameroon', '', '500 Francs', 1983),
    ('Austria', '', '100 Kronen', 1922),
]
for i, (c, s, d, y) in enumerate(rows, 1):
    db.execute("INSERT INTO banknotes (id, country, series, denomination, date_1) "
               "VALUES (?, ?, ?, ?, ?)", (i, c, s, d, y))

got = [(r[0], r[1]) for r in db.execute(
    "SELECT country, date_1 FROM banknotes ORDER BY "
    + stuffapp.CATEGORY_ORDER_BY['banknotes'])]
for row in got:
    print(row)

expected = [
    ('Austria', 1922),
    ('British Honduras', 1973),   # Belize 1894-1973 era
    ('Belize', 2021),             # Belize 1973-2100 era
    ('Cameroon', 1983),
    ('British East Africa', 1943),  # Kenya
    ('British East Africa', 1956),  # Kenya
]
assert got == expected, f"\nexpected {expected}\ngot      {got}"

# Panel titles for the merged Belize run should both read 'Belize'.
assert stuffapp._nation_sort_name('British Honduras') == 'Belize'
assert stuffapp._nation_sort_name('British East Africa') == 'Kenya'
assert stuffapp._nation_sort_name('United States of America') == 'United States'
assert stuffapp._nation_sort_name('') == 'zzz'
assert stuffapp._nation_sort_name('Atlantis') == 'Atlantis'
print('ALL ASSERTIONS PASSED')

# French Somaliland maps to Djibouti with an era covering the 1952 note.
assert stuffapp._nation_sort_name('French Somaliland') == 'Djibouti'
assert stuffapp._country_key('Côte Française des Somalis') == 'djibouti'
assert stuffapp._country_key('French Territory of the Afars and Issas') == 'djibouti'
panel = stuffapp._series_panel_for_row(
    {'country': 'French Somaliland', 'series': '', 'date_1': 1952})
assert panel is not None, 'French Somaliland should get a history panel'
# The panel is headed by the name on the note; the modern nation follows as 'now …'.
assert panel['title'] == 'French Somaliland' and panel['now'] == 'Djibouti' \
    and panel['era']['label'] == 'The Djibouti franc', panel
# Boundary years and the other two bands still resolve.
for y, label in ((1910, 'French Somaliland'), (1949, 'French Somaliland'),
                 (1977, 'The Djibouti franc'), (2020, 'Independent Djibouti')):
    p = stuffapp._series_panel_for_row({'country': 'French Somaliland', 'series': '', 'date_1': y})
    assert p and p['era'], (y, p)
# Somalia proper still maps to Somalia, untouched.
assert stuffapp._nation_sort_name('Italian Somaliland') == 'Somalia'
assert stuffapp._nation_sort_name('British Somaliland') == 'Somalia'
print('DJIBOUTI ASSERTIONS PASSED')

# Philippines: occupation money and the legitimate government's notes
# share the same years (1942-45) — the issuer tells them apart. JIM
# notes go under Japanese occupation; VICTORY notes printed for the
# 1944 liberation are Commonwealth; the 1949 Central Bank overprint
# opens the Central Bank era.
for year, issuer, series, want in (
    (1943, 'The Japanese Government', '', 'Japanese occupation'),
    (1944, 'The Japanese Government', '', 'Japanese occupation'),
    (1944, 'Commonwealth of the Philippines (Treasury of the '
           'Philippines)', 'Victory Series No. 66', 'Liberation'),
    (1944, 'Commonwealth of the Philippines (Philippine Treasury)', '',
     'Liberation'),
    (1941, 'Treasury of the Philippines (Commonwealth of the '
           'Philippines)', '', 'Commonwealth'),
    (1949, 'Treasury of the Philippines (Central Bank of the '
           'Philippines overprint)', 'Victory Series No. 66',
     'Central Bank'),
    (1937, 'Philippine National Bank', 'Series of 1937', 'Commonwealth'),
    (1933, 'Bank of the Philippine Islands', 'Series of 1933',
     'US administration'),
    (1921, 'Philippine National Bank', 'Series of 1921',
     'US administration'),
    # No issuer on file: the gate stays open, year-only status quo.
    (1944, '', '', 'Japanese occupation'),
):
    p = stuffapp._series_panel_for_row(
        {'country': 'Philippines', 'issuer': issuer, 'series': series,
         'date_1': year})
    assert p and p['era']['label'] == want, (year, issuer, p and p['era'])
print('PHILIPPINES ERA ASSERTIONS PASSED')

# The LIST keeps each era block contiguous even where bands overlap in
# years: occupation scrip must not be split by the 1944 VICTORY notes.
db2 = sqlite3.connect(':memory:')
stuffapp._configure_db_connection(db2)
db2.execute("""CREATE TABLE banknotes (
    id INTEGER PRIMARY KEY, country TEXT, municipality TEXT, series TEXT,
    issuer TEXT, official TEXT, lettering TEXT, lettering_translation TEXT,
    other_catalog TEXT, description TEXT, condition TEXT, denomination TEXT,
    date_1 INTEGER)""")
ph_rows = [
    # (denomination, issuer, series, date_1) — the screenshot's mix
    ('5 Pesos', 'The Japanese Government', '', 1943),
    ('20 Pesos', 'Commonwealth of the Philippines (Treasury of the '
     'Philippines)', 'Victory Series No. 66', 1944),
    ('100 Pesos', 'Commonwealth of the Philippines (Philippine Treasury)',
     '', 1944),
    ('500 Pesos', 'The Japanese Government', '', 1944),
    ('1 Peso', 'Treasury of the Philippines (Central Bank of the '
     'Philippines overprint)', 'Victory Series No. 66', 1949),
    ('10 Pesos', 'Philippine National Bank', 'Series of 1937', 1937),
    ('1 Peso', 'Philippine National Bank', 'Series of 1921', 1921),
]
for i, (d, iss, s, y) in enumerate(ph_rows, 1):
    db2.execute(
        "INSERT INTO banknotes (id, country, issuer, series, denomination, "
        "date_1) VALUES (?, 'Philippines', ?, ?, ?, ?)", (i, iss, s, d, y))
got = [(r[0], r[1]) for r in db2.execute(
    "SELECT denomination, date_1 FROM banknotes ORDER BY "
    + stuffapp.CATEGORY_ORDER_BY['banknotes'])]
expected = [
    ('1 Peso', 1921),        # US administration (1903)
    ('10 Pesos', 1937),      # Commonwealth (1935)
    ('5 Pesos', 1943),       # Japanese occupation (1942), contiguous
    ('500 Pesos', 1944),     # Japanese occupation
    ('20 Pesos', 1944),      # Liberation (1944) — VICTORY, after occupation
    ('100 Pesos', 1944),     # Liberation — VICTORY
    ('1 Peso', 1949),        # Central Bank (1949)
]
assert got == expected, f"\nexpected {expected}\ngot      {got}"
print('PHILIPPINES ERA ORDER ASSERTIONS PASSED')

# Colonial American issues file under the United States, ahead of the
# federal run, with state/obsolete issues still last — and Portuguese
# Guinea no longer wedges between the colonies.
db2 = sqlite3.connect(':memory:')
stuffapp._configure_db_connection(db2)
db2.execute("""CREATE TABLE banknotes (
    id INTEGER PRIMARY KEY, country TEXT, municipality TEXT, series TEXT,
    issuer TEXT, official TEXT, lettering TEXT, lettering_translation TEXT,
    other_catalog TEXT, description TEXT, condition TEXT, denomination TEXT,
    date_1 INTEGER)""")
us_rows = [
    # (country, series, lettering, issuer, date_1)
    ('Rhode Island and Providence Plantations', '', '', 'State of Rhode Island', 1780),
    ('United States', 'Series of 1934', 'Federal Reserve Note', '', 1934),
    ('Portuguese Guinea', '', '', 'Banco Nacional Ultramarino', 1971),
    ('Pennsylvania Colony', '', '', 'General Assembly of Pennsylvania', 1773),
    ('United States', '', 'Revenue Bond Scrip', 'State of South Carolina', 1872),
    ('Venezuela', '', '', '', 1940),
]
for i, (c, s, l, iss, y) in enumerate(us_rows, 1):
    db2.execute("INSERT INTO banknotes (id, country, series, lettering, issuer, date_1) "
                "VALUES (?, ?, ?, ?, ?, ?)", (i, c, s, l, iss, y))
got2 = [(r[0], r[1]) for r in db2.execute(
    "SELECT country, date_1 FROM banknotes ORDER BY "
    + stuffapp.CATEGORY_ORDER_BY['banknotes'])]
for row in got2:
    print(row)
expected2 = [
    ('Portuguese Guinea', 1971),
    ('Pennsylvania Colony', 1773),                       # colonial block opens the US
    ('Rhode Island and Providence Plantations', 1780),
    ('United States', 1934),                             # federal run
    ('United States', 1872),                             # state/obsolete block last
    ('Venezuela', 1940),
]
assert got2 == expected2, f"\nexpected {expected2}\ngot      {got2}"
# The colonial panels still render with their own title and eras.
p = stuffapp._series_panel_for_row(
    {'country': 'Pennsylvania Colony', 'series': '', 'date_1': 1773})
assert p and p['title'] == 'Pennsylvania Colony' and p['now'] == 'United States' \
    and p['era']['span'] == '1690–1774', p
p = stuffapp._series_panel_for_row(
    {'country': 'Rhode Island and Providence Plantations', 'series': '', 'date_1': 1780})
assert p and p['title'] == 'Rhode Island and Providence Plantations' \
    and p['era']['span'] == '1775–1783', p
print('COLONIAL ASSERTIONS PASSED')

# Portuguese Guinea maps to Guinea-Bissau with a panel for the 1971 notes.
assert stuffapp._nation_sort_name('Portuguese Guinea') == 'Guinea-Bissau'
p = stuffapp._series_panel_for_row(
    {'country': 'Portuguese Guinea', 'series': '', 'date_1': 1971})
assert p and p['title'] == 'Portuguese Guinea' and p['now'] == 'Guinea-Bissau' \
    and p['era']['label'] == 'Portuguese Guinea', p
for y in (1914, 1975, 2005):
    p = stuffapp._series_panel_for_row({'country': 'Portuguese Guinea', 'series': '', 'date_1': y})
    assert p and p['era'], (y, p)
print('GUINEA-BISSAU ASSERTIONS PASSED')

# Bermuda and British Guiana (Guyana) have panels; British Guiana files
# under G, not B.
assert stuffapp._nation_sort_name('Bermuda') == 'Bermuda'
assert stuffapp._nation_sort_name('British Guiana') == 'Guyana'
p = stuffapp._series_panel_for_row({'country': 'Bermuda', 'series': '', 'date_1': 1952})
assert p and p['title'] == 'Bermuda' and not p['now'] and p['era']['label'] == 'The Bermuda pound', p
p = stuffapp._series_panel_for_row({'country': 'British Guiana', 'series': '', 'date_1': 1942})
assert p and p['title'] == 'British Guiana' and p['now'] == 'Guyana' \
    and 'West Indian dollar' in p['era']['label'], p

# A year outside every band clamps to the nearest band instead of
# dropping the panel (Malta's bands start at 1800; 1750 still panels).
p = stuffapp._series_panel_for_row({'country': 'Malta', 'series': '', 'date_1': 1750})
assert p and p['era'] and p['era']['span'].startswith('1800'), p
# Colonial America stays strict: no clamping past 1783.
assert stuffapp._series_panel_for_row(
    {'country': 'Pennsylvania Colony', 'series': '', 'date_1': 1872}) is None
print('BERMUDA/GUYANA/CLAMP ASSERTIONS PASSED')

# Fiji has a built-in history covering the 1965 government pound note.
assert stuffapp._nation_sort_name('Fiji') == 'Fiji'
p = stuffapp._series_panel_for_row({'country': 'Fiji', 'series': '', 'date_1': 1965})
assert p and p['title'] == 'Fiji' and p['era']['label'] == 'The Fiji pound', p
for y, label in ((1890, 'Kingdom and early colony'), (1969, 'The Fiji dollar'),
                 (2011, 'The Fiji dollar')):
    p = stuffapp._series_panel_for_row({'country': 'Fiji', 'series': '', 'date_1': y})
    assert p and p['era']['label'] == label, (y, p)
print('FIJI ASSERTIONS PASSED')

# Netherlands Indies files as its own nation — not folded into the
# Netherlands — and a parenthetical translation doesn't split the
# denomination into its own currency family (1/2 must sort before 10).
assert stuffapp._nation_sort_name('Netherlands Indies') == 'Netherlands Indies'
assert stuffapp._nation_sort_name('Dutch East Indies') == 'Netherlands Indies'
assert stuffapp._nation_sort_name('Netherlands') == 'Netherlands'
assert stuffapp._denom_value('1/2 Roepiah (Setengah Roepiah)') == 0.5
assert (stuffapp._denom_currency('1/2 Roepiah (Setengah Roepiah)')
        == stuffapp._denom_currency('10 Roepiah'))
p = stuffapp._series_panel_for_row(
    {'country': 'Netherlands Indies', 'series': '', 'date_1': 1944})
assert p and p['title'] == 'Netherlands Indies' \
    and p['era']['label'] == 'Japanese occupation', p
for y, label in ((1900, 'The gulden'), (1948, 'Succession to Indonesia')):
    p = stuffapp._series_panel_for_row(
        {'country': 'Netherlands Indies', 'series': '', 'date_1': y})
    assert p and p['era']['label'] == label, (y, p)

db3 = sqlite3.connect(':memory:')
stuffapp._configure_db_connection(db3)
db3.execute("""CREATE TABLE banknotes (
    id INTEGER PRIMARY KEY, country TEXT, municipality TEXT, series TEXT,
    issuer TEXT, official TEXT, lettering TEXT, lettering_translation TEXT,
    other_catalog TEXT, description TEXT, condition TEXT, denomination TEXT,
    date_1 INTEGER)""")
ni_rows = [
    ('Netherlands', '10 Gulden', 1943),
    ('Netherlands Indies', '10 Roepiah', 1944),
    ('Netherlands Indies', '1/2 Roepiah (Setengah Roepiah)', 1944),
    ('New Zealand', '1 Pound', 1940),
]
for i, (c, d, y) in enumerate(ni_rows, 1):
    db3.execute("INSERT INTO banknotes (id, country, denomination, date_1) "
                "VALUES (?, ?, ?, ?)", (i, c, d, y))
got3 = [(r[0], r[1]) for r in db3.execute(
    "SELECT country, denomination FROM banknotes ORDER BY "
    + stuffapp.CATEGORY_ORDER_BY['banknotes'])]
expected3 = [
    ('Netherlands', '10 Gulden'),
    ('Netherlands Indies', '1/2 Roepiah (Setengah Roepiah)'),
    ('Netherlands Indies', '10 Roepiah'),
    ('New Zealand', '1 Pound'),
]
assert got3 == expected3, f"\nexpected {expected3}\ngot      {got3}"
print('NETHERLANDS INDIES ASSERTIONS PASSED')

# WWII emergency issues — the HAWAII overprints (lettering) and the
# North Africa yellow seals (condition narrative) — classify as one
# class, share one panel, and file as one block at 1942, after the
# regular 1928/1935 runs and before the 1950s FRNs.
hawaii_frn = {
    'country': 'United States of America', 'series': '1934A',
    'issuer': 'Federal Reserve Bank of San Francisco',
    'lettering': 'FEDERAL RESERVE NOTE\nSERIES OF 1934 A\nHAWAII\n'
                 'WILL PAY TO THE BEARER ON DEMAND FIVE DOLLARS',
    'date_1': 1934}
hawaii_sc = {
    'country': 'United States of America', 'series': 'Series 1935A',
    'issuer': 'United States Treasury',
    'lettering': 'SILVER CERTIFICATE\nHAWAII\nSERIES 1935A\nONE DOLLAR',
    'date_1': 1935}
nafrica_sc = {
    'country': 'United States of America', 'series': '1934A',
    'issuer': 'United States Treasury',
    'lettering': 'SILVER CERTIFICATE\nSERIES OF 1934 A\nTEN DOLLARS',
    'condition': 'Issued for U.S. forces during the November 1942 '
                 'Operation Torch invasion of North Africa, with a '
                 'distinctive yellow Treasury seal.',
    'date_1': 1934}
plain_sc = {
    'country': 'United States of America', 'series': '1935A',
    'issuer': 'United States Treasury (Silver Certificate)',
    'lettering': 'SILVER CERTIFICATE\nSERIES 1935A\nONE DOLLAR',
    'date_1': 1935}
for row in (hawaii_frn, hawaii_sc, nafrica_sc):
    nc = stuffapp._us_note_class(row)
    assert nc and nc['name'] == 'WWII Emergency Issue', (row['series'], nc)
    p = stuffapp._series_panel_for_row(row)
    assert p and p['title'] == 'WWII Emergency Issues', p and p['title']
# A regular 1935A Silver Certificate stays a Silver Certificate, and a
# Honolulu National Bank Note is NOT an emergency issue: HAWAII without
# a 1934/1935 series token doesn't match.
nc = stuffapp._us_note_class(plain_sc)
assert nc and nc['name'] == 'Silver Certificate', nc
nc = stuffapp._us_note_class({
    'country': 'United States', 'series': '1929',
    'issuer': 'The Bishop First National Bank of Honolulu, Hawaii',
    'lettering': 'NATIONAL CURRENCY\nTEN DOLLARS'})
assert nc and nc['name'] == 'National Bank Note', nc

db4 = sqlite3.connect(':memory:')
stuffapp._configure_db_connection(db4)
db4.execute("""CREATE TABLE banknotes (
    id INTEGER PRIMARY KEY, country TEXT, municipality TEXT, series TEXT,
    issuer TEXT, official TEXT, lettering TEXT, lettering_translation TEXT,
    other_catalog TEXT, description TEXT, condition TEXT, denomination TEXT,
    date_1 INTEGER)""")
em_rows = [
    # (series, issuer, lettering, condition, denomination, date_1)
    ('1928B', 'United States Treasury',
     'SILVER CERTIFICATE\nONE DOLLAR', '', '$1', 1928),
    (hawaii_frn['series'], hawaii_frn['issuer'], hawaii_frn['lettering'],
     '', '$5', 1934),
    (nafrica_sc['series'], nafrica_sc['issuer'], nafrica_sc['lettering'],
     nafrica_sc['condition'], '$10', 1934),
    (plain_sc['series'], plain_sc['issuer'], plain_sc['lettering'],
     '', '$1', 1935),
    (hawaii_sc['series'], hawaii_sc['issuer'], hawaii_sc['lettering'],
     '', '$1', 1935),
    ('Series of 1950', 'Federal Reserve Bank of New York',
     'FEDERAL RESERVE NOTE', '', '$20', 1950),
]
for i, (s, iss, l, cond, d, y) in enumerate(em_rows, 1):
    db4.execute(
        "INSERT INTO banknotes (id, country, series, issuer, lettering, "
        "condition, denomination, date_1) VALUES "
        "(?, 'United States of America', ?, ?, ?, ?, ?, ?)",
        (i, s, iss, l, cond, d, y))
got4 = [(r[0], r[1]) for r in db4.execute(
    "SELECT denomination, date_1 FROM banknotes ORDER BY "
    + stuffapp.CATEGORY_ORDER_BY['banknotes'])]
expected4 = [
    ('$1', 1928),    # regular Silver Certificate run
    ('$1', 1935),    # regular 1935A Silver Certificate
    ('$1', 1935),    # emergency block opens at 1942: Hawaii set first
    ('$5', 1934),    # HAWAII $5 FRN
    ('$10', 1934),   # then North Africa (yellow seal, via condition)
    ('$20', 1950),   # regular run resumes
]
assert got4 == expected4, f"\nexpected {expected4}\ngot      {got4}"
print('WWII EMERGENCY ISSUE ASSERTIONS PASSED')

# Manchukuo is its own nation, apart from China — however a catalogue
# qualifies it — and China's Japanese-occupation issues (military yen,
# the puppet banks) file in their own band after the Republic's
# wartime run rather than interleaving with it by year.
for spelling in ('Manchukuo', 'Manchoukuo', 'China (Manchukuo)', 'China — Manchukuo',
                 'Empire of Manchukuo'):
    assert stuffapp._country_key(spelling) == 'manchukuo', spelling
assert stuffapp._country_key('China') == 'china'
assert stuffapp._nation_sort_name('Manchukuo') == 'Manchukuo'
assert stuffapp._nation_sort_name('China') == 'China'
assert stuffapp._canonical_banknote_country('China — Manchukuo') == 'Manchukuo'
assert stuffapp._canonical_banknote_country('Manchoukuo') == 'Manchukuo'
assert stuffapp._canonical_banknote_country('China') == 'China'
assert stuffapp.BANKNOTE_CAPITALS['manchukuo'][0].startswith('Hsinking')
assert 'manchukuo' in stuffapp.BANKNOTE_STATE_NAMES
p = stuffapp._series_panel_for_row({'country': 'Manchukuo', 'issuer': 'Central Bank of Manchou',
                                    'series': '', 'denomination': '10 Yuan', 'date_1': 1938})
assert p and p['title'] == 'Manchukuo' and p['era']['label'] == 'War finance', p
assert p['colonial'] and 'Puyi' in p['colonial'], p
for y, label in ((1932, 'A state proclaimed'), (1935, 'Empire and the yen bloc'),
                 (1944, 'War finance'), (1947, 'Collapse')):
    p = stuffapp._series_panel_for_row({'country': 'Manchukuo', 'issuer': 'Central Bank of Manchou',
                                        'series': '', 'denomination': '1 Yuan', 'date_1': y})
    assert p and p['era']['label'] == label, (y, p)
# China: the issuer gates the occupation band; the Republic's own notes
# of the same years stay in the fabi/gold-yuan band.
p = stuffapp._series_panel_for_row({'country': 'China', 'issuer': 'Imperial Japanese Government (military currency)',
                                    'series': 'Block 3', 'denomination': '100 Yen', 'date_1': 1945})
assert p['era']['label'] == 'Japanese occupation' and p['era']['gated'], p
p = stuffapp._series_panel_for_row({'country': 'China', 'issuer': 'Federal Reserve Bank of China',
                                    'series': '', 'denomination': '10 Yuan', 'date_1': 1938})
assert p['era']['label'] == 'Japanese occupation', p
p = stuffapp._series_panel_for_row({'country': 'China', 'issuer': 'Bank of China (中國銀行)',
                                    'series': '', 'denomination': '5 Yuan', 'date_1': 1937})
assert p['era']['label'] == 'War inflation and the gold yuan' and not p['era']['gated'], p
p = stuffapp._series_panel_for_row({'country': 'China', 'issuer': 'Central Bank of China',
                                    'series': '', 'denomination': '10 Gold Yuan', 'date_1': 1948})
assert p['era']['label'] == 'War inflation and the gold yuan', p

db3 = sqlite3.connect(':memory:')
stuffapp._configure_db_connection(db3)
db3.execute("""CREATE TABLE banknotes (
    id INTEGER PRIMARY KEY, country TEXT, municipality TEXT, series TEXT,
    issuer TEXT, official TEXT, lettering TEXT, lettering_translation TEXT,
    other_catalog TEXT, description TEXT, condition TEXT, denomination TEXT,
    date_1 INTEGER)""")
rows = [
    ('Manchukuo', 'Central Bank of Manchou', '', '10 Yuan', 1938),
    ('China', 'Imperial Japanese Government (military currency)', 'Block 3', '100 Yen', 1945),
    ('China', 'Bank of Communications', '', '100 Yuan', 1941),
    ('China', "People's Bank of China", '', '1 Yuan', 1953),
    ('Japan', 'Bank of Japan', '', '1 Yen', 1943),
    ('China', 'Central Bank of China', '', '10 Gold Yuan', 1948),
    ('China', 'Federal Reserve Bank of China', '', '10 Yuan', 1938),
    ('China', 'Bank of China (中國銀行)', '', '5 Yuan', 1937),
    ('China', 'Imperial Japanese Government (大日本帝國政府)', 'Block 1 - Title A', '100 Yen', 1945),
]
for i, (c, iss, s, d, y) in enumerate(rows, 1):
    db3.execute("INSERT INTO banknotes (id, country, issuer, series, denomination, date_1) "
                "VALUES (?, ?, ?, ?, ?, ?)", (i, c, iss, s, d, y))
got = [(r[0], r[1].split(' (')[0], r[2]) for r in db3.execute(
    "SELECT country, issuer, date_1 FROM banknotes ORDER BY "
    + stuffapp.CATEGORY_ORDER_BY['banknotes'])]
for row in got:
    print(row)
expected = [
    ('China', 'Bank of China', 1937),                    # Republic's wartime run…
    ('China', 'Bank of Communications', 1941),
    ('China', 'Central Bank of China', 1948),            # …through the gold yuan
    ('China', 'Federal Reserve Bank of China', 1938),    # then the occupation block
    ('China', 'Imperial Japanese Government', 1945),
    ('China', 'Imperial Japanese Government', 1945),
    ('China', "People's Bank of China", 1953),           # renminbi
    ('Japan', 'Bank of Japan', 1943),
    ('Manchukuo', 'Central Bank of Manchou', 1938),      # its own nation, under M
]
assert got == expected, f"\nexpected {expected}\ngot      {got}"
print('MANCHUKUO ASSERTIONS PASSED')

# The issuer names the state: a Central Bank of Manchou note filed
# under China (the catalogue convention the extractor follows) moves
# to Manchukuo on save, on a partial update that only stored the
# issuer, and on Market Scan candidates — never a Republic bank.
f = stuffapp.canonicalize_banknote_fields(
    {'country': 'China', 'issuer': 'Central Bank of Manchukuo (滿洲中央銀行)'})
assert f['country'] == 'Manchukuo', f
f = stuffapp.canonicalize_banknote_fields(
    {'country': 'China', 'issuer': 'Central Bank of Manchou'})
assert f['country'] == 'Manchukuo', f
f = stuffapp.canonicalize_banknote_fields({'issuer': 'Central Bank of Manchou'},
                                          existing={'country': 'China'})
assert f.get('country') == 'Manchukuo', f          # key added on a partial save
f = stuffapp.canonicalize_banknote_fields({'country': 'China'},
                                          existing={'country': 'China', 'issuer': 'Central Bank of Manchou'})
assert f['country'] == 'Manchukuo', f
f = stuffapp.canonicalize_banknote_fields({'country': 'China', 'issuer': 'Bank of China (中國銀行)'})
assert f['country'] == 'China', f
f = stuffapp.canonicalize_banknote_fields({'country': 'China', 'issuer': 'Bank of Manchuria (Three Eastern Provinces)'})
assert f['country'] == 'China', f                  # Republic's provincial bank stays
f = stuffapp.canonicalize_banknote_fields({'country': 'Japan', 'issuer': 'Bank of Japan'})
assert f['country'] == 'Japan', f
assert stuffapp._mentions_manchukuo('MANCHUKUO 1 Yuan 1932 P-J125a PMG 64') is True
assert stuffapp._mentions_manchukuo('China 5 Yuan 1937 P-80') is False
print('MANCHUKUO ISSUER-FOLD ASSERTIONS PASSED')

# Manchukuo paper is Japanese puppet-bank issue (Pick's J series): a
# note arriving as National or untyped files as occupation money; a
# type set by hand stays.
f = stuffapp.canonicalize_banknote_fields(
    {'country': 'China', 'issuer': 'Central Bank of Manchukuo (Manchou)', 'issue_type': 'National'})
assert f['country'] == 'Manchukuo' and f['issue_type'] == 'Military / Occupation', f
f = stuffapp.canonicalize_banknote_fields({'country': 'Manchukuo', 'issuer': 'Central Bank of Manchou'})
assert f['issue_type'] == 'Military / Occupation', f
f = stuffapp.canonicalize_banknote_fields({'issuer': 'Central Bank of Manchou'},
                                          existing={'country': 'China', 'issue_type': 'National'})
assert f.get('country') == 'Manchukuo' and f.get('issue_type') == 'Military / Occupation', f
f = stuffapp.canonicalize_banknote_fields(
    {'country': 'Manchukuo', 'issuer': 'Central Bank of Manchou', 'issue_type': 'Colonial'})
assert f['issue_type'] == 'Colonial', f
f = stuffapp.canonicalize_banknote_fields(
    {'country': 'China', 'issuer': 'Bank of China (中國銀行)', 'issue_type': 'National'})
assert f['issue_type'] == 'National', f
print('MANCHUKUO ISSUE-TYPE ASSERTIONS PASSED')

# Colonial period, Japanese-theatre territories: a pre-independence
# note that arrived as National (or untyped) files as Colonial; an
# occupation issuer and a hand-set type are left alone; a Macau note
# with no issuer is the Banco Nacional Ultramarino's.
C = stuffapp.canonicalize_banknote_fields
assert C({'country': 'Philippines', 'issuer': 'Commonwealth of the Philippines (Philippine Treasury)',
          'issue_type': 'National', 'date_1': 1936})['issue_type'] == 'Colonial'
assert C({'country': 'Philippines', 'issuer': 'Philippine National Bank', 'date_1': 1921})['issue_type'] == 'Colonial'
assert C({'country': 'Philippines', 'issuer': 'Treasury of the Philippines (Central Bank overprint)',
          'issue_type': 'National', 'date_1': 1949})['issue_type'] == 'National'
assert C({'country': 'Philippines', 'issuer': 'The Japanese Government', 'issue_type': 'National',
          'date_1': 1943})['issue_type'] == 'National'          # never Colonial for an occupier
assert C({'country': 'Philippines', 'issuer': 'The Japanese Government', 'issue_type': 'Military / Occupation',
          'date_1': 1943})['issue_type'] == 'Military / Occupation'
assert C({'country': 'Philippines', 'issuer': 'Bank of the Philippine Islands', 'issue_type': 'Specimen',
          'date_1': 1933})['issue_type'] == 'Specimen'
assert C({'country': 'Hong Kong', 'issuer': 'The Hongkong and Shanghai Banking Corporation',
          'issue_type': 'National', 'date_1': 1987})['issue_type'] == 'Colonial'
assert C({'country': 'Hong Kong', 'issuer': 'The Hongkong and Shanghai Banking Corporation',
          'issue_type': 'National', 'date_1': 2003})['issue_type'] == 'National'
f = C({'country': 'Macau', 'issuer': '', 'issue_type': '', 'date_1': 1968})
assert f['issue_type'] == 'Colonial' and f['issuer'] == 'Banco Nacional Ultramarino', f
assert C({'country': 'Malaysia', 'issuer': 'Bank Negara Malaysia', 'issue_type': 'National',
          'date_1': 2012})['issue_type'] == 'National'
assert C({'country': 'Ceylon', 'issuer': 'Central Bank of Ceylon', 'issue_type': 'National',
          'date_1': 1954})['issue_type'] == 'National'
# Partial update: only the year was saved; the stored type moves.
f = C({'date_1': 1941}, existing={'country': 'Philippines', 'issuer': 'Treasury of the Philippines',
                                  'issue_type': 'National', 'date_1': None})
assert f.get('issue_type') == 'Colonial', f
# Panel heads: years for a non-US panel, series for a US one.
rows_p = [{'id': 'x1', 'country': 'China', 'issuer': 'Imperial Japanese Government', 'series': 'Block 3',
           'denomination': '100 Yen', 'date_1': 1945},
          {'id': 'x2', 'country': 'China', 'issuer': 'Imperial Japanese Government', 'series': 'Block 1 - Title A',
           'denomination': '100 Yen', 'date_1': 1945}]
pl = stuffapp.series_panels(rows_p)
head = pl['x1']['panel']['series_list']
assert head == ['1945'], head                      # not 'Block 3 · Block 1 - Title A'
rows_us = [{'id': 'u1', 'country': 'United States of America', 'issuer': '', 'series': 'Series of 1935A',
            'denomination': '$1', 'date_1': 1935, 'official': '', 'lettering': '', 'lettering_translation': '',
            'other_catalog': '', 'description': 'Silver Certificate', 'condition': ''}]
pl = stuffapp.series_panels(rows_us)
assert pl['u1']['panel']['series_list'] == ['Series of 1935A'], pl['u1']['panel']['series_list']
print('COLONIAL-PERIOD ASSERTIONS PASSED')
