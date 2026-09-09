"""Banknote price currency: Check keeps the dealer's currency, and the
apply step adds the same " / $X,XXX" tail the detail page writes."""
import os, sys, sqlite3, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-price-')

import app as stuffapp

parse = stuffapp._parse_price_amount
assert parse('$450') == ('USD', 450.0)
assert parse('450') == ('USD', 450.0)
assert parse('€1.200,00') == ('EUR', 1200.0)
assert parse('€1,200.50') == ('EUR', 1200.5)
assert parse('1.200 EUR') == ('EUR', 1200.0)
assert parse('CHF 1,200') == ('CHF', 1200.0)
assert parse('chf 1200') == ('CHF', 1200.0)
assert parse('850 gbp') == ('GBP', 850.0)
assert parse('A$2,000') == ('AUD', 2000.0)
assert parse('US$99') == ('USD', 99.0)
assert parse('¥50,000') == ('JPY', 50000.0)
assert parse('€1,200 / $1,300') == ('EUR', 1200.0), 'tail stripped'
assert parse('') == (None, None) and parse('abc') == (None, None)
assert parse('C$80') == ('CAD', 80.0) and parse('c$ 80') == ('CAD', 80.0)
assert parse('cdn 80') == ('CAD', 80.0) and parse('CA$80') == ('CAD', 80.0)
assert parse('80 cad') == ('CAD', 80.0) and parse('can 80') == ('CAD', 80.0)
assert parse('NZ$120') == ('NZD', 120.0) and parse('HK$5,000') == ('HKD', 5000.0)
assert parse('S$40') == ('SGD', 40.0) and parse('US$40') == ('USD', 40.0)
assert parse('R$300') == ('BRL', 300.0) and parse('MX$300') == ('MXN', 300.0)
print('PARSE OK')

fmt = stuffapp._format_purchase_price
assert fmt('$2,000') == '$2,000'
assert fmt('449.50') == '$449.50'
assert fmt('€1.200,00') == '€1,200'
assert fmt('1.200,50 EUR') == '€1,200.50'
assert fmt('CHF 1,200') == 'CHF 1,200'
assert fmt('850 GBP') == '£850'
assert fmt('A$ 2000') == 'A$2,000'
assert fmt('€1,200 / $1,300') == '€1,200'
assert fmt('0') is None and fmt('99999999') is None and fmt('') is None
assert fmt('cdn 80') == 'C$80' and fmt('c$ 80') == 'C$80' and fmt('80 CAD') == 'C$80'
assert fmt('NZ$120') == 'NZ$120' and fmt('S$40') == 'S$40'
# Round-trips through the server-side price normaliser and display filter.
for text in ('C$80', 'C$80 / $58', 'NZ$120', 'S$40 / $30', 'A$200', 'CHF 900 / $1,100'):
    assert stuffapp._normalize_price_input(text) == text, text
    assert stuffapp.currency_filter(text) == text, text
assert stuffapp._normalize_price_input('80') == '80'
print('FORMAT OK')


def _row(**kw):
    base = {'description': '', 'note_references': '', 'notes': ''}
    base.update(kw)
    return base


desc = stuffapp._banknote_description_fields
assert desc(_row(description='My Cost €1.200,00. Series 1943.')).get('price') == '€1,200'
assert desc(_row(description='Purchase price: CHF 1,200'))['price'] == 'CHF 1,200'
assert desc(_row(notes='paid 850 GBP on 2024-03-15'))['price'] == '£850'
assert desc(_row(description='Purchased from Spink for £1,250 in 2024.'))['price'] == '£1,250'
assert desc(_row(description='My Cost $450'))['price'] == '$450'
assert desc(_row(description='Paid C$80 at the Toronto show'))['price'] == 'C$80'
assert desc(_row(description='Purchase price: CDN 80'))['price'] == 'C$80'
assert 'price' not in desc(_row(description='Bought for a song; catalog value $500.'))
print('EXTRACT OK')

# USD tail: cached rate, no network (the fetch is stubbed to fail).
stuffapp._fetch_usd_rate = lambda currency, date_str: None
db = sqlite3.connect(':memory:')
db.row_factory = sqlite3.Row
db.execute("CREATE TABLE fx_rates (currency TEXT NOT NULL, date TEXT NOT NULL, "
           "usd_rate REAL NOT NULL, fetched_at TEXT NOT NULL, PRIMARY KEY (currency, date))")
db.execute("INSERT INTO fx_rates VALUES ('EUR', '2024-03-15', 1.09, 'x')")
tail = stuffapp._price_with_usd_tail
assert tail(db, '€1,200', '2024-03-15') == '€1,200 / $1,308', tail(db, '€1,200', '2024-03-15')
assert tail(db, '€1,200 / $999', '2024-03-15') == '€1,200 / $1,308', 'stale tail replaced'
assert tail(db, '$450', '2024-03-15') == '$450'
assert tail(db, '€1,200', '2024-03-16') == '€1,200', 'no rate, no tail'
assert tail(db, '', '2024-03-15') == ''
# A fetched rate is cached.
stuffapp._fetch_usd_rate = lambda currency, date_str: 1.25 if currency == 'CHF' else None
assert tail(db, 'CHF 1,000', '2024-03-16') == 'CHF 1,000 / $1,250'
assert db.execute("SELECT usd_rate FROM fx_rates WHERE currency='CHF' AND date='2024-03-16'").fetchone()[0] == 1.25
print('USD TAIL OK')
print('ALL BANKNOTE-PRICE-CURRENCY ASSERTIONS PASSED')
