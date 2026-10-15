"""List headings show non-owned status without changing collection ownership."""
from html.parser import HTMLParser
import os
from pathlib import Path
import sys
import tempfile
import types
import json

REPO = Path(__file__).resolve().parents[1]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-status-badge-')
os.environ.pop('ANTHROPIC_API_KEY', None)
os.environ['EBAY_SYNC_WORKER'] = '0'
os.environ['ORIGINAL_LISTING_WORKER'] = '0'
sys.modules['dotenv'] = types.SimpleNamespace(load_dotenv=lambda **kwargs: None)

import app as stuffapp


class Headings(HTMLParser):
    def __init__(self):
        super().__init__()
        self.rows = {}
        self.row = None
        self.heading = False
        self.span = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = attrs.get('class', '').split()
        if tag == 'div' and 'item-row' in classes:
            self.row = attrs['id']
        if tag == 'div' and 'item-line1' in classes:
            self.heading = True
            self.rows[self.row] = []
        if tag == 'span' and self.heading:
            self.span = [classes, '', attrs.get('title', '')]
            self.rows[self.row].append(self.span)

    def handle_data(self, data):
        if self.span is not None:
            self.span[1] += data

    def handle_endtag(self, tag):
        if tag == 'span':
            self.span = None
        if tag == 'div':
            self.heading = False


cases = [
    ('owned', 'Own', None, None, ''),
    ('owned-delivered', 'Own', 'Delivered', None, ''),
    ('legacy-owned', 'Owned', 'Shipped', None, ''),
    ('blank', '', 'Delivered', None, ''),
    ('null', None, None, None, ''),
    ('ordered', 'Ordered', None, None, 'Ordered'),
    ('ordered-linked', 'Ordered', 'Ordered', None, 'Ordered'),
    ('shipped', 'Ordered', 'Shipped', None, 'Shipped'),
    ('delivered', 'Ordered', 'Delivered', None, 'Delivered'),
    ('manual', 'Ordered', 'Shipped', 'Delivered', 'Delivered'),
    ('sold', 'Sold', 'Delivered', None, 'Sold'),
    ('loaned', 'Loaned', None, None, 'Loaned'),
    ('manual-shipped', 'Shipped', None, None, 'Shipped'),
    ('manual-delivered', 'Delivered', None, None, 'Delivered'),
    ('corrected', 'Delivered', 'Shipped', None, 'Shipped'),
    ('raw-shipped-delivered', 'Shipped', 'Delivered', None, 'Delivered'),
    ('unverified', 'Ordered', 'Delivered', None, 'Ordered'),
    ('refunded-pending', 'Ordered', 'Shipped', None, 'Ordered'),
    ('refunded-owned', 'Own', 'Shipped', None, ''),
    ('cancelled-pending', 'Shipped', 'Shipped', None, 'Shipped'),
]

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    for note_id, ownership, delivery, manual, expected in cases:
        db.execute('INSERT INTO banknotes (id,country,denomination,status) VALUES (?,?,?,?)',
                   (note_id, 'Hong Kong', '1 Dollar', ownership))
        if delivery:
            db.execute('INSERT INTO ebay_order_items '
                       '(line_key,order_id,item_id,title,quantity,delivery_status,last_seen) '
                       'VALUES (?,?,?,?,1,?,?)',
                       (note_id, note_id, note_id, 'Hong Kong 1 Dollar', delivery, '2026-09-22T12:00:00Z'))
            db.execute('INSERT INTO banknote_ebay_links '
                       '(banknote_id,line_key,matched_by,matched_at,manual_status) VALUES (?,?,?,?,?)',
                       (note_id, note_id, 'manual', '2026-09-22T12:00:00Z', manual))
    db.execute("INSERT INTO ebay_mail_receipts VALUES ('fixture-mail','unverified','Delivered','email only','2026-10-15T12:00:00Z')")
    for ident in ('refunded-pending','refunded-owned','cancelled-pending'):
        db.execute('INSERT INTO ebay_purchase_observations VALUES (?,?,?,?)',
                   (ident,'2026-10-15T12:00:00Z','Cancelled' if ident.startswith('cancelled') else 'Refunded',''))
    db.commit()
    before = [tuple(r) for r in db.execute('SELECT id,status FROM banknotes ORDER BY id')]

response = stuffapp.app.test_client().get('/banknotes?history=0')
assert response.status_code == 200, response.status_code
headings = Headings()
headings.feed(response.get_data(as_text=True))
for note_id, ownership, delivery, manual, expected in cases:
    spans = headings.rows['item-' + note_id]
    assert [s[1] for s in spans if 'item-brand' in s[0] or 'item-model' in s[0]] == ['Hong Kong', '1 Dollar'], (note_id, spans)
    badges = [s for s in spans if 'banknote-status-badge' in s[0]]
    assert [s[1] for s in badges] == ([expected] if expected else []), (note_id, badges)
    if expected:
        denomination_index = next(i for i,s in enumerate(spans) if 'item-model' in s[0])
        assert spans[denomination_index+1] == badges[0], (note_id, 'badge must follow denomination')
        assert 'ebay-' + expected.lower() in badges[0][0]
    if manual:
        assert 'manual correction' in badges[0][2]
    if expected == 'Delivered':
        assert 'awaiting visual inspection' in badges[0][2]
    reviews = [s for s in spans if 'purchase-review-pill' in s[0]]
    assert bool(reviews) == (note_id in ('unverified','refunded-pending','refunded-owned','cancelled-pending')), (note_id,reviews)

class InitialState(HTMLParser):
    def __init__(self,text):
        super().__init__();self.active=False;self.value='';self.feed(text)
    def handle_starttag(self,tag,attrs):
        if tag=='script' and 'data-purchase-status-initial' in dict(attrs):self.active=True
    def handle_endtag(self,tag):
        if tag=='script':self.active=False
    def handle_data(self,text):
        if self.active:self.value+=text

for note_id, ownership, delivery, manual, expected in cases:
    response=stuffapp.app.test_client().get('/banknotes/'+note_id)
    assert response.status_code==200,(note_id,response.status_code)
    state=json.loads(InitialState(response.get_data(as_text=True)).value)
    assert state['label']==(expected or 'Owned'),(note_id,state)
    assert state['status']==(expected or 'Own'),(note_id,state)
    assert state['attention']==(note_id in ('unverified','refunded-pending','refunded-owned','cancelled-pending')),(note_id,state)

with stuffapp.app.app_context():
    after = [tuple(r) for r in stuffapp.get_db().execute('SELECT id,status FROM banknotes ORDER BY id')]
assert after == before, 'Rendering the list must never change ownership'
print(f'BANKNOTE STATUS BADGE OK: {len(cases)} cases; ownership unchanged')
