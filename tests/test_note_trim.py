"""Tests for the slabbed-banknote trimmer (vision-only pipeline).

The vision model outlines TWO rectangles in one call: the engraved
area (alignment) and the note's physical paper edge (margins). The
design quad is warped level; the paper quad is mapped through the
same homography and bounds the crop per side. There is no pixel
classification anywhere — shadows and backgrounds are irrelevant by
construction, and without a model answer the image is left untouched.
Run: .venv/bin/python tests/test_note_trim.py
"""
import io
import math
import os
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(REPO)
sys.path.insert(0, REPO)
os.environ.setdefault('DATA_DIR', tempfile.mkdtemp(prefix='stuffapp-trim-'))
# The no-quad path must be deterministic in tests: never let a real
# key turn these synthetic scenes into live model calls.
os.environ.pop('ANTHROPIC_API_KEY', None)

from PIL import Image, ImageDraw

import app as stuffapp


PAPER = (228, 219, 188)
INK = (60, 55, 70)
HOLDER = (24, 24, 26)


def _lerp2(quad, u, v):
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = quad
    x = (1 - u) * (1 - v) * ax + u * (1 - v) * bx + u * v * cx + (1 - u) * v * dx
    y = (1 - u) * (1 - v) * ay + u * (1 - v) * by + u * v * cy + (1 - u) * v * dy
    return x, y


def _draw_note(draw, quad, paper=PAPER, m=0.07):
    """Paper quad with a dark design inside it; returns the design quad
    (the outline the vision model would draw), m in from the paper."""
    draw.polygon(quad, fill=paper)
    design = [_lerp2(quad, m, m), _lerp2(quad, 1 - m, m),
              _lerp2(quad, 1 - m, 1 - m), _lerp2(quad, m, 1 - m)]
    draw.polygon(design, outline=INK, width=4)
    u = m + 0.02
    while u < 1 - m - 0.02:
        draw.line([_lerp2(quad, u, m + 0.02), _lerp2(quad, u, 1 - m - 0.02)],
                  fill=INK, width=2)
        u += 0.015
    return tuple((float(x), float(y)) for x, y in design)


def _trim_to_image(img):
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=92)
    out = stuffapp._trim_slabbed_note_image(buf.getvalue())
    return Image.open(io.BytesIO(out)) if out else None


def _fake_quads(design, paper=None):
    """Monkeypatch factory: (design, paper) on the first call, None
    after — the second-look refine skips instead of re-applying
    full-scene coordinates to the cropped image."""
    calls = {'n': 0}

    def fake(im, **kw):
        calls['n'] += 1
        return (design, paper) if calls['n'] == 1 else None
    return fake


def _paper_frac(img):
    """Test-side check that an output is mostly warm paper (the app
    itself no longer classifies pixels — that is the point)."""
    small = img.convert('RGB').copy()
    small.thumbnail((80, 80))
    px = small.load()
    w, h = small.size
    n = sum(1 for y in range(h) for x in range(w)
            if max(px[x, y][:3]) > 140
            and max(px[x, y][:3]) - min(px[x, y][:3]) < 70)
    return n / float(w * h or 1)


def _design_insets(img, ring=8):
    g = img.convert('L')
    px = g.load()
    w, h = g.size
    rows = [sum(1 for x in range(ring, w - ring, 2) if px[x, y] < 110)
            / ((w - 2 * ring) / 2) for y in range(ring, h - ring)]
    cols = [sum(1 for y in range(ring, h - ring, 2) if px[x, y] < 110)
            / ((h - 2 * ring) / 2) for x in range(ring, w - ring)]
    ink_rows = [i for i, f in enumerate(rows) if f > 0.08]
    ink_cols = [i for i, f in enumerate(cols) if f > 0.08]
    assert ink_rows and ink_cols, 'no design found in output'
    return (min(ink_cols) / w, min(ink_rows) / h,
            (len(cols) - 1 - max(ink_cols)) / w,
            (len(rows) - 1 - max(ink_rows)) / h)


# --- No model, no guessing: the image is left untouched --------------------
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
_draw_note(draw, [(300, 300), (1300, 306), (1296, 900), (304, 894)])
assert _trim_to_image(img) is None, \
    'without a vision answer the trimmer must not touch the image'
print('NO-MODEL NO-OP ASSERTIONS PASSED')


# --- Level slab shot, paper quad given: margins end at the paper edge ------
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
paper_quad = [(300, 300), (1340, 300), (1340, 880), (300, 880)]
design = _draw_note(draw, paper_quad)
stuffapp._ai_note_quad = _fake_quads(design, tuple(map(tuple, paper_quad)))
trimmed = _trim_to_image(img)
assert trimmed is not None, 'level slab shot was not trimmed'
got = trimmed.size[0] / float(trimmed.size[1])
want = 1040.0 / 580.0     # the paper's aspect: margins bounded by paper edge
assert abs(got - want) / want < 0.08, \
    f'aspect off: got {got:.3f}, want {want:.3f}'
insets = _design_insets(trimmed)
assert all(f >= 0.01 for f in insets), f'design touches edge: {insets}'
assert all(f <= 0.12 for f in insets), f'margins too wide: {insets}'
assert _paper_frac(trimmed) > 0.8, 'holder left in the crop'
print('LEVEL SLAB (paper-bounded margins) ASSERTIONS PASSED')


# --- Keystoned shot: the design quad is warped level -----------------------
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
paper_quad = [(320, 310), (1310, 400), (1280, 950), (350, 840)]
design = _draw_note(draw, paper_quad)
stuffapp._ai_note_quad = _fake_quads(design, tuple(map(tuple, paper_quad)))
trimmed = _trim_to_image(img)
assert trimmed is not None, 'keystoned slab shot was not trimmed'
pq = paper_quad
davg_w = (math.hypot(pq[1][0] - pq[0][0], pq[1][1] - pq[0][1])
          + math.hypot(pq[2][0] - pq[3][0], pq[2][1] - pq[3][1])) / 2
davg_h = (math.hypot(pq[3][0] - pq[0][0], pq[3][1] - pq[0][1])
          + math.hypot(pq[2][0] - pq[1][0], pq[2][1] - pq[1][1])) / 2
want = davg_w / davg_h
got = trimmed.size[0] / float(trimmed.size[1])
assert abs(got - want) / want < 0.12, \
    f'keystone aspect off: got {got:.3f}, want {want:.3f}'
insets = _design_insets(trimmed)
assert all(f >= 0.005 for f in insets), f'design touches edge: {insets}'
assert _paper_frac(trimmed) > 0.6, 'output not mostly paper'
print('KEYSTONE ASSERTIONS PASSED')


# --- Thin bottom margin: crop ends at the paper edge, not the 7% frame -----
# The paper quad's bottom sits 2% below the design; the top margin is a
# full 7%. The output must be asymmetric to match the REAL margins —
# no color/shadow reasoning involved.
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
draw.rectangle([300, 300, 1340, 892], fill=PAPER)   # paper: bottom margin thin
design = ((373, 341), (1267, 341), (1267, 880), (373, 880))
draw.rectangle([373, 341, 1267, 880], outline=INK, width=4)
for gx in range(395, 1250, 20):
    draw.line([(gx, 361), (gx, 860)], fill=INK, width=2)
paper_quad = ((300, 300), (1340, 300), (1340, 892), (300, 892))
stuffapp._ai_note_quad = _fake_quads(design, paper_quad)
trimmed = _trim_to_image(img)
assert trimmed is not None, 'thin-margin shot was not trimmed'
left, top, right, bottom = _design_insets(trimmed)
assert bottom < top, \
    f'bottom margin should be thinner than top: top {top:.3f}, bottom {bottom:.3f}'
assert bottom >= 0.004, f'floor margin missing at bottom: {bottom:.3f}'
assert _paper_frac(trimmed) > 0.8, 'holder included beyond the paper edge'
print('THIN-MARGIN (paper-bounded) ASSERTIONS PASSED')


# --- No paper quad: the fixed context frame stands as the margin -----------
img = Image.new('RGB', (1600, 1200), PAPER)   # borderless: same-tone backdrop
draw = ImageDraw.Draw(img)
design = ((373, 341), (1267, 341), (1267, 880), (373, 880))
draw.rectangle(list(design[0] + design[2]), outline=INK, width=4)
for gx in range(395, 1250, 20):
    draw.line([(gx, 361), (gx, 860)], fill=INK, width=2)
stuffapp._ai_note_quad = _fake_quads(design, None)
trimmed = _trim_to_image(img)
assert trimmed is not None, 'no-paper-quad shot was not trimmed'
insets = _design_insets(trimmed)
assert all(0.03 <= f <= 0.10 for f in insets), \
    f'context-frame margins off: {insets}'
print('NO-PAPER-QUAD (context frame) ASSERTIONS PASSED')


# --- Bad paper outline: rejected, design frame stands ----------------------
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
paper_quad = [(300, 300), (1340, 300), (1340, 880), (300, 880)]
design = _draw_note(draw, paper_quad)
bogus_paper = ((500, 400), (900, 400), (900, 700), (500, 700))  # inside design
stuffapp._ai_note_quad = _fake_quads(design, bogus_paper)
trimmed = _trim_to_image(img)
assert trimmed is not None, 'bad-paper shot was not trimmed at all'
# The fallback is the design quad + 10% frame — verify by dimensions
# (in this synthetic scene the frame band lands partly on dark holder,
# which an ink-based inset measure cannot tell apart from design).
dw = design[1][0] - design[0][0]
dh = design[3][1] - design[0][1]
assert abs(trimmed.size[0] - dw * 1.2) <= 4 and \
    abs(trimmed.size[1] - dh * 1.2) <= 4, \
    f'design-frame fallback dims off: {trimmed.size} vs {(dw * 1.2, dh * 1.2)}'
print('BAD-PAPER-OUTLINE (fallback) ASSERTIONS PASSED')


# --- Paper outline collapsed on one axis: ask again -----------------------
# The real 2026-08-17 failure: on the back of a PMG-slabbed 2-Peso note
# the model drew paper_corners along the printed border top and bottom
# while keeping real left/right margins, so the crop came out 2.71:1
# for a 2.43:1 sheet — the note's own margins shaved off. The trimmer
# must notice the collapsed axis and re-ask instead of shipping it.
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
paper_quad = ((300, 300), (1340, 300), (1340, 880), (300, 880))
design = _draw_note(draw, paper_quad)
# Just outside the design vertically — a couple of pixels, the way a
# real answer traced onto the printed border looks: it clears the
# "design must sit inside the paper" test, and is still no margin.
flat = ((design[0][0] - 30, design[0][1] - 2),
        (design[1][0] + 30, design[1][1] - 2),
        (design[2][0] + 30, design[2][1] + 2),
        (design[3][0] - 30, design[3][1] + 2))

answers = {'n': 0}


def _collapsing_then_right(im, retry_collapsed=False, **kw):
    """First answer collapses top/bottom onto the border; the re-ask
    (and only the re-ask) returns the true sheet edge."""
    answers['n'] += 1
    if answers['n'] == 1:
        assert not retry_collapsed, 'first ask must not carry the retry hint'
        return design, flat
    if answers['n'] == 2:
        assert retry_collapsed, 'the second ask must say the outline collapsed'
        return design, tuple(map(tuple, paper_quad))
    return None            # no third-look refine in this test


stuffapp._ai_note_quad = _collapsing_then_right
trimmed = _trim_to_image(img)
assert trimmed is not None, 'collapsed-outline shot was not trimmed'
assert answers['n'] >= 2, 'the collapsed outline was accepted without a re-ask'
got = trimmed.size[0] / float(trimmed.size[1])
want = 1040.0 / 580.0
assert abs(got - want) / want < 0.08, \
    f'collapsed-outline aspect off: got {got:.3f}, want {want:.3f}'
insets = _design_insets(trimmed)
assert all(f >= 0.01 for f in insets), \
    f'margins still shaved after the re-ask: {insets}'
print('COLLAPSED-PAPER-OUTLINE (re-ask) ASSERTIONS PASSED')


# --- Collapsed twice: the design frame stands, never a shaved sheet --------
answers2 = {'n': 0}


def _always_collapsing(im, retry_collapsed=False, **kw):
    answers2['n'] += 1
    return (design, flat) if answers2['n'] <= 2 else None


stuffapp._ai_note_quad = _always_collapsing
trimmed = _trim_to_image(img)
assert trimmed is not None, 'twice-collapsed shot was not trimmed'
dw = design[1][0] - design[0][0]
dh = design[3][1] - design[0][1]
assert abs(trimmed.size[0] - dw * 1.2) <= 4 and \
    abs(trimmed.size[1] - dh * 1.2) <= 4, \
    f'expected the design frame, got {trimmed.size}'
print('TWICE-COLLAPSED (design frame) ASSERTIONS PASSED')


# --- A second look may tighten, but may not restretch the note ------------
# 1179x459 -> 1165x430 was the shipped regression: 2.57 -> 2.71, a 5.4%
# aspect move that is a margin being eaten, not a holder being trimmed.
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
paper_quad = ((240, 300), (1420, 300), (1420, 900), (240, 900))
design = _draw_note(draw, paper_quad)
shorter = ((paper_quad[0][0], paper_quad[0][1] + 60),
           (paper_quad[1][0], paper_quad[1][1] + 60),
           (paper_quad[2][0], paper_quad[2][1] - 60),
           (paper_quad[3][0], paper_quad[3][1] - 60))

looks = {'n': 0}


def _refine_restretches(im, retry_collapsed=False, **kw):
    looks['n'] += 1
    if looks['n'] == 1:
        return design, tuple(map(tuple, paper_quad))
    if looks['n'] == 2:                      # the second look, on the crop
        w2, h2 = im.size
        inset = ((6.0, 70.0), (w2 - 6.0, 70.0),
                 (w2 - 6.0, h2 - 70.0), (6.0, h2 - 70.0))
        return inset, inset
    return None


stuffapp._ai_note_quad = _refine_restretches
trimmed = _trim_to_image(img)
assert trimmed is not None, 'refine-guard shot was not trimmed'
got = trimmed.size[0] / float(trimmed.size[1])
want = 1180.0 / 600.0
assert abs(got - want) / want < 0.08, \
    f'a restretching second look was applied: got {got:.3f}, want {want:.3f}'
print('SECOND-LOOK ASPECT GUARD ASSERTIONS PASSED')


# --- Catalog ratio: a margin-shaving outline is caught by physics ----------
# The guard _margins_collapsed cannot catch: the model shaves MOST of
# the top/bottom margin (thin-but-nonzero survives the collapse test),
# giving a 2.18:1 crop of a 1.79:1 sheet. With the record's catalog
# dimensions known, the ratio itself convicts the outline; the re-ask
# (told the expected ratio) returns the true sheet edge.
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
paper_quad = ((300, 300), (1340, 300), (1340, 880), (300, 880))
design = _draw_note(draw, paper_quad)
# margins mostly (not entirely) eaten top and bottom, kept left/right
shaved = ((285, 330), (1355, 330), (1355, 850), (285, 850))
EXPECT = 1040.0 / 580.0

asked = {'n': 0, 'retry_seen': False}


def _shaved_then_true(im, retry_collapsed=False, expect_aspect=None):
    asked['n'] += 1
    assert expect_aspect is not None, 'catalog ratio was not threaded through'
    if asked['n'] == 1:
        return design, shaved
    if asked['n'] == 2:
        asked['retry_seen'] = retry_collapsed
        return design, paper_quad
    return None


def _trim_expect(img, expect):
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=92)
    out = stuffapp._trim_slabbed_note_image(buf.getvalue(),
                                            expect_aspect=expect)
    return Image.open(io.BytesIO(out)) if out else None


stuffapp._ai_note_quad = _shaved_then_true
trimmed = _trim_expect(img, EXPECT)
assert trimmed is not None, 'ratio-guard shot was not trimmed'
assert asked['n'] >= 2 and asked['retry_seen'], \
    'the off-ratio outline was accepted without a re-ask'
got = trimmed.size[0] / float(trimmed.size[1])
assert abs(got - EXPECT) / EXPECT < 0.06, \
    f'ratio-guard aspect off: got {got:.3f}, want {EXPECT:.3f}'
insets = _design_insets(trimmed)
assert all(f >= 0.01 for f in insets), \
    f'margins still shaved with the catalog ratio known: {insets}'
print('CATALOG-RATIO GUARD (re-ask) ASSERTIONS PASSED')


# --- Catalog ratio: shaved twice -> the design frame stands ---------------
asked2 = {'n': 0}


def _always_shaved(im, retry_collapsed=False, expect_aspect=None):
    asked2['n'] += 1
    return (design, shaved) if asked2['n'] <= 2 else None


stuffapp._ai_note_quad = _always_shaved
trimmed = _trim_expect(img, EXPECT)
assert trimmed is not None, 'twice-shaved shot was not trimmed'
dw = design[1][0] - design[0][0]
dh = design[3][1] - design[0][1]
assert abs(trimmed.size[0] - dw * 1.2) <= 4 and \
    abs(trimmed.size[1] - dh * 1.2) <= 4, \
    f'expected the design frame, got {trimmed.size}'
print('CATALOG-RATIO TWICE-SHAVED (design frame) ASSERTIONS PASSED')


# --- Catalog ratio: refine may only move the aspect toward the sheet's ----
looks2 = {'n': 0}


def _refine_away_from_catalog(im, retry_collapsed=False, expect_aspect=None):
    looks2['n'] += 1
    if looks2['n'] == 1:
        return design, paper_quad             # correct 1.79:1 crop
    if looks2['n'] == 2:                      # second look shaves again
        w2, h2 = im.size
        inset = ((6.0, 40.0), (w2 - 6.0, 40.0),
                 (w2 - 6.0, h2 - 40.0), (6.0, h2 - 40.0))
        return inset, inset
    return None


stuffapp._ai_note_quad = _refine_away_from_catalog
trimmed = _trim_expect(img, EXPECT)
assert trimmed is not None, 'refine-away shot was not trimmed'
got = trimmed.size[0] / float(trimmed.size[1])
assert abs(got - EXPECT) / EXPECT < 0.06, \
    f'refine moved the aspect away from catalog: got {got:.3f}'
print('CATALOG-RATIO REFINE GUARD ASSERTIONS PASSED')


# --- Edge QA: overshoot slivers are shaved, clamped, shrink-only ----------
# The 2026-08-17 front-of-note failure inverted: a paper outline that
# OVERSHOT the sheet leaves backdrop wedges in the warp, and no aspect
# guard can see it — the ratio can be perfect. The QA pass shaves what
# the model reports per side, clamped to 3% so a hallucinated answer
# can only nibble.
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
paper_quad = ((300, 300), (1340, 300), (1340, 880), (300, 880))
design = _draw_note(draw, paper_quad)
# outline overshoots the sheet: 24px of holder on the left, 18 below
over = ((276, 300), (1340, 300), (1340, 898), (276, 898))
stuffapp._ai_note_quad = _fake_quads(design, over)

reported = {}


def _fake_qa(crop):
    w2, h2 = crop.size
    reported['size'] = (w2, h2)
    return {'left': 24.0, 'top': 300.0, 'right': 0.0, 'bottom': 18.0}


_real_qa = stuffapp._edge_qa_sides
stuffapp._edge_qa_sides = _fake_qa
trimmed = _trim_to_image(img)
stuffapp._edge_qa_sides = _real_qa
assert trimmed is not None, 'edge-QA shot was not trimmed'
assert reported, 'edge QA pass never ran'
w0, h0 = reported['size']
# left/bottom shaved as reported; the absurd 300px top claim clamped to 3%
assert trimmed.size[0] == w0 - 24, \
    f'left sliver not shaved: {trimmed.size[0]} vs {w0 - 24}'
assert trimmed.size[1] == h0 - 18 - int(round(0.03 * h0)), \
    f'top clamp / bottom shave wrong: {trimmed.size[1]}'
assert _paper_frac(trimmed) > 0.9, 'backdrop sliver survived the QA pass'
print('EDGE-QA (sliver shave, clamped) ASSERTIONS PASSED')


# --- Homography sanity ----------------------------------------------------
quad = ((10.0, 20.0), (410.0, 44.0), (400.0, 260.0), (18.0, 240.0))
W, H = 400, 220
c = stuffapp._perspective_coeffs(quad, W, H)
assert c is not None
for (dx, dy), (sx, sy) in zip(((0, 0), (W, 0), (W, H), (0, H)), quad):
    den = c[6] * dx + c[7] * dy + 1.0
    mx = (c[0] * dx + c[1] * dy + c[2]) / den
    my = (c[3] * dx + c[4] * dy + c[5]) / den
    assert abs(mx - sx) < 1e-6 and abs(my - sy) < 1e-6, \
        (dx, dy, mx, my, sx, sy)
print('HOMOGRAPHY ASSERTIONS PASSED')


# --- Round-trip: paper corners land where the inverse mapping says ---------
coeffs = stuffapp._perspective_coeffs(quad, W, H)
back = stuffapp._map_source_points_to_output(coeffs, quad)
for (gx, gy), (ex, ey) in zip(back, ((0, 0), (W, 0), (W, H), (0, H))):
    assert abs(gx - ex) < 1e-4 and abs(gy - ey) < 1e-4, (gx, gy, ex, ey)
print('INVERSE-MAPPING ASSERTIONS PASSED')

print('ALL NOTE-TRIM ASSERTIONS PASSED')
