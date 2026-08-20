"""Round-trip tests for sale_plans — the normalized home of the sell
panel (one child table instead of 15 TEXT columns on every category
table). Pins: save-field writes go to sale_plans typed and leave the
legacy columns frozen; the detail view re-renders what was entered;
the price <-> purchase-price mirror works both ways; the sell/keep
list filter reads sale_plans; the backfill parses legacy text.
Run: .venv/bin/python tests/test_sale_plans.py
"""
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-sale-')

import app as appmod

client = appmod.app.test_client()
HDR = {'Cf-Access-Authenticated-User-Email': 'MarkArmenante@gmail.com'}

with appmod.app.app_context():
    db = appmod.get_db()
    db.execute("INSERT INTO watches (id, brand, model, price, status) "
               "VALUES ('w1', 'Breguet', 'Type XX', 100.0, 'Own')")
    db.execute("INSERT INTO watches (id, brand, model, status) "
               "VALUES ('w2', 'Omega', 'Speedmaster', 'Own')")
    db.commit()


def save(rid, field, value):
    r = client.post(f'/watches/{rid}/save-field',
                    json={'field': field, 'value': value}, headers=HDR)
    assert r.status_code == 200, (field, r.status_code, r.get_data())


# --- Writes land in sale_plans, typed; legacy columns stay frozen ----------
save('w1', 'sell_keep', 'Sell')
save('w1', 'sell_estimated_sales_price', '$2,500')
save('w1', 'sell_commission_percent', '20')
save('w1', 'sell_net_gain_loss', '-$150')
save('w1', 'sold_to', 'Heritage Auctions')

with appmod.app.app_context():
    db = appmod.get_db()
    sp = db.execute("SELECT * FROM sale_plans WHERE category = 'watches' "
                    "AND record_id = 'w1'").fetchone()
    assert sp is not None, 'no sale_plans row created'
    assert sp['sell_keep'] == 'Sell'
    assert sp['estimated_sales_price'] == 2500.0, sp['estimated_sales_price']
    assert sp['commission_percent'] == 20.0
    assert sp['net_gain_loss'] == -150.0, sp['net_gain_loss']
    assert sp['sold_to'] == 'Heritage Auctions'
    legacy = db.execute("SELECT sell_keep, sell_estimated_sales_price "
                        "FROM watches WHERE id = 'w1'").fetchone()
    assert legacy['sell_keep'] is None, 'legacy column written'
    assert legacy['sell_estimated_sales_price'] is None, 'legacy column written'
print('TYPED WRITE / FROZEN LEGACY ASSERTIONS PASSED')


# --- Detail view re-renders what was entered -------------------------------
html = client.get('/watches/w1', headers=HDR).get_data(as_text=True)
assert 'value="$2,500"' in html, 'estimated sales price not re-rendered'
assert 'value="20"' in html, 'commission 20 must re-render as 20, not 20.0'
assert 'Heritage Auctions' in html
print('DETAIL RE-RENDER ASSERTIONS PASSED')


# --- price <-> purchase price mirror, both directions ----------------------
save('w1', 'price', '$425')
with appmod.app.app_context():
    db = appmod.get_db()
    sp = db.execute("SELECT purchase_price FROM sale_plans WHERE "
                    "category = 'watches' AND record_id = 'w1'").fetchone()
    assert sp['purchase_price'] == 425.0, sp['purchase_price']
save('w1', 'sell_purchase_price', '$500')
with appmod.app.app_context():
    db = appmod.get_db()
    row = db.execute("SELECT price FROM watches WHERE id = 'w1'").fetchone()
    assert appmod._money_number(row['price']) == 500.0, row['price']
print('PRICE MIRROR ASSERTIONS PASSED')


# --- The sell/keep list filter reads sale_plans ----------------------------
html = client.get('/watches?q=sell', headers=HDR).get_data(as_text=True)
assert 'item-w1' in html, 'q=sell must find the Sell-marked record'
assert 'item-w2' not in html, 'q=sell must not return Keep records'
html = client.get('/watches?q=keep', headers=HDR).get_data(as_text=True)
assert 'item-w2' in html and 'item-w1' not in html, \
    'q=keep must return the default-Keep record only'
print('SELL/KEEP FILTER ASSERTIONS PASSED')


# --- The admin sell report reads sale_plans --------------------------------
html = client.get('/admin/sell-options', headers=HDR).get_data(as_text=True)
assert 'Breguet' in html, 'Sell-marked watch missing from sell report'
assert 'Speedmaster' not in html, 'Keep watch must not be in sell report'
print('SELL REPORT ASSERTIONS PASSED')


# --- sold_to remains searchable (via sale_plans) ---------------------------
html = client.get('/watches?q=heritage', headers=HDR).get_data(as_text=True)
assert 'item-w1' in html, 'sold_to must be searchable from sale_plans'
print('SOLD-TO SEARCH ASSERTIONS PASSED')


# --- Purchase input re-renders as currency, not a raw float ----------------
html = client.get('/watches/w1', headers=HDR).get_data(as_text=True)
assert 'value="$500"' in html, 'purchase price must render as $500, not 500.0'
print('PURCHASE RENDER ASSERTIONS PASSED')


# --- Art Sales Terms: shown when Sold, values round-trip through
# sale_plans (sale_date / sale_price / sold_to) -----------------------------
with appmod.app.app_context():
    db = appmod.get_db()
    db.execute("INSERT INTO art (id, title, artist, status) "
               "VALUES ('a1', 'Nocturne', 'Whistler', 'Own')")
    db.commit()

html = client.get('/art/a1', headers=HDR).get_data(as_text=True)
assert 'Sales Terms' in html, 'Sales Terms section missing from art detail'
import re as _re
_terms = _re.search(r'<div id="artSalesTerms"[^>]*>', html).group(0)
assert 'display:none' in _terms, \
    'Sales Terms must stay hidden while the piece is not Sold'

r = client.post('/art/a1/save-field',
                json={'field': 'status', 'value': 'Sold'}, headers=HDR)
assert r.status_code == 200, r.get_data()
for f, v in (('sale_date', '2026-08-01'), ('sale_price', '$12,500'),
             ('sold_to', 'Christie’s')):
    r = client.post('/art/a1/save-field',
                    json={'field': f, 'value': v}, headers=HDR)
    assert r.status_code == 200, (f, r.status_code, r.get_data())

with appmod.app.app_context():
    db = appmod.get_db()
    sp = db.execute("SELECT * FROM sale_plans WHERE category = 'art' "
                    "AND record_id = 'a1'").fetchone()
    assert sp is not None, 'no sale_plans row for the art record'
    assert sp['sale_date'] == '2026-08-01', sp['sale_date']
    assert sp['sale_price'] == 12500.0, sp['sale_price']
    assert sp['sold_to'] == 'Christie’s'

html = client.get('/art/a1', headers=HDR).get_data(as_text=True)
_terms = _re.search(r'<div id="artSalesTerms"[^>]*>', html).group(0)
assert 'display:none' not in _terms, \
    'Sales Terms must be visible once the piece is Sold'
assert 'value="2026-08-01"' in html, 'sale date lost on re-render'
assert 'value="$12,500"' in html, 'sale price must re-render as currency'
assert 'id="artGainLoss"' in html and 'Gain / Loss' in html, \
    'Gain / Loss cell missing from the purchase row'
print('ART SALES-TERMS ASSERTIONS PASSED')


# --- Create form: sell fields land in sale_plans, not frozen columns -------
resp = client.post('/watches/new', headers=HDR, data={
    'brand': 'Patek', 'model': 'Calatrava', 'status': 'Own',
    'sell_keep': 'Sell', 'sell_estimated_sales_price': '$9,000',
})
assert resp.status_code in (200, 302), resp.status_code
with appmod.app.app_context():
    db = appmod.get_db()
    row = db.execute("SELECT id, sell_keep FROM watches "
                     "WHERE brand = 'Patek'").fetchone()
    assert row is not None, 'created watch missing'
    assert row['sell_keep'] is None, 'create form wrote frozen legacy column'
    sp = db.execute("SELECT * FROM sale_plans WHERE category = 'watches' "
                    "AND record_id = ?", [row['id']]).fetchone()
    assert sp is not None and sp['sell_keep'] == 'Sell', \
        'create-form sell data lost'
    assert sp['estimated_sales_price'] == 9000.0, sp['estimated_sales_price']
    patek_id = row['id']
print('CREATE-FORM ROUTING ASSERTIONS PASSED')


# --- Deleting a record deletes its sale plan -------------------------------
resp = client.post(f'/watches/{patek_id}/delete', headers=HDR)
if resp.status_code == 404:  # route shape fallback
    resp = client.post(f'/delete/watches/{patek_id}', headers=HDR)
with appmod.app.app_context():
    db = appmod.get_db()
    gone = db.execute("SELECT 1 FROM watches WHERE id = ?",
                      [patek_id]).fetchone()
    if gone is None:  # only assert cleanup when the delete route ran
        orphan = db.execute("SELECT 1 FROM sale_plans WHERE record_id = ?",
                            [patek_id]).fetchone()
        assert orphan is None, 'deleted record left an orphaned sale plan'
        print('DELETE-CLEANUP ASSERTIONS PASSED')
    else:
        raise AssertionError('delete route not found for watches')


# --- Backfill parses frozen legacy text into typed sale_plans --------------
with appmod.app.app_context():
    db = appmod.get_db()
    db.execute("INSERT INTO banknotes (id, country, sell_keep, "
               "sell_estimated_sales_price, sell_commission_percent) "
               "VALUES ('bn3', 'Spain', 'Sell', '$1,250', '15%')")
    db.execute("DELETE FROM migration_state WHERE key = 'sale_plans_backfill_v1'")
    db.commit()
    appmod._backfill_sale_plans(db)
    sp = db.execute("SELECT * FROM sale_plans WHERE category = 'banknotes' "
                    "AND record_id = 'bn3'").fetchone()
    assert sp is not None, 'backfill created no row'
    assert sp['sell_keep'] == 'Sell'
    assert sp['estimated_sales_price'] == 1250.0, sp['estimated_sales_price']
    assert sp['commission_percent'] == 15.0, sp['commission_percent']
    # Idempotent: running again must not duplicate or error.
    db.execute("DELETE FROM migration_state WHERE key = 'sale_plans_backfill_v1'")
    db.commit()
    appmod._backfill_sale_plans(db)
    n = db.execute("SELECT COUNT(*) c FROM sale_plans WHERE record_id = 'bn3'"
                   ).fetchone()['c']
    assert n == 1, f'backfill duplicated rows: {n}'
print('BACKFILL ASSERTIONS PASSED')

print('ALL SALE-PLAN ASSERTIONS PASSED')
