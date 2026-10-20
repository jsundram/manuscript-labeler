# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless==4.10.0.84", "numpy"]
# ///
"""The staff map: where each symbol of a staff's label is on the page.

A labelled staff (dataset.py's crop and its LMX) says what is there and in
what order; the labels' bar lines say which stretch of the staff each bar
fills; the crop is straightened, so a pitch is a height (the staff from 2.5
to 6.5 spaces). So nothing needs naming, only finding: each note is looked
for at its own height, inside its own bar, and the bar's notes are placed
together, in playing order, chord notes sharing one x.

    uv run experiments/synth/align.py D-B_KHM-602/p10s4 [...] [--out DIR] [--sheet]

For each staff, the map (JSON): per bar its x range, per note its pitch,
head centre, filled or hollow, how sure (the head's evidence against the
next best place), and its stem (direction, end, length). --sheet draws the
map over the staff to judge it by eye.
"""
import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np

ZEUS = Path.home() / ".cache/manuscript-labeler/zeus"
LABELS = Path.home() / "Dropbox/Code/manuscript-labeler/data/boccherini-opus-48/sources"
GERARD = {"D-B_KHM-602": "G226", "D-B_KHM-603": "G227", "F-Po_RES-507-14": "G228", "F-Pn_Vma-ms-1067-1": "G228",
          "F-Po_RES-507-17": "G230", "F-Pn_Vma-ms-1067-3": "G230"}
STEPS = "CDEFGAB"
TOP = {"G2": 3 + 7 * 5, "C3": 4 + 7 * 4, "C4": 2 + 7 * 4, "C1": 1 + 7 * 5, "F4": 5 + 7 * 3}  # the top line's step (F5, G4, E4, D5, A3)
HOLLOW = {"half", "whole", "breve"}


# -- the label ------------------------------------------------------------------------

def parse(lmx: str) -> list[dict]:
    """The staff's bars, each a list of events in the label's order: notes (step, chord, grace, voice, kind, accidental,
    dots) and rests, with the clef in force."""
    bars, clef, voice = [], "G2", "1"
    toks = lmx.split()
    ev = None
    pending = []  # prefix tokens (chord, grace) for the next pitch
    for t in toks:
        if t == "measure":
            bars.append({"clef": clef, "events": []})
            voice = "1"
            continue
        if not bars:
            continue
        bar = bars[-1]
        if t.startswith("clef:"):
            clef = t[5:]
            if not bar["events"]:
                bar["clef"] = clef
            else:
                bar["events"].append({"type": "clef", "clef": clef})
        elif t.startswith("voice:"):
            voice = t[6:]
            if ev is not None:
                ev["voice"] = voice
        elif t in ("chord", "grace", "grace:slash"):
            pending.append(t)
        elif re.fullmatch(r"[A-G]\d", t) or t == "rest":
            ev = {"type": "rest" if t == "rest" else "note", "voice": voice, "clef": clef,
                  "chord": "chord" in pending, "grace": any(p.startswith("grace") for p in pending),
                  "dots": 0, "accidental": None, "kind": None, "beams": [], "trill": False, "tuplet": False}
            if ev["type"] == "note":
                ev["step"] = STEPS.index(t[0]) + 7 * int(t[1])
            pending = []
            bar["events"].append(ev)
        elif ev is not None:
            if t in ("whole", "half", "quarter", "eighth", "16th", "32nd", "64th", "breve", "long"):
                ev["kind"] = t
            elif t == "dot":
                ev["dots"] += 1
            elif t == "trill-mark":
                ev["trill"] = True
            elif t == "tuplet:start":
                ev["tuplet"] = True
            elif t in ("sharp", "flat", "natural", "double-sharp", "flat-flat"):
                ev["accidental"] = t
            elif t.startswith("beam:"):
                ev["beams"].append(t[5:])
            elif t == "rest:measure":
                ev["kind"] = "measure"
            elif t == "backup":
                ev = None
    return bars


def height(step: int, clef: str, ss: float, top: float | None = None) -> float:
    """A step's centre in the crop: the top line at `top` (2.5 spaces if not known), a step half a space."""
    return (2.5 * ss if top is None else top) + (TOP.get(clef, TOP["G2"]) - step) * ss / 2


def fit_lines(ink: np.ndarray, ss0: float) -> list[int]:
    """The five staff lines' rows. Only long horizontal strokes count (an opening a few spaces wide keeps the lines,
    however faint, and drops heads, stems and most beams); in strips across the staff, so lines that bow or slope
    still line up; the spacing is the one whose evenly spaced combs, one per strip, cover the most of them. The
    crop's height only guesses the spacing; on some crops it's off by a fifth."""
    h, w = ink.shape
    lines = cv2.morphologyEx(ink, cv2.MORPH_OPEN, cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, int(3 * ss0)), 1)))
    nstrip = max(1, min(8, int(w / (6 * ss0))))
    profs = [lines[:, i * w // nstrip:(i + 1) * w // nstrip].mean(1) for i in range(nstrip)]
    best = None
    for sp in np.arange(0.65 * ss0, 1.3 * ss0, 0.25):
        offs = np.arange(0, int(h - 4 * sp))
        if len(offs) == 0:
            continue
        idx = np.round(offs[:, None] + np.arange(5)[None, :] * sp).astype(int)
        per = [pr[idx].sum(1) for pr in profs]  # each strip's comb score at each offset
        tops = [int(offs[np.argmax(c)]) for c in per]
        score = sum(c.max() for c in per)
        # the strips' combs should agree: a staff doesn't jump
        score -= 0.05 * np.std(tops) / sp * score
        if best is None or score > best[0]:
            best = (score, sp, int(np.median(tops)))
    _, sp, top = best
    return [int(round(top + i * sp)) for i in range(5)]


# -- the page -------------------------------------------------------------------------

def system_of(key: str) -> dict:
    src, staff = key.split("/")
    src = re.sub(r"-noslur$", "", src)
    pages = json.loads((LABELS / GERARD[src] / f"{src}.labels.json").read_text())["pages"]
    page = re.match(r"p(\d+)", staff).group(1)
    return next(s for s in pages[page]["systems"] if s["id"] == staff)


def bar_edges(s: dict, w: int, ss: float, nbars: int) -> list[tuple[float, float]]:
    """Each bar's x range in the crop (at the staff's middle line), from the labels' bar lines."""
    W = (w - 2 * ss) / (s["right"] - s["left"])  # the page width in crop pixels: the crop is the staff plus a space each end
    cx = lambda px: (px - s["left"]) * W + ss
    lines = sorted(cx((b["x0"] + b["x1"]) / 2) for b in s["barlines"])  # stored in the order they were drawn
    start = cx(s["start"]) if s.get("start") else ss + 3 * ss
    edges = [start] + lines
    if len(edges) - 1 < nbars:  # the last bar runs to the staff's end
        edges.append(w - ss)
    return list(zip(edges[:-1], edges[1:]))[:nbars]


def barline_strokes(s: dict, w: int, ss: float, rows: list[int]) -> list[list[int]]:
    """The labels' bar lines in the crop, each [x at the top line, top line's row, x at the bottom line, its row]: the
    labels snap them to the ink, so these are where the strokes are."""
    W = (w - 2 * ss) / (s["right"] - s["left"])
    cx = lambda px: (px - s["left"]) * W + ss
    return [[int(round(cx(b["x0"]))), int(rows[0]), int(round(cx(b["x1"]))), int(rows[-1]), b.get("kind", "single")]
            for b in s["barlines"]]


def ink_map(g: np.ndarray, ss: float) -> tuple[np.ndarray, list[float], float]:
    """Ink (0..1) with the staff lines lifted off, the lines' rows, their thickness."""
    ink = np.clip((1 - g.astype(np.float32) / 255 - 0.15) / 0.6, 0, 1)
    h, w = ink.shape
    prof = (ink > 0.5).mean(1)
    rows = fit_lines(ink, ss)
    # thickness: how many rows around each line are mostly ink
    th = int(np.median([sum(prof[min(h - 1, max(0, r + d))] > 0.35 for d in range(-3, 4)) for r in rows])) or 1
    out = ink.copy()
    half = max(1, (th + 1) // 2)
    sp = (rows[-1] - rows[0]) / 4
    ledgers = [int(round(rows[0] - k * sp)) for k in (1, 2)] + [int(round(rows[-1] + k * sp)) for k in (1, 2)]
    for r in rows + [r for r in ledgers if half < r < h - half - 1]:  # ledger lines too: short, at the lines' spacing
        a, b = max(0, r - half), min(h, r + half + 1)
        above = ink[max(0, a - 2):a].max(0) if a > 0 else np.zeros(w)
        below = ink[b:min(h, b + 2)].max(0) if b < h else np.zeros(w)
        line_only = (above < 0.4) & (below < 0.4)  # nothing crosses here: only the line
        out[a:b, line_only] = 0
    return out, rows, th


def head_maps(ink: np.ndarray, ss: float) -> tuple[np.ndarray, np.ndarray]:
    """Evidence for a filled head and for a hollow head centred at each pixel."""
    rx, ry = 0.55 * ss, 0.42 * ss
    size = int(2 * rx) | 1, int(2 * ry) | 1
    k = np.zeros((size[1], size[0]), np.float32)
    cv2.ellipse(k, (size[0] // 2, size[1] // 2), (int(rx), int(ry)), -25, 0, 360, 1, -1)
    fill = cv2.filter2D(ink, -1, k / k.sum())
    # a head is compact: less ink a head's width to either side (beams and slurs run on)
    sx = int(1.15 * ss)
    left = np.roll(fill, sx, axis=1)
    right = np.roll(fill, -sx, axis=1)
    filled = fill - 0.5 * np.minimum(left, right)
    # hollow: a ring with an empty middle
    ring = np.zeros_like(k)
    cv2.ellipse(ring, (size[0] // 2, size[1] // 2), (int(rx), int(ry)), -25, 0, 360, 1, max(1, int(0.18 * ss)))
    inner = np.zeros_like(k)
    cv2.ellipse(inner, (size[0] // 2, size[1] // 2), (max(1, int(rx * 0.45)), max(1, int(ry * 0.4))), -25, 0, 360, 1, -1)
    hollow = cv2.filter2D(ink, -1, ring / ring.sum()) - cv2.filter2D(ink, -1, inner / max(inner.sum(), 1))
    return filled, hollow


# -- placing a bar's notes ------------------------------------------------------------

def place_bar(events: list[dict], x0: float, x1: float, maps, ss: float, clef: str, top: float | None = None) -> list[dict]:
    """Each note's x in [x0, x1]: per voice, in the label's order, chord notes at their chord's x; the most evidence
    overall (dynamic programming over the onsets' x)."""
    filled, hollow = maps
    h, w = filled.shape
    xs = np.arange(max(0, int(x0 + 0.2 * ss)), min(w, int(x1 - 0.2 * ss)))
    if len(xs) == 0:
        return []
    out = []
    for voice in sorted({e["voice"] for e in events if e["type"] == "note"}):
        # onsets: a note and the chord notes after it; rests take a slot too (they need room)
        slots = []
        for e in events:
            if e["voice"] != voice or e["type"] not in ("note", "rest"):
                continue
            if e["type"] == "note" and e["chord"] and slots and slots[-1]["notes"]:
                slots[-1]["notes"].append(e)
            else:
                slots.append({"notes": [e] if e["type"] == "note" else [], "rest": e if e["type"] == "rest" else None,
                              "grace": e.get("grace", False)})
        n, m = len(slots), len(xs)
        if n == 0:
            continue
        # evidence of each slot at each x: the sum over its notes at their heights
        ev = np.zeros((n, m), np.float32)
        for i, sl in enumerate(slots):
            if sl["rest"]:
                ev[i] = 0.0  # placed by order only, for now
                continue
            for e in sl["notes"]:
                y = height(e["step"], e["clef"], ss, top)
                band = slice(max(0, int(y - 0.2 * ss)), min(h, int(y + 0.2 * ss) + 1))
                mp = hollow if e["kind"] in HOLLOW else filled
                ev[i] += mp[band, xs[0]:xs[-1] + 1].max(0) if band.start < band.stop else 0
            ev[i] /= max(1, len(sl["notes"]))
        # DP: slot i at x index j, x strictly increasing with a minimum gap
        gap = max(1, int((0.45 if any(s["grace"] for s in slots) else 0.8) * ss))
        D = np.full((n, m), -1e9, np.float32)
        B = np.zeros((n, m), np.int32)
        D[0] = ev[0]
        for i in range(1, n):
            g_i = max(1, int(0.45 * ss)) if (slots[i]["grace"] or slots[i - 1]["grace"]) else gap
            best = np.maximum.accumulate(D[i - 1])
            arg = np.zeros(m, np.int32)
            run = 0
            for j in range(m):  # argmax of D[i-1, :j] kept as we go
                if D[i - 1, j] >= D[i - 1, run]:
                    run = j
                arg[j] = run
            shifted = np.full(m, -1e9, np.float32)
            shifted[g_i:] = best[:-g_i]
            D[i] = shifted + ev[i]
            B[i, g_i:] = arg[:-g_i]
        j = int(np.argmax(D[-1]))
        place = [0] * n
        for i in range(n - 1, -1, -1):
            place[i] = j
            j = B[i, j]
        for i, sl in enumerate(slots):
            x = float(xs[place[i]])
            for e in sl["notes"]:
                y = height(e["step"], e["clef"], ss, top)
                if not 0.2 * ss <= y <= h - 0.2 * ss:  # beyond the crop (ledger lines far above or below)
                    out.append({**{k: e[k] for k in ("step", "kind", "chord", "grace", "voice", "accidental", "dots", "beams", "trill", "tuplet")},
                                "x": int(x), "y": int(min(max(y, 0), h - 1)), "evidence": 0.0, "margin": 0.0, "outside": True})
                    continue
                mp = hollow if e["kind"] in HOLLOW else filled
                xi = int(x)
                band = mp[max(0, int(y - 0.2 * ss)):int(y + 0.2 * ss) + 1, max(0, xi - int(0.4 * ss)):xi + int(0.4 * ss) + 1]
                yy, xx = np.unravel_index(int(np.argmax(band)), band.shape) if band.size else (0, 0)
                cy = int(max(0, int(y - 0.2 * ss)) + yy)
                cx = int(max(0, xi - int(0.4 * ss)) + xx)
                here = float(mp[cy, cx])
                # how sure: this head's evidence against the best elsewhere in the bar at its height
                row = mp[min(h - 1, cy), xs[0]:xs[-1] + 1].copy()
                lo, hi = max(0, cx - xs[0] - int(0.6 * ss)), max(0, cx - xs[0] + int(0.6 * ss))
                row[lo:hi] = -1
                out.append({**{k: e[k] for k in ("step", "kind", "chord", "grace", "voice", "accidental", "dots", "beams", "trill", "tuplet")},
                            "x": cx, "y": cy, "evidence": here, "margin": here - float(row.max()) if row.size else here})
            if sl["rest"]:
                out.append({"rest": True, "voice": voice, "x": x, "kind": sl["rest"]["kind"], "dots": sl["rest"]["dots"]})
    return out


def head_blob(on: np.ndarray, cx: int, cy: int, ss: float):
    """The head's own ink near (cx, cy): the ink opened with a disc (thin stems and beams vanish, the head's body stays),
    the piece nearest the centre, grown back over the ink it covered. -> (mask, x0, y0) in a window, or None."""
    h, w = on.shape
    r = int(1.2 * ss)
    x0, y0, x1, y1 = max(0, cx - r), max(0, cy - r), min(w, cx + r + 1), min(h, cy + r + 1)
    win = on[y0:y1, x0:x1].astype(np.uint8)
    d = max(3, int(0.42 * ss)) | 1
    disc = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (d, d))
    body = cv2.morphologyEx(win, cv2.MORPH_OPEN, disc)
    n, lab, stats, cents = cv2.connectedComponentsWithStats(body, 8)
    best, bd = None, 0.75 * ss
    for i in range(1, n):
        ys, xs = np.nonzero(lab == i)
        dist = np.min(np.hypot(xs + x0 - cx, ys + y0 - cy))
        if dist < bd and stats[i][4] > 0.12 * ss * ss:
            best, bd = i, dist
    if best is None:
        return None
    core = (lab == best).astype(np.uint8)
    grown = cv2.dilate(core, disc) & win  # back over the ink it covered: the head's rim, not the stem beyond
    ys, xs = np.nonzero(core)
    gx, gy = xs.mean(), ys.mean()
    yy, xx = np.mgrid[0:win.shape[0], 0:win.shape[1]]
    grown &= ((xx - gx) ** 2 / (0.95 * ss) ** 2 + (yy - gy) ** 2 / (0.8 * ss) ** 2 <= 1).astype(np.uint8)
    return grown.astype(bool), x0, y0


def refine_heads(notes: list[dict], ink: np.ndarray, ss: float):
    """Each head's centre moved to its own ink's centre (head_blob), its box kept."""
    on = ink > 0.4
    for n in notes:
        if n.get("rest") or n.get("outside") or n["kind"] in HOLLOW:
            continue
        hb = head_blob(on, n["x"], n["y"], ss)
        if hb is None:
            continue
        m, x0, y0 = hb
        ys, xs = np.nonzero(m)
        if len(xs) < 0.2 * ss * ss:
            continue
        n["x"], n["y"] = int(round(xs.mean() + x0)), int(round(ys.mean() + y0))
        n["box"] = [int(xs.min() + x0), int(ys.min() + y0), int(xs.max() + x0), int(ys.max() + y0)]


def stems(notes: list[dict], ink: np.ndarray, ss: float):
    """Each head's stem: the longest run of ink from the head's edge, up from its right side or down from its left, along
    a line leaning as the hand leans (x = x0 + lean * rise)."""
    h, w = ink.shape
    on = ink > 0.4
    gap_max = max(1, int(0.15 * ss))
    leans = np.linspace(-0.1, 0.45, 12)
    for n in notes:
        if n.get("rest") or n.get("outside") or n["kind"] in ("whole", "breve"):
            continue
        cx, cy = n["x"], n["y"]
        best = None
        for d in (-1, 1):  # -1 up, from the right side; 1 down, from the left
            starts = range(cx + int(0.15 * ss), cx + int(0.75 * ss) + 1) if d < 0 else range(cx - int(0.75 * ss), cx - int(0.15 * ss) + 1)
            for x0 in starts:
                for lean in leans:
                    y, end, gapn = cy, cy, 0
                    while gapn <= gap_max:
                        y += d
                        if not 0 <= y < h:
                            break
                        x = int(round(x0 + lean * (cy - y)))
                        if 0 <= x < w and (on[y, x] or (x + 1 < w and on[y, x + 1])):
                            end, gapn = y, 0
                        else:
                            gapn += 1
                    length = abs(end - cy) / ss
                    if best is None or length > best[0]:
                        best = (length, "up" if d < 0 else "down", x0, end, lean)
        if best and best[0] > 1.8:
            length, dr, x0, end, lean = best
            n["stem"] = {"dir": dr, "x0": int(x0), "x1": int(round(x0 + lean * (cy - end))), "end": int(end),
                         "length": round(length, 2), "lean": round(float(lean), 3)}


def map_staff(key: str, data: Path = ZEUS / "dataL2") -> dict:
    g = cv2.imread(str(data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
    h, w = g.shape
    rows = fit_lines(np.clip((1 - g.astype(np.float32) / 255 - 0.15) / 0.6, 0, 1), h / 9)  # the crop's height only guesses
    ss = (rows[-1] - rows[0]) / 4
    bars = parse((data / f"{key}.lmx").read_text())
    s = system_of(key)
    edges = bar_edges(s, w, ss, len(bars))
    ink, rows, th = ink_map(g, ss)
    maps = head_maps(ink, ss)
    strokes = barline_strokes(s, w, ss, rows)
    # no head on a bar line, or among a repeat's strokes and dots (they look like heads, a double stroke like a hollow one)
    for xt, yt, xb, yb, kind in strokes:
        xm = (xt + xb) / 2
        lo = xm - (3.0 if kind in ("repeat_end", "repeat_both") else 0.5) * ss
        hi = xm + (3.0 if kind in ("repeat_start", "repeat_both") else 0.5) * ss
        if kind == "double":
            lo, hi = xm - 0.9 * ss, xm + 0.9 * ss
        for mp in maps:
            mp[:, max(0, int(lo)):min(w, int(hi) + 1)] = -1.0
    out = {"key": key, "ss": ss, "lines": rows, "barlines": strokes, "bars": []}  # ss: the lines' spacing
    for bar, (x0, x1) in zip(bars, edges):
        notes = place_bar(bar["events"], x0, x1, maps, ss, bar["clef"], rows[0])
        refine_heads(notes, ink, ss)
        stems([n for n in notes], ink, ss)
        out["bars"].append({"x0": x0, "x1": x1, "clef": bar["clef"], "symbols": notes})
    return out


def sheet(m: dict, g: np.ndarray, sure: float = 0.45) -> np.ndarray:
    vis = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    ss = m["ss"]
    for b in m["bars"]:
        cv2.line(vis, (int(b["x0"]), 0), (int(b["x0"]), vis.shape[0]), (200, 120, 0), 1)
        for n in b["symbols"]:
            if n.get("rest"):
                cv2.drawMarker(vis, (int(n["x"]), int(4.5 * ss)), (0, 160, 0), cv2.MARKER_TILTED_CROSS, int(ss * 0.6), 1)
                continue
            col = (0, 0, 230) if n["evidence"] > sure else (0, 160, 255)
            cv2.ellipse(vis, (n["x"], n["y"]), (int(0.55 * ss), int(0.42 * ss)), 0, 0, 360, col, 1)
            if "stem" in n:
                st = n["stem"]
                cv2.line(vis, (st["x0"], n["y"]), (st["x1"], st["end"]), (230, 0, 160), 2)
    return vis


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="+")
    ap.add_argument("--data", type=Path, default=ZEUS / "dataL2")
    ap.add_argument("--out", type=Path, default=ZEUS / "maps")
    ap.add_argument("--sheet", action="store_true")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    rows = []
    for key in a.keys:
        m = map_staff(key, a.data)
        notes = [n for b in m["bars"] for n in b["symbols"] if not n.get("rest")]
        sure = sum(n["evidence"] > 0.45 for n in notes)
        stemmed = sum("stem" in n for n in notes if n["kind"] not in ("whole", "breve"))
        print(f"{key}: {len(notes)} notes, {sure} sure ({sure / max(1, len(notes)):.0%}), stems {stemmed}", flush=True)
        (a.out / f"{key.replace('/', '_')}.json").write_text(json.dumps(m))
        if a.sheet:
            g = cv2.imread(str(a.data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
            rows.append(sheet(m, g))
    if rows:
        width = max(r.shape[1] for r in rows)
        cv2.imwrite(str(a.out / "sheet.png"), np.vstack([np.hstack([r, np.full((r.shape[0], width - r.shape[1], 3), 255, np.uint8)])
                                                         for r in rows]))


if __name__ == "__main__":
    main()
