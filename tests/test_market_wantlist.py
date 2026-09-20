"""Colonial want-list for the banknote Market Scan: the issuers the
collection lacks, retired automatically once a note from that issuer
(in its colonial period) is Own or Ordered, and turned into up to three
TOP-PRIORITY scan themes grouped by empire.

Run: .venv/bin/python tests/test_market_wantlist.py
"""
import os, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-wl-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuffapp

WL = stuffapp.BANKNOTE_COLONIAL_WANTLIST
assert len(WL) == 35, len(WL)
names = [e[0] for e in WL]
assert len(set(names)) == 35, 'duplicate entries'
assert {e[1] for e in WL} == {'british', 'french', 'other'}
print('TABLE OK')

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    # Empty collection: everything open, three themes.
    open_entries = stuffapp._banknote_wantlist_open(db)
    assert len(open_entries) == 35
    themes = stuffapp._banknote_wantlist_themes(db)
    assert [k for k, _ in themes] == ['wantlist-british', 'wantlist-french', 'wantlist-other'], [k for k, _ in themes]
    assert 'Palestine Currency Board' in themes[0][1] and 'TOP PRIORITY' in themes[0][1]
    assert 'Banco Nacional Ultramarino, Goa' in themes[1][1]
    assert 'Bank of Taiwan' in themes[2][1]

    # Held detection, with and without the period gate.
    rows = [
        ('Palestine', 1939, 'Own'),                 # plain match -> retired
        ('Cuba', 1958, 'Own'),                      # republic note: colonial Cuba stays open
        ('Sao Tome and Principe', 1993, 'Own'),     # post-independence: stays open
        ('Netherlands Antilles', 1962, 'Ordered'),  # Curaçao entry retired by an Ordered note
        ('Taiwan', 1933, 'Own'),                    # colonial-period Taiwan -> retired
        ('Zanzibar', 1920, 'Sold'),                 # not active -> still open
        ('Philippines', 1944, 'Own'),               # US period: Spanish-colonial entry stays open
        ('New Jersey', 1776, 'Own'),                # colonial America, not the Channel Island
    ]
    for i, (c, y, st) in enumerate(rows):
        db.execute("INSERT INTO banknotes (id, country, date_1, status) VALUES (?, ?, ?, ?)", [f'w{i}', c, y, st])
    db.commit()
    open_names = [e[0] for e in stuffapp._banknote_wantlist_open(db)]
    assert 'Palestine' not in open_names
    assert 'Curaçao' not in open_names
    assert 'Taiwan (Japanese)' not in open_names
    assert 'Cuba (Spanish colonial)' in open_names
    assert 'São Tomé e Príncipe (colonial)' in open_names
    assert 'Zanzibar' in open_names
    assert 'Philippines (Spanish colonial)' in open_names
    assert 'Jersey' in open_names, 'New Jersey must not retire Jersey'
    assert len(open_names) == 32, len(open_names)
    db.execute("INSERT INTO banknotes (id, country, date_1, status) VALUES ('w8', 'Jersey', 1976, 'Own')")
    db.commit()
    assert 'Jersey' not in [e[0] for e in stuffapp._banknote_wantlist_open(db)]
    # A colonial-period Cuban note retires the entry.
    db.execute("INSERT INTO banknotes (id, country, date_1, status) VALUES ('w9', 'Cuba', 1896, 'Own')")
    db.commit()
    assert 'Cuba (Spanish colonial)' not in [e[0] for e in stuffapp._banknote_wantlist_open(db)]
    print('HELD DETECTION OK')

    # A group with nothing open yields no theme.
    for e in WL:
        if e[1] == 'british':
            db.execute("INSERT INTO banknotes (id, country, date_1, status) VALUES (?, ?, ?, 'Own')",
                       [f'b-{e[0]}', e[0].split(' (')[0], 1930])
    db.commit()
    themes = stuffapp._banknote_wantlist_themes(db)
    assert [k for k, _ in themes] == ['wantlist-french', 'wantlist-other'], [k for k, _ in themes]
    print('THEMES OK')

# US large-size types (2026-09-19): Friedberg ranges, retired by any
# Own/Ordered US note whose catalogue fields carry a number in range.
USWL = stuffapp.BANKNOTE_US_LARGE_WANTLIST
assert len({e[0] for e in USWL}) == len(USWL), 'duplicate US entries'
assert {e[1] for e in USWL} == {'treasury', 'banks'}
spans = sorted((lo, hi, e[0]) for e in USWL for lo, hi in e[2])
for (lo1, hi1, n1), (lo2, hi2, n2) in zip(spans, spans[1:]):
    assert hi1 < lo2, f'overlapping Friedberg ranges: {n1} / {n2}'
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute("DELETE FROM banknotes")
    assert len(stuffapp._banknote_us_wantlist_open(db)) == len(USWL)
    us_rows = [
        ('United States of America', 1899, '$1', 'United States Treasury', 'Friedberg 229, Greysheet 60401', '', 'Own'),
        ('United States of America', 1896, '$2', 'United States Treasury', 'Fr#248, Friedberg 248 (FR #248)', '', 'Own'),
        ('United States of America', 1922, '$20', 'United States Treasury', 'Fr. 1187m', '', 'Own'),
        ('United States of America', 1882, '$5', 'The San Francisco National Bank', 'Fr.475', '', 'Own'),
        ('United States of America', 1890, '$10', 'United States Treasury', 'Fr#368', '', 'Ordered'),
        ('United States of America', 1772, '2 Shillings', 'Province of Pennsylvania', 'Fr#PA-156', '', 'Own'),
        ('United States of America', 1850, '$50', 'Canal Bank (New Orleans)', 'LA105G48a', '', 'Own'),
        ('United States of America', 1860, '$1', 'State Bank at New Brunswick', 'Haxby NJ350-G16a', '', 'Own'),
        ('United States of America', 1872, '$20', 'State of South Carolina', 'SCCR7, Cr-SC-7', '', 'Own'),
        ('United States of America', 1857, '$5', 'Western Exchange Fire & Marine Insurance Co. (Bishop Hill Colony)', 'NEW215', 'Bishop Hill, Illinois', 'Own'),
        ('United States of America', 1869, '50 Cents', 'United States Treasury (Fractional Currency)', 'Fr#1379', '', 'Own'),
        ('United States of America', 1935, '$1', 'United States Treasury', 'Fr#2300', '', 'Own'),
        ('United States of America', 1862, '$1', 'United States Treasury', 'Fr. 16', '', 'Sold'),
        ('Philippines', 1944, '1 Peso', 'Treasury', 'P-94', '', 'Own'),
    ]
    for i, (c, y, d, iss, pick, muni, st) in enumerate(us_rows):
        db.execute("INSERT INTO banknotes (id, country, date_1, denomination, issuer, pick_number, municipality, status) "
                   "VALUES (?, ?, ?, ?, ?, ?, ?, ?)", [f'us{i}', c, y, d, iss, pick, muni, st])
    db.commit()
    held = stuffapp._banknote_us_friedberg_held(db)
    assert held == {229, 248, 1187, 475, 368, 1379, 2300}, held  # PA-156 is no Friedberg number; a Sold note does not count
    open_names = [e[0] for e in stuffapp._banknote_us_wantlist_open(db)]
    for name in ('$1 Silver Certificate 1899 "Black Eagle"', '$2 Silver Certificate 1896 Educational',
                 '$20 Gold Certificate 1922', '$5 National Bank Note 1882 Brown Back', '$10 Treasury (Coin) Note 1890'):
        assert name not in open_names, name
    for name in ('$1 Legal Tender 1862 (Chase)', '$1 Legal Tender 1869 "Rainbow"', '$10 National Bank Note 1882 Brown Back',
                 '$5 Federal Reserve Note 1914 Red Seal'):
        assert name in open_names, name
    assert len(open_names) == len(USWL) - 5, len(open_names)
    themes = stuffapp._banknote_us_wantlist_themes(db)
    assert [k for k, _ in themes] == ['us-large-treasury', 'us-large-banks'], [k for k, _ in themes]
    assert '$1 Legal Tender 1869 "Rainbow" (Fr. 18)' in themes[0][1]
    assert 'Black Eagle' not in themes[0][1], 'a held type must not be asked for'
    assert '$10 National Bank Note 1882 Brown Back (Fr. 479–492)' in themes[1][1]
    assert 'five-figure type' in themes[0][1] and '`empire` to "US"' in themes[1][1]
    # Obsoletes: the states held come from the Haxby / Criswell prefix and the issuer / municipality text.
    states = stuffapp._banknote_obsolete_states_held(db)
    assert states == {'LA', 'NJ', 'SC', 'IL'}, states  # PA-156 (1772) is a colonial, not an obsolete; Fr. notes are federal
    key, text = stuffapp._banknote_obsolete_theme(db)
    assert key == 'us-obsolete'
    assert 'States already represented: Illinois, Louisiana, New Jersey, South Carolina' in text, text
    assert 'Massachusetts' in text and 'SIGNED AND DATED' in text and 'remainders' in text
    # Every group held -> no US theme.
    for e in USWL:
        if e[1] == 'banks':
            db.execute("INSERT INTO banknotes (id, country, date_1, pick_number, status) VALUES (?, 'USA', 1902, ?, 'Own')",
                       [f'usb-{e[0]}', f'Fr. {e[2][0][0]}'])
    db.commit()
    assert [k for k, _ in stuffapp._banknote_us_wantlist_themes(db)] == ['us-large-treasury']
    print('US LARGE-SIZE OK')

# The market page shows the open count.
client = stuffapp.app.test_client()
r = client.get('/banknotes/market')
assert r.status_code == 200
html = r.get_data(as_text=True)
assert 'colonial want-list:' in html and 'of 35 still open' in html, 'want-list count missing'
assert 'US large-size types:' in html and f'of {len(stuffapp.BANKNOTE_US_LARGE_WANTLIST)} still open' in html, 'US count missing'
r = client.get('/coins/market')
assert 'colonial want-list' not in r.get_data(as_text=True)
print('PAGE OK')
print('ALL MARKET-WANTLIST ASSERTIONS PASSED')
