"""Tests for the slabbed-banknote trimmer (vision-primary pipeline).

The vision model is the trimmer's only detector: it outlines the
engraved area, which is perspective-warped level and cropped with a
uniform paper margin; backdrop swept into the margin is clamped per
side. These tests fake the model's quad and assert the geometry that
follows from it. Without a quad (no API key, nothing found) the
trimmer must leave the image untouched — no heuristic guessing; the
old CV cascade was deleted 2026-08-16.
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


PAPER = (228, 219, 188)     # warm aged paper
GREEN_PAPER = (215, 224, 205)  # cool JIM-style paper
INK = (60, 55, 70)
HOLDER = (24, 24, 26)       # dark PMG holder


def _lerp2(quad, u, v):
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = quad
    x = (1 - u) * (1 - v) * ax + u * (1 - v) * bx + u * v * cx + (1 - u) * v * dx
    y = (1 - u) * (1 - v) * ay + u * (1 - v) * by + u * v * cy + (1 - u) * v * dy
    return x, y


def _draw_note(draw, quad, paper=PAPER):
    """Paper quad with a dark design inside it (border + line work).
    Returns the design quad (the outline the vision model would draw),
    at 7% in from the paper edge."""
    draw.polygon(quad, fill=paper)
    m = 0.07
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


def _fake_quad(quad):
    """Monkeypatch factory: return `quad` on the first call, None after
    (so _finish_ai_crop's second look skips instead of re-applying
    full-scene coordinates to the already-cropped image)."""
    calls = {'n': 0}

    def fake(im):
        calls['n'] += 1
        return quad if calls['n'] == 1 else None
    return fake


def _design_insets(img, ring=8):
    """Fractional inset of the printed area from each output edge."""
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
    'without a vision quad the trimmer must not touch the image'
print('NO-MODEL NO-OP ASSERTIONS PASSED')


# --- Level slab shot: engraved area + margins, squared ---------------------
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
design = _draw_note(draw, [(300, 300), (1340, 300), (1340, 880), (300, 880)])
stuffapp._ai_note_quad = _fake_quad(design)
trimmed = _trim_to_image(img)
assert trimmed is not None, 'level slab shot was not trimmed'
qw = design[1][0] - design[0][0]
qh = design[3][1] - design[0][1]
got = trimmed.size[0] / float(trimmed.size[1])
assert abs(got - qw / qh) / (qw / qh) < 0.08, \
    f'aspect off: got {got:.3f}, want {qw / qh:.3f}'
insets = _design_insets(trimmed)
assert all(f >= 0.01 for f in insets), f'design touches edge: {insets}'
assert all(f <= 0.12 for f in insets), f'margins too wide: {insets}'
assert stuffapp._note_paper_fraction(trimmed) > 0.6, 'output not mostly paper'
print('LEVEL SLAB ASSERTIONS PASSED')


# --- Keystoned shot: the quad is warped level ------------------------------
# The note photographed at an angle: the model's tilted quad must come
# out square-on — that IS the "align horizontally and vertically"
# contract. Aspect follows the quad's average side lengths.
img = Image.new('RGB', (1600, 1200), HOLDER)
draw = ImageDraw.Draw(img)
design = _draw_note(draw, [(340, 330), (1290, 380), (1260, 930), (370, 860)])
stuffapp._ai_note_quad = _fake_quad(design)
trimmed = _trim_to_image(img)
assert trimmed is not None, 'keystoned slab shot was not trimmed'
davg_w = (math.hypot(design[1][0] - design[0][0], design[1][1] - design[0][1])
          + math.hypot(design[2][0] - design[3][0], design[2][1] - design[3][1])) / 2
davg_h = (math.hypot(design[3][0] - design[0][0], design[3][1] - design[0][1])
          + math.hypot(design[2][0] - design[1][0], design[2][1] - design[1][1])) / 2
want = davg_w / davg_h
got = trimmed.size[0] / float(trimmed.size[1])
assert abs(got - want) / want < 0.08, \
    f'keystone aspect off: got {got:.3f}, want {want:.3f}'
insets = _design_insets(trimmed)
assert all(f >= 0.005 for f in insets), f'design touches edge: {insets}'
assert stuffapp._note_paper_fraction(trimmed) > 0.55, 'output not mostly paper'
print('KEYSTONE ASSERTIONS PASSED')


# --- Margin clamp: cool paper kept, dark holder trimmed --------------------
# The clamp's paper reference is sampled from the note's own margin ring,
# so greenish JIM paper is not shaved as backdrop; and a mostly-dark edge
# band is holder plastic, not engraving, so it IS trimmed.
img = Image.new('RGB', (1000, 500), GREEN_PAPER)
draw = ImageDraw.Draw(img)
draw.rectangle([0, 0, 59, 499], fill=(28, 28, 30))       # dark holder band, left
draw.rectangle([120, 60, 940, 440], outline=INK, width=8)  # design
for gx in range(140, 920, 20):
    draw.line([(gx, 80), (gx, 420)], fill=INK, width=2)
inner = (120, 60, 940, 440)
out = stuffapp._clamp_ai_margins(img, inner)
ow, oh = out.size
assert ow <= 1000 - 55, f'dark holder band kept: {out.size}'
assert oh == 500, f'green paper margins shaved vertically: {out.size}'
opx = out.convert('RGB').load()
c = opx[5, 250]
assert max(c) >= 95, f'left edge still holder-dark: {c}'
print('MARGIN-CLAMP (cool paper / dark holder) ASSERTIONS PASSED')


# --- Margin clamp: shadowed bottom margin is paper, not backdrop -----------
# In a holder photo the note's bottom edge sits in shadow: darker than
# the reference paper but the same hue. The clamp must keep it (the JIM
# notes lost their bottom margins to a fixed color-distance test) and
# may never eat more than a sliver into the model's rectangle.
SHADOW = tuple(int(v * 0.55) for v in PAPER)
img = Image.new('RGB', (1000, 560), PAPER)
draw = ImageDraw.Draw(img)
draw.rectangle([120, 60, 940, 440], outline=INK, width=8)   # design
for gx in range(140, 920, 20):
    draw.line([(gx, 80), (gx, 420)], fill=INK, width=2)
draw.rectangle([0, 470, 999, 509], fill=SHADOW)             # shadowed margin
draw.rectangle([0, 510, 999, 559], fill=(22, 22, 24))       # holder below
inner = (120, 60, 940, 440)
out = stuffapp._clamp_ai_margins(img, inner)
ow, oh = out.size
assert oh >= 505, f'shadowed bottom margin eaten: {out.size}'
assert oh <= 520, f'holder band below shadow kept: {out.size}'
print('MARGIN-CLAMP (shadowed bottom) ASSERTIONS PASSED')


# --- Homography sanity ----------------------------------------------------
# The PERSPECTIVE coefficients must map each output corner exactly onto
# its source-quad corner (PIL samples source = H(output)).
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

print('ALL NOTE-TRIM ASSERTIONS PASSED')
