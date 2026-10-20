# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless==4.10.0.84", "numpy", "lxml", "pillow",
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""Training windows for Segment Anything with perfect masks: staves drawn as copyist.draw draws them (the same
steps, in Petaluma, the copyist's own rests pasted in), and beside each drawing a second one in which every symbol
is its own flat colour, warped by the same displacement, so each symbol's mask is exactly its ink.

Rests: no font has the copyists' quarter rest (a sideways S), so the font's quarter, eighth and 16th rests are
replaced by the hand's own, cut from its pages (segment.py) and kept by curate.py, staff-line remnants lifted.

Writes sam_data.py's format (OUT/<name>_w<i>.npz: image, kinds, prompts, masks), one window per pair of bars, so
sam_train.py trains on it unchanged.

    uv run experiments/synth/sam_synth.py LMX_DIR_OR_LIST --glyphs GLYPHS/berlin --hand berlin --out DIR [--n 500]
        [--fonts Petaluma,Petaluma,Leland,Gootville,Leipzig,Bravura]
    uv run experiments/synth/sam_synth.py ONE.lmx --glyphs GLYPHS/berlin --sheet OUT.png   # look at one
    ... --plain --fonts Leipzig,Bravura,Gootville,Leland,Petaluma   # out of the box: Verovio's fonts as engraved
"""
import argparse
import copy
import io
import json
import math
import random
import sys
from pathlib import Path

import cv2
import numpy as np
import resvg_py
from lxml import etree
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import copyist  # noqa: E402
from copyist import SP, SVG, XL, _cls  # noqa: E402

# what each drawn element is called in the training windows (sam_data.py's kinds)
KINDS = {"notehead": "head", "stem": "stem", "flag": "flag", "dots": "dot", "accid": "accidental", "rest": "rest",
         "barLine": "barline", "slur": "slur", "tie": "slur", "tupletNum": "tuplet", "trill": "trill", "beam": "beam"}
RESTS = {"E4E5": "quarter", "E4E6": "eighth", "E4E7": "16th"}
DRAWN = ("path", "ellipse", "polygon", "use", "rect", "circle", "line", "polyline")


def rest_library(glyphs: Path) -> dict:
    """The hand's own rests by kind, as ink (0..1), staff-line remnants lifted (thin rows of long runs)."""
    cur = json.loads((glyphs / "curated.json").read_text())
    out = {}
    for f, v in cur.items():
        k = v["kind"]
        if not k.startswith("rest-") or v["verdict"] == "out" or k[5:] not in RESTS.values():
            continue
        g = cv2.imread(str(glyphs / f), cv2.IMREAD_GRAYSCALE)
        if g is None:
            continue
        ink = np.clip(1 - g.astype(np.float32) / 255, 0, 1)
        u8 = (ink > 0.3).astype(np.uint8)
        runs = cv2.morphologyEx(u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, g.shape[1] // 2), 1)))
        thick = cv2.morphologyEx(u8, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (1, 4)))
        ink[(runs > 0) & (thick == 0)] = 0
        out.setdefault(k[5:], []).append(ink / max(float(ink.max()), 0.1))
    return out


def tag(svg, rest_kinds: set) -> list:
    """Each symbol to mask, as (kind, element); the font's rests of kinds we replace are marked to be drawn
    invisibly (their place kept for the copyist's)."""
    out = []
    for g in svg.iter(f"{{{SVG}}}g"):
        cls = (g.get("class") or "").split()
        name = next((c for c in cls if c in KINDS), None)
        # a flag sits inside its stem's group: its own symbol (the nearest owner colours each element)
        if name is None or any(_cls(a, n) for a in g.iterancestors() for n in ("notehead", "flag", "dots",
                                                                                   "accid", "rest", "tupletNum")):
            continue
        if name == "accid" and not len(g):
            continue
        kind = KINDS[name]
        if name == "rest":
            use = g.find(f"{{{SVG}}}use")
            code = (use.get(f"{{{XL}}}href") or use.get("href") or "#")[1:5] if use is not None else ""
            if RESTS.get(code) in rest_kinds:
                kind = "rest-" + RESTS[code]
                g.set("data-replace", RESTS[code])
        out.append((kind, g))
    return out


def colour(i: int) -> str:
    return f"#{(i >> 16) & 255:02x}{(i >> 8) & 255:02x}{i & 255:02x}"


def id_svg(svg, tagged: list):
    """A copy in which every tagged symbol is its own colour (1, 2, ... as RGB) and everything else is undrawn."""
    ids = {id(el): i + 1 for i, (_, el) in enumerate(tagged)}
    c = copy.deepcopy(svg)
    orig = list(svg.iter())
    copies = list(c.iter())
    owner = {}
    for o, k in zip(orig, copies):
        if id(o) in ids:
            owner[k] = ids[id(o)]
    for el in c.iter():
        if not isinstance(el.tag, str) or etree.QName(el).localname not in DRAWN:
            continue
        if any(a.tag == f"{{{SVG}}}defs" for a in el.iterancestors()):
            continue
        who = next((owner[a] for a in [el, *el.iterancestors()] if a in owner), None)
        if who is None:
            el.set("fill", "none")
            el.set("stroke", "none")
            el.set("style", "fill:none;stroke:none")
            continue
        col = colour(who)
        # fill and stroke as drawn: the element's own, else the nearest group's (stems and bar lines are stroked
        # from their group), fill black and stroke none by default
        fill = next((x.get("fill") for x in [el, *el.iterancestors()] if x.get("fill")), "black")
        stroke = next((x.get("stroke") for x in [el, *el.iterancestors()] if x.get("stroke")), "none")
        if stroke == "none" and el.get("stroke-width"):  # stroked by verovio's stylesheet (stems, bar lines, rings)
            stroke = "currentColor"
        f, s = ("none" if fill == "none" else col), ("none" if stroke == "none" else col)
        el.set("fill", f)
        el.set("stroke", s)
        el.set("style", f"fill:{f};stroke:{s}")  # verovio's stylesheet would otherwise stroke paths black
    c.set("shape-rendering", "crispEdges")
    return c


def warp_fields(shape, amp, wave, rng):
    """copyist.warp's displacement (the same draws from rng), returned to apply to more than one image."""
    h, w = shape
    nr = np.random.default_rng(rng.randrange(1 << 30))
    sh = (max(2, int(h / wave) + 2), max(2, int(w / wave) + 2))
    dx = cv2.resize(nr.normal(0, amp, sh).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    dy = cv2.resize(nr.normal(0, amp, sh).astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    mx, my = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))
    return mx + dx, my + dy


def raster(svg, W, H, lines="#ff00ff"):
    text = etree.tostring(svg).decode().replace('stroke="var(--line)"', f'stroke="{lines}"')
    png = resvg_py.svg_to_bytes(svg_string=text, width=W, height=H, background="white")
    return np.asarray(Image.open(io.BytesIO(bytes(png))).convert("RGB"))


def render(lmx: str, hand: str, seed: int, rests: dict, width: float | None = None, fonts: tuple = ("Petaluma",),
           plain: bool = False, detail: bool = False):
    """(image, [(kind, mask)], ss) for one staff, in one of `fonts` (repeat one to weight it); masks at the
    image's size, each the symbol's visible ink. `plain`: the font as Verovio engraves it, black on white, at the
    hand's staff size and length only (no redrawing, slant, warp, pasted rests or clef, paper or noise).
    `detail`: a fourth item, {"tagged": [(kind, element)], "idm": each pixel's symbol (its index in tagged, from 1),
    "ink": the drawn ink (0..1)}, to tie the masks back to the engraving's elements (pos_data.py)."""
    rng = random.Random(seed)
    p = copyist.sample(copyist.HANDS[hand], rng)
    p["font"] = random.Random(seed ^ 0x5F0).choice(fonts)  # its own draw: the rest of the staff as it would be
    xml = copyist.lmx_to_musicxml(lmx)
    svg = copyist.engrave(xml, p["font"], width or p["width"])
    copyist.check(svg, lmx, xml)
    if plain:
        p.update(slant=0.0, warp=0.0)
        rests, clef = {}, None
    else:
        copyist.redraw(svg, p, rng)
        clef = copyist.take_clef(svg, lmx, hand, p, rng)
    tagged = tag(svg, set(rests))
    inner = svg.find(f"{{{SVG}}}svg")
    x0, top, x1, bot = copyist.staff_box(svg)
    cx0, cy0, cw, ch = x0 - SP, top - 2.5 * SP, (x1 - x0) + 2 * SP, (bot - top) + 5 * SP
    t = math.tan(math.radians(p["slant"]))
    mid = (top + bot) / 2
    holder = etree.SubElement(inner, f"{{{SVG}}}g", transform=f"translate({t * mid:.1f},0) skewX({-p['slant']:.2f})")
    for c in [c for c in inner if c is not holder]:
        holder.append(c)
    inner.set("viewBox", f"{cx0:.0f} {cy0:.0f} {cw:.0f} {ch:.0f}")
    os_ = 2
    W, H = int(cw / SP * p["ss"] * os_), int(ch / SP * p["ss"] * os_)
    for el in (svg, inner):
        el.set("width", str(W))
        el.set("height", str(H))
    svg.set("viewBox", f"0 0 {W} {H}")
    inner.set("preserveAspectRatio", "none")
    ids = id_svg(svg, tagged)
    for _, el in tagged:  # the font's rests we replace: their place kept, their ink not drawn
        if el.get("data-replace"):
            for d in el.iter():
                if isinstance(d.tag, str) and etree.QName(d).localname in DRAWN:
                    d.set("fill", "none")
    rgb = raster(svg, W, H).astype(np.float32) / 255
    a = 1 - rgb[..., 0]
    li = np.clip(rgb[..., 0] - rgb[..., 1], 0, 1)
    idc = raster(ids, W, H, lines="none").astype(np.int32)
    idm = (idc[..., 0] << 16) | (idc[..., 1] << 8) | idc[..., 2]
    idm[idm == 0xFFFFFF] = 0
    ss2 = p["ss"] * os_
    wv = rng.uniform(2.5, 5) * ss2
    fx, fy = warp_fields(a.shape, p["warp"] * ss2, wv, rng)
    a = cv2.remap(a, fx, fy, cv2.INTER_LINEAR, borderValue=0)
    idm = cv2.remap(idm.astype(np.float32), fx, fy, cv2.INTER_NEAREST, borderValue=0).astype(np.int32)
    li = copyist.warp(li, p["warp"] * ss2 * 0.5, wv * 2, rng)
    a = cv2.resize(a, (W // os_, H // os_), interpolation=cv2.INTER_AREA)
    li = cv2.resize(li, (W // os_, H // os_), interpolation=cv2.INTER_AREA)
    idm = cv2.resize(idm.astype(np.float32), (W // os_, H // os_), interpolation=cv2.INTER_NEAREST).astype(np.int32)
    ss = p["ss"]
    if plain:
        img = (255 * (1 - np.clip(np.maximum(a, li), 0, 1))).astype(np.uint8)
        masks = [(k, m) for i, (k, _) in enumerate(tagged, 1) if (m := (idm == i) & (a > 0.3)).sum() >= 4]
        return (img, masks, ss, {"tagged": tagged, "idm": idm, "ink": a}) if detail else (img, masks, ss)
    # the copyist's rests where the font's were: as tall as the font's (its box in the id drawing), centred there
    for i, (kind, el) in enumerate(tagged, 1):
        rk = el.get("data-replace")
        if not rk:
            continue
        ys, xs = np.nonzero(idm == i)
        idm[idm == i] = 0
        if len(xs) == 0 or not rests.get(rk):
            continue
        glyph = rng.choice(rests[rk])
        hgt = {"quarter": 2.2, "eighth": 1.9, "16th": 2.4}[rk] * ss * rng.uniform(0.85, 1.1)
        f = hgt / glyph.shape[0]
        patch = cv2.resize(glyph, (max(1, int(glyph.shape[1] * f)), max(1, int(hgt))), interpolation=cv2.INTER_AREA)
        cy, cx = int(ys.mean()), int(xs.mean())
        py0, px0 = cy - patch.shape[0] // 2, cx - patch.shape[1] // 2
        sy0, sx0 = max(0, -py0), max(0, -px0)
        py0, px0 = max(0, py0), max(0, px0)
        py1, px1 = min(a.shape[0], py0 + patch.shape[0] - sy0), min(a.shape[1], px0 + patch.shape[1] - sx0)
        if py1 <= py0 or px1 <= px0:
            continue
        pp = patch[sy0:sy0 + py1 - py0, sx0:sx0 + px1 - px0] * rng.uniform(0.85, 1.0)
        np.maximum(a[py0:py1, px0:px1], pp, out=a[py0:py1, px0:px1])
        region = idm[py0:py1, px0:px1]
        region[(pp > 0.3) & (region == 0)] = i
    if clef is not None:
        copyist.paste_clef(a, clef, cx0, ss, rng)
    copyist.distract(a, ss, rng)
    a = cv2.GaussianBlur(a, (0, 0), p["blur"])
    li = cv2.GaussianBlur(li, (0, 0), p["blur"])
    h, w = a.shape
    bg, other = copyist.paper(h, w, rng)
    if rng.random() < 0.5:
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
    visible = a > 0.3
    masks = []
    for i, (kind, _) in enumerate(tagged, 1):
        m = (idm == i) & visible
        if m.sum() >= 4:
            masks.append((kind, m))
    return (img, masks, ss, {"tagged": tagged, "idm": idm, "ink": a}) if detail else (img, masks, ss)


def prompt(kind: str, m: np.ndarray) -> list:
    """A point (repeated) for a head or a stem, the ink pixel nearest the mask's middle; else its box."""
    ys, xs = np.nonzero(m)
    if kind in ("head", "stem"):
        cy, cx = ys.mean(), xs.mean()
        j = int(np.argmin((ys - cy) ** 2 + (xs - cx) ** 2))
        return [int(xs[j]), int(ys[j]), int(xs[j]), int(ys[j])]
    return [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]


def windows(masks: list, w: int, ss: float) -> list:
    """Overlapping pairs of bars, from the drawn bar lines (as sam_data.windows from the labelled ones)."""
    xs = sorted(int(np.nonzero(m)[1].mean()) for k, m in masks if k == "barline")
    edges = [int(ss)] + [x for x in xs if ss < x < w - ss] + [w - int(ss)]
    bars = list(zip(edges[:-1], edges[1:]))
    pairs = [(bars[i][0], bars[i + 1][1]) for i in range(len(bars) - 1)] or bars
    return [(max(0, int(a - 0.5 * ss)), min(w, int(b + 0.5 * ss))) for a, b in pairs]


COLORS = {"head": (200, 60, 0), "stem": (235, 170, 40), "flag": (210, 210, 0), "beam": (140, 140, 0),
          "dot": (220, 40, 90), "rest": (60, 170, 0), "accidental": (0, 100, 240), "slur": (30, 30, 200),
          "tuplet": (90, 90, 235), "trill": (90, 90, 235), "barline": (20, 70, 140)}


def sheet_rows(img, masks):
    vis = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    for k, m in masks:
        col = np.array(COLORS.get(k.split("-")[0], (0, 0, 0)))
        vis[m] = (0.25 * vis[m] + 0.75 * col).astype(np.uint8)
        e = m & ~(cv2.erode(m.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
        vis[e] = (0.45 * vis[e]).astype(np.uint8)
    return [cv2.cvtColor(img, cv2.COLOR_GRAY2BGR), np.full((4, img.shape[1], 3), 255, np.uint8), vis]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", type=Path, help="an .lmx file, a directory of them, or a text file listing them")
    ap.add_argument("--glyphs", type=Path, required=True, help="GLYPHS/<hand>, with curate.py's curated.json")
    ap.add_argument("--hand", default="berlin", choices=sorted(copyist.HANDS))
    ap.add_argument("--fonts", default="Petaluma", help="comma-separated, one chosen per staff; repeat one to weight it "
                    "(e.g. Petaluma,Petaluma,Leland,Gootville,Leipzig,Bravura)")
    ap.add_argument("--plain", action="store_true", help="the fonts as engraved, black on white (see render)")
    ap.add_argument("--out", type=Path)
    ap.add_argument("--sheet", type=Path)
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    if a.src.is_dir():
        files = sorted(a.src.rglob("*.lmx"))
    elif a.src.suffix == ".lmx":
        files = [a.src]
    else:
        files = [Path(l) for l in a.src.read_text().split() if l]
    random.Random(a.seed).shuffle(files)
    rests = rest_library(a.glyphs)
    print("the hand's rests:", {k: len(v) for k, v in rests.items()}, flush=True)
    rows, done, tally, nwin, fails = [], 0, {}, 0, 0
    if a.out:
        a.out.mkdir(parents=True, exist_ok=True)
    for i, f in enumerate(files):
        if done >= a.n:
            break
        try:
            img, masks, ss = render(f.read_text(), a.hand, a.seed + i, rests, fonts=tuple(a.fonts.split(",")),
                                    plain=a.plain)
        except Exception as e:  # verovio's misdrawn staves (copyist.check), overlong ones
            fails += 1
            continue
        done += 1
        if a.sheet:
            rows += sheet_rows(img, masks) + [np.full((12, img.shape[1], 3), 200, np.uint8)]
        if a.out:
            h, w = img.shape
            for wi, (x0, x1) in enumerate(windows(masks, w, ss)):
                kinds, prompts, ms = [], [], []
                for k, m in masks:
                    ys, xs = np.nonzero(m)
                    if xs.min() >= x0 and xs.max() < x1:
                        pr = prompt(k, m)
                        kinds.append(k)
                        prompts.append([pr[0] - x0, pr[1], pr[2] - x0, pr[3]])
                        ms.append(m[:, x0:x1])
                if not kinds:
                    continue
                np.savez_compressed(a.out / f"{f.stem}_{a.seed + i}_w{wi}.npz", image=img[:, x0:x1], kinds=np.array(kinds),
                                    prompts=np.array(prompts, np.int32), masks=np.packbits(np.stack(ms), axis=-1),
                                    width=x1 - x0)
                nwin += 1
                for k in kinds:
                    tally[k] = tally.get(k, 0) + 1
    print(f"{done} staves ({fails} skipped), {nwin} windows", json.dumps(dict(sorted(tally.items(), key=lambda kv: -kv[1]))))
    if rows:
        width = max(r.shape[1] for r in rows)
        cv2.imwrite(str(a.sheet), np.vstack([np.hstack([r, np.full((r.shape[0], width - r.shape[1], 3), 255, np.uint8)]) for r in rows]))


if __name__ == "__main__":
    main()
