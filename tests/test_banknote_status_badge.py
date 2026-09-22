"""List headings show non-owned status without changing collection ownership."""
from html.parser import HTMLParser
import os
from pathlib import Path
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]
os.chdir(REPO)
sys.path.insert(0, str(REPO))
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-status-badge-')
os.environ.pop('ANTHROPIC_API_KEY', None)

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
    db.commit()
    before = [tuple(r) for r in db.execute('SELECT id,status FROM banknotes ORDER BY id')]

response = stuffapp.app.test_client().get('/banknotes?history=0')
assert response.status_code == 200, response.status_code
headings = Headings()
headings.feed(response.get_data(as_text=True))
for note_id, ownership, delivery, manual, expected in cases:
    spans = headings.rows['item-' + note_id]
    assert [s[1] for s in spans[:2]] == ['Hong Kong', '1 Dollar'], (note_id, spans)
    badges = [s for s in spans if 'banknote-status-badge' in s[0]]
    assert [s[1] for s in badges] == ([expected] if expected else []), (note_id, badges)
    if expected:
        assert spans[2] == badges[0], (note_id, 'badge must follow denomination')
        assert 'ebay-' + expected.lower() in badges[0][0]
    if manual:
        assert 'manual correction' in badges[0][2]

with stuffapp.app.app_context():
    after = [tuple(r) for r in stuffapp.get_db().execute('SELECT id,status FROM banknotes ORDER BY id')]
assert after == before, 'Rendering the list must never change ownership'
print(f'BANKNOTE STATUS BADGE OK: {len(cases)} cases; ownership unchanged')
