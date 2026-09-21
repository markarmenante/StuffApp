"""Check reads holder labels without replacing upload or hand-adjusted crops.

Regression: Canada's 1937 $20 (2026-09-20) had aligned upload crops;
Check re-ran corner detection and enlarged the reverse relative to the front.
Run: python3 tests/test_banknote_check_preserves_images.py
"""
import hashlib
import io
import os
import sys
import tempfile
from unittest.mock import patch

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-check-crops-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuffapp  # noqa: E402

client = stuffapp.app.test_client()


def jpeg(width, height):
    buf = io.BytesIO()
    Image.new('RGB', (width, height), (235, 230, 215)).save(buf, 'JPEG')
    return buf.getvalue()


def crop_on_upload(raw, expect_aspect=None, meta=None):
    meta['quad'] = [[50, 150], [750, 150], [750, 485], [50, 485]]
    return jpeg(700, 335)


def snapshot():
    with stuffapp.app.app_context():
        db = stuffapp.get_db()
        row = db.execute('SELECT image_1, image_2 FROM banknotes WHERE id = ?',
                         ('aligned',)).fetchone()
        mappings = [tuple(r) for r in db.execute(
            'SELECT trimmed, source, quad FROM trimmed_image_sources ORDER BY trimmed')]
        files = {}
        for filename in os.listdir(stuffapp.UPLOAD_FOLDER):
            path = os.path.join(stuffapp.UPLOAD_FOLDER, filename)
            if os.path.isfile(path):
                with open(path, 'rb') as fh:
                    files[filename] = hashlib.sha256(fh.read()).hexdigest()
        return tuple(row), mappings, files


with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute("INSERT INTO banknotes (id, country, denomination) "
               "VALUES ('aligned', 'Canada', '20 Dollars')")
    db.commit()

# Upload still trims each side once and keeps the holder originals.
with patch.object(stuffapp, '_trim_slabbed_note_image', side_effect=crop_on_upload) as trim:
    for field in ('image_1', 'image_2'):
        result = client.post('/banknotes/aligned/upload-image', data={
            'field': field, 'image': (io.BytesIO(jpeg(800, 600)), field + '.jpg'),
        })
        assert result.status_code == 200, result.get_json()
    assert trim.call_count == 2

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    note = db.execute("SELECT * FROM banknotes WHERE id = 'aligned'").fetchone()
    for field in ('image_1', 'image_2'):
        original = stuffapp._banknote_vision_source(note[field], db)
        assert original != note[field]
        assert Image.open(os.path.join(stuffapp.UPLOAD_FOLDER, original)).size == (800, 600)


def check_preserves_images(suggestions, expected_dims, lookup_error=False):
    before = snapshot()
    fetch = (patch.object(stuffapp, 'fetch_banknote_specs',
                          side_effect=RuntimeError('lookup unavailable'))
             if lookup_error else
             patch.object(stuffapp, 'fetch_banknote_specs', return_value=suggestions))
    with fetch, patch.object(stuffapp, 'ensure_country_history'), \
            patch.object(stuffapp, '_banknote_dims_scan_or_lookup', return_value=(152, 73)), \
            patch.object(stuffapp, '_trim_banknote_image') as trim:
        result = client.post('/banknotes/aligned/lookup-specs')
        if lookup_error:
            assert result.status_code == 503, result.get_json()
            assert result.get_json()['error'] == 'lookup unavailable'
            assert not trim.called
            assert snapshot() == before, 'Failed Check changed the images'
            return
        assert result.status_code == 200, result.get_json()
        data = result.get_json()
        assert not trim.called, 'Check must not re-crop either displayed image'
        assert data['images'] == {}, data
        assert snapshot() == before, 'Check changed crop files, mappings, or image fields'
        assert bool(data['lookup_error']) == lookup_error, data
        updates = dict(data['filled'])
        updates.update({k: v['new'] for k, v in data['overwritten'].items()})
        if updates:
            applied = client.post('/banknotes/aligned/apply-lookup-specs',
                                  json={'updates': updates})
            assert applied.status_code == 200, applied.get_json()
        assert snapshot() == before, 'Applying Check suggestions changed the images'
    if expected_dims:
        with stuffapp.app.app_context():
            row = stuffapp.get_db().execute(
                "SELECT size_width, size_height FROM banknotes WHERE id = 'aligned'").fetchone()
            assert tuple(row) == expected_dims, tuple(row)


# New dimensions, repeated Check, and a changed catalog size are all metadata only.
specs = {'size_width': 152, 'size_height': 73, 'grading_authority': 'PMG',
         'grade': 'Gem UNC', 'grade_numeric': 65, 'grade_modifier': 'EPQ'}
check_preserves_images(specs, (152, 73))
check_preserves_images(specs, (152, 73))
check_preserves_images({'size_width': 160, 'size_height': 80}, (160, 80))

# Deliberate manual corner adjustment must survive Check too.
result = client.post('/banknotes/aligned/trim-quad/image_2', json={
    'quad': [[60, 155], [740, 155], [740, 480], [60, 480]],
})
assert result.status_code == 200, result.get_json()
check_preserves_images(specs, (152, 73))

# Missing dimensions still get the existing catalog fallback, without cropping.
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute("UPDATE banknotes SET size_width = NULL, size_height = NULL WHERE id = 'aligned'")
    db.commit()
check_preserves_images({}, (152, 73))

# Older/unmapped images are left alone too; Check is not an implicit image editor.
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute('DELETE FROM trimmed_image_sources')
    db.commit()
check_preserves_images(specs, (152, 73))
check_preserves_images({}, (152, 73), lookup_error=True)

print('ALL BANKNOTE CHECK-PRESERVES-IMAGES ASSERTIONS PASSED')
