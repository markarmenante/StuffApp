"""Check and the serial scan read the UNTRIMMED slab photo: since uploads
are trimmed to the bare note on arrival (2026-09-10), the stored
image_1/image_2 no longer carry the PMG/PCGS label, and Check read no
grading data at all. _banknote_vision_source resolves a trimmed file to
its recorded original when that is still on disk.

Run: .venv/bin/python tests/test_banknote_vision_source.py
"""
import base64, os, sys, tempfile
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-vsrc-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuffapp

os.makedirs(stuffapp.UPLOAD_FOLDER, exist_ok=True)
for name, color in (('orig-front.jpg', 'yellow'), ('trim-front.jpg', 'blue'), ('trim-back.jpg', 'red')):
    Image.new('RGB', (100, 50), color).save(os.path.join(stuffapp.UPLOAD_FOLDER, name))

with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute("INSERT INTO banknotes (id, country, denomination, date_1, image_1, image_2) "
               "VALUES (9201, 'Morocco', '5 Francs', 1924, 'trim-front.jpg', 'trim-back.jpg')")
    # Front: trimmed from an original that is still on disk.
    db.execute("INSERT INTO trimmed_image_sources (trimmed, source, quad) VALUES (?, ?, NULL)",
               ('trim-front.jpg', 'orig-front.jpg'))
    # Back: trimmed from an original that has since been swept away.
    db.execute("INSERT INTO trimmed_image_sources (trimmed, source, quad) VALUES (?, ?, NULL)",
               ('trim-back.jpg', 'gone-back.jpg'))
    db.commit()

    src = stuffapp._banknote_vision_source
    assert src('trim-front.jpg') == 'orig-front.jpg'
    assert src('trim-back.jpg') == 'trim-back.jpg'      # original missing -> stored file
    assert src('untracked.jpg') == 'untracked.jpg'      # never trimmed
    assert src('') == '' and src(None) is None
    print('RESOLVER OK')

    # Check encodes the original holder bytes, retaining the saved back only
    # when its original has gone. Distinct colors make an accidental crop
    # substitution observable independently of helper implementation.
    note = db.execute("SELECT * FROM banknotes WHERE id = 9201").fetchone()
    images = stuffapp._banknote_check_vision_images(note)
    assert [image['label'] for image in images] == ['front', 'back'], images
    for image, filename in zip(images, ('orig-front.jpg', 'trim-back.jpg')):
        with open(os.path.join(stuffapp.UPLOAD_FOLDER, filename), 'rb') as source:
            assert base64.b64decode(image['data']) == source.read()
    stuffapp._require_anthropic_key = lambda: (_ for _ in ()).throw(RuntimeError('no key in test'))
    note = db.execute("SELECT * FROM banknotes WHERE id = 9201").fetchone()
    try:
        stuffapp.fetch_banknote_specs(note)
    except RuntimeError as e:
        assert 'no key in test' in str(e), e
    seen = []
    real_loader = stuffapp._load_vision_images
    stuffapp._load_vision_images = lambda items: seen.append(list(items)) or []
    try:
        stuffapp.scan_banknote_serial(note)
    except RuntimeError as e:
        pass
    assert seen and seen[-1] == [('orig-front.jpg', 'front'), ('trim-back.jpg', 'back')], seen
    stuffapp._load_vision_images = real_loader
    print('CHECK + SERIAL SCAN READ ORIGINALS OK')

print('ALL BANKNOTE-VISION-SOURCE ASSERTIONS PASSED')
