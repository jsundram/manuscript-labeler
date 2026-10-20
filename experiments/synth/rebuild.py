# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless==4.10.0.84", "numpy"]
# ///
"""A real staff drawn again from its map, with the copyist's glyphs from
their other staves (never its own): the test that the map and the glyphs
together hold the hand.

- staff lines: straight, at the rows and thickness measured on the staff;
- heads: a head of the right kind (filled, hollow) from another staff, at
  the head's place;
- stems: a pen stroke from the head to the stem's measured end, as wide as
  the staff's stems;
- beams: through the group's stem ends, as thick as the staff's beams, one
  per level of the group's shortest note;
- rests, accidentals, flags, dots, slurs: one of the copyist's own of the
  same kind, fitted to where the symbol was found;
- the opening clef and key: another staff's, with the same clef and key;
- bar lines at the labels' bar lines; words in the margins left out.

    uv run experiments/synth/rebuild.py D-B_KHM-602/p10s4 [...] --maps DIR --glyphs DIR [--out sheet.png]
"""
import argparse
import json
import random
import re
from pathlib import Path

import cv2
import numpy as np

import align

PASTE = ("rest", "accidental", "flag", "dot", "slur", "barline", "trill")


def library(glyphs: Path, hand: str) -> dict[str, list[tuple[str, np.ndarray]]]:
    out = {}
    for d in (glyphs / hand).iterdir():
        items = []
        for f in sorted(d.glob("*.png")):
            g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
            ink = np.clip((255 - g.astype(np.float32)) / max(1.0, 255 - float(np.percentile(g, 2))), 0, 1)  # its darkest = full ink
            if (ink > 0.3).sum() >= 12:  # scraps out
                items.append((f.stem.rsplit("_", 2)[0], ink))
        out[d.name] = items
    return out


def pick(lib, kind, staff, rng, aspect=None):
    """A glyph of this kind from another staff; if aspect is given, one of the closest in shape."""
    cands = [(s, g) for s, g in lib.get(kind, []) if s != staff]
    if not cands:
        return None
    if aspect is not None:
        cands.sort(key=lambda sg: abs(np.log(sg[1].shape[1] / sg[1].shape[0] / max(aspect, 1e-3))))
        cands = cands[: max(3, len(cands) // 5)]
    return rng.choice(cands)[1]


def paste(a, ink, cx, cy, w=None, h=None):
    """ink (0..1) into a, centred at (cx, cy), resized to w x h if given."""
    if w and h:
        ink = cv2.resize(ink, (max(1, int(w)), max(1, int(h))), interpolation=cv2.INTER_AREA)
    gh, gw = ink.shape
    x0, y0 = int(round(cx - gw / 2)), int(round(cy - gh / 2))
    ax0, ay0, ax1, ay1 = max(0, x0), max(0, y0), min(a.shape[1], x0 + gw), min(a.shape[0], y0 + gh)
    if ax1 <= ax0 or ay1 <= ay0:
        return
    np.maximum(a[ay0:ay1, ax0:ax1], ink[ay0 - y0:ay1 - y0, ax0 - x0:ax1 - x0], out=a[ay0:ay1, ax0:ax1])


def measure(g, m):
    """The staff's stem width, beam thickness, line thickness and darkness, ink darkness."""
    ss = m["ss"]
    ink = np.clip((1 - g.astype(np.float32) / 255 - 0.15) / 0.6, 0, 1)
    on = ink > 0.45
    widths, beams = [], []
    for n in (n for b in m["bars"] for n in b["symbols"] if not n.get("rest") and "stem" in n):
        st = n["stem"]
        span = st["end"] - n["y"]
        for f in (0.45, 0.6, 0.75):  # along the stem, clear of head and beam
            y = int(n["y"] + f * span)
            x = int(round(st["x0"] + (st["x1"] - st["x0"]) * f))
            row = on[y, max(0, x - int(0.4 * ss)):x + int(0.4 * ss) + 1].astype(int)
            runs = np.diff(np.r_[0, row, 0])
            for a0, a1 in zip(np.where(runs == 1)[0], np.where(runs == -1)[0]):
                if a0 <= len(row) // 2 + 2 and a1 >= len(row) // 2 - 2 and a1 - a0 <= 0.4 * ss:
                    widths.append(a1 - a0)
        if n["kind"] in ("eighth", "16th", "32nd"):
            d = 1 if st["dir"] == "up" else -1
            y, run = st["end"], 0
            while 0 <= y < g.shape[0] and on[y, min(g.shape[1] - 1, st["x1"])] and run < ss:
                y += d
                run += 1
            beams.append(run)
    _, rows, th = align.ink_map(g, ss)
    line_dark = float(np.median([np.percentile(1 - g[r].astype(np.float32) / 255, 70) for r in rows]))
    ink_dark = float(np.percentile(1 - g[on].astype(np.float32) / 255, 60)) if on.any() else 0.7
    return {"stem": float(np.median(widths)) if widths else 0.12 * ss,
            "beam": float(np.clip(np.median(beams) if beams else 0.5 * ss, 0.3 * ss, 0.8 * ss)),
            "line": float(max(1, th)), "line_dark": line_dark, "ink_dark": ink_dark}


def start_from(data: Path, key: str, clef: str, keysig: str, rng, maps: Path):
    """Another staff's opening (clef and key), with the same clef and key: its ink left of its first bar."""
    src = key.split("/")[0]
    cands = []
    for f in maps.glob(f"{src.split('-')[0]}*.json"):
        other = "/".join(f.stem.rsplit("_", 1))  # maps are named SOURCE_STAFF
        if f.name.endswith(".symbols.json") or other == key:
            continue
        lmx = (data / f"{other}.lmx")
        if not lmx.exists():
            continue
        toks = lmx.read_text().split()[:4]
        if f"clef:{clef}" in toks and keysig in toks:
            cands.append((other, json.loads(f.read_text())))
    if not cands:
        return None
    other, om = rng.choice(cands)
    g = cv2.imread(str(data / f"{other}.jpg"), cv2.IMREAD_GRAYSCALE)
    x1 = int(om["bars"][0]["x0"] - 0.2 * om["ss"]) if om["bars"] else int(3 * om["ss"])
    ink, _, _ = align.ink_map(g, om["ss"])
    return ink[:, :x1], om["ss"]


def paper(data: Path, h: int, w: int, rng) -> np.ndarray:
    f = rng.choice(sorted(data.glob("D-B_KHM-60*/*.jpg")))
    g = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE)
    bg = cv2.GaussianBlur(cv2.dilate(g, np.ones((19, 19), np.uint8)), (0, 0), 8)
    return cv2.resize(bg, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)


def rebuild(key: str, data: Path, maps: Path, lib: dict, seed: int = 0) -> np.ndarray:
    rng = random.Random(seed)
    stem_key = key.replace("/", "_")
    m = json.loads((maps / f"{stem_key}.json").read_text())
    syms = json.loads((maps / f"{stem_key}.symbols.json").read_text())
    g = cv2.imread(str(data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
    h, w = g.shape
    ss = m["ss"]
    me = measure(g, m)
    a = np.zeros((h, w), np.float32)      # the notes' ink
    li = np.zeros((h, w), np.float32)     # the staff lines'
    x_start = int(m["bars"][0]["x0"] - 3.2 * ss) if m["bars"] else int(ss)
    for r in m["lines"]:
        cv2.line(li, (int(ss * 0.9), r), (w - int(ss * 0.9), r), 0.9, max(1, int(round(me["line"]))), cv2.LINE_AA)
    # the opening
    toks = (data / f"{key}.lmx").read_text().split()
    clef = next((t[5:] for t in toks if t.startswith("clef:")), "G2")
    keysig = next((t for t in toks if t.startswith("key:fifths:")), "key:fifths:0")
    st = start_from(data, key, clef, keysig, rng, maps)
    if st is not None:
        ink, oss = st
        ink = cv2.resize(ink, (max(1, int(ink.shape[1] * h / ink.shape[0])), h), interpolation=cv2.INTER_AREA)
        x1 = min(w, ink.shape[1])
        np.maximum(a[:, :x1], ink[:, :x1], out=a[:, :x1])
    # heads and stems
    sw = max(1, int(round(me["stem"] * 0.65)))  # the measured width includes the scan's blur
    for b in m["bars"]:
        for n in b["symbols"]:
            if n.get("rest") or n.get("outside"):
                continue
            kind = "head-hollow" if n["kind"] in align.HOLLOW else "head-filled"
            gl = pick(lib, kind, stem_key, rng)
            if gl is not None:
                sc = (0.6 if n["grace"] else 1.0)
                paste(a, gl, n["x"], n["y"], gl.shape[1] * sc, gl.shape[0] * sc)
            if "stem" in n:
                s = n["stem"]
                cv2.line(a, (s["x0"], n["y"]), (s["x1"], s["end"]), 1.0, max(1, int(sw * (0.6 if n["grace"] else 1))), cv2.LINE_AA)
    # beams
    bt = max(2, int(round(me["beam"])))
    for s in syms:
        if s["kind"] != "beam":
            continue
        ends = sorted(s["ends"])
        (xa, ya), (xb, yb) = ends[0], ends[-1]
        up = ya < s["box"][3] - 0.2 * ss  # beams of up-stems hang below their ends
        d = 1 if (s["box"][1] + s["box"][3]) / 2 > (ya + yb) / 2 else -1
        for lv in range(s.get("levels", 1)):
            off = d * lv * (bt + 0.06 * ss)  # Berlin runs its beams together
            pts = np.array([[xa, ya + off], [xb, yb + off], [xb, yb + off + d * bt], [xa, ya + off + d * bt]], np.int32)
            cv2.fillPoly(a, [pts], 1.0, cv2.LINE_AA)
    # the copyist's other symbols, fitted to where each was found
    for s in syms:
        base = s["kind"].split("-")[0]
        if base not in PASTE or s["kind"] in ("dot-mark",):
            continue
        x0, y0, x1, y1 = s["box"]
        bw, bh = max(2, x1 - x0), max(2, y1 - y0)
        if base == "barline":
            cv2.line(a, (int((x0 + x1) / 2), int(m["lines"][0])), (int((x0 + x1) / 2), int(m["lines"][-1])), 1.0,
                     max(2, int(sw * 1.4)), cv2.LINE_AA)
            continue
        gl = pick(lib, s["kind"], stem_key, rng, aspect=bw / bh)
        if gl is None:
            continue
        if base == "slur":
            paste(a, gl, (x0 + x1) / 2, (y0 + y1) / 2, bw, bh)
        else:  # keep the glyph's own proportions, at the found symbol's height
            paste(a, gl, (x0 + x1) / 2, (y0 + y1) / 2, gl.shape[1] * bh / gl.shape[0], bh)
    # ink on paper
    a = cv2.GaussianBlur(a, (0, 0), 0.6)
    li = cv2.GaussianBlur(li, (0, 0), 0.5)
    bg = paper(data, h, w, rng)
    ink_level = 255 * (1 - me["ink_dark"])
    line_level = 255 * (1 - me["line_dark"])
    out = bg * (1 - li) + line_level * li
    out = out * (1 - np.clip(a, 0, 1)) + ink_level * np.clip(a, 0, 1)
    out = np.clip(out / max(np.percentile(out, 90), 1) * 255, 0, 255).astype(np.uint8)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="+")
    ap.add_argument("--data", type=Path, default=align.ZEUS / "dataL2")
    ap.add_argument("--maps", type=Path, required=True)
    ap.add_argument("--glyphs", type=Path, required=True)
    ap.add_argument("--hand", default="berlin")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    lib = library(a.glyphs, a.hand)
    rows = []
    for k, key in enumerate(a.keys):
        real = cv2.imread(str(a.data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
        img = rebuild(key, a.data, a.maps, lib, seed=k)
        cv2.imwrite(str(a.out.with_name(f"{key.replace('/', '_')}.rebuilt.jpg")), img)
        rows += [real, img, np.full((8, real.shape[1]), 200, np.uint8)]
    width = max(r.shape[1] for r in rows)
    cv2.imwrite(str(a.out), np.vstack([np.hstack([r, np.full((r.shape[0], width - r.shape[1]), 255, np.uint8)]) for r in rows]))
    print(a.out)


if __name__ == "__main__":
    main()
