"""Art and Vehicles lists open on Own; their status pill rotates
Own -> Ordered -> All -> Own with All as an explicit ?filter=all, and
the other status-bearing lists keep All as their bare default.

Run: .venv/bin/python tests/test_status_default_own.py
"""
import os, sys, tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-status-')

import app as stuffapp

client = stuffapp.app.test_client()

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute("INSERT INTO art (id, title, status) VALUES (9101, 'Owned Piece', 'Own')")
    db.execute("INSERT INTO art (id, title, status) VALUES (9102, 'Ordered Piece', 'Ordered')")
    db.execute("INSERT INTO art (id, title, status) VALUES (9103, 'Sold Piece', 'Sold')")
    db.commit()


def html(path):
    r = client.get(path)
    assert r.status_code == 200, (path, r.status_code)
    return r.get_data(as_text=True)


# Fresh visit: Own only, pill reads Own and links to Ordered.
h = html('/art')
assert 'Owned Piece' in h and 'Ordered Piece' not in h and 'Sold Piece' not in h
assert '>Own</a>' in h, 'pill should read Own on a fresh visit'
assert '/art?filter=ordered' in h, 'Own stop should link to Ordered'

# Ordered stop links to the explicit All stop.
h = html('/art?filter=ordered')
assert 'Ordered Piece' in h and 'Owned Piece' not in h
assert '/art?filter=all' in h, 'Ordered stop should link to ?filter=all'

# All stop shows everything and links back to Own.
h = html('/art?filter=all')
assert 'Owned Piece' in h and 'Ordered Piece' in h and 'Sold Piece' in h
assert 'Status: All' in h
assert '/art?filter=own' in h, 'All stop should link back to Own'

# A search bypasses the default so sold pieces are findable.
h = html('/art?q_art=Sold')
assert 'Sold Piece' in h

# Categories not in STATUS_DEFAULT_OWN keep All as the bare default.
h = html('/cameras')
assert 'Status: All' in h and '/cameras?filter=own' in h

# Vehicles (already default-own) now has a reachable All stop.
h = html('/vehicles?filter=ordered')
assert '/vehicles?filter=all' in h

print('STATUS DEFAULT OWN OK')
