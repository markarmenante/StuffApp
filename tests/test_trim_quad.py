"""Quad-corner crop fix-up round-trip: the info route reports the
recorded original and its quad, the apply route warps the original by a
hand-adjusted quad, stores it as the field's image, and records the new
quad — so the crop stays a re-derivable transform.

Run: .venv/bin/python tests/test_trim_quad.py
"""
import io
import json
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-quad-')

import app as stuffapp  # noqa: E402

from PIL import Image, ImageDraw  # noqa: E402

client = stuffapp.app.test_client()

# A synthetic "original photo": grey backdrop, note paper at a known
# offset so the warp result is checkable by size.
orig = Image.new('RGB', (1200, 800), (120, 122, 128))
d = ImageDraw.Draw(orig)
d.rectangle([200, 150, 1000, 590], fill=(246, 242, 230))
d.rectangle([240, 190, 960, 550], outline=(60, 50, 40), width=12)
buf = io.BytesIO()
orig.save(buf, format='JPEG', quality=90)

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    os.makedirs(stuffapp.UPLOAD_FOLDER, exist_ok=True)
    with open(os.path.join(stuffapp.UPLOAD_FOLDER, 'quadsrc.jpg'), 'wb') as fh:
        fh.write(buf.getvalue())
    # The stored image is a stand-in crop derived from quadsrc.jpg.
    with open(os.path.join(stuffapp.UPLOAD_FOLDER, 'quadtrim.jpg'), 'wb') as fh:
        crop = orig.crop((210, 160, 990, 580))
        cbuf = io.BytesIO()
        crop.save(cbuf, format='JPEG')
        fh.write(cbuf.getvalue())
    db.execute(
        "INSERT INTO banknotes (id, country, denomination, image_1) "
        "VALUES ('q1', 'Testland', '5 Test', 'quadtrim.jpg')")
    db.execute(
        "INSERT OR REPLACE INTO trimmed_image_sources (trimmed, source, quad) "
        "VALUES ('quadtrim.jpg', 'quadsrc.jpg', ?)",
        (json.dumps([[210, 160], [990, 160], [990, 580], [210, 580]]),))
    db.commit()

# --- info route: reports the original's dims and the stored quad.
r = client.get('/banknotes/q1/trim-quad/image_1')
assert r.status_code == 200, r.status_code
info = r.get_json()
assert info['width'] == 1200 and info['height'] == 800, info
assert info['quad'][0] == [210, 160], info['quad']
assert 'trim-source' in info['source_url'], info

# --- source route serves the original even though no row links it.
r = client.get('/banknotes/q1/trim-source/image_1')
assert r.status_code == 200, r.status_code
assert len(r.data) == len(buf.getvalue())

# --- a field with no image 404s; an unknown field 400s.
assert client.get('/banknotes/q1/trim-quad/image_2').status_code == 404
assert client.get('/banknotes/q1/trim-quad/notes').status_code == 400

# --- apply: warp the original by the paper's true corners.
r = client.post('/banknotes/q1/trim-quad/image_1',
                json={'quad': [[200, 150], [1000, 150],
                               [1000, 590], [200, 590]]})
assert r.status_code == 200, (r.status_code, r.get_json())
applied = r.get_json()
assert abs(applied['width'] - 800) <= 2, applied
assert abs(applied['height'] - 440) <= 2, applied

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    row = db.execute("SELECT image_1 FROM banknotes WHERE id = 'q1'").fetchone()
    new_name = row['image_1']
    assert new_name != 'quadtrim.jpg'
    src = db.execute(
        'SELECT source, quad FROM trimmed_image_sources WHERE trimmed = ?',
        (new_name,)).fetchone()
    # The new crop chains back to the ORIGINAL, never to a prior trim,
    # and carries the quad it was cut with.
    assert src['source'] == 'quadsrc.jpg', src['source']
    assert json.loads(src['quad'])[0] == [200.0, 150.0], src['quad']
    assert os.path.exists(os.path.join(stuffapp.UPLOAD_FOLDER, new_name))

# --- the new crop is itself servable and re-adjustable from the same
# original (idempotent re-derivation).
r = client.get('/banknotes/q1/trim-quad/image_1')
assert r.get_json()['quad'][0] == [200.0, 150.0]

# --- corners too close together are refused.
r = client.post('/banknotes/q1/trim-quad/image_1',
                json={'quad': [[10, 10], [20, 10], [20, 18], [10, 18]]})
assert r.status_code == 400, r.status_code

# --- malformed quads are refused.
for bad in (None, [], [[1, 2]], 'x', [[1, 2], [3, 4], [5, 6], ['a', 'b']]):
    r = client.post('/banknotes/q1/trim-quad/image_1', json={'quad': bad})
    assert r.status_code == 400, (bad, r.status_code)

print('ALL TRIM-QUAD ASSERTIONS PASSED')
