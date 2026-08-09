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
    other_catalog TEXT, description TEXT, denomination TEXT, date_1 INTEGER)""")

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
assert panel['title'] == 'Djibouti' and panel['era']['label'] == 'The Djibouti franc', panel
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
           'Philippines)', 'Victory Series No. 66', 'Commonwealth'),
    (1944, 'Commonwealth of the Philippines (Philippine Treasury)', '',
     'Commonwealth'),
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

# Colonial American issues file under the United States, ahead of the
# federal run, with state/obsolete issues still last — and Portuguese
# Guinea no longer wedges between the colonies.
db2 = sqlite3.connect(':memory:')
stuffapp._configure_db_connection(db2)
db2.execute("""CREATE TABLE banknotes (
    id INTEGER PRIMARY KEY, country TEXT, municipality TEXT, series TEXT,
    issuer TEXT, official TEXT, lettering TEXT, lettering_translation TEXT,
    other_catalog TEXT, description TEXT, denomination TEXT, date_1 INTEGER)""")
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
assert p and p['title'] == 'Colonial America' and p['era']['span'] == '1690–1774', p
p = stuffapp._series_panel_for_row(
    {'country': 'Rhode Island and Providence Plantations', 'series': '', 'date_1': 1780})
assert p and p['title'] == 'Colonial America' and p['era']['span'] == '1775–1783', p
print('COLONIAL ASSERTIONS PASSED')

# Portuguese Guinea maps to Guinea-Bissau with a panel for the 1971 notes.
assert stuffapp._nation_sort_name('Portuguese Guinea') == 'Guinea-Bissau'
p = stuffapp._series_panel_for_row(
    {'country': 'Portuguese Guinea', 'series': '', 'date_1': 1971})
assert p and p['title'] == 'Guinea-Bissau' and p['era']['label'] == 'Portuguese Guinea', p
for y in (1914, 1975, 2005):
    p = stuffapp._series_panel_for_row({'country': 'Portuguese Guinea', 'series': '', 'date_1': y})
    assert p and p['era'], (y, p)
print('GUINEA-BISSAU ASSERTIONS PASSED')

# Bermuda and British Guiana (Guyana) have panels; British Guiana files
# under G, not B.
assert stuffapp._nation_sort_name('Bermuda') == 'Bermuda'
assert stuffapp._nation_sort_name('British Guiana') == 'Guyana'
p = stuffapp._series_panel_for_row({'country': 'Bermuda', 'series': '', 'date_1': 1952})
assert p and p['title'] == 'Bermuda' and p['era']['label'] == 'The Bermuda pound', p
p = stuffapp._series_panel_for_row({'country': 'British Guiana', 'series': '', 'date_1': 1942})
assert p and p['title'] == 'Guyana' and 'West Indian dollar' in p['era']['label'], p

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
