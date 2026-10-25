"""Missing-entity priorities use pill coverage and reviewed issue periods.

US large-size/obsolete discovery remains independent of entity-gap priorities.
No network, browser, production database or external purchase is used.
"""
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

REPO = str(Path(__file__).resolve().parents[1])
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-wl-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuffapp


def open_keys(db):
    return {entity['key'] for entity in stuffapp._banknote_wantlist_open(db)}


def add(db, ident, country, year, status='Own', issuer=''):
    db.execute('INSERT INTO banknotes(id,country,date_1,status,issuer) VALUES(?,?,?,?,?)',
               (ident, country, year, status, issuer))


with stuffapp.app.app_context():
    db = stuffapp.get_db()
    eligible = stuffapp._banknote_wantlist_catalog()
    eligible_keys = {entity['key'] for entity in eligible}
    assert len(eligible_keys) == len(eligible)
    assert len(eligible) > 35, 'active coverage must extend beyond the historical fixed list'
    assert all(entity['issued'] is True and entity['scan_period'] for entity in eligible)
    for excluded in ('british-pitcairn-islands', 'portuguese-nyassa-company',
                     'british-east-caribbean-states', 'french-west-african-states'):
        assert excluded not in eligible_keys, excluded
    assert open_keys(db) == eligible_keys
    themes = stuffapp._banknote_wantlist_themes(db)
    assert [key for key, _ in themes] == ['entity-gap-british', 'entity-gap-french', 'entity-gap-other']
    combined = '\n'.join(text for _, text in themes)
    assert 'BEFORE INDEPENDENCE' in combined and '`entity_key`' in combined
    for entity in eligible:
        assert combined.count('[' + entity['key'] + ']') == 1, entity['key']
        period = entity['scan_period']
        if period['year_end'] is not None:
            assert f"{period['year_start']}–{period['year_end'] - 1} only" in combined
    assert '[portuguese-nyassa-company]' not in combined
    assert '[british-pitcairn-islands]' not in combined
    print('SHARED ELIGIBLE ROSTER AND THREE THEMES OK')

    fixtures = [
        ('palestine', 'Palestine', 1939, 'Own', 'Palestine Currency Board'),
        ('cuba-modern', 'Cuba', 1958, 'Own', 'Banco Nacional de Cuba'),
        ('sao-modern', 'Sao Tome and Principe', 1993, 'Own', 'Banco Central'),
        ('taiwan', 'Taiwan', 1933, 'Own', 'Bank of Taiwan'),
        ('zanzibar-sold', 'Zanzibar', 1920, 'Sold', 'Zanzibar Government'),
        ('philippines', 'Philippines', 1944, 'Own', 'Treasury'),
        ('new-jersey', 'New Jersey', 1776, 'Own', 'Colony of New Jersey'),
        ('canada-modern', 'Canada', 1967, 'Own', 'Bank of Canada'),
        ('afars-alias', 'French Afars & Issas', 1975, 'Ordered', 'Trésor Public'),
        ('regional', 'Malaya and British Borneo', 1959, 'Shipped',
         'Board of Commissioners of Currency, Malaya and British Borneo'),
    ]
    for row in fixtures:
        add(db, *row)
    db.commit()
    missing = open_keys(db)
    for held in ('british-palestine', 'japanese-taiwan', 'us-philippines',
                 'british-canada', 'french-french-territory-of-the-afars-and-issas',
                 'british-malaya-and-british-borneo', 'british-british-north-borneo',
                 'british-sarawak', 'british-singapore', 'british-brunei'):
        assert held not in missing, held
    for still_missing in ('spanish-cuba', 'portuguese-sao-tome-and-principe',
                          'british-zanzibar', 'british-malaya'):
        assert still_missing in missing, still_missing
    jersey_row = db.execute("SELECT * FROM banknotes WHERE id='new-jersey'").fetchone()
    assert 'british-jersey' not in {entity['key'] for entity in
                                  stuffapp.banknote_entity_coverage.entities_for_row(jersey_row)}
    if 'british-jersey' in eligible_keys:
        assert 'british-jersey' in missing
    # Green Commonwealth coverage stays covered even though new offers have
    # stricter colonial-period rules. Pending regional coverage matches pills.
    with stuffapp.app.test_request_context('/banknotes?filter=ordered&q_banknotes=nothing&dot=1'):
        stuffapp.g.current_user = {'role': 'owner'}
        pills = stuffapp.banknote_entity_pills(db, [])
        yellow = {pill['key'] for group in pills.values() for pill in group
                  if pill['coverage'] == 'missing' and pill['key'] in eligible_keys}
        assert missing == yellow, (missing ^ yellow)
    prompts = '\n'.join(text for _, text in stuffapp._banknote_wantlist_themes(db))
    assert '[british-british-north-borneo]' not in prompts
    assert '[french-french-territory-of-the-afars-and-issas]' not in prompts
    assert '[spanish-cuba]' in prompts
    # A colonial Cuba note closes only that historical identity.
    add(db, 'cuba-colonial', 'Cuba', 1896, 'Delivered', 'Banco Español de la Isla de Cuba')
    db.commit()
    assert 'spanish-cuba' not in open_keys(db)
    print('IDENTITY, REGIONAL COVERAGE AND FILTER INDEPENDENCE OK')

    for status in ('Own', 'Owned', '', None, 'Ordered', 'Shipped', 'Delivered', ' ordered '):
        add(db, 'status-check', 'Bahamas', 1960, status)
        assert 'british-bahamas' not in open_keys(db), status
        db.execute("DELETE FROM banknotes WHERE id='status-check'")
    for status in ('Sold', 'Gifted', 'Lost', 'Consigned', 'Loaned'):
        add(db, 'status-check', 'Bahamas', 1960, status)
        assert 'british-bahamas' in open_keys(db), status
        db.execute("DELETE FROM banknotes WHERE id='status-check'")
    db.commit()
    with patch.object(stuffapp, '_banknote_wantlist_open', return_value=[]):
        assert stuffapp._banknote_wantlist_themes(db) == []
        keys = [key for key, _ in stuffapp._BanknoteMarketPolicy().themes(db)]
        assert not any(key.startswith('entity-gap-') for key in keys)
        assert 'us-obsolete' in keys
        assert all(key in keys for key, _ in stuffapp._MARKET_THEMES['banknotes'])
    class UnavailableCollection:
        def execute(self, *_args):
            raise sqlite3.OperationalError('fixture unavailable')
    try:
        stuffapp._banknote_wantlist_open(UnavailableCollection())
    except sqlite3.OperationalError:
        pass
    else:
        raise AssertionError('an unreadable collection must not imply all entities are missing')
    print('PURCHASE PHASES, BROAD DISCOVERY AND READ FAILURE OK')

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
assert 'missing entities:' in html and f'of {len(stuffapp._banknote_wantlist_catalog())}' in html, 'entity count missing'
assert 'US large-size types:' in html and f'of {len(stuffapp.BANKNOTE_US_LARGE_WANTLIST)} still open' in html, 'US count missing'
r = client.get('/coins/market')
assert 'missing entities:' not in r.get_data(as_text=True)
print('PAGE OK')
print('ALL MARKET-WANTLIST ASSERTIONS PASSED')
