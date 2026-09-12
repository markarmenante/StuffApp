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

# The market page shows the open count.
client = stuffapp.app.test_client()
r = client.get('/banknotes/market')
assert r.status_code == 200
html = r.get_data(as_text=True)
assert 'colonial want-list:' in html and 'of 35 still open' in html, 'want-list count missing'
r = client.get('/coins/market')
assert 'colonial want-list' not in r.get_data(as_text=True)
print('PAGE OK')
print('ALL MARKET-WANTLIST ASSERTIONS PASSED')
