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


# A pale left vignette can disappear from the engraving mask after a complete
# paper quad was found. An unavailable model must not ship that partial design.
whole = Image.new('RGB', (1162, 659), (240, 226, 198))
draw = ImageDraw.Draw(whole)
draw.rectangle((28, 28, 1134, 630), fill=(215, 175, 145))
draw.text((40, 600), 'LEFT DENOMINATION', fill=(80, 60, 40))
whole_bytes = encoded(whole)
fragment = encoded(whole.crop((358, 20, 1162, 641)))
with patch.object(stuffapp, '_trim_slab_note_cv', side_effect=[whole_bytes, None]), \
        patch.object(stuffapp, '_trim_dark_slab_note', return_value=None), \
        patch.object(stuffapp, '_trim_light_slab_note', return_value=None), \
        patch.object(stuffapp, '_trim_note_design_crop', return_value=fragment):
    result = stuffapp._trim_note_cv_cascade(Image.new('RGB', (1511, 1132), (55, 115, 120)))
assert result == whole_bytes, 'A darker partial design must not replace the measured full sheet'
# Small edge cleanup remains available; no blanket prohibition on later passes.
tidied = encoded(whole.crop((3, 3, 1159, 656)))
with patch.object(stuffapp, '_trim_slab_note_cv', side_effect=[whole_bytes, None, None]), \
        patch.object(stuffapp, '_trim_dark_slab_note', return_value=None), \
        patch.object(stuffapp, '_trim_light_slab_note', return_value=None), \
        patch.object(stuffapp, '_trim_note_design_crop', side_effect=[tidied, None]):
    result = stuffapp._trim_note_cv_cascade(Image.new('RGB', (1511, 1132), (55, 115, 120)))
assert result == tidied, 'Small cleanup should preserve the established crop behavior'
# A harmless first cleanup cannot discard the paper anchor for a later pass.
with patch.object(stuffapp, '_trim_slab_note_cv', side_effect=[whole_bytes, None, None]), \
        patch.object(stuffapp, '_trim_dark_slab_note', return_value=None), \
        patch.object(stuffapp, '_trim_light_slab_note', return_value=None), \
        patch.object(stuffapp, '_trim_note_design_crop', side_effect=[tidied, fragment]):
    result = stuffapp._trim_note_cv_cascade(Image.new('RGB', (1511, 1132), (55, 115, 120)))
assert result == tidied, 'Cumulative cleanup must retain the latest measured paper outline'


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

# Neutral PMG holder scans (South Carolina 1872 $5, 2026-10-07): the
# previous blue-only surround gate rejected all four real paper edges.
def neutral_holder(paper=(232, 223, 185), label=True):
    img = holder(background=(238, 237, 234))
    draw = ImageDraw.Draw(img)
    draw.rectangle((0, 0, 1599, 280), fill=(238, 237, 234))
    if label:
        draw.rectangle((85, 55, 1540, 250), fill=(50, 75, 60))
        draw.rectangle((98, 68, 1527, 237), fill=(232, 232, 232))
        draw.text((110, 90), 'PMG - 66 EPQ', fill=(25, 25, 25))
    draw.polygon([(220, 300), (1400, 315), (1395, 855), (215, 840)], fill=paper)
    draw.polygon([(260, 345), (1360, 359), (1355, 810), (255, 796)],
                 fill=(45, 85, 65))
    return img


for angle in (0, 2, -2):
    img = neutral_holder().rotate(angle, resample=Image.Resampling.BICUBIC,
                                  fillcolor=(238, 237, 234))
    meta = {}
    with patch.object(stuffapp, '_trim_note_v2', side_effect=AssertionError('second crop')), \
            patch.object(stuffapp, '_trim_note_cv_cascade', side_effect=AssertionError('second crop')):
        output = stuffapp._trim_slabbed_note_image(encoded(img), meta=meta)
    result = Image.open(io.BytesIO(output))
    assert meta['engine'] == 'paper-boundary', meta
    assert abs(result.width - 1180) <= 8 and abs(result.height - 540) <= 8, result.size
    assert stuffapp._warm_paper_on_light_holder_quad(result) is None
    assert JpegImagePlugin.get_sampling(result) == 0
assert stuffapp._warm_paper_on_light_holder_quad(neutral_holder(label=False)) is None
assert stuffapp._warm_paper_on_light_holder_quad(neutral_holder(), expect_aspect=3.4) is None
# Even with a holder label, a saturated print surrounded by white paper
# must not be mistaken for the sheet's quiet cream edge.
assert stuffapp._warm_paper_on_light_holder_quad(neutral_holder(paper=(190, 65, 40))) is None
solid_bar = neutral_holder()
ImageDraw.Draw(solid_bar).rectangle((85, 55, 1540, 250), fill=(50, 75, 60))
assert stuffapp._warm_paper_on_light_holder_quad(solid_bar) is None

# A pale green PMG panel can carry text without any dark rectangular
# frame. Virginia 1862: the reverse is unprinted, and the front's paper
# rim is much narrower than the detector's old deep margin sample.
def pale_label_holder(blank=False, text=True):
    img = neutral_holder(label=False)
    draw = ImageDraw.Draw(img)
    draw.rectangle((85, 55, 1540, 250), fill=(226, 237, 227))
    if text:
        for x in (130, 540, 1100):
            for y in (85, 115, 145):
                draw.rectangle((x, y, x + 150, y + 8), fill=(35, 40, 35))
    paper_quad = [(220, 300), (1400, 315), (1395, 855), (215, 840)]
    draw.polygon(paper_quad, fill=(232, 223, 185))
    if blank:
        # Faint show-through does not supply a dense engraving anchor.
        draw.ellipse((600, 430, 950, 720), outline=(216, 207, 173), width=2)
    else:
        # Warm dark engraving reaches within three pixels of the rim;
        # the full paper outline must survive without an inward shave.
        draw.polygon([(224, 304), (1397, 319), (1392, 851), (219, 836)],
                     fill=(95, 85, 65))
    return img


for blank in (False, True):
    img = pale_label_holder(blank=blank)
    meta = {}
    with patch.object(stuffapp, '_trim_note_v2', side_effect=AssertionError('model fallback')), \
            patch.object(stuffapp, '_trim_note_cv_cascade', side_effect=AssertionError('ink fallback')):
        output = stuffapp._trim_slabbed_note_image(encoded(img), meta=meta)
    assert output and meta['engine'] == 'paper-boundary', (blank, meta)
    assert all(math.dist(a, b) < 5 for a, b in zip(meta['quad'],
               [(220, 300), (1400, 315), (1395, 855), (215, 840)])), meta
    assert all(abs(a - b) < 5 for a, b in
               zip(Image.open(io.BytesIO(output)).size, (1180, 540)))
assert stuffapp._warm_paper_on_light_holder_quad(pale_label_holder(text=False)) is None, \
    'A plain pale panel must not count as a grading label'

# Screenshot uploads with alpha are flattened to JPEG before detection.
# Exercise that saved-image format too, including chroma subsampling.
for quality in (80, 90, 95):
    jpeg = io.BytesIO()
    neutral_holder().save(jpeg, format='JPEG', quality=quality)
    meta = {}
    with patch.object(stuffapp, '_trim_note_v2', side_effect=AssertionError('fallback')), \
            patch.object(stuffapp, '_trim_note_cv_cascade', side_effect=AssertionError('fallback')):
        output = stuffapp._trim_slabbed_note_image(jpeg.getvalue(), meta=meta)
    assert meta['engine'] == 'paper-boundary', meta
    assert all(abs(a - b) <= 8 for a, b in
               zip(Image.open(io.BytesIO(output)).size, (1180, 540)))

# A seller's already-tight photo can retain only a thin black backdrop.
# Its paper occupies >90% of the frame, beyond the general holder area cap.
def tight_dark_scan(ink=(38, 100, 64), paper=(238, 237, 232), background=(22, 23, 22)):
    img = Image.new('RGB', (1280, 560), background)
    draw = ImageDraw.Draw(img)
    quad = [(18, 17), (1262, 14), (1259, 544), (16, 542)]
    draw.polygon(quad, fill=paper)
    draw.polygon([(36, 36), (1242, 33), (1239, 523), (35, 522)], fill=ink)
    # Dense dark engraving remains part of the note, not background.
    for x in range(70, 1210, 14):
        draw.line((x, 80, x, 480), fill=(180, 184, 142), width=2)
    return img, quad


for ink in ((38, 100, 64), (20, 20, 20)):
    photo, paper_quad = tight_dark_scan(ink)
    for fmt in ('PNG', 'WEBP', 'JPEG'):
        raw_tight = encoded(photo, fmt)
        meta = {}
        with patch.object(stuffapp, '_trim_note_v2', side_effect=AssertionError('model fallback')), \
                patch.object(stuffapp, '_trim_note_cv_cascade', side_effect=AssertionError('design fallback')):
            output = stuffapp._trim_slabbed_note_image(raw_tight, meta=meta)
        assert output and meta['engine'] == 'paper-on-dark-backdrop', (ink, fmt, meta)
        assert all(math.dist(a, b) < 3 for a, b in zip(meta['quad'], paper_quad)), meta
        crop = Image.open(io.BytesIO(output))
        assert abs(crop.width - 1244) <= 3 and abs(crop.height - 528) <= 3, crop.size
        # Each genuine white margin survives, including dark-note designs.
        for point in ((crop.width // 2, 5), (crop.width // 2, crop.height - 6),
                      (5, crop.height // 2), (crop.width - 6, crop.height // 2)):
            assert min(crop.getpixel(point)) > 180, (fmt, point, crop.getpixel(point))
        assert stuffapp._paper_on_dark_backdrop_quad(crop) is None, 'Never re-trim a finished paper outline'
        assert JpegImagePlugin.get_sampling(crop) == 0
        assert min(crop.getpixel((crop.width // 2, crop.height // 2))) < 120, 'Do not erase dark engraving'

photo, _ = tight_dark_scan()
assert stuffapp._paper_on_dark_backdrop_quad(photo, expect_aspect=1.5) is None
# A coloured design or printed black border on a full sheet is not a backdrop.
full_sheet = Image.new('RGB', (1280, 560), (238, 237, 232))
ImageDraw.Draw(full_sheet).rectangle((15, 15, 1265, 545), outline=(15, 15, 15), width=10)
assert stuffapp._paper_on_dark_backdrop_quad(full_sheet) is None
ImageDraw.Draw(full_sheet).rectangle((35, 35, 1245, 525), fill=(50, 100, 65))
assert stuffapp._paper_on_dark_backdrop_quad(full_sheet) is None
# Dark paper, a dark frame with a bright portrait, and gray backgrounds lack
# four independently supported pale paper margins on a near-black surround.
assert stuffapp._paper_on_dark_backdrop_quad(tight_dark_scan(paper=(110, 100, 80))[0]) is None
assert stuffapp._paper_on_dark_backdrop_quad(tight_dark_scan(background=(100, 100, 100))[0]) is None
portrait = Image.new('RGB', (1280, 560), (25, 25, 25))
ImageDraw.Draw(portrait).ellipse((50, 30, 1230, 530), fill=(230, 225, 210))
assert stuffapp._paper_on_dark_backdrop_quad(portrait) is None
# A sheet touching the photo edge has no evidence of backdrop on that side.
edge_cut = photo.crop((18, 0, photo.width, photo.height))
assert stuffapp._paper_on_dark_backdrop_quad(edge_cut) is None
one_gray_edge = photo.copy()
ImageDraw.Draw(one_gray_edge).rectangle((1263, 0, 1279, 559), fill=(100, 100, 100))
assert stuffapp._paper_on_dark_backdrop_quad(one_gray_edge) is None
# Full paper edges also suffice inside a dark holder; the holder/label may
# be clipped by the photograph while the whole sheet remains visible.
def clipped_dark_holder(ink=(35, 65, 85), background=(22, 23, 22), label=True, paper=True):
    img = Image.new('RGB', (1280, 1000), background)
    draw = ImageDraw.Draw(img)
    if label:
        draw.rectangle((-30, 100, 1300, 280), fill=(220, 232, 222))
        for x in (60, 480, 900):
            for y in (140, 170, 200):
                draw.rectangle((x, y, x + 190, y + 9), fill=(25, 35, 25))
    quad = [(26, 310), (1148, 308), (1149, 922), (27, 924)]
    if paper:
        # Transparent holder seam reflects light just OUTSIDE the top paper
        # edge. The crop must not move inward to evade this reflection.
        draw.polygon([(26, 305), (1148, 303), (1148, 307), (26, 309)], fill=(110, 110, 110))
        draw.polygon(quad, fill=(238, 237, 232))
        draw.polygon([(45, 329), (1129, 327), (1130, 903), (46, 905)], fill=ink)
        for x in range(65, 1110, 14):
            draw.line((x, 355, x, 875), fill=(180, 184, 170), width=2)
    return img, quad


for ink in ((35, 65, 85), (20, 20, 20)):
    for fmt in ('PNG', 'WEBP', 'JPEG'):
        # Clip both the sides and top of the holder's label, keeping every
        # paper edge. The label's shape is not the crop's authority.
        photo, quad = clipped_dark_holder(ink)
        photo = photo.crop((10, 180, 1240, 975))
        expected = [(x - 10, y - 180) for x, y in quad]
        meta = {}
        with patch.object(stuffapp, '_trim_note_v2', side_effect=AssertionError('model fallback')), \
                patch.object(stuffapp, '_trim_note_cv_cascade', side_effect=AssertionError('design fallback')):
            output = stuffapp._trim_slabbed_note_image(encoded(photo, fmt), expect_aspect=1.83, meta=meta)
        assert output and meta['engine'] == 'paper-on-dark-backdrop', (ink, fmt, meta)
        assert all(math.dist(a, b) < 3 for a, b in zip(meta['quad'], expected)), meta
        result = Image.open(io.BytesIO(output))
        assert abs(result.width - 1122) <= 3 and abs(result.height - 614) <= 3, result.size
        for point in ((result.width // 2, 5), (result.width // 2, result.height - 6),
                      (5, result.height // 2), (result.width - 6, result.height // 2)):
            assert min(result.getpixel(point)) > 180, (fmt, point, result.getpixel(point))
        assert stuffapp._paper_on_dark_backdrop_quad(result) is None
        assert JpegImagePlugin.get_sampling(result) == 0
        assert min(result.getpixel((result.width // 2, result.height // 2))) < 120

# Egypt 1945 PCGS: a thin reflective seam below the paper crosses the
# immediate backdrop probe. Its bounded farther backing is still black;
# do not move the complete paper edge inward to avoid the reflection.
seam_holder, seam_quad = clipped_dark_holder()
ImageDraw.Draw(seam_holder).rectangle((250, 928, 450, 934), fill=(115, 115, 115))
meta = {}
with patch.object(stuffapp, '_trim_note_v2', side_effect=AssertionError('model fallback')), \
        patch.object(stuffapp, '_trim_note_cv_cascade', side_effect=AssertionError('design fallback')):
    output = stuffapp._trim_slabbed_note_image(encoded(seam_holder), meta=meta)
assert output and meta['engine'] == 'paper-on-dark-backdrop', meta
assert all(math.dist(a, b) < 3 for a, b in zip(meta['quad'], seam_quad)), meta
assert all(abs(a - b) < 3 for a, b in zip(Image.open(io.BytesIO(output)).size, (1122, 614)))
assert stuffapp._paper_on_dark_backdrop_quad(Image.open(io.BytesIO(output))) is None
# A seam allowance never substitutes for label evidence or permits wider
# glare/gray backing. Both farther probes must pass independently.
no_label, _ = clipped_dark_holder(label=False)
ImageDraw.Draw(no_label).rectangle((250, 928, 450, 934), fill=(115, 115, 115))
assert stuffapp._paper_on_dark_backdrop_quad(no_label) is None
wide_seam, _ = clipped_dark_holder()
ImageDraw.Draw(wide_seam).rectangle((250, 928, 650, 934), fill=(115, 115, 115))
assert stuffapp._paper_on_dark_backdrop_quad(wide_seam) is None
deep_gray = seam_holder.copy()
ImageDraw.Draw(deep_gray).rectangle((250, 928, 450, 945), fill=(115, 115, 115))
assert stuffapp._paper_on_dark_backdrop_quad(deep_gray) is None
second_probe_gray = seam_holder.copy()
ImageDraw.Draw(second_probe_gray).rectangle((250, 937, 450, 941), fill=(115, 115, 115))
assert stuffapp._paper_on_dark_backdrop_quad(second_probe_gray) is None
# The normal near-probe path may accept a tight scan; the seam exception
# must reject it when either farther probe would leave the actual photograph.
assert stuffapp._paper_on_dark_backdrop_quad(clipped_dark_holder()[0].crop((0, 0, 1280, 933))) is not None
assert stuffapp._paper_on_dark_backdrop_quad(seam_holder.crop((0, 0, 1280, 933))) is None

broad, _ = clipped_dark_holder()
assert stuffapp._paper_on_dark_backdrop_quad(broad, expect_aspect=3.4) is None
assert stuffapp._paper_on_dark_backdrop_quad(broad.crop((30, 0, 1280, 1000))) is None, 'Never invent a clipped paper edge'
assert stuffapp._paper_on_dark_backdrop_quad(clipped_dark_holder(paper=False)[0]) is None, 'A clipped label is not the note'
assert stuffapp._paper_on_dark_backdrop_quad(clipped_dark_holder(background=(110, 110, 110))[0]) is None
assert stuffapp._paper_on_dark_backdrop_quad(clipped_dark_holder(background=(245, 245, 242))[0]) is None
blank_bar, _ = clipped_dark_holder(paper=False, label=False)
ImageDraw.Draw(blank_bar).rectangle((0, 100, 1279, 280), fill=(220, 232, 222))
assert stuffapp._paper_on_dark_backdrop_quad(blank_bar) is None
blank_label, _ = clipped_dark_holder()
ImageDraw.Draw(blank_label).rectangle((0, 100, 1279, 280), fill=(220, 232, 222))
assert stuffapp._paper_on_dark_backdrop_quad(blank_label) is None, 'A blank panel is not a printed holder label'
fragments, _ = clipped_dark_holder(label=False)
fragment_draw = ImageDraw.Draw(fragments)
for x in (80, 480, 900):
    fragment_draw.text((x, 220), 'Caption fragments', fill=(220, 232, 222))
assert stuffapp._paper_on_dark_backdrop_quad(fragments) is None
# A large pale inner panel in a dark printed note is indistinguishable
# from a separate sheet without the independent holder label.
assert stuffapp._paper_on_dark_backdrop_quad(clipped_dark_holder(label=False)[0]) is None
inner_panel = Image.new('RGB', (1400, 750), (22, 23, 22))
ImageDraw.Draw(inner_panel).rectangle((180, 120, 1220, 630), fill=(238, 237, 232))
assert stuffapp._paper_on_dark_backdrop_quad(inner_panel) is None

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
raw = encoded(neutral_holder())
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
    saved = Image.open(os.path.join(stuffapp.UPLOAD_FOLDER, name))
    assert abs(saved.width - 1180) <= 8 and abs(saved.height - 540) <= 8, saved.size
    images = stuffapp._load_vision_images([(source, 'holder')])
    assert images and images[0]['media_type'] == 'image/webp'

# The same upload path retains originals and exact geometry for both tight
# scans and broader clipped holders; Check can still read the original label.
for record_id, photo, expected_size in (
        ('tight-quality', tight_dark_scan()[0], (1244, 528)),
        ('clipped-quality', clipped_dark_holder()[0].crop((10, 180, 1240, 975)), (1122, 614))):
    with stuffapp.app.app_context():
        db = stuffapp.get_db()
        db.execute("INSERT INTO banknotes (id) VALUES (?)", (record_id,))
        db.commit()
    original = encoded(photo)
    response = client.post('/banknotes/' + record_id + '/upload-image', data={
        'field': 'image_1', 'image': (io.BytesIO(original), 'holder-original.webp'),
    })
    assert response.status_code == 200, response.get_json()
    with stuffapp.app.app_context():
        db = stuffapp.get_db()
        name = db.execute("SELECT image_1 FROM banknotes WHERE id=?", (record_id,)).fetchone()[0]
        source = stuffapp._banknote_vision_source(name, db)
        assert source != name and source.endswith('.webp')
        with open(os.path.join(stuffapp.UPLOAD_FOLDER, source), 'rb') as f:
            assert f.read() == original, 'Keep every original pixel and paper margin recoverable'
        mapping = db.execute('SELECT quad FROM trimmed_image_sources WHERE trimmed=?', (name,)).fetchone()
        import json
        assert len(json.loads(mapping['quad'])) == 4
        saved = Image.open(os.path.join(stuffapp.UPLOAD_FOLDER, name))
        assert all(abs(actual - expected) <= 3 for actual, expected in zip(saved.size, expected_size)), saved.size

# Market acquisitions use the same source-preservation rule for notes.
def classify_market_front(photos):
    return dict(
        photos=[dict(id=photo['id'], side='front', confidence='high',
                     complete_note=True, same_note=True, reason='Synthetic complete front')
                for photo in photos],
        front=photos[0]['id'], back=None, pair_verified=False, pair_reason='')

with patch.object(stuffapp, '_market_fetch_image', return_value=(raw, 'webp')), \
        patch.object(stuffapp, '_market_page_image_urls', return_value=['https://dealer.example/front.webp']), \
        patch.object(stuffapp, '_classify_banknote_listing_photos', side_effect=classify_market_front):
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
