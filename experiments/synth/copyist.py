# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless==4.10.0.84", "numpy", "lxml", "pillow",
#   # the LMX reader (Delinearizer); score_to_lmx.py writes LMX with Zeus's pinned encoder
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""A staff of music drawn as a copyist might: verovio lays it out (every
symbol LMX has: key and time signatures, slurs, ties, tuplets, grace notes,
ornaments), then each symbol is redrawn by hand rules -- tilted oval
noteheads touching their stems, thick wavering beams, slanted stems, loose
slurs, wavy staff lines, jittered glyphs -- the whole sheared and warped,
inked onto paper cut from real staves, and cropped as compare.staff_crop
crops (the staff, 2.5 spaces above and below, a space each end).

The label is the LMX it was drawn from: nothing is added or left out.

    uv run experiments/synth/copyist.py IN.lmx OUT.png [--hand berlin] [--seed 1] [--width SPACES]
"""
import argparse
import copy
import io
import math
import random
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import resvg_py
import verovio

verovio.enableLog(verovio.LOG_OFF)
from lxml import etree
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lmx2xml import lmx_to_musicxml  # noqa: E402
from harvest_clefs import TRAIN  # noqa: E402

SVG = "http://www.w3.org/2000/svg"
XL = "http://www.w3.org/1999/xlink"
SP = 180  # verovio's staff space in its SVG units
DATA = Path.home() / ".cache/manuscript-labeler/zeus/dataL2"


@dataclass
class Hand:
    """A copyist's habits, each a range sampled per staff."""
    font: tuple = ("Petaluma", "Petaluma", "Leipzig", "Bravura")
    ss: tuple = (15, 19)                 # staff space, px
    width: tuple = (85, 160)             # staff length, spaces (when not given)
    slant: tuple = (4, 12)               # degrees, stems lean right
    nh_w: tuple = (0.45, 0.62)           # notehead half-width, spaces
    nh_h: tuple = (0.3, 0.42)            # notehead half-height
    nh_tilt: tuple = (15, 35)            # degrees
    stem_w: tuple = (0.09, 0.16)         # spaces
    stem_len: tuple = (0.9, 1.15)        # x engraved
    beam_th: tuple = (0.42, 0.6)         # spaces (engraved 0.5)
    beam_wobble: tuple = (0.05, 0.15)
    line_w: tuple = (0.06, 0.12)
    line_wave: tuple = (0.02, 0.1)       # staff-line waviness, spaces
    line_ink: tuple = (0.45, 0.85)       # staff lines' darkness against the notes'
    glyph_jit: tuple = (0.03, 0.1)       # spaces
    glyph_rot: tuple = (2, 8)            # degrees
    glyph_scale: tuple = (0.85, 1.05)
    warp: tuple = (0.05, 0.15)           # elastic warp amplitude, spaces
    ink: tuple = (40, 110)               # ink grey level
    blur: tuple = (0.4, 0.9)             # px
    hide_tuplet: tuple = (0.0, 1.0)      # chance a staff's tuplet numbers are left unwritten
    bare_start: tuple = (0.0, 0.0)       # chance the staff starts with no clef or key (continuation lines)
    real_clef: tuple = (0.8, 0.8)        # chance its opening clef is one of the copyist's own (harvest_clefs.py)


HANDS = {
    "generic": Hand(),
    # Berlin (KHM 602/603): small slanted heads, long thin stems, heavy short beams
    "berlin": Hand(ss=(14.5, 16.5), slant=(8, 16), nh_w=(0.45, 0.6), nh_h=(0.3, 0.4), nh_tilt=(25, 45),
                   stem_w=(0.08, 0.12), beam_th=(0.5, 0.65), width=(138, 156)),
    # Paris (RES 507), two hands: A writes vn1 and vc, B vn2 and va and leaves clef and key off
    # its continuation lines (the label keeps them: the reader must know them from the part)
    # (ruled small and long: 13.7 px a space, 176 spaces a staff, against Paris B's 18.6 and 116)
    "parisA": Hand(ss=(13, 14.5), slant=(0, 6), nh_w=(0.55, 0.7), nh_h=(0.42, 0.52), nh_tilt=(10, 25),
                   stem_w=(0.1, 0.16), beam_th=(0.45, 0.6), width=(170, 182)),
    "parisB": Hand(ss=(17, 19.5), slant=(-2, 5), nh_w=(0.5, 0.65), nh_h=(0.4, 0.5), nh_tilt=(5, 25),
                   stem_w=(0.07, 0.12), beam_th=(0.4, 0.55), width=(115, 130), bare_start=(0.8, 0.8)),
    # Vma: compact, fine pen
    "vma": Hand(ss=(18, 20), slant=(2, 8), nh_w=(0.5, 0.62), nh_h=(0.38, 0.46), stem_w=(0.07, 0.11),
                beam_th=(0.4, 0.55), width=(84, 98)),
}


def sample(h: Hand, rng: random.Random) -> dict:
    return {k: (rng.choice(v) if isinstance(v[0], str) else rng.uniform(*v)) for k, v in h.__dict__.items()}


# -- layout ---------------------------------------------------------------------------

def engrave(xml: str, font: str, width: float | None, squeeze: float = 0.9) -> etree._Element:
    """Verovio's engraving on one staff, justified to `width` staff spaces (never squeezed below
    `squeeze` of its natural width)."""
    xml = re.sub(r"<part-name>[^<]*</part-name>", "<part-name></part-name>", xml)
    xml = re.sub(r"<part-abbreviation>[^<]*</part-abbreviation>", "", xml)
    base = {"font": font, "adjustPageHeight": True, "header": "none", "footer": "none",
            "pageMarginLeft": 0, "pageMarginRight": 0, "pageMarginTop": 0, "pageMarginBottom": 0,
            "svgViewBox": True, "scale": 100, "staffLineWidth": 0.12, "stemWidth": 0.15}

    def run(**opts):
        tk = verovio.toolkit()
        tk.setOptions({**base, **opts})
        if not tk.loadData(xml):
            raise ValueError("verovio could not read the MusicXML")
        svg = etree.fromstring(tk.renderToSVG(1).encode())
        one = tk.getPageCount() == 1 and sum(_cls(g, "system") for g in svg.iter(f"{{{SVG}}}g")) == 1
        x0, _, x1, _ = staff_box(svg)
        return svg, (x1 - x0) / SP, one

    svg, natural, _ = run(breaks="none")
    if width is None:
        return svg
    want = max(width, natural * squeeze)
    pw = want * 19
    for _ in range(3):  # page width to staff length is nearly linear: correct, and widen if it wrapped
        new, got, one = run(breaks="encoded", pageWidth=int(pw), minLastJustification=0)
        if one:
            svg = new
            if abs(got - want) < 0.03 * want:
                break
            pw *= want / got
        else:
            pw *= 1.15
            want *= 1.15
    return svg


# -- redrawing ------------------------------------------------------------------------

def _cls(el, name):
    return name in (el.get("class") or "").split()


def _nums(s):
    return [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", s)]


def _use_xy(use):
    m = re.search(r"translate\(([-\d.]+),\s*([-\d.]+)\)", use.get("transform", ""))
    return float(m.group(1)), float(m.group(2))


def redraw(svg, p: dict, rng: random.Random):
    """Change the engraving in place into hand-drawn shapes."""
    inner = svg.find(f"{{{SVG}}}svg")
    defs = svg.find(f"{{{SVG}}}defs")
    g = lambda lo, hi: rng.uniform(lo, hi)

    # notehead width in this font, from a note whose stem is up: stem x is the head's right edge
    head_w = 1.18 * SP
    for note in inner.iter(f"{{{SVG}}}g"):
        if not _cls(note, "note"):
            continue
        u = note.find(f".//{{{SVG}}}g[@class='notehead']/{{{SVG}}}use")
        st = note.find(f".//{{{SVG}}}g[@class='stem']/{{{SVG}}}path")
        if u is not None and st is not None:
            x0, y0 = _use_xy(u)
            sx, sy1, _, sy2 = _nums(st.get("d"))
            if sy2 < sy1 and sx > x0:
                head_w = sx - x0
                break

    rx, ry = p["nh_w"] * SP, p["nh_h"] * SP

    # staff lines: wavy, own ink
    for staff in inner.iter(f"{{{SVG}}}g"):
        if not _cls(staff, "staff"):
            continue
        for path in staff.findall(f"{{{SVG}}}path"):
            x1, y, x2, _ = _nums(path.get("d"))
            n = max(2, int((x2 - x1) / (6 * SP)))
            pts = [(x1 + (x2 - x1) * i / n, y + g(-1, 1) * p["line_wave"] * SP) for i in range(n + 1)]
            d = f"M{pts[0][0]:.0f} {pts[0][1]:.0f}" + "".join(
                f" Q{(a[0] + b[0]) / 2:.0f} {(a[1] + b[1]) / 2 + g(-1, 1) * p['line_wave'] * SP:.0f} {b[0]:.0f} {b[1]:.0f}"
                for a, b in zip(pts, pts[1:]))
            path.set("d", d)
            path.set("stroke-width", f"{p['line_w'] * SP * g(0.85, 1.15):.0f}")
            path.set("stroke", "var(--line)")
            path.set("class", "staffline")

    # stems: jittered length and width; remember where they are for the heads
    stems = {}
    for st in inner.iter(f"{{{SVG}}}g"):
        if not _cls(st, "stem"):
            continue
        path = st.find(f"{{{SVG}}}path")
        if path is None:
            continue
        x, y1, _, y2 = _nums(path.get("d"))
        y2b = y1 + (y2 - y1) * (p["stem_len"] if st.getparent().find(f".//{{{SVG}}}g[@class='beam']") is None else 1)
        path.set("d", f"M{x:.0f} {y1:.0f} L{x + g(-0.03, 0.03) * SP:.0f} {y2b:.0f}")
        path.set("stroke-width", f"{p['stem_w'] * SP * g(0.8, 1.2):.0f}")
        path.set("stroke-linecap", "round")
        stems[st.getparent()] = (x, y1, y2)

    # noteheads: tilted ovals that touch their stem
    def stem_of(el):
        while el is not None:
            if el in stems:
                return stems[el]
            for c in el:
                if c in stems:
                    return stems[c]
            el = el.getparent()
            if el is not None and (_cls(el, "beam") or _cls(el, "layer")):
                return None
        return None

    for nh in list(inner.iter(f"{{{SVG}}}g")):
        if not _cls(nh, "notehead"):
            continue
        u = nh.find(f"{{{SVG}}}use")
        if u is None:
            continue
        code = u.get(f"{{{XL}}}href", "")[1:5]
        if code not in ("E0A4", "E0A3", "E0A2"):
            continue  # other heads (crosses, slashes) keep the font's glyph
        x0, y = _use_xy(u)
        note = nh.getparent()
        s = stem_of(note) if not _cls(note, "chord") else None
        if s is None and _cls(note.getparent(), "chord"):
            s = stems.get(note.getparent())
        a, b = rx * g(0.9, 1.1), ry * g(0.9, 1.1)
        tilt = p["nh_tilt"] * g(0.8, 1.2)
        if s is not None:
            sx = s[0]
            left = x0 + head_w / 2 < sx  # head to the left of its stem
            reach = math.hypot(a * math.cos(math.radians(tilt)), b * math.sin(math.radians(tilt))) * 0.92
            cx = sx - reach if left else sx + reach
        else:
            cx = x0 + head_w / 2
        cy = y + g(-0.05, 0.05) * SP
        el = etree.SubElement(nh, f"{{{SVG}}}ellipse", cx=f"{cx:.0f}", cy=f"{cy:.0f}", rx=f"{a:.0f}", ry=f"{b:.0f}",
                              transform=f"rotate({-tilt:.1f} {cx:.0f} {cy:.0f})")
        if code != "E0A4":  # hollow: a pen ring, thicker at the sides
            el.set("fill", "none")
            el.set("stroke", "currentColor")
            el.set("stroke-width", f"{0.13 * SP * g(0.8, 1.3):.0f}")
            if code == "E0A2":
                el.set("rx", f"{a * 1.25:.0f}")
        nh.remove(u)

    # beams: thicker, one slope error per beam, a little wobble
    for bm in inner.iter(f"{{{SVG}}}g"):
        if not _cls(bm, "beam"):
            continue
        dy = g(-1, 1) * p["beam_wobble"] * SP
        for poly in bm.findall(f"{{{SVG}}}polygon"):
            v = _nums(poly.get("points"))
            pts = list(zip(v[0::2], v[1::2]))
            if len(pts) != 4:
                continue
            (xa, ya), (xb, yb), (xc, yc), (xd, yd) = pts
            mid_top, mid_bot = (ya + yb) / 2, (yc + yd) / 2
            grow = min((p["beam_th"] / 0.5 - 1) * (yd - ya) / 2, 0.08 * SP)  # keep a gap between beams
            w = lambda: g(-1, 1) * p["beam_wobble"] * SP * 0.5
            new = [(xa, ya - grow + w()), (xb, yb - grow + dy + w()), (xc, yc + grow + dy + w()), (xd, yd + grow + w())]
            poly.set("points", " ".join(f"{x:.0f},{y:.0f}" for x, y in new))

    # slurs and ties: control points loosened
    for sl in inner.iter(f"{{{SVG}}}g"):
        if not (_cls(sl, "slur") or _cls(sl, "tie")):
            continue
        for path in sl.findall(f"{{{SVG}}}path"):
            v = _nums(path.get("d"))
            if len(v) < 14:
                continue
            k = p["glyph_jit"] * SP * 3
            v = [x + g(-k, k) if i % 2 else x + g(-k / 2, k / 2) for i, x in enumerate(v)]
            path.set("d", "M{:.0f},{:.0f} C{:.0f},{:.0f} {:.0f},{:.0f} {:.0f},{:.0f} C{:.0f},{:.0f} {:.0f},{:.0f} {:.0f},{:.0f}".format(*v[:14]))

    # tuplet numbers: copyists often leave them out (the rhythm, and so the label, is unchanged)
    if rng.random() < p["hide_tuplet"]:
        for tn in list(inner.iter(f"{{{SVG}}}g")):
            if _cls(tn, "tupletNum") or _cls(tn, "tupletBracket"):
                tn.getparent().remove(tn)

    # continuation lines: no clef or key at the start
    if rng.random() < p["bare_start"]:
        first = inner.find(f".//{{{SVG}}}g[@class='measure']")
        for kind in ("clef", "keySig"):
            el = first.find(f".//{{{SVG}}}g[@class='{kind}']") if first is not None else None
            if el is not None:
                el.getparent().remove(el)

    # glyphs (clefs, rests, flags, accidentals, dots, numbers, ornaments): jittered
    for u in list(inner.iter(f"{{{SVG}}}use")):
        t = u.get("transform", "")
        m = re.match(r"translate\(([-\d.]+),\s*([-\d.]+)\)\s*scale\(([-\d.]+),\s*([-\d.]+)\)", t)
        if not m:
            continue
        x, y, sx, sy = map(float, m.groups())
        j = p["glyph_jit"] * SP
        sc = p["glyph_scale"] * g(0.95, 1.05)
        u.set("transform", f"translate({x + g(-j, j):.0f}, {y + g(-j, j):.0f}) rotate({g(-1, 1) * p['glyph_rot']:.1f}) "
                           f"scale({sx * sc:.3f}, {sy * sc:.3f})")

    # bar lines: lean a little
    for bl in inner.iter(f"{{{SVG}}}g"):
        if not _cls(bl, "barLine"):
            continue
        for path in bl.findall(f"{{{SVG}}}path"):
            v = _nums(path.get("d"))
            if len(v) == 4:
                x, y1, _, y2 = v
                path.set("d", f"M{x + g(-0.1, 0.1) * SP:.0f} {y1 - g(0, 0.15) * SP:.0f} L{x + g(-0.1, 0.1) * SP:.0f} {y2 + g(0, 0.15) * SP:.0f}")
                path.set("stroke-width", f"{p['stem_w'] * SP * g(1.0, 1.6):.0f}")


def staff_box(svg):
    """(x0, top line y, x1, bottom line y) of the staff, in SVG units."""
    ys, xs = [], []
    for path in svg.iter(f"{{{SVG}}}path"):
        if path.get("class") == "staffline" or (_cls(path.getparent(), "staff") and path.get("d", "").startswith("M")
                                                 and len(_nums(path.get("d"))) == 4):
            v = _nums(path.get("d"))
            xs += [v[0], v[-2]]
            ys.append(v[1])
    return min(xs), min(ys), max(xs), max(ys)


# -- ink and paper -------------------------------------------------------------------

# paper and margin ink come only from D1's training staves, never the practice exam's (KHM 602 II, Op. 48/5 I)
_REAL = sorted(DATA / f"{k}.jpg" for t in TRAIN for k in (DATA / f"samples.{t}.txt").read_text().split())


def paper(h, w, rng):
    g = cv2.imread(str(rng.choice(_REAL)), cv2.IMREAD_GRAYSCALE)
    bg = cv2.GaussianBlur(cv2.dilate(g, np.ones((11, 11), np.uint8)), (0, 0), 6)  # the ink lifted off
    bg = cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    return bg, g


def warp(a, amp, wave, rng):
    """Smooth random displacement of every stroke (amp, wave in px)."""
    h, w = a.shape
    nr = np.random.default_rng(rng.randrange(1 << 30))
    sh = (max(2, int(h / wave) + 2), max(2, int(w / wave) + 2))
    dx = cv2.resize(nr.normal(0, amp, sh).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    dy = cv2.resize(nr.normal(0, amp, sh).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    mx, my = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return cv2.remap(a, mx + dx, my + dy, cv2.INTER_LINEAR, borderValue=0)


WORDS = ["pia", "for", "p", "f", "pp", "ff", "dolce", "dol", "cresc", "Cres", "poco", "pizz", "arco", "Solo", "tr",
         "sf", "fp", "rf", "mezza voce", "con sordini", "Allegro", "Largo", "Minuetto", "Trio", "D.C.", "Fine", "Va",
         "Violino", "Viola", "Basso", "Tutti", "smorz", "ten"]


def distract(a, ss, rng):
    """What the reader must learn to ignore, in the margins: words (dynamics, tempo, names) and the
    ink of the staves above and below. Neither is in LMX, so the label is unchanged."""
    h, w = a.shape
    for _ in range(rng.choice([0, 0, 1, 1, 2, 3])):
        word = rng.choice(WORDS)
        scale = ss / 20 * rng.uniform(0.9, 1.7)
        th = max(1, int(round(ss / 12 * rng.uniform(0.8, 1.4))))
        (tw, tht), _ = cv2.getTextSize(word, cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, scale, th)
        if tw >= w - 2:
            continue
        x = rng.randrange(0, w - tw)
        y = int(rng.uniform(7.0, 8.9) * ss) if rng.random() < 0.7 else int(rng.uniform(0.2, 2.2) * ss) + tht
        layer = np.zeros_like(a)
        cv2.putText(layer, word, (x, min(h - 1, y)), cv2.FONT_HERSHEY_SCRIPT_SIMPLEX, scale, 1.0, th, cv2.LINE_AA)
        sh = np.float32([[1, -rng.uniform(0.1, 0.35), 0], [0, 1, 0]])  # cursive leans
        sh[0, 2] = -sh[0, 1] * y
        np.maximum(a, cv2.warpAffine(layer, sh, (w, h)), out=a)
    if rng.random() < 0.6:  # a neighbour's notes reaching into the margin
        o = cv2.imread(str(rng.choice(_REAL)), cv2.IMREAD_GRAYSCALE)
        o = cv2.resize(o, (w, int(o.shape[0] * w / o.shape[1])), interpolation=cv2.INTER_AREA)
        oss = o.shape[0] / 9
        d = np.clip((1 - o.astype(np.float32) / 255 - 0.3) / 0.7, 0, 1)
        k = int(rng.uniform(1.0, 2.2) * ss)
        if rng.random() < 0.5:   # its bottom margin over our top
            src = d[int(9 * oss) - k:int(9 * oss)]
            dst = a[:src.shape[0]]
        else:                    # its top margin under our bottom
            src = d[:k]
            dst = a[h - src.shape[0]:]
        n = min(len(src), len(dst))
        np.maximum(dst[:n], src[:n] * rng.uniform(0.7, 1.0), out=dst[:n])


def check(svg, lmx: str, xml: str):
    """Verovio drew every note, rest and beamed group there is (it misreads a few beamed chords), or ValueError.
    Notes and rests are counted in the LMX; beamed groups (a primary beam's begin) in the MusicXML made from it."""
    toks = lmx.split()
    groups = len(re.findall(r'<beam number="1">begin</beam>', re.sub(r"<note>(?:(?!</note>).)*<chord ?/>.*?</note>", "", xml, flags=re.S)))
    want = (sum(bool(re.match(r"[A-G]\d$", t)) for t in toks), toks.count("rest"), groups)
    got = [0, 0, 0]
    for g in svg.iter(f"{{{SVG}}}g"):
        c = (g.get("class") or "").split()
        got[0] += "note" in c
        got[1] += "rest" in c or "mRest" in c
        got[2] += "beam" in c
    if tuple(got) != want:
        raise ValueError(f"drew {got[0]} notes, {got[1]} rests, {got[2]} beams; the LMX has {want}")


CLEFS = Path.home() / ".cache/manuscript-labeler/zeus/glyphs/clefs"
_clefs: dict = {}


def clef_library(hand: str, kind: str) -> list:
    """The copyist's clefs of this kind (harvest_clefs.py), as ink; for "generic", every hand's."""
    key = (hand, kind)
    if key not in _clefs:
        hands = [hand] if hand != "generic" else [d.name for d in CLEFS.iterdir()] if CLEFS.exists() else []
        inks = [1 - cv2.imread(str(f), cv2.IMREAD_GRAYSCALE).astype(np.float32) / 255
                for h in hands for f in sorted((CLEFS / h / kind).glob("*.png"))]
        # full strength: the harvest lifted the paper and lines off, and the ink's contrast with them
        _clefs[key] = [np.clip(i / max(np.percentile(i[i > 0.05], 90), 0.1), 0, 1) ** 0.6 if (i > 0.05).any() else i
                       for i in inks]
    return _clefs[key]


def take_clef(svg, lmx: str, hand: str, p: dict, rng: random.Random):
    """If the copyist's own opening clef is to be drawn: remove the font's, and return (its ink, x where
    it starts and the room it has, both in SVG units); else None."""
    kind = next((t.split(":")[1] for t in lmx.split() if t.startswith("clef:")), None)
    lib = clef_library(hand, kind) if kind else []
    first = svg.find(f".//{{{SVG}}}g[@class='measure']")
    el = first.find(f".//{{{SVG}}}g[@class='clef']") if first is not None else None
    if not lib or el is None or rng.random() >= p["real_clef"]:
        return None
    x = _use_xy(el.find(f"{{{SVG}}}use"))[0]
    nxt = [_use_xy(u)[0] for u in first.iter(f"{{{SVG}}}use") if _use_xy(u)[0] > x + 0.5 * SP and not
           any(_cls(a, "clef") for a in u.iterancestors())]
    room = (min(nxt) if nxt else x + 3 * SP) - x - 0.15 * SP
    el.getparent().remove(el)
    return rng.choice(lib), x, room


def paste_clef(a: np.ndarray, clef, cx0: float, ss: float, rng: random.Random):
    """The copyist's clef into the ink, the staff where the crop's is (both are nine spaces high).
    clef: (ink, x, room) or (ink, x, room, dy): dy moves it up (negative) or down, in spaces."""
    ink, x, room = clef[:3]
    dy = clef[3] if len(clef) > 3 else 0
    f = a.shape[0] / ink.shape[0]
    w = ink.shape[1] * f
    fx = min(1.0, max(0.75, room / SP * ss / w))  # narrowed a little if it would run into what follows
    patch = cv2.resize(ink, (max(1, int(w * fx)), a.shape[0]), interpolation=cv2.INTER_AREA)
    k = int(round(dy * ss))
    if k:
        patch = np.roll(patch, k, axis=0)
        if k < 0:
            patch[k:] = 0  # what rolled round from the top
        else:
            patch[:k] = 0
    left = int(round((x - cx0) / SP * ss))
    right = min(a.shape[1], left + patch.shape[1])
    if left < 0 or right <= left:
        return
    np.maximum(a[:, left:right], patch[:, : right - left] * rng.uniform(0.8, 1.0), out=a[:, left:right])


# -- clef changes inside the staff (draw(..., changes=True); dataS3's sets were drawn without) -------------

# per hand: the chance a change at a bar line is written after it (else before, as engravers do), and the
# chance the key is written again after the new clef (Berlin and Vma do, Paris doesn't; the label never has it)
CHANGE_HABITS = {"berlin": (0.95, 0.85), "vma": (0.95, 0.8), "parisA": (0.9, 0.1), "parisB": (0.9, 0.1),
                 "generic": (0.8, 0.5)}
CLEF_GLYPH = {"E050": "G", "E07A": "G", "E05C": "C", "E07B": "C", "E062": "F", "E07C": "F"}


def mark_changes(xml: str, hand: str, rng: random.Random) -> str:
    """The MusicXML's clef changes at a bar line marked to be drawn after it, and the key in force
    written again with some of them. Only the drawing changes; the label is the LMX."""
    root = etree.fromstring(xml.encode())
    after, again = CHANGE_HABITS[hand]
    fifths = None
    for i, m in enumerate(root.iter("measure")):
        at = m[0] if len(m) and m[0].tag == "attributes" else None
        clef = at.find("clef") if at is not None else None
        if i and clef is not None and rng.random() < after:
            clef.set("after-barline", "yes")
            if fifths not in (None, "0") and at.find("key") is None and rng.random() < again:
                key = etree.Element("key")
                etree.SubElement(key, "fifths").text = fifths
                at.insert(1 if at[0].tag == "divisions" else 0, key)
        for k in m.iter("key"):
            fifths = k.findtext("fifths")
    return etree.tostring(root, encoding="unicode")


_KEYPOS: dict = {}


def key_offsets(sign: str, line: int, fifths: int) -> list:
    """Each accidental of the key signature's height below the top staff line (SVG units), in this clef:
    verovio's own placing, from a one-bar score."""
    k = (sign, line, fifths)
    if k not in _KEYPOS:
        xml = ('<?xml version="1.0"?><score-partwise version="3.1"><part-list><score-part id="P1"><part-name/>'
               '</score-part></part-list><part id="P1"><measure number="1"><attributes><divisions>1</divisions>'
               f'<key><fifths>{fifths}</fifths></key><clef><sign>{sign}</sign><line>{line}</line></clef>'
               '</attributes><note><rest/><duration>4</duration><type>whole</type></note></measure></part>'
               '</score-partwise>')
        tk = verovio.toolkit()
        tk.setOptions({"breaks": "none", "svgViewBox": True, "header": "none", "footer": "none", "scale": 100})
        tk.loadData(xml)
        svg = etree.fromstring(tk.renderToSVG(1).encode())
        _, top, _, _ = staff_box(svg)
        ks = svg.find(f".//{{{SVG}}}g[@class='keySig']")
        _KEYPOS[k] = [_use_xy(u)[1] - top for u in ks.iter(f"{{{SVG}}}use")] if ks is not None else []
    return _KEYPOS[k]


def _set_xy(use, x, y, scale=1.0):
    t = use.get("transform", "")
    m = re.search(r"scale\(([-\d.]+),\s*([-\d.]+)\)", t)
    sx, sy = (float(m.group(1)), float(m.group(2))) if m else (1.0, 1.0)
    use.set("transform", f"translate({x:.0f}, {y:.0f}) scale({sx * scale:.3f}, {sy * scale:.3f})")


def change_clefs(svg) -> list:
    """[(clef <g>, sign, line)] of the clefs inside the staff (verovio puts them in a layer), in order."""
    _, top, _, _ = staff_box(svg)
    out = []
    for layer in svg.iter(f"{{{SVG}}}g"):
        if not _cls(layer, "layer"):
            continue
        for c in layer.iter(f"{{{SVG}}}g"):
            u = c.find(f"{{{SVG}}}use") if _cls(c, "clef") else None
            if u is None:
                continue
            sign = CLEF_GLYPH.get(u.get(f"{{{XL}}}href", "")[1:5])
            if sign:
                out.append((c, sign, 5 - round((_use_xy(u)[1] - top) / SP)))
    return out


def copyist_changes(svg, rng: random.Random):
    """Changes drawn as the copyists draw them: about full size (verovio draws them small), and a key
    written again after a change goes after the new clef, in its positions (verovio puts it before)."""
    _, top, _, _ = staff_box(svg)
    for c, sign, line in change_clefs(svg):
        u = c.find(f"{{{SVG}}}use")
        grow = rng.uniform(1.05, 1.25)
        xc, yc = _use_xy(u)
        _set_xy(u, xc, yc, grow)
        staff = next((a for a in c.iterancestors() if _cls(a, "staff")), None)
        ks = staff.find(f"{{{SVG}}}g[@class='keySig']") if staff is not None else None
        layer = next((a for a in c.iterancestors() if _cls(a, "layer")), None)
        first = next((e for e in layer.iter(f"{{{SVG}}}g") if e is c or any(
            _cls(e, k) for k in ("note", "rest", "chord", "mRest", "space", "mSpace"))), None) if layer is not None else None
        if ks is None or first is not c or any(_cls(e, "clef") for e in staff if e is not layer):
            continue  # only a clef that opens its bar (verovio may put it in the first beam), never in the opening bar
        accs = list(ks.iter(f"{{{SVG}}}use"))
        codes = {a.get(f"{{{XL}}}href", "")[1:5] for a in accs}
        xs = [_use_xy(a)[0] for a in accs]
        if not accs or len(codes) != 1 or codes - {"E262", "E260"} or min(xs) > xc:
            continue  # a key with naturals (a real change), or none before this clef
        fifths = len(accs) * (1 if codes == {"E262"} else -1)
        offs = key_offsets(sign, line, fifths)
        if len(offs) != len(accs):
            continue
        x0, gap = min(xs), xc - (max(xs) + 0.8 * SP)
        _set_xy(u, x0, yc, 1.0)
        shift = 2.1 * SP * grow + max(gap, 0.3 * SP)
        for a, x, off in zip(sorted(accs, key=lambda a: _use_xy(a)[0]), sorted(xs), offs):
            _set_xy(a, x + shift, top + off)


def inner_clef(ink: np.ndarray) -> np.ndarray:
    """A harvested clef cleaned for use inside the staff, where the cut's leftovers would show: faint
    residue (lifted staff lines, paper) and small fragments taken off, and trimmed to its ink."""
    out = np.where(ink < 0.25, 0, ink).astype(np.float32)
    n, lab, stats, _ = cv2.connectedComponentsWithStats((out > 0).astype(np.uint8), connectivity=8)
    if n < 2:
        return ink
    area = stats[1:, cv2.CC_STAT_AREA]
    keep = np.zeros(n, bool)
    peak = np.zeros(n, np.float32)
    np.maximum.at(peak, lab.ravel(), out.ravel())
    # big strokes, and small dark ones (a bass clef's dots); residue is faint
    keep[1:] = (area >= 0.08 * area.max()) | ((area >= 0.01 * area.max()) & (peak[1:] >= 0.7))
    out[~keep[lab]] = 0
    cols = np.flatnonzero((out > 0.3).sum(0) >= 2)
    if len(cols) < 3:
        return ink
    out = out[:, max(0, cols[0] - 1):cols[-1] + 2]
    if (out > 0.5).mean() < 0.14:  # hairline cuts (Vma's treble clefs) blur to grey: thicken them a little
        out = np.maximum(out, 0.8 * cv2.dilate(out, np.ones((2, 2), np.uint8)))
    return np.clip(out / 0.75, 0, 1)


def take_clefs(svg, lmx: str, hand: str, p: dict, rng: random.Random) -> list:
    """take_clef for every clef on the staff, the opening one and the changes: each to be drawn in the
    copyist's own hand (removed from the SVG; returned as (ink, x, room, dy)) with chance real_clef.
    A tenor clef is the copyist's alto clef a space higher."""
    _, top, _, _ = staff_box(svg)
    first = svg.find(f".//{{{SVG}}}g[@class='measure']")
    opening = first.find(f".//{{{SVG}}}g[@class='clef']") if first is not None else None
    kind = next((t.split(":")[1] for t in lmx.split() if t.startswith("clef:")), None)
    found = []
    if opening is not None and kind and opening.getparent() is not None and not _cls(opening.getparent(), "layer"):
        found.append((opening, kind[0], int(kind[1]), False))
    found += [(c, s, l, True) for c, s, l in change_clefs(svg)]
    # what follows each clef: glyphs, and noteheads (ellipses after redraw)
    after = [_use_xy(u)[0] for u in svg.iter(f"{{{SVG}}}use") if not any(_cls(a, "clef") for a in u.iterancestors())]
    after += [float(e.get("cx")) - float(e.get("rx")) for e in svg.iter(f"{{{SVG}}}ellipse")]
    out = []
    for el, sign, line, inside in found:
        k, dy = f"{sign}{line}", 0
        if k == "C4":
            k, dy = "C3", -1
        lib = clef_library(hand, k)
        if not lib or rng.random() >= p["real_clef"]:
            continue
        x = _use_xy(el.find(f"{{{SVG}}}use"))[0]
        nxt = [v for v in after if v > x + 0.5 * SP]
        room = (min(nxt) if nxt else x + 3 * SP) - x - 0.15 * SP
        el.getparent().remove(el)
        ink = rng.choice(lib)
        out.append((inner_clef(ink) if inside else ink, x, room, dy))
    return out


def plain(svg, ss: float) -> np.ndarray:
    """An SVG staff (a copy) rastered black on white at ss px a space, cropped as draw() crops: for showing stages."""
    svg = copy.deepcopy(svg)
    inner = svg.find(f"{{{SVG}}}svg")
    x0, top, x1, bot = staff_box(svg)
    cx0, cy0, cw, ch = x0 - SP, top - 2.5 * SP, (x1 - x0) + 2 * SP, (bot - top) + 5 * SP
    inner.set("viewBox", f"{cx0:.0f} {cy0:.0f} {cw:.0f} {ch:.0f}")
    W, H = int(cw / SP * ss), int(ch / SP * ss)
    for el in (svg, inner):
        el.set("width", str(W))
        el.set("height", str(H))
    svg.set("viewBox", f"0 0 {W} {H}")
    inner.set("preserveAspectRatio", "none")
    text = etree.tostring(svg).decode().replace('stroke="var(--line)"', 'stroke="#555"')
    png = resvg_py.svg_to_bytes(svg_string=text, width=W, height=H, background="white")
    return np.asarray(Image.open(io.BytesIO(bytes(png))).convert("L"))


def on_white(a: np.ndarray, li: np.ndarray) -> np.ndarray:
    return (255 * (1 - np.clip(np.maximum(a, 0.55 * li), 0, 1))).astype(np.uint8)


def draw(lmx: str, hand: str = "generic", seed: int = 0, width: float | None = None, return_params=False,
         stages: dict | None = None, changes: bool = False):
    """width: the staff's length in staff spaces (a real staff's, to match it); else the hand's.
    stages: if a dict, it gets each stage's image (engraved, redrawn, warped, margins), for showing how it's made.
    changes: clef changes inside the staff drawn as the copyists draw them (mark_changes, copyist_changes),
    each clef, not just the opening one, possibly the copyist's own (gen_clefs.py; off for dataS3's sets)."""
    rng = random.Random(seed)
    p = sample(HANDS[hand], rng)
    xml = lmx_to_musicxml(lmx)
    if changes:
        xml = mark_changes(xml, hand, rng)
    svg = engrave(xml, p["font"], width or p["width"])
    check(svg, lmx, xml)
    if changes:
        copyist_changes(svg, rng)
    if stages is not None:
        stages["engraved"] = plain(svg, p["ss"])
    redraw(svg, p, rng)
    clefs = take_clefs(svg, lmx, hand, p, rng) if changes else [take_clef(svg, lmx, hand, p, rng)]
    if stages is not None:
        stages["redrawn"] = plain(svg, p["ss"])
    inner = svg.find(f"{{{SVG}}}svg")
    x0, top, x1, bot = staff_box(svg)
    # crop as compare.staff_crop: 2.5 spaces above and below, one space each end
    cx0, cy0, cw, ch = x0 - SP, top - 2.5 * SP, (x1 - x0) + 2 * SP, (bot - top) + 5 * SP
    # shear the music about the staff's middle so stems lean right (lines stay level)
    t = math.tan(math.radians(p["slant"]))
    mid = (top + bot) / 2
    holder = etree.SubElement(inner, f"{{{SVG}}}g", transform=f"translate({t * mid:.1f},0) skewX({-p['slant']:.2f})")
    for c in [c for c in inner if c is not holder]:
        holder.append(c)
    inner.set("viewBox", f"{cx0:.0f} {cy0:.0f} {cw:.0f} {ch:.0f}")
    os_ = 2  # draw at twice the size, then shrink
    W, H = int(cw / SP * p["ss"] * os_), int(ch / SP * p["ss"] * os_)
    svg.set("viewBox", f"0 0 {W} {H}")
    svg.set("width", str(W))
    svg.set("height", str(H))
    inner.set("width", str(W))
    inner.set("height", str(H))
    inner.set("preserveAspectRatio", "none")
    # one raster, staff lines in magenta under black notes: red is the notes' ink, red less green the lines'
    text = etree.tostring(svg).decode().replace('stroke="var(--line)"', 'stroke="#ff00ff"')
    png = resvg_py.svg_to_bytes(svg_string=text, width=W, height=H, background="white")
    rgb = np.asarray(Image.open(io.BytesIO(bytes(png))).convert("RGB")).astype(np.float32) / 255
    a = 1 - rgb[..., 0]
    li = np.clip(rgb[..., 0] - rgb[..., 1], 0, 1)
    ss2 = p["ss"] * os_
    wv = rng.uniform(2.5, 5) * ss2
    a = warp(a, p["warp"] * ss2, wv, rng)
    li = warp(li, p["warp"] * ss2 * 0.5, wv * 2, rng)
    a = cv2.resize(a, (W // os_, H // os_), interpolation=cv2.INTER_AREA)
    li = cv2.resize(li, (W // os_, H // os_), interpolation=cv2.INTER_AREA)
    h, w = a.shape
    if stages is not None:
        stages["warped"] = on_white(a, li)
    for clef in clefs:
        if clef is not None:
            paste_clef(a, clef, cx0, p["ss"], rng)
    distract(a, p["ss"], rng)
    if stages is not None:
        stages["margins"] = on_white(a, li)
    a = cv2.GaussianBlur(a, (0, 0), p["blur"])
    li = cv2.GaussianBlur(li, (0, 0), p["blur"])
    bg, other = paper(h, w, rng)
    if rng.random() < 0.5:  # show-through from the other side
        o = 1 - cv2.GaussianBlur(cv2.resize(cv2.flip(other, 1), (w, h)), (0, 0), 2.5).astype(np.float32) / 255
        bg = bg - rng.uniform(4, 12) * np.clip(o - 0.15, 0, 1)
    ink = p["ink"]
    line_ink = ink + (255 - ink) * (1 - p["line_ink"])
    out = bg * (1 - np.clip(li, 0, 1)) + line_ink * np.clip(li, 0, 1)
    out = out * (1 - np.clip(a, 0, 1)) + ink * np.clip(a, 0, 1)
    out += np.random.default_rng(seed).normal(0, 3, out.shape)
    out = np.clip(out, 0, 255)
    out = np.clip(out / max(np.percentile(out, 90), 1) * 255, 0, 255).astype(np.uint8)
    ok, buf = cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, rng.randint(70, 92)])
    img = cv2.imdecode(buf, cv2.IMREAD_GRAYSCALE)
    return (img, p) if return_params else img


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("out")
    ap.add_argument("--hand", default="generic", choices=sorted(HANDS))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--width", type=float, help="the staff's length in staff spaces (else the hand's)")
    a = ap.parse_args()
    img, p = draw(Path(a.src).read_text(), a.hand, a.seed, width=a.width, return_params=True)
    cv2.imwrite(a.out, img)
    print(a.out, img.shape, p["font"])
