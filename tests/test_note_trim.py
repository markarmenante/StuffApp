"""Perspective-rectification tests for the slabbed-banknote trimmer.

Synthetic slab shots: a keystoned note photographed at an angle must
come out square-on — level edges, note filling the frame edge to edge,
aspect ratio matching the physical note, no dark holder wedges left in
the corners. A level shot must still trim via the classic no-warp path.
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

from PIL import Image, ImageDraw

import app as stuffapp


PAPER = (228, 219, 188)     # warm aged paper
INK = (60, 55, 70)


def _draw_note(draw, quad, label_band=None):
    """Paper quad with a dark design inside it (border + line work)."""
    draw.polygon(quad, fill=PAPER)

    def lerp2(u, v):
        (ax, ay), (bx, by), (cx, cy), (dx, dy) = quad
        x = (1 - u) * (1 - v) * ax + u * (1 - v) * bx \
            + u * v * cx + (1 - u) * v * dx
        y = (1 - u) * (1 - v) * ay + u * (1 - v) * by \
            + u * v * cy + (1 - u) * v * dy
        return x, y

    # Design border at 7% in from the paper edge, then dense line work
    # so the design reads as one solid textured component.
    m = 0.07
    border = [lerp2(m, m), lerp2(1 - m, m), lerp2(1 - m, 1 - m),
              lerp2(m, 1 - m)]
    draw.polygon(border, outline=INK, width=4)
    u = m + 0.02
    while u < 1 - m - 0.02:
        draw.line([lerp2(u, m + 0.02), lerp2(u, 1 - m - 0.02)],
                  fill=INK, width=2)
        u += 0.015
    if label_band:
        draw.rectangle(label_band, fill=(240, 240, 240))
        for i in range(6):
            x0 = label_band[0] + 20 + i * 60
            draw.line([(x0, label_band[1] + 8), (x0 + 40, label_band[1] + 8)],
                      fill=(30, 30, 30), width=3)


def _trim_to_image(img):
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=92)
    out = stuffapp._trim_slabbed_note_image(buf.getvalue())
    return Image.open(io.BytesIO(out)) if out else None


def _quad_aspect(quad):
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = quad
    top = math.hypot(bx - ax, by - ay)
    bottom = math.hypot(cx - dx, cy - dy)
    left = math.hypot(dx - ax, dy - ay)
    right = math.hypot(cx - bx, cy - by)
    return ((top + bottom) / 2.0) / ((left + right) / 2.0)


def _corner_luma(img, inset=8):
    w, h = img.size
    px = img.load()
    out = []
    for x, y in ((inset, inset), (w - 1 - inset, inset),
                 (inset, h - 1 - inset), (w - 1 - inset, h - 1 - inset)):
        p = px[x, y]
        out.append((p[0] + p[1] + p[2]) // 3)
    return out


def _holder_fraction(img, thresh=45, band=6):
    """Fraction of near-black pixels in the outer border band — that's
    where leftover holder plastic (or an uncorrected keystone wedge)
    lives. The design's own ink sits 7% inside the paper edge, so a
    clean rectification leaves this band pure paper."""
    g = img.convert('L')
    px = g.load()
    w, h = g.size
    hit = n = 0
    for y in range(h):
        for x in range(w):
            if band <= x < w - band and band <= y < h - band:
                continue
            n += 1
            if px[x, y] < thresh:
                hit += 1
    return hit / max(1, n)


# --- Keystoned dark-slab shot -------------------------------------------
# Handheld photo: the note is a trapezoid (camera below-left), inside
# black holder plastic, with a bright grading label above.
img = Image.new('RGB', (1300, 950), (12, 12, 14))
draw = ImageDraw.Draw(img)
KEYSTONE = [(300, 260), (1020, 300), (985, 725), (330, 680)]
_draw_note(draw, KEYSTONE, label_band=(280, 60, 1040, 190))

trimmed = _trim_to_image(img)
assert trimmed is not None, 'keystoned dark-slab shot was not trimmed'
tw, th = trimmed.size
want = _quad_aspect(KEYSTONE)
got = tw / float(th)
assert abs(got - want) / want < 0.08, \
    f'aspect off: got {got:.3f}, want {want:.3f}'
# Perspective corrected => no dark holder wedges survive in the corners.
lumas = _corner_luma(trimmed)
assert all(v > 140 for v in lumas), f'dark corner wedge left: {lumas}'
assert _holder_fraction(trimmed) < 0.02, 'holder plastic left in frame'
# Idempotent: a rectified note must come back as nothing-to-do.
buf = io.BytesIO()
trimmed.save(buf, format='JPEG', quality=92)
assert stuffapp._trim_slabbed_note_image(buf.getvalue()) is None, \
    're-trim of a rectified note should be a no-op'
print('KEYSTONE DARK-SLAB ASSERTIONS PASSED')


# --- Rotated (not keystoned) dark-slab shot ------------------------------
img = Image.new('RGB', (1300, 950), (10, 10, 12))
draw = ImageDraw.Draw(img)
cx, cy, hw, hh, th_deg = 660, 500, 360, 220, 2.5
rad = math.radians(th_deg)
ROT = []
for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
    dx, dy = sx * hw, sy * hh
    ROT.append((cx + dx * math.cos(rad) - dy * math.sin(rad),
                cy + dx * math.sin(rad) + dy * math.cos(rad)))
_draw_note(draw, ROT, label_band=(280, 40, 1040, 160))

trimmed = _trim_to_image(img)
assert trimmed is not None, 'rotated dark-slab shot was not trimmed'
tw, th = trimmed.size
got = tw / float(th)
want = hw / float(hh)
assert abs(got - want) / want < 0.08, \
    f'rotated aspect off: got {got:.3f}, want {want:.3f}'
lumas = _corner_luma(trimmed)
assert all(v > 140 for v in lumas), \
    f'rotation not levelled, dark corner left: {lumas}'
assert _holder_fraction(trimmed) < 0.02, 'holder plastic left in frame'
print('ROTATED DARK-SLAB ASSERTIONS PASSED')


# --- Level dark-slab shot keeps working ----------------------------------
img = Image.new('RGB', (1300, 950), (12, 12, 14))
draw = ImageDraw.Draw(img)
LEVEL = [(300, 280), (1010, 280), (1010, 700), (300, 700)]
_draw_note(draw, LEVEL, label_band=(280, 60, 1030, 200))

trimmed = _trim_to_image(img)
assert trimmed is not None, 'level dark-slab shot was not trimmed'
tw, th = trimmed.size
got = tw / float(th)
want = (1010 - 300) / float(700 - 280)
assert abs(got - want) / want < 0.08, \
    f'level aspect off: got {got:.3f}, want {want:.3f}'
assert _holder_fraction(trimmed) < 0.02, 'holder plastic left in frame'
print('LEVEL DARK-SLAB ASSERTIONS PASSED')


# --- Clear slab photographed on couch fabric ------------------------------
# The real-world case the ring gate used to reject: a clear holder on
# furniture, so the ring around the note is textured mid-dark fabric —
# nowhere near black, but clearly darker than the paper. Contrast
# evidence must let the slab-shot gate pass and the keystone come out.
img = Image.new('RGB', (1300, 950), (78, 70, 64))
draw = ImageDraw.Draw(img)
# blotchy weave texture, deterministic
for i in range(0, 1300, 13):
    for j in range(0, 950, 11):
        v = 55 + ((i * 7 + j * 13) % 47)
        draw.rectangle([i, j, i + 12, j + 10], fill=(v, v - 6, v - 10))
_draw_note(draw, KEYSTONE, label_band=(280, 60, 1040, 190))

trimmed = _trim_to_image(img)
assert trimmed is not None, 'couch-background slab shot was not trimmed'
tw, th = trimmed.size
want = _quad_aspect(KEYSTONE)
got = tw / float(th)
assert abs(got - want) / want < 0.08, \
    f'couch aspect off: got {got:.3f}, want {want:.3f}'
lumas = _corner_luma(trimmed)
assert all(v > 140 for v in lumas), f'couch wedge left in corner: {lumas}'
print('COUCH-BACKGROUND SLAB ASSERTIONS PASSED')


# --- Slab on a saturated blue backdrop ------------------------------------
# The 50-Pesos failure: a dealer shot of the slab on a blue board. In
# grayscale the inked note and the blue backdrop are nearly the same
# brightness, so the Otsu path finds nothing — the low-saturation
# paper mask has to carry it.
img = Image.new('RGB', (1600, 900), (100, 130, 200))
draw = ImageDraw.Draw(img)
BLUE_QUAD = [(300, 250), (1290, 262), (1286, 700), (306, 690)]
draw.polygon(BLUE_QUAD, fill=(235, 232, 225))


def _lerp_q(quad, u, v):
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = quad
    return ((1 - u) * (1 - v) * ax + u * (1 - v) * bx
            + u * v * cx + (1 - u) * v * dx,
            (1 - u) * (1 - v) * ay + u * (1 - v) * by
            + u * v * cy + (1 - u) * v * dy)


# dense two-colour overprint like a Victory note — most of the paper
# is saturated ink, only margins and gaps stay pale
u = 0.08
while u < 0.92:
    ink = (40, 60, 140) if int(u * 100) % 2 else (170, 40, 50)
    draw.line([_lerp_q(BLUE_QUAD, u, 0.10), _lerp_q(BLUE_QUAD, u, 0.90)],
              fill=ink, width=5)
    u += 0.008
draw.rectangle([280, 40, 1300, 190], fill=(240, 245, 240))  # PMG label

trimmed = _trim_to_image(img)
assert trimmed is not None, 'blue-backdrop slab shot was not trimmed'
tw, th = trimmed.size
want = _quad_aspect(BLUE_QUAD)
got = tw / float(th)
assert abs(got - want) / want < 0.08, \
    f'blue-backdrop aspect off: got {got:.3f}, want {want:.3f}'
px = trimmed.load()
for x, y in ((6, 6), (tw - 7, 6), (6, th - 7), (tw - 7, th - 7)):
    r, g, b = px[x, y][:3]
    assert b - r < 40, f'blue backdrop left at {(x, y)}: {(r, g, b)}'
print('BLUE-BACKDROP SLAB ASSERTIONS PASSED')


# --- Slab on green felt (clear holder shows felt through plastic) ---------
# The 100-Pesos failure: the whole slab region reads as one bright-ish
# blob, and the slab's own proportions pass a banknote aspect gate, so
# a global threshold either finds nothing or crops to the SLAB. The
# ink anchor has to tie the accepted quad to the printed design.
img = Image.new('RGB', (1600, 1200), (40, 120, 70))
draw = ImageDraw.Draw(img)
for i in range(0, 1600, 9):
    for j in range(0, 1200, 7):
        dv = ((i * 11 + j * 17) % 50) - 25
        draw.rectangle([i, j, i + 8, j + 6],
                       fill=(40 + dv, 120 + dv, 70 + dv))
# clear slab: felt seen through plastic reads brighter and washed out
SLAB = (250, 150, 1350, 1050)
for i in range(SLAB[0], SLAB[2], 9):
    for j in range(SLAB[1], SLAB[3], 7):
        dv = ((i * 11 + j * 17) % 30) - 15
        draw.rectangle([i, j, min(i + 8, SLAB[2]), min(j + 6, SLAB[3])],
                       fill=(120 + dv, 200 + dv, 150 + dv))
draw.rectangle([270, 180, 1330, 330], fill=(245, 248, 245))  # label
for k in range(5):
    draw.line([(300 + k * 180, 230), (400 + k * 180, 230)],
              fill=(30, 30, 30), width=6)
NOTE_QUAD = [(350, 420), (1250, 435), (1240, 950), (360, 935)]
_draw_note(draw, NOTE_QUAD)

trimmed = _trim_to_image(img)
assert trimmed is not None, 'green-felt slab shot was not trimmed'
tw, th = trimmed.size
want = _quad_aspect(NOTE_QUAD)
got = tw / float(th)
assert abs(got - want) / want < 0.08, \
    f'green-felt crop is not the note (slab?): got {got:.3f}, want {want:.3f}'
px = trimmed.load()
for x, y in ((6, 6), (tw - 7, 6), (6, th - 7), (tw - 7, th - 7)):
    r, g, b = px[x, y][:3]
    assert not (g - r > 30 and g - b > 30), \
        f'green felt left at {(x, y)}: {(r, g, b)}'
print('GREEN-FELT SLAB ASSERTIONS PASSED')


# --- Light-holder keystone shots -----------------------------------------
# A flat note rendered through a REAL homography into a light-holder
# scene: the trimmer must warp it square-on and keep a border around
# the printed area — whatever the paper colour (warm, blue, white).

def _solve_h(src, dst):
    mtx = []
    for (dx, dy), (sx, sy) in zip(src, dst):
        mtx.append([dx, dy, 1, 0, 0, 0, -sx * dx, -sx * dy, sx])
        mtx.append([0, 0, 0, dx, dy, 1, -sy * dx, -sy * dy, sy])
    for col in range(8):
        piv = max(range(col, 8), key=lambda r: abs(mtx[r][col]))
        mtx[col], mtx[piv] = mtx[piv], mtx[col]
        pv = mtx[col][col]
        mtx[col] = [v / pv for v in mtx[col]]
        for r2 in range(8):
            if r2 != col and mtx[r2][col]:
                f = mtx[r2][col]
                mtx[r2] = [v - f * u for v, u in zip(mtx[r2], mtx[col])]
    return [mtx[r][8] for r in range(8)]


def _light_scene(paper, holder):
    NW, NH = 1400, 860
    note = Image.new('RGB', (NW, NH), paper)
    d = ImageDraw.Draw(note)
    mx, my = int(0.09 * NW), int(0.09 * NH)
    d.rectangle([mx, my, NW - mx, NH - my], outline=INK, width=3)
    # Dot-grid "engraving": one solid blob after dilation, yet no
    # scanline reads as mostly ink, so the paper walk crosses freely.
    for j, gy in enumerate(range(my + 10, NH - my - 18, 14)):
        off = 7 if j % 2 else 0
        for gx in range(mx + 10 + off, NW - mx - 18, 14):
            d.rectangle([gx, gy, gx + 8, gy + 8], fill=INK)
    quad = ((300, 260), (1020, 300), (985, 725), (330, 680))
    C = _solve_h(quad, ((0, 0), (NW, 0), (NW, NH), (0, NH)))
    wn = note.transform((1300, 950), Image.PERSPECTIVE, C,
                        resample=Image.BICUBIC, fillcolor=(0, 0, 0))
    # Mask by the quad polygon itself: the projective inverse map
    # wraps beyond its horizon line and would paint ghost content.
    cx = sum(p[0] for p in quad) / 4.0
    cy = sum(p[1] for p in quad) / 4.0
    shrunk = [(px_ + (cx - px_) * 0.006, py_ + (cy - py_) * 0.006)
              for px_, py_ in quad]
    mask = Image.new('L', (1300, 950), 0)
    ImageDraw.Draw(mask).polygon(shrunk, fill=255)
    scene = Image.new('RGB', (1300, 950), holder)
    scene.paste(wn, (0, 0), mask)
    return scene, NW / NH


def _design_insets(img, ring=8):
    """Fractional inset of the printed area from each output edge,
    ignoring the outermost ring (crop-boundary seam pixels aren't
    ink). Rows/cols count as design only when clusters of dark pixels
    cover them — a stray hairline doesn't."""
    g = img.convert('L')
    px = g.load()
    w, h = g.size
    rows = [sum(1 for x in range(ring, w - ring, 2)
                if px[x, y] < 110) / ((w - 2 * ring) / 2)
            for y in range(ring, h - ring)]
    cols = [sum(1 for y in range(ring, h - ring, 2)
                if px[x, y] < 110) / ((h - 2 * ring) / 2)
            for x in range(ring, w - ring)]
    ink_rows = [i for i, f in enumerate(rows) if f > 0.08]
    ink_cols = [i for i, f in enumerate(cols) if f > 0.08]
    assert ink_rows and ink_cols, 'no design found in output'
    return (min(ink_cols) / w, min(ink_rows) / h,
            (len(cols) - 1 - max(ink_cols)) / w,
            (len(rows) - 1 - max(ink_rows)) / h)


for name, paper, holder in (
    ('warm on grey holder', (238, 230, 202), (222, 222, 224)),
    ('blue on white holder', (205, 212, 240), (245, 245, 245)),
    ('white on grey holder', (240, 240, 241), (215, 215, 217)),
):
    scene, want = _light_scene(paper, holder)
    trimmed = _trim_to_image(scene)
    assert trimmed is not None, f'{name}: keystoned shot was not trimmed'
    got = trimmed.size[0] / float(trimmed.size[1])
    assert abs(got - want) / want < 0.07, \
        f'{name}: aspect off: got {got:.3f}, want {want:.3f}'
    insets = _design_insets(trimmed)
    assert all(f >= 0.01 for f in insets), \
        f'{name}: printed area touches the edge: {insets}'
    assert all(f <= 0.17 for f in insets), \
        f'{name}: border too wide (holder ring kept): {insets}'
    print(f'LIGHT-HOLDER ({name}) ASSERTIONS PASSED')


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
