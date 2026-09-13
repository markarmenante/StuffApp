"""Banknote collection report PDF: one country / colony per section on
a fresh page, its history first, then the notes three to a page with
front and back on one row and two detail lines under them. Built by a
background job; the Report pill on the list polls for it.

Run: .venv/bin/python tests/test_banknote_report.py
"""
import os, sys, io, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-report-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuffapp
from PIL import Image

os.makedirs(stuffapp.UPLOAD_FOLDER, exist_ok=True)
def photo(name, color):
    Image.new('RGB', (900, 420), color).save(os.path.join(stuffapp.UPLOAD_FOLDER, name), 'JPEG')
    return name

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    n = 0
    def add(country, denom, year, **kw):
        global n
        n += 1
        cols = {'id': f'n{n}', 'cat_id': f'B{n}', 'country': country, 'denomination': denom, 'date_1': year,
                'image_1': photo(f'f{n}.jpg', 'red'), 'image_2': photo(f'b{n}.jpg', 'blue'), 'status': 'Own'}
        cols.update(kw)
        db.execute(f"INSERT INTO banknotes ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})", list(cols.values()))
    # Germany: 5 notes (two pages of three), Djibouti: 1 note, sold note excluded, Ordered kept.
    for i in range(5):
        add('Germany', f'{10 * (i + 1)} Mark', 1910 + i, issuer='Reichsbank', pick_number='P-40',
            grading_authority='PMG', grade_numeric=65, grade='Gem Unc', grade_modifier='EPQ',
            serial_number=f'A{i}12345', size_width=160, size_height=90, printer='Reichsdruckerei',
            price='$120', vendor='dealer', purchase_date='2026-01-0%d' % (i + 1),
            slab_number='1234567-00%d' % i, material='Paper', watermark='Germania head',
                        condition=('Issued in the goldmark era, when the Reichsbank note was convertible to gold at a fixed parity and '
                       'circulated alongside the state banks\' paper; the series was withdrawn after the 1914 suspension. ' * 3)[:600],
            signatures=('Havenstein (Reichsbankpräsident) · Glasenapp · von Grimm · Kauffmann · Schmidt · Wagner · Schneider · '
                        'Friedrich · Müller · Lang · Weber · Fischer · Braun · Becker · Hoffmann · Schäfer · Koch · Bauer')[:239],
            obv_rev='Obv: Germania seated with sword and shield before an oak, value in each corner, serial in red at left and right / Rev: arabesque frame with eagle')
    add('Germany', '5000 Mark', 1922); add('Germany', '10000 Mark', 1922); add('Germany', '20000 Mark', 1923); add('Germany', '50000 Mark', 1923)
    add('French Somaliland', '100 Francs', 1952, issuer='Trésor Public', status='Ordered')
    add('Germany', '1000 Mark', 1922, status='Sold')
    db.commit()

    sections = stuffapp._banknote_report_sections(db)
    names = [(c, len(rows)) for c, _k, rows in sections]
    assert ('Germany', 9) in names and ('French Somaliland', 1) in names, names
    assert sum(k for _c, k in names) == 10, names   # the Sold note is out
    title, colonial, eras = stuffapp._banknote_report_history('French Somaliland', 'djibouti', [])
    assert title == 'Djibouti' and colonial and 'French Somaliland' in colonial and len(eras) >= 3
    title, colonial, eras = stuffapp._banknote_report_history('United States of America', 'us', [])
    assert title == 'United States' and eras
    l1, l2, l3, l4, l5 = stuffapp._banknote_report_lines(sections[[c for c, _k, _r in sections].index('Germany')][2][0])
    assert 'B1' in l1 and '10 Mark' in l1 and 'Reichsbank' in l1 and 'Pick P-40' not in ' '.join(l1) and 'P-40' in l1
    assert 'PMG 65 Gem Unc EPQ' in l2 and 'cert 1234567-000' in l2 and 'S/N A012345' in l2 and '160×90 mm' in l2 and 'Paper' in l2
    assert 'Reichsdruckerei' in l3 and 'wmk Germania head' in l3 and any(x.startswith('Havenstein') for x in l3)
    assert l4[0].startswith('Obv: Germania seated with sword')
    assert l5[0].startswith('Issued in the goldmark era') and len(l5[0]) >= 500
    joined = ' '.join(l1 + l2 + l3 + l4 + l5)
    assert '$120' not in joined and 'dealer' not in joined and '2026-01' not in joined, 'no price / vendor / purchase date'
    print('SECTIONS OK')

    path = stuffapp._banknote_report_path()
    notes, secs = stuffapp._build_banknote_report(path)
    assert notes == 10 and secs == 2 and os.path.exists(path) and os.path.getsize(path) > 10_000
    from pypdf import PdfReader
    pdf = PdfReader(path)
    texts = [p.extract_text() or '' for p in pdf.pages]
    import re as _re
    ids = [sorted(set(_re.findall(r'\bB(\d+)\b', x)), key=int) for x in texts]
    assert 'Banknote Collection' in texts[0]
    # The German section: its history page (era label present) comes first
    # and holds the history BEFORE any note; note pages after it carry
    # exactly four until the tail; every one of them opens with the
    # continued line ("Germany · continued", distinct from the era text).
    g_hist = next(i for i, t in enumerate(texts) if 'The goldmark' in t)
    assert '1' in ids[g_hist] and texts[g_hist].index('The goldmark') < texts[g_hist].index('B1 ')
    g_pages = [i for i, x in enumerate(ids) if x and int(x[0]) <= 9 and i > g_hist]
    counts = [len(ids[i]) for i in g_pages]
    assert all(c == 4 for c in counts[:-1]) and 1 <= counts[-1] <= 4, (counts, ids)
    assert all('Germany  ·  continued' in texts[i] or 'Germany · continued' in texts[i] for i in g_pages), 'continued line missing'
    assert all(len(x) <= 4 for x in ids), ids
    # French Somaliland: its own page, history first, ORDERED flagged.
    somali_page = next(i for i, x in enumerate(texts) if 'French Somaliland' in x and '10' in ids[i])
    assert 'Djibouti' in texts[somali_page] and 'ORDERED' in texts[somali_page]
    assert not any('1' in ids[i] and '10' in ids[i] for i in range(len(ids))), 'countries share no page'
    # Nothing is truncated: the 600-character context and the full signature list are
    # in the page text of every German note page, and no ellipsis was added.
    rich_pages = [i for i in g_pages + [g_hist] if 'PMG 65' in texts[i]]   # the five fully described notes
    assert rich_pages
    for i in rich_pages:
        t = texts[i].replace('\n', ' ')
        assert 'suspension' in t and 'Bauer' in t and 'eagle' in t, i   # tail words of context, signatures, design
        assert '…' not in t, 'a line was clipped'
    print('PDF OK', len(pdf.pages), 'pages')

# Routes and the pill.
client = stuffapp.app.test_client()
r = client.get('/banknotes')
html = r.get_data(as_text=True)
assert 'id="banknoteReport"' in html and '/banknotes/report/build' in html
r = client.get('/banknotes/report/status'); d = r.get_json()
assert d['exists'] and d['url'] == '/banknotes/report.pdf' and d['built_at'], d
r = client.get('/banknotes/report.pdf')
assert r.status_code == 200 and r.mimetype == 'application/pdf' and r.data[:4] == b'%PDF'
r = client.post('/banknotes/report/build'); assert r.status_code == 200 and r.get_json()['ok']
import time
for _ in range(60):
    d = client.get('/banknotes/report/status').get_json()
    if d['state'] in ('done', 'failed'): break
    time.sleep(0.5)
assert d['state'] == 'done' and d['notes'] == 10, d
r = client.get('/coins'); assert 'id="banknoteReport"' not in r.get_data(as_text=True)
print('ROUTES OK')
print('ALL BANKNOTE-REPORT ASSERTIONS PASSED')
