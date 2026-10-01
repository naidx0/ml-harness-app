"""THE CLEAVE - the ML Harness app icon, and the only place it is drawn.

Writes every file the shell and the web frontend take it from: the SVG master,
the PNG set, the .ico, the .icns and the favicon.

    python scripts/make_icon.py

## WHY THIS IS A SCRIPT AND NOT SEVEN PNGs

An icon that arrives as seven binaries is an icon nobody can change. This draws
it, so the mark has a source, and the source is written out as vector too:
`src-tauri/icons/icon.svg` and `frontend/public/favicon.svg` are the same
geometry, so the mark can be placed anywhere at any size without touching a
raster. The numbers in `Icon.tsx`'s `mark` glyph and the book's sprite come
from `--glyph`, printed by this script, and a test pins them.

## THE MARK: THE CLEAVE

One stone, one straight fault across it, and the top piece sheared along that
fault so the two halves no longer line up. The silhouette steps where they
disagree, and that step is the whole idea: a harness splits things. Train
against held out, candidate against baseline, a run cut open so you can see
what is inside it.

The owner asked on 2026-09-13 for a mark invented the way ChatGPT's and
Obsidian's are made rather than another block, and took this one: "yes clean i
like it". The rotational construction (ChatGPT's: one element rotated n times,
the overlaps making the form) was tried first and closed - built with a strap
that loops at each corner, the 4-fold version renders the Apple Command glyph
almost exactly, and a square-hook version turns to mush below 32px.

## HOW IT IS BUILT, WHICH IS OBSIDIAN'S CONSTRUCTION

Read off obsidian.exe's own icon: an irregular silhouette split by a few
internal lines into LARGE facets, one gradient each, a radial pool of white
where the light lands, and no strokes. Applied here with four rules, all
mechanical, so the SVG and the PNG are one drawing and neither can drift:

  * one silhouette, seven points, including one long straight flank so it
    cannot settle into a stock crystal outline
  * TWO junction points per piece, never one. A fan from a single interior
    point is what makes every low-poly mark look the same; Obsidian's
    interior lines meet in several places and so do these
  * every facet's brightness is lambert against ONE light, up and to the
    left. No hand-picked values, so the solid stays coherent
  * corners softened by round JOINS in the facet's own colour. Never blur: a
    hard edge downsamples to a hard edge and a soft one to a smudge, which is
    what made the 2026-09-11 icon look blurry on the owner's desktop

## ONE RAMP, AND IT IS THE PRODUCT'S ACCENT

ML Harness's tokens (`graphite/_core.html`) put the accent at #6088EE, and the
stone is one ramp with that blue sitting inside it. A two-tone cut was drawn
first, a cream cap over a blue body, on the theory that differing in value as
well as position would help the split survive at 16px. It did the opposite: the
cream piece stopped belonging to the same stone and floated above it like a
paper wedge. The step in the silhouette is what carries the cleave, and it
carries it without help.

## TWO CUTS, WHICH IS STILL THE POINT

**The detailed cut** carries all ten facets and the light pool. Used at 256,
128 and 64, and it is what the SVG holds.

**The simplified cut** merges the facets that fall below a pixel into their
neighbours - ten faces become eight - and widens the parting between the two
pieces so the cleave still registers. Used at 48, 32, 24 and 16. It does NOT
raise contrast: that was tried and measured, and a Lanczos reduction of the
detailed cut beat it on interior range at 16, 24 and 32px every time, because
the resampling overshoots at every edge. A `.ico` can carry different artwork
per size and Pillow only does that when handed the frames explicitly, so
regenerating from one image would silently ship seven scaled copies;
`tests/test_the_icon_survives_being_small.py` asserts the cuts really differ.

## WHAT CONSUMES THESE

`src-tauri/tauri.conf.json` lists them under `bundle.icon`; the window, the
taskbar, the installer, the desktop shortcut and the tray all resolve from
there. `frontend/public/favicon.svg` is written by this script. The `mark`
glyph in `frontend/src/components/Icon.tsx` and `#mark-basilica` in
`docs/brand/basilica/basilica.html` are the flat two-piece silhouette on a 24
grid, which is what survives in a 14px rail where a gradient cannot.
"""

from __future__ import annotations

import io
import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

#: ADOPTED 2026-09-14. Max, having kept the gauge the day before: *"cleave, go
#: with the cleave, it's cool and new and creative, make sure it's AAA
#: quality."* The shelf copy at Documents/AI Workspace/app-icons/mlh-cleave is
#: where it was designed and it still holds the seven shears and the reasoning;
#: this is that file with its two output paths pointed back into the tree, so
#: the icon has a source here again and nobody has to open a raster editor.
REPO = Path(__file__).resolve().parents[1]
ICONS = REPO / "src-tauri" / "icons"
FAVICON = REPO / "frontend" / "public" / "favicon.svg"

#: Supersampled, then downsampled with LANCZOS.
SS = 1024

#: ONE RAMP, and the product's accent #6088EE sits inside it. A two-tone
#: version was drawn first - cream cap, blue body - and thrown away: the cream
#: piece stopped reading as part of the same stone and floated above it like a
#: paper wedge. The cleave does not need a colour change to be visible; the
#: step in the silhouette is what carries it.
DEEP, LIT = (12, 28, 104), (192, 214, 255)

#: One light, up and to the left. Screen y grows downward.
LIGHT = (-0.55, -0.83)

#: The silhouette, seven points on a unit canvas. O[6] -> O[0] is the long
#: straight flank. Everything else in the drawing is derived from these.
#: WIDENED 1.25x ON X, 2026-09-14. Max, with his taskbar beside the icon:
#: *"[the] icon looks low res and small compared to other icons - what can we
#: do about that."*
#:
#: MEASURED, and it is arithmetic rather than resolution. The silhouette's
#: bounding box was 0.98 wide by 1.68 tall - aspect 0.58, a tall narrow stone -
#: and `_fit` scales the LONGER side to `FILL` of the frame. So the height
#: reached 88% and the width could only ever reach 0.98/1.68 of that: 51%. The
#: mark covered 30% of its tile while the near-square gems beside it on the
#: taskbar cover well over half theirs. Nothing was under-resolved; it was
#: half the width of its neighbours and read as small because it WAS small.
#:
#: Widening the stone and raising FILL takes it to 44%. Rotating it would have
#: reached 52%, and was rejected: turning the fault off vertical flattens the
#: shear into a horizontal gap and the two pieces stop reading as one cleaved
#: object, which is the whole mark.
_SIL_RAW = [(-0.16, -0.86), (0.26, -0.74), (0.50, -0.24), (0.44, 0.34),
            (0.14, 0.82), (-0.30, 0.66), (-0.48, 0.02)]
WIDEN = 1.25
SIL = [(x * WIDEN, y) for x, y in _SIL_RAW]

#: Where the fault crosses the flanks, how far the cap slid along it, and how
#: wide the parting is. The owner picked this shear on 2026-09-13 (cleave-f):
#: a thick cap and a modest slide, the one that still reads as ONE cleaved
#: object at 16px rather than as two unrelated chips.
LO_CUT, HI_CUT = 0.20, 0.34
SLIDE = 0.16
GAP_DETAILED, GAP_SIMPLE = 0.048, 0.090

#: Junction points. Two per piece: a single one makes a fan, and a fan is what
#: every generic faceted mark looks like.
#: IN THE SAME SPACE AS `SIL`, so they take the same widening - a junction
#: left at its old x while the flanks move is a facet that tears away from the
#: outline it is supposed to meet.
U = (0.02 * WIDEN, -0.60)
D1, D2 = (-0.09 * WIDEN, -0.09), (0.21 * WIDEN, 0.33)

#: Round joins in the facet's own colour, as a fraction of the canvas.
ROUND_DETAILED, ROUND_SIMPLE = 0.018, 0.026

#: How much of the canvas the mark's bounding box fills. Obsidian's gem fills
#: about this much of its frame; less and the icon reads as a small thing in a
#: big empty tile.
FILL = 0.96

GLOW = 0.55


def _hex(colour) -> str:
    return "#%02X%02X%02X" % colour


def _ramp(deep, lit, u: float):
    u = max(0.0, min(1.0, u))
    return tuple(int(deep[i] + (lit[i] - deep[i]) * u) for i in range(3))


def _lerp(p, q, u):
    return (p[0] + (q[0] - p[0]) * u, p[1] + (q[1] - p[1]) * u)


def _shade(poly, anchor: tuple) -> float:
    """Lambert brightness for one facet: the vector from its piece's anchor to
    the facet's centroid stands in for the normal it would have on a solid."""
    cx = sum(p[0] for p in poly) / len(poly)
    cy = sum(p[1] for p in poly) / len(poly)
    dx, dy = cx - anchor[0], cy - anchor[1]
    n = math.hypot(dx, dy) or 1.0
    lam = (dx / n) * LIGHT[0] + (dy / n) * LIGHT[1]
    return 0.10 + 0.88 * (0.5 + 0.5 * lam)


def geometry(simple: bool) -> dict:
    """Every polygon in the mark, in unit space, already sheared.

    Returns the cap and body outlines (for the silhouette glyph and the light
    pool's clip) and the facet list as (points, deep_ramp, lit_ramp, anchor).
    """
    o = SIL
    lo = _lerp(o[6], o[0], LO_CUT)          # the fault meets the long left flank
    hi = _lerp(o[1], o[2], HI_CUT)          # and the right shoulder
    ux, uy = hi[0] - lo[0], hi[1] - lo[1]
    n = math.hypot(ux, uy)
    ux, uy = ux / n, uy / n
    mx, my = -uy, ux                        # the fault's normal
    gap = GAP_SIMPLE if simple else GAP_DETAILED
    up = (SLIDE / 2 * ux - gap / 2 * mx, SLIDE / 2 * uy - gap / 2 * my)
    dn = (-SLIDE / 2 * ux + gap / 2 * mx, -SLIDE / 2 * uy + gap / 2 * my)

    def shift(poly, s):
        return [(x + s[0], y + s[1]) for x, y in poly]

    if simple:
        #: MERGED, but only where merging costs nothing. The three slivers
        #: along the bottom-right are each under a pixel wide at 16px and read
        #: as noise, so they become one face. THE CAP KEEPS ALL THREE: its
        #: dark underside is the shadow that separates it from the body, and
        #: folding that into the shoulder (tried first) left the two pieces
        #: reading as one pale blob.
        cap_f = [[lo, o[0], o[1], U], [o[1], hi, U], [hi, lo, U]]
        body_f = [[lo, hi, D1], [hi, o[2], o[3], D2, D1],
                  [o[3], o[4], o[5], D2], [o[5], o[6], D1, D2], [o[6], lo, D1]]
    else:
        cap_f = [[lo, o[0], o[1], U], [o[1], hi, U], [hi, lo, U]]
        body_f = [[lo, hi, D1], [hi, o[2], D2, D1], [o[2], o[3], D2],
                  [o[3], o[4], D2], [o[4], o[5], D2], [o[5], o[6], D1, D2],
                  [o[6], lo, D1]]

    facets = ([(shift(p, up), DEEP, LIT, U) for p in cap_f]
              + [(shift(p, dn), DEEP, LIT, (0.04, 0.12)) for p in body_f])
    return dict(
        cap=shift([lo, o[0], o[1], hi], up),
        body=shift([lo, hi, o[2], o[3], o[4], o[5], o[6]], dn),
        facets=facets,
        glow=(-0.22 + up[0], -0.62 + up[1]),
    )


def _fit(geo: dict, size: int):
    """Centre the mark's bounding box in the canvas and scale it to FILL.

    The mark is free-standing, with no tile behind it - Chrome's, Cursor's and
    Obsidian's all are - so nothing else establishes the margin.
    """
    pts = [p for poly, *_ in geo["facets"] for p in poly]
    x0 = min(p[0] for p in pts); x1 = max(p[0] for p in pts)
    y0 = min(p[1] for p in pts); y1 = max(p[1] for p in pts)
    k = size * FILL / max(x1 - x0, y1 - y0)
    ox = size / 2 - (x0 + x1) / 2 * k
    oy = size / 2 - (y0 + y1) / 2 * k
    return (lambda p: (p[0] * k + ox, p[1] * k + oy)), k


def cleave(size: int = SS, simple: bool = False) -> Image.Image:
    geo = geometry(simple)
    to, k = _fit(geo, size)
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    rows = np.mgrid[0:size, 0:size][0].astype(np.float32)
    round_w = (ROUND_SIMPLE if simple else ROUND_DETAILED) * size

    for poly, deep, lit, anchor in geo["facets"]:
        pts = [to(p) for p in poly]
        mask = Image.new("L", (size, size), 0)
        md = ImageDraw.Draw(mask)
        md.polygon(pts, fill=255)
        md.line(pts + [pts[0]], fill=255, width=int(round_w), joint="curve")
        for x, y in pts:
            md.ellipse([x - round_w / 2, y - round_w / 2,
                        x + round_w / 2, y + round_w / 2], fill=255)
        t = _shade(poly, anchor)
        #: BOTH CUTS USE THE SAME COLOURS. Raising the small cut's contrast was
        #: tried and measured: a Lanczos reduction of the detailed cut beat it
        #: on range at 16, 24 and 32px every time, because the resampling
        #: overshoots at every edge. The small cut earns its place by having
        #: fewer facets and a wider parting, not by shouting.
        hi_c = _ramp(deep, lit, t + 0.10)
        lo_c = _ramp(deep, lit, t - 0.26)
        ys = [p[1] for p in pts]
        u = np.clip((rows - min(ys)) / max(1.0, max(ys) - min(ys)), 0, 1)
        rgb = (np.array(hi_c, np.float32)[None, None, :] * (1 - u[..., None])
               + np.array(lo_c, np.float32)[None, None, :] * u[..., None]).astype(np.uint8)
        img.paste(Image.fromarray(
            np.dstack([rgb, np.full((size, size, 1), 255, np.uint8)]), "RGBA"), (0, 0), mask)

    #: The pool of light on the cap's shoulder, clipped to the cap.
    clip = Image.new("L", (size, size), 0)
    cd = ImageDraw.Draw(clip)
    cap = [to(p) for p in geo["cap"]]
    cd.polygon(cap, fill=255)
    cd.line(cap + [cap[0]], fill=255, width=int(round_w), joint="curve")
    yy, xx = np.mgrid[0:size, 0:size].astype(np.float32)
    gx, gy = to(geo["glow"])
    field = np.clip(1 - np.sqrt((xx - gx) ** 2 + (yy - gy) ** 2) / (0.46 * k), 0, 1) ** 1.5 * GLOW
    img.alpha_composite(Image.fromarray(np.dstack([
        np.full((size, size, 3), 255, np.uint8),
        (field * 255 * (np.array(clip) / 255)).astype(np.uint8)]), "RGBA"))
    return img


def svg(size: int = SS, simple: bool = False) -> str:
    """The same geometry as vector: one linear gradient per facet, one radial
    pool, no strokes but the round joins, which are the facet's own colour."""
    geo = geometry(simple)
    to, k = _fit(geo, size)
    round_w = (ROUND_SIMPLE if simple else ROUND_DETAILED) * size
    defs, body = [], []
    for i, (poly, deep, lit, anchor) in enumerate(geo["facets"]):
        pts = [to(p) for p in poly]
        t = _shade(poly, anchor)
        hi_c = _ramp(deep, lit, t + 0.10)
        lo_c = _ramp(deep, lit, t - 0.26)
        y0 = min(p[1] for p in pts); y1 = max(p[1] for p in pts)
        defs.append(
            f'<linearGradient id="c{i}" gradientUnits="userSpaceOnUse" '
            f'x1="0" y1="{y0:.2f}" x2="0" y2="{y1:.2f}">'
            f'<stop offset="0" stop-color="{_hex(hi_c)}"/>'
            f'<stop offset="1" stop-color="{_hex(lo_c)}"/></linearGradient>')
        pl = " ".join("%.2f,%.2f" % p for p in pts)
        body.append(f'<polygon points="{pl}" fill="url(#c{i})" stroke="url(#c{i})" '
                    f'stroke-width="{round_w:.2f}" stroke-linejoin="round"/>')
    gx, gy = to(geo["glow"])
    cap = " ".join("%.2f,%.2f" % to(p) for p in geo["cap"])
    nl = chr(10)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
            f'width="{size}" height="{size}">' + nl
            + '  <defs>' + nl + '    ' + (nl + '    ').join(defs) + nl
            + f'    <radialGradient id="pool" gradientUnits="userSpaceOnUse" '
              f'cx="{gx:.2f}" cy="{gy:.2f}" r="{0.46 * k:.2f}">'
              f'<stop offset="0" stop-color="#FFFFFF" stop-opacity="{GLOW:.2f}"/>'
              f'<stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></radialGradient>' + nl
            + '  </defs>' + nl
            + '  ' + (nl + '  ').join(body) + nl
            + f'  <polygon points="{cap}" fill="url(#pool)" stroke="url(#pool)" '
              f'stroke-width="{round_w:.2f}" stroke-linejoin="round"/>' + nl
            + '</svg>' + nl)


def glyph(size: int = 24) -> tuple[str, str]:
    """The flat two-piece silhouette, for the rail and the book.

    A gradient cannot survive a 14px rail, and `currentColor` is the only way a
    glyph follows the ink it sits in. So the small surfaces get the CLEAVE
    ITSELF and nothing else: the cap's outline and the body's outline, the
    parting between them left open. Returns (cap points, body points).
    """
    geo = geometry(simple=True)
    to, _ = _fit(geo, size)
    return (" ".join("%.2f,%.2f" % to(p) for p in geo["cap"]),
            " ".join("%.2f,%.2f" % to(p) for p in geo["body"]))


#: Which cut each size gets. A test asserts the `.ico` still carries both.
#: 24 is here because Windows uses it for small toolbar and Alt-Tab contexts.
#: 30 AND 36 ARE NOT DECORATION: they are what the taskbar asks for at 125% and
#: 150% display scaling, and a missing entry means Windows scales a neighbour
#: into the slot - which is the softness the owner pointed at on 2026-09-13 and
#: which `test_the_icon_survives_being_small` has pinned ever since. The shelf
#: copy predates that lesson and shipped without them.
CUTS = {256: False, 128: False, 64: False, 48: True, 36: True, 32: True,
        30: True, 24: True, 16: True}


def _icns(detailed: Image.Image, path: Path) -> None:
    """ICNS with PNG-coded members, which is all macOS needs to read it."""
    members = [(b"ic10", 1024), (b"ic09", 512), (b"ic14", 512), (b"ic08", 256),
               (b"ic13", 256), (b"ic07", 128), (b"ic12", 64), (b"ic11", 32),
               (b"icp5", 32), (b"icp4", 16)]
    body = b""
    for tag, px in members:
        buf = io.BytesIO()
        detailed.resize((px, px), Image.LANCZOS).save(buf, "PNG")
        data = buf.getvalue()
        body += tag + struct.pack(">I", 8 + len(data)) + data
    path.write_bytes(b"icns" + struct.pack(">I", 8 + len(body)) + body)


def build() -> dict:
    detailed = cleave(SS, simple=False)
    #: The simple cut is drawn at 4x its largest use, not at 1024: the round
    #: joins and the widened gap are fractions of the canvas, so drawing it
    #: huge and shrinking it far would thin them back to nothing.
    simplified = cleave(192, simple=True)
    made = {s: (simplified if simple else detailed).resize((s, s), Image.LANCZOS)
            for s, simple in CUTS.items()}

    ICONS.mkdir(parents=True, exist_ok=True)
    FAVICON.parent.mkdir(parents=True, exist_ok=True)
    (ICONS / "icon.svg").write_text(svg(), encoding="utf-8", newline="\n")
    FAVICON.write_text(
        "<!-- THE CLEAVE, written by scripts/make_icon.py. Do not hand-edit: it\n"
        "     is the same geometry as src-tauri/icons/icon.svg on a 48 grid, and\n"
        "     the rail glyph in Icon.tsx is its flat silhouette. -->\n"
        + svg(48), encoding="utf-8", newline="\n")
    made[32].save(ICONS / "32x32.png")
    made[128].save(ICONS / "128x128.png")
    made[256].save(ICONS / "128x128@2x.png")
    detailed.save(ICONS / "icon.png")

    #: PER-SIZE ARTWORK IN ONE FILE. Pillow takes the base image plus
    #: `append_images` and picks whichever matches each requested size, so the
    #: simplified cut really does ship at 16/24/32/48 rather than a shrunk
    #: detailed one. That is the whole reason for two cuts.
    made[256].save(ICONS / "icon.ico", format="ICO",
                   sizes=[(s, s) for s in sorted(CUTS)],
                   append_images=[made[s] for s in sorted(CUTS) if s != 256])
    _icns(detailed, ICONS / "icon.icns")
    return made


if __name__ == "__main__":
    made = build()
    for size in sorted(made):
        print("  %3d  %s cut" % (size, "simplified" if CUTS[size] else "detailed"))
    cap, body = glyph(24)
    print("wrote", ICONS)
    print("wrote", FAVICON)
    print()
    print("--glyph, the 24 grid for Icon.tsx and the book's sprite:")
    print("  cap  ", cap)
    print("  body ", body)
