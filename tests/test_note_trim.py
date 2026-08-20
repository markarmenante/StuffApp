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


# --- Dark slab photographed on a bright backdrop --------------------------
# The Javasche-Bank reverse failure (Aug 2026): an eBay photo of the
# slab on a near-white table. Backdrop, grading label, and note all
# clear the brightness threshold, and a thin seam highlight across the
# holder ties them into ONE frame-filling component, so the plain mask
# holds no banknote-shaped blob. The erode + border-flood retry must
# isolate the note — the one bright block ringed by black plastic.
img = Image.new('RGB', (1600, 1000), (205, 204, 200))      # bright table
draw = ImageDraw.Draw(img)
draw.rectangle([60, 20, 1540, 980], fill=(14, 14, 16))     # slab plastic
draw.rectangle([80, 40, 1520, 240], fill=(228, 232, 226))  # grading label
for i in range(6):
    lx = 120 + i * 90
    draw.line([(lx, 90), (lx + 60, 90)], fill=(30, 30, 30), width=4)
BRIGHT_BACK = [(210, 300), (1390, 300), (1390, 890), (210, 890)]
# Seam highlight along the note's top edge, running to both frame
# borders — the thin bridge that merges note and backdrop.
draw.line([(0, 300), (1600, 300)], fill=(210, 210, 208), width=3)
_draw_note(draw, BRIGHT_BACK)

dark_direct = stuffapp._trim_dark_slab_note(img)
assert dark_direct is not None, \
    'dark detector did not isolate the border-bridged ringed note'

trimmed = _trim_to_image(img)
assert trimmed is not None, 'bright-backdrop dark-slab shot was not trimmed'
tw, th = trimmed.size
want = (1390 - 210) / float(890 - 300)
got = tw / float(th)
assert abs(got - want) / want < 0.08, \
    f'bright-backdrop aspect off: got {got:.3f}, want {want:.3f}'
assert _holder_fraction(trimmed) < 0.02, 'holder plastic left in frame'
print('BRIGHT-BACKDROP DARK-SLAB ASSERTIONS PASSED')


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


# --- Notes with a solid dark vignette --------------------------------------
# The BPI/Victory/PNB failures of Aug 2026: a real portrait or volcano
# vignette is a solid dark mass that punches a big hole in every
# brightness mask, so demanding near-full mask coverage inside the
# accepted quad rejected the real note every time. Three scenes:
#   V1 green felt (nothing trimmed at all in production),
#   V2 tight slab crop with the grading label still on (label's text
#      used to fail the ring-uniformity gate => label never came off),
#   V3 slab BACK with the small edge-dense PMG hologram sticker that
#      the ink anchor used to lock onto (crop came out as the sticker).

def _draw_vignette_note(draw, quad, vignette_frac=0.55):
    """Paper quad with border, sparse lathework, solid dark central
    vignette (with the fine light line texture real engraving has) and
    solid corner counters."""
    draw.polygon(quad, fill=PAPER)

    def lerp2(u, v):
        (ax, ay), (bx, by), (cx, cy), (dx, dy) = quad
        return ((1 - u) * (1 - v) * ax + u * (1 - v) * bx
                + u * v * cx + (1 - u) * v * dx,
                (1 - u) * (1 - v) * ay + u * (1 - v) * by
                + u * v * cy + (1 - u) * v * dy)

    m = 0.06
    border = [lerp2(m, m), lerp2(1 - m, m), lerp2(1 - m, 1 - m),
              lerp2(m, 1 - m)]
    draw.polygon(border, outline=INK, width=5)
    u = m + 0.02
    while u < 1 - m - 0.02:
        draw.line([lerp2(u, m + 0.03), lerp2(u, 1 - m - 0.03)],
                  fill=INK, width=1)
        u += 0.035
    v0, v1 = 0.5 - vignette_frac / 2, 0.5 + vignette_frac / 2
    vig = [lerp2(v0, 0.18), lerp2(v1, 0.18), lerp2(v1, 0.85),
           lerp2(v0, 0.85)]
    draw.polygon(vig, fill=INK)
    vv = 0.20
    while vv < 0.84:
        draw.line([lerp2(v0 + 0.01, vv), lerp2(v1 - 0.01, vv)],
                  fill=(130, 132, 142), width=2)
        vv += 0.045
    for (u, v) in ((0.12, 0.2), (0.88, 0.2), (0.12, 0.8), (0.88, 0.8)):
        cx, cy = lerp2(u, v)
        draw.ellipse([cx - 28, cy - 28, cx + 28, cy + 28], fill=INK)


# V1: green felt, solid vignette — must still find the note.
img = Image.new('RGB', (1600, 1200), (40, 120, 70))
draw = ImageDraw.Draw(img)
for i in range(0, 1600, 9):
    for j in range(0, 1200, 7):
        dv = ((i * 11 + j * 17) % 50) - 25
        draw.rectangle([i, j, i + 8, j + 6],
                       fill=(40 + dv, 120 + dv, 70 + dv))
for i in range(SLAB[0], SLAB[2], 9):
    for j in range(SLAB[1], SLAB[3], 7):
        dv = ((i * 11 + j * 17) % 30) - 15
        draw.rectangle([i, j, min(i + 8, SLAB[2]), min(j + 6, SLAB[3])],
                       fill=(120 + dv, 200 + dv, 150 + dv))
draw.rectangle([270, 180, 1330, 330], fill=(245, 248, 245))
for k in range(5):
    draw.line([(300 + k * 180, 230), (400 + k * 180, 230)],
              fill=(30, 30, 30), width=6)
_draw_vignette_note(draw, NOTE_QUAD)

trimmed = _trim_to_image(img)
assert trimmed is not None, 'vignette note on green felt was not trimmed'
tw, th = trimmed.size
want = _quad_aspect(NOTE_QUAD)
got = tw / float(th)
assert abs(got - want) / want < 0.08, \
    f'vignette green-felt crop is not the note: got {got:.3f}, want {want:.3f}'
px = trimmed.load()
for x, y in ((6, 6), (tw - 7, 6), (6, th - 7), (tw - 7, th - 7)):
    r, g, b = px[x, y][:3]
    assert not (g - r > 30 and g - b > 30), \
        f'green felt left at {(x, y)}: {(r, g, b)}'
print('VIGNETTE GREEN-FELT ASSERTIONS PASSED')


# V2: tight slab crop — teal grading label on top, dark note below,
# white background showing through the clear holder. The label must
# come off even though its text sits right inside the ring the light
# detector inspects.
img = Image.new('RGB', (1220, 650), (238, 238, 236))
draw = ImageDraw.Draw(img)
draw.rectangle([8, 6, 1212, 190], fill=(214, 236, 228))
for k in range(6):
    draw.line([(40 + k * 190, 60), (170 + k * 190, 60)],
              fill=(40, 60, 55), width=8)
    draw.line([(40 + k * 190, 120), (150 + k * 190, 120)],
              fill=(60, 80, 75), width=5)
SLAB_NOTE = [(60, 225), (1160, 230), (1157, 625), (63, 620)]
_draw_vignette_note(draw, SLAB_NOTE, vignette_frac=0.6)

trimmed = _trim_to_image(img)
assert trimmed is not None, 'tight slab crop was not trimmed'
tw, th = trimmed.size
want = _quad_aspect(SLAB_NOTE)
got = tw / float(th)
assert abs(got - want) / want < 0.08, \
    f'slab-crop result is not the note: got {got:.3f}, want {want:.3f}'
px = trimmed.load()
r, g, b = px[tw // 2, 4][:3]
assert not (g - r > 10 and g - b > 4), \
    f'grading label left at top: {(r, g, b)}'
print('TIGHT SLAB-CROP LABEL ASSERTIONS PASSED')


# V3: slab back — the hologram sticker (small, guilloche-dense,
# banknote-ish aspect) must not become the crop.
img = Image.new('RGB', (1600, 860), (240, 240, 238))
draw = ImageDraw.Draw(img)
draw.rectangle([8, 8, 1592, 215], fill=(216, 233, 224))
draw.rectangle([30, 45, 495, 200], fill=(70, 110, 160))
for k in range(30, 495, 6):
    draw.line([(k, 45), (k + 30, 200)], fill=(150, 200, 230), width=1)
    draw.line([(k, 200), (k + 30, 45)], fill=(40, 60, 110), width=1)
for k in range(1300, 1560, 7):
    draw.line([(k, 60), (k, 175)], fill=(30, 30, 30),
              width=2 if k % 3 else 4)
BACK_NOTE = [(70, 245), (1530, 250), (1526, 830), (74, 825)]
draw.polygon(BACK_NOTE, fill=(232, 222, 196))


def _lerp_back(u, v):
    (ax, ay), (bx, by), (cx, cy), (dx, dy) = BACK_NOTE
    return ((1 - u) * (1 - v) * ax + u * (1 - v) * bx
            + u * v * cx + (1 - u) * v * dx,
            (1 - u) * (1 - v) * ay + u * (1 - v) * by
            + u * v * cy + (1 - u) * v * dy)


BROWN = (150, 92, 48)
draw.polygon([_lerp_back(0.05, 0.06), _lerp_back(0.95, 0.06),
              _lerp_back(0.95, 0.94), _lerp_back(0.05, 0.94)],
             outline=BROWN, width=6)
u = 0.07
while u < 0.93:
    draw.line([_lerp_back(u, 0.10), _lerp_back(u, 0.90)],
              fill=BROWN, width=2)
    u += 0.009
v = 0.12
while v < 0.90:
    draw.line([_lerp_back(0.07, v), _lerp_back(0.93, v)],
              fill=BROWN, width=2)
    v += 0.05
for (u, v) in ((0.10, 0.5), (0.90, 0.5)):
    cx, cy = _lerp_back(u, v)
    draw.ellipse([cx - 55, cy - 55, cx + 55, cy + 55], fill=BROWN)

trimmed = _trim_to_image(img)
assert trimmed is not None, 'slab back was not trimmed'
tw, th = trimmed.size
assert tw > 900, \
    f'crop locked onto the hologram sticker: {trimmed.size}'
want = _quad_aspect(BACK_NOTE)
got = tw / float(th)
assert abs(got - want) / want < 0.10, \
    f'slab-back crop is not the note: got {got:.3f}, want {want:.3f}'
print('HOLOGRAM-STICKER SLAB-BACK ASSERTIONS PASSED')


# --- Holder pocket on felt: crop the note, not the pocket ------------------
# The PCGS 1-Peso failure: felt seen through the holder plastic is
# DESATURATED (below any fixed saturation bar) but stays
# green-dominant. The pocket region (note + washed felt stripes) is
# itself banknote-shaped and used to win as the accepted quad, leaving
# green stripes and the shot's tilt in the stored image. The
# backdrop-spill gate plus the channel-dominance (warm) mask must
# yield the note itself, levelled.

def _rot_quad(cx, cy, hw, hh, deg):
    rad = math.radians(deg)
    out = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dy = sx * hw, sy * hh
        out.append((cx + dx * math.cos(rad) - dy * math.sin(rad),
                    cy + dx * math.sin(rad) + dy * math.cos(rad)))
    return out


img = Image.new('RGB', (1600, 1200), (36, 150, 90))
draw = ImageDraw.Draw(img)
for i in range(0, 1600, 9):
    for j in range(0, 1200, 7):
        dv = ((i * 13 + j * 19) % 46) - 23
        draw.rectangle([i, j, i + 8, j + 6],
                       fill=(36 + dv, 150 + dv, 90 + dv))
POCKET = (100, 200, 1520, 1080)
for i in range(POCKET[0], POCKET[2], 9):
    for j in range(POCKET[1], POCKET[3], 7):
        dv = ((i * 13 + j * 19) % 28) - 14
        draw.rectangle([i, j, min(i + 8, POCKET[2]), min(j + 6, POCKET[3])],
                       fill=(168 + dv, 205 + dv, 182 + dv))
draw.rectangle([120, 230, 1500, 400], fill=(228, 240, 230))
for k in range(6):
    draw.line([(160 + k * 200, 290), (300 + k * 200, 290)],
              fill=(20, 25, 20), width=8)
    draw.line([(160 + k * 200, 340), (280 + k * 200, 340)],
              fill=(40, 45, 40), width=5)
POCKET_NOTE = _rot_quad(800, 760, 540, 245, 1.5)
_draw_vignette_note(draw, POCKET_NOTE, vignette_frac=0.35)

trimmed = _trim_to_image(img)
assert trimmed is not None, 'pocket-on-felt shot was not trimmed'
tw, th = trimmed.size
want = 540 / 245.0
got = tw / float(th)
assert abs(got - want) / want < 0.09, \
    f'pocket crop is not the note: got {got:.3f}, want {want:.3f}'
px = trimmed.load()
for x, y in ((5, 5), (tw - 6, 5), (5, th - 6), (tw - 6, th - 6),
             (5, th // 2), (tw - 6, th // 2)):
    r, g, b = px[x, y][:3]
    assert not (g - r > 25 and g - b > 25), \
        f'washed felt left in crop at {(x, y)}: {(r, g, b)}'
print('POCKET-ON-FELT ASSERTIONS PASSED')


# --- Pocket crop dead-end: green stripes must still come off --------------
# Production pass-2 state after a pocket quad was accepted: note plus
# washed-felt stripes, slight tilt. The design fills ~3/4 of the frame
# — the ink anchor must survive (cap 0.85) so the strict coverage bar
# stays relaxed and the stripes come off.
img = Image.new('RGB', (1490, 505), (168, 205, 182))
draw = ImageDraw.Draw(img)
for i in range(0, 1490, 9):
    for j in range(0, 505, 7):
        dv = ((i * 13 + j * 19) % 28) - 14
        draw.rectangle([i, j, i + 8, j + 6],
                       fill=(168 + dv, 205 + dv, 182 + dv))
STRIPE_NOTE = _rot_quad(745, 252, 590, 232, 1.0)
_draw_vignette_note(draw, STRIPE_NOTE, vignette_frac=0.35)

trimmed = _trim_to_image(img)
assert trimmed is not None, 'pocket-crop dead-end: stripes never removed'
tw, th = trimmed.size
want = 590 / 232.0
got = tw / float(th)
assert abs(got - want) / want < 0.09, \
    f'stripe crop is not the note: got {got:.3f}, want {want:.3f}'
px = trimmed.load()
for x, y in ((5, 5), (tw - 6, 5), (5, th - 6), (tw - 6, th - 6),
             (5, th // 2), (tw - 6, th // 2)):
    r, g, b = px[x, y][:3]
    assert not (g - r > 25 and g - b > 25), \
        f'washed felt left in stripe crop at {(x, y)}: {(r, g, b)}'
print('POCKET-CROP STRIPE ASSERTIONS PASSED')


# --- Ornate frame, blank centre: never cut INTO the note -------------------
# The JIM 5-Pesos reverse: an already-trimmed note whose saturated
# border frame surrounds a big blank field. The blank field is
# banknote-shaped and solid in the paper mask — without full design
# containment the detector cropped to it, amputating the border. All
# printed area must survive every trim: correct behaviour is a no-op
# (or at minimum a crop that keeps the full frame width).
img = Image.new('RGB', (1180, 505), (245, 238, 215))
draw = ImageDraw.Draw(img)
RUST = (165, 75, 55)
draw.rectangle([47, 20, 1133, 485], outline=RUST, width=42)
for k in range(60, 1120, 24):
    draw.line([(k, 22), (k + 14, 60)], fill=(200, 120, 95), width=3)
    draw.line([(k, 483), (k + 14, 445)], fill=(200, 120, 95), width=3)
for k in range(30, 480, 22):
    draw.line([(49, k), (87, k + 12)], fill=(200, 120, 95), width=3)
    draw.line([(1131, k), (1093, k + 12)], fill=(200, 120, 95), width=3)
for x in range(330, 850, 90):
    draw.rectangle([x, 210, x + 60, 300], outline=RUST, width=14)

trimmed = _trim_to_image(img)
assert trimmed is None or trimmed.size[0] >= 1050, \
    f'cut into the note (border amputated): {trimmed.size}'
print('ORNATE-FRAME BLANK-CENTRE ASSERTIONS PASSED')


# --- Design-union fallback crop --------------------------------------------
# When no detector finds a paper edge (note on a same-tone backing),
# the fallback must deliver ALL printed area plus a small margin.
img = Image.new('RGB', (1600, 900), (243, 236, 214))
draw = ImageDraw.Draw(img)
FALLBACK_NOTE = [(260, 220), (1340, 226), (1336, 680), (264, 674)]
_draw_vignette_note(draw, FALLBACK_NOTE, vignette_frac=0.4)
buf = io.BytesIO()
img.save(buf, format='JPEG', quality=92)
img2 = stuffapp._flatten_image_for_jpeg(
    stuffapp._open_upload_image(buf.getvalue()))
out = stuffapp._trim_note_design_crop(img2)
assert out is not None, 'design fallback found nothing'
trimmed = Image.open(io.BytesIO(out))
tw, th = trimmed.size
assert 1.15 <= tw / float(th) <= 3.8, f'fallback aspect wild: {trimmed.size}'
g2 = trimmed.convert('L')
gpx = g2.load()
# margin present: no ink ON the crop edge...
assert not any(gpx[x, 1] < 120 or gpx[x, th - 2] < 120
               for x in range(0, tw, 3)), 'design touches crop edge'
assert not any(gpx[1, y] < 120 or gpx[tw - 2, y] < 120
               for y in range(0, th, 3)), 'design touches crop edge'


def _has_ink_band(xs, ys):
    return any(gpx[x, y] < 120 for x in xs for y in ys)


# ...but all printed area kept close to every edge (nothing amputated,
# margins small): ink must appear within 9% of each edge.
assert _has_ink_band(range(0, tw, 3), range(2, int(0.09 * th))), \
    'top border lost or margin too wide'
assert _has_ink_band(range(0, tw, 3), range(th - int(0.09 * th), th - 2)), \
    'bottom border lost or margin too wide'
assert _has_ink_band(range(2, int(0.09 * tw)), range(0, th, 3)), \
    'left border lost or margin too wide'
assert _has_ink_band(range(tw - int(0.09 * tw), tw - 2), range(0, th, 3)), \
    'right border lost or margin too wide'
print('DESIGN-UNION FALLBACK ASSERTIONS PASSED')


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


# --- Runaway pass-2 shrink (Victory 10 Pesos front) -----------------------
# Pass 1 legitimately cuts a raw photo down to the note region; passes
# 2-3 only shave slivers. A pass-2 detector gone wrong (glare-split
# paper mask, collapsed ink anchor) that discards most of the remaining
# image must be refused — the final crop is pass 1's, never the band.
_real_cv = stuffapp._trim_slab_note_cv
_calls = {'n': 0}


def _fake_cv(img):
    _calls['n'] += 1
    w, h = img.size
    if _calls['n'] == 1:
        crop = img.crop((int(w * 0.1), int(h * 0.1), int(w * 0.9), int(h * 0.85)))
    elif _calls['n'] == 2:
        crop = img.crop((int(w * 0.2), int(h * 0.35), int(w * 0.75), int(h * 0.62)))
    else:
        return None
    return stuffapp._encode_trimmed_note(crop)


img = Image.new('RGB', (1600, 1200), (40, 150, 80))
draw = ImageDraw.Draw(img)
draw.rectangle([300, 300, 1300, 900], fill=PAPER)
buf = io.BytesIO()
img.save(buf, format='JPEG', quality=90)
stuffapp._trim_slab_note_cv = _fake_cv
try:
    out = stuffapp._trim_slabbed_note_image(buf.getvalue())
finally:
    stuffapp._trim_slab_note_cv = _real_cv
res = Image.open(io.BytesIO(out))
assert abs(res.size[0] - 1280) < 4 and abs(res.size[1] - 900) < 4, \
    f'runaway pass-2 crop kept: {res.size}'
print('RUNAWAY PASS-2 SHRINK ASSERTIONS PASSED')


# --- Design union spanning the frame is not a design (Victory back) --------
# Felt/label edges merged into the union so it ran edge-to-edge of the
# photo; a real printed design never does — reject instead of "trimming"
# to a full-width band and halting the pipeline on a bogus success.
img = Image.new('RGB', (1600, 700), (40, 150, 80))
draw = ImageDraw.Draw(img)
draw.rectangle([0, 180, 1599, 560], fill=PAPER)
for row in range(5):
    y = 220 + row * 60
    draw.rectangle([10, y, 1590, y + 26], fill=(120, 75, 45))
assert stuffapp._trim_note_design_crop(img) is None, \
    'edge-to-edge design union must be rejected'
print('EDGE-TO-EDGE UNION ASSERTIONS PASSED')

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

# --- Key hygiene: the validator must not fire in tests ---------------------
os.environ.pop('ANTHROPIC_API_KEY', None)


# --- Catalog-ratio veto: a stretched CV crop is never shipped --------------
# The validator layer (2026-08-17): the CV cascade is primary again and
# the pipeline may VETO its result but never re-crop it. A CV crop more
# than 8% off the sheet's catalog long:short ratio leaves the stored
# image untouched.
_real_cascade = stuffapp._trim_note_cv_cascade

img = Image.new('RGB', (1600, 1200), (24, 24, 26))
draw = ImageDraw.Draw(img)
_draw_note(draw, [(300, 300), (1340, 300), (1340, 880), (300, 880)])
buf = io.BytesIO(); img.save(buf, format='JPEG', quality=92)

stretched = Image.new('RGB', (1200, 400), PAPER)   # 3.0:1 "crop"
sb = io.BytesIO(); stretched.save(sb, format='JPEG', quality=90)
stuffapp._trim_note_cv_cascade = lambda im: sb.getvalue()
out = stuffapp._trim_slabbed_note_image(buf.getvalue(), expect_aspect=1.79)
assert out is None, 'a 3.0:1 crop of a 1.79:1 sheet must not ship'
print('CATALOG-RATIO VETO ASSERTIONS PASSED')

# --- Ratio inside tolerance ships (validator absent without a key) ---------
okimg = Image.new('RGB', (1040, 580), PAPER)
ob = io.BytesIO(); okimg.save(ob, format='JPEG', quality=90)
stuffapp._trim_note_cv_cascade = lambda im: ob.getvalue()
out = stuffapp._trim_slabbed_note_image(buf.getvalue(), expect_aspect=1.79)
assert out is not None, 'an on-ratio CV crop must ship'
print('ON-RATIO SHIP ASSERTIONS PASSED')

# --- Vision veto: bad verdict leaves the image untouched -------------------
_real_verdict = stuffapp._vision_crop_verdict
stuffapp._vision_crop_verdict = lambda crop: False
out = stuffapp._trim_slabbed_note_image(buf.getvalue(), expect_aspect=1.79)
assert out is None, 'a vetoed crop must not ship'
stuffapp._vision_crop_verdict = lambda crop: True
out = stuffapp._trim_slabbed_note_image(buf.getvalue(), expect_aspect=1.79)
assert out is not None, 'an approved crop must ship'
stuffapp._vision_crop_verdict = lambda crop: None
out = stuffapp._trim_slabbed_note_image(buf.getvalue(), expect_aspect=1.79)
assert out is not None, 'validator unavailable falls back to shipping CV'
stuffapp._vision_crop_verdict = _real_verdict
stuffapp._trim_note_cv_cascade = _real_cascade
print('VISION-VETO ASSERTIONS PASSED')

print('ALL NOTE-TRIM ASSERTIONS PASSED')
