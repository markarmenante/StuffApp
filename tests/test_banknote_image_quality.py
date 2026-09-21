"""Holder uploads keep their source pixels and crop the paper, not the ink.

Canada 1935 $5 regression: the red reverse lost its margins and was
re-compressed several times. No model/network calls in these tests.
"""
import io
import math
import os
import sys
import tempfile
from unittest.mock import patch

from PIL import Image, ImageDraw, JpegImagePlugin

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
os.chdir(REPO)
os.environ['DATA_DIR'] = tempfile.mkdtemp(prefix='stuffapp-image-quality-')
os.environ.pop('ANTHROPIC_API_KEY', None)

import app as stuffapp  # noqa: E402


def holder(colour=(180, 60, 45), background=(215, 225, 232)):
    img = Image.new('RGB', (1600, 1000), background)
    draw = ImageDraw.Draw(img)
    draw.rectangle((85, 55, 1540, 250), fill=(148, 177, 153))
    draw.text((100, 85), 'PMG - 50 EPQ - 1935 $5', fill=(20, 30, 25))
    draw.polygon([(220, 300), (1400, 315), (1395, 855), (215, 840)],
                 fill=(232, 223, 185))
    draw.polygon([(260, 345), (1360, 359), (1355, 810), (255, 796)],
                 fill=colour)
    for x in range(285, 1330, 9):
        draw.line((x, 385, x, 765), fill=(240, 204, 160), width=2)
    draw.text((620, 815), 'PRINTER IMPRINT', fill=(60, 50, 35))
    return img


def encoded(img, fmt='WEBP'):
    buf = io.BytesIO()
    img.save(buf, format=fmt, lossless=True)
    return buf.getvalue()


for colour in ((180, 60, 45), (45, 45, 42)):
    img = holder(colour)
    expected = [(220, 300), (1400, 315), (1395, 855), (215, 840)]
    quad = stuffapp._warm_paper_on_light_holder_quad(img)
    assert quad, 'Both coloured and black designs should retain the paper outline'
    assert all(math.dist(a, b) < 4 for a, b in zip(quad, expected)), quad
    meta = {}
    with patch.object(stuffapp, '_trim_note_v2', side_effect=AssertionError('second crop')), \
            patch.object(stuffapp, '_trim_note_cv_cascade', side_effect=AssertionError('second crop')):
        output = stuffapp._trim_slabbed_note_image(encoded(img), meta=meta)
    result = Image.open(io.BytesIO(output))
    assert abs(result.width - 1180) <= 4 and abs(result.height - 540) <= 4, result.size
    assert meta['engine'] == 'paper-boundary' and len(meta['quad']) == 4, meta
    assert JpegImagePlugin.get_sampling(result) == 0, 'Do not subsample coloured engraving'
    # The wide paper margin below the printing must survive.
    r, g, b = result.getpixel((result.width // 2, result.height - 8))
    assert r > 200 and g > 190 and b < g - 15, (r, g, b)
    assert stuffapp._warm_paper_on_light_holder_quad(result) is None, 'Never re-crop a finished sheet'
    assert stuffapp._warm_paper_on_light_holder_quad(img, expect_aspect=3.4) is None

# A warm rectangular design on white paper is NOT a paper/holder boundary.
white_note = Image.new('RGB', (1200, 650), (245, 245, 242))
ImageDraw.Draw(white_note).rectangle((70, 65, 1130, 580), fill=(190, 65, 40))
assert stuffapp._warm_paper_on_light_holder_quad(white_note) is None
# Neutral/dark surrounds lack the affirmative cool-holder evidence.
assert stuffapp._warm_paper_on_light_holder_quad(holder(background=(45, 45, 45))) is None
assert stuffapp._warm_paper_on_light_holder_quad(Image.new('RGB', (1600, 1000), 'white')) is None
rotated = holder().rotate(2, resample=Image.Resampling.BICUBIC,
                          fillcolor=(215, 225, 232))
assert stuffapp._warm_paper_on_light_holder_quad(rotated) is not None

# Preserve native crop dimensions, even beyond the general photo resize cap.
large = Image.new('RGB', (3600, 1600), (225, 215, 185))
result = Image.open(io.BytesIO(stuffapp._encode_trimmed_note(large)))
assert result.size == large.size == (3600, 1600)
assert JpegImagePlugin.get_sampling(result) == 0

# Actual multipart drag/drop route: original WebP is kept byte-for-byte;
# the display crop points back to that source for Check and manual edits.
client = stuffapp.app.test_client()
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    db.execute("INSERT INTO banknotes (id) VALUES ('quality')")
    db.commit()
raw = encoded(holder())
response = client.post('/banknotes/quality/upload-image', data={
    'field': 'image_2', 'image': (io.BytesIO(raw), 'original.webp'),
})
assert response.status_code == 200, response.get_json()
with stuffapp.app.app_context():
    db = stuffapp.get_db()
    name = db.execute("SELECT image_2 FROM banknotes WHERE id='quality'").fetchone()[0]
    source = stuffapp._banknote_vision_source(name, db)
    assert source.endswith('.webp') and source != name
    with open(os.path.join(stuffapp.UPLOAD_FOLDER, source), 'rb') as f:
        assert f.read() == raw, 'Holder original must not be JPEG re-encoded'
    mapping = db.execute('SELECT quad FROM trimmed_image_sources WHERE trimmed=?', (name,)).fetchone()
    assert mapping['quad'], 'Full source geometry must be saved'
    images = stuffapp._load_vision_images([(source, 'holder')])
    assert images and images[0]['media_type'] == 'image/webp'

# Market acquisitions use the same source-preservation rule for notes.
with patch.object(stuffapp, '_market_fetch_image', return_value=(raw, 'webp')), \
        patch.object(stuffapp, '_market_page_image_urls', return_value=[]):
    stored = stuffapp._market_store_images({
        'title': 'Test banknote', 'listing_url': 'https://dealer.example/note',
        'image_urls': ['https://dealer.example/front.webp'],
    }, category='banknotes')
with open(os.path.join(stuffapp.UPLOAD_FOLDER, stored['image_1']), 'rb') as f:
    assert f.read() == raw

# Keep unrelated categories on their existing optimized-photo policy.
assert not stuffapp._should_optimize_item_image('banknotes', 'image_1')
assert stuffapp._should_optimize_item_image('coins', 'image_1')
assert not stuffapp._should_optimize_item_image('banknotes', 'description')

print('ALL BANKNOTE IMAGE-QUALITY ASSERTIONS PASSED')
