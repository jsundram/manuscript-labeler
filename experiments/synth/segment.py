# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless==4.10.0.84", "numpy"]
# ///
"""Every symbol of a mapped staff, as its own pixels.

align.py places the heads and stems. Here they are lifted out of the ink
(staff lines already gone), and so are the beams (what joins two stem ends of
a beamed group). What's left is sorted against the label:
- left of a head that has an accidental: the accidental;
- right of a head that has dots: dots;
- at the end of an unbeamed short note's stem: its flag;
- in a rest's place, between its neighbours: the rest;
- anything else: a slur or tie (long and thin), a mark over or under a note
  (staccato, trill, tuplet number), or something the label doesn't hold
  (words, the neighbours' ink).

    uv run experiments/synth/segment.py D-B_KHM-602/p10s4 [...] [--maps DIR] [--glyphs DIR] [--sheet]

Writes each staff's symbols beside its map (KEY.symbols.json) and each cut
glyph into GLYPHS/<hand>/<kind>/ (ink as a PNG, the crop's full height kept
in its name: y offset, so it can go back where it was).
"""
import argparse
import json
import re
from pathlib import Path

import cv2
import numpy as np

import align

HAND = lambda key: "berlin" if key.startswith("D-B") else "vma" if "Vma" in key else "paris"
SHORT = {"eighth": 1, "16th": 2, "32nd": 3, "64th": 4}


def groups(notes: list[dict]) -> list[list[dict]]:
    """Beamed groups, per voice in order: from a note that opens beams until they all close."""
    out = []
    for voice in sorted({n["voice"] for n in notes}):
        cur, open_ = [], 0
        for n in [n for n in notes if n["voice"] == voice and not n["chord"]]:
            b = n.get("beams", [])
            if open_ or "begin" in b:
                cur.append(n)
            open_ += b.count("begin") - b.count("end")
            if cur and open_ <= 0:
                if len(cur) > 1:
                    out.append(cur)
                cur, open_ = [], 0
    return out


def segment(key: str, m: dict, g: np.ndarray) -> dict:
    ss = m["ss"]
    ink, _, _ = align.ink_map(g, ss)
    on = (ink > 0.4).astype(np.uint8)
    h, w = on.shape
    taken = np.zeros_like(on)
    notes = [n for b in m["bars"] for n in b["symbols"] if not n.get("rest") and not n.get("outside")]
    rests = [n for b in m["bars"] for n in b["symbols"] if n.get("rest")]
    # heads and stems
    for n in notes:
        hb = align.head_blob(ink > 0.4, n["x"], n["y"], ss) if n["kind"] not in align.HOLLOW else None
        if hb is not None:  # the head's own ink
            msk, x0, y0 = hb
            sub = taken[y0:y0 + msk.shape[0], x0:x0 + msk.shape[1]]
            sub[cv2.dilate(msk.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0] = 1
        else:
            cv2.ellipse(taken, (n["x"], n["y"]), (int(0.72 * ss), int(0.56 * ss)), -25, 0, 360, 1, -1)
        if "stem" in n:
            st = n["stem"]
            cv2.line(taken, (st["x0"], n["y"]), (st["x1"], st["end"]), 1, max(2, int(0.25 * ss)))
    lifted = on * (1 - taken)
    nlab, lab, stats, _ = cv2.connectedComponentsWithStats(lifted, 8)
    used = set()
    symbols = []

    def comp_at(x, y, r):
        """Components within r of (x, y)."""
        x0, x1, y0, y1 = max(0, int(x - r)), min(w, int(x + r)), max(0, int(y - r)), min(h, int(y + r))
        return {int(c) for c in np.unique(lab[y0:y1, x0:x1]) if c}

    def add(kind, comps, **extra):
        comps = [c for c in comps if c not in used and stats[c][4] > 2]
        if not comps:
            return None
        used.update(comps)
        xs = [stats[c][0] for c in comps] + [stats[c][0] + stats[c][2] for c in comps]
        ys = [stats[c][1] for c in comps] + [stats[c][1] + stats[c][3] for c in comps]
        box = [int(min(xs)), int(min(ys)), int(max(xs)), int(max(ys))]
        symbols.append({"kind": kind, "box": box, "comps": [int(c) for c in comps], **extra})
        return symbols[-1]

    # bar lines: where the labels put them (snapped to the ink)
    for bl in m.get("barlines", []):
        xt, yt, xb, yb = bl[:4]
        kind = bl[4] if len(bl) > 4 else "single"
        wide = kind != "single"  # double bars and repeats: two strokes and the dots
        line = np.zeros_like(on)
        cv2.line(line, (xt, max(0, int(yt - 0.6 * ss))), (xb, min(h - 1, int(yb + 0.6 * ss))), 1,
                 max(3, int((2.6 if wide else 0.5) * ss)))
        cs = []
        for c in np.unique(lab[line > 0]):
            if not c or c in used:
                continue
            inside = lab[line > 0] == c
            rows_in = np.unique(np.nonzero((lab == c) & (line > 0))[0])
            # mostly inside, or running most of the staff's height inside (a stroke with the copyist's tail)
            if inside.sum() >= 0.5 * stats[c][4] or len(rows_in) >= 2.5 * ss or (wide and stats[c][2] < 0.6 * ss and stats[c][3] < 0.6 * ss):
                cs.append(int(c))
        if kind.startswith("repeat"):  # its dots: small round pieces in the two middle spaces, up to 3.5 spaces away
            xm = (xt + xb) / 2
            for c in range(1, nlab):
                x, y, cw, ch, a_ = stats[c]
                if c in used or c in cs or cw > 1.8 * ss or ch > 1.4 * ss or a_ < 0.05 * ss * ss:  # Berlin writes them as dashes
                    continue
                cxc, cyc = x + cw / 2, y + ch / 2
                left_ok = kind in ("repeat_end", "repeat_both") and xm - 3.5 * ss <= cxc < xm
                right_ok = kind in ("repeat_start", "repeat_both") and xm < cxc <= xm + 3.5 * ss
                if (left_ok or right_ok) and yt + 0.7 * ss <= cyc <= yb - 0.7 * ss:
                    cs.append(int(c))
        add("barline-" + kind if wide else "barline", cs)
    # beams: components touching the stem ends of two or more notes of a beamed group
    for grp in groups(notes):
        ends = [(n["stem"]["x1"], n["stem"]["end"]) for n in grp if "stem" in n]
        if len(ends) < 2:
            continue
        cs = set()
        for x, y in ends:
            cs |= comp_at(x, y, 0.35 * ss)
        cs = {c for c in cs if stats[c][2] > 0.8 * ss}  # beams run sideways
        levels = max(SHORT.get(n["kind"], 1) for n in grp)
        # the secondary beams: wide pieces between the group's first and last stems, within the beams' depth of their ends
        xa, xb = min(e[0] for e in ends) - 0.3 * ss, max(e[0] for e in ends) + 0.3 * ss
        up = sum(n["stem"]["dir"] == "up" for n in grp if "stem" in n) * 2 >= len(ends)
        for c in range(1, nlab):
            x, y, cw, ch, a = stats[c]
            if c in used or c in cs or cw < 0.6 * ss or x < xa or x + cw > xb:
                continue
            yb = np.interp(x + cw / 2, [e[0] for e in sorted(ends)], [e[1] for e in sorted(ends)])
            depth = (y + ch / 2 - yb) * (1 if up else -1)
            if -0.4 * ss < depth < (0.75 * levels + 0.3) * ss:
                cs.add(c)
        add("beam", cs, notes=len(grp), levels=levels, ends=[list(map(int, e)) for e in ends])
    # per note: accidental to the left, dots to the right, a flag at an unbeamed short note's stem end
    in_group = {id(n) for grp in groups(notes) for n in grp}
    for n in notes:
        if n.get("accidental"):
            cs = {c for c in comp_at(n["x"] - 1.2 * ss, n["y"], 0.75 * ss)
                  if stats[c][0] + stats[c][2] <= n["x"] - 0.2 * ss and stats[c][3] > 0.6 * ss}
            add("accidental-" + n["accidental"], cs, note=[n["x"], n["y"]])
        if n.get("dots"):
            cs = {c for c in comp_at(n["x"] + 0.95 * ss, n["y"], 0.55 * ss)
                  if stats[c][2] < 0.6 * ss and stats[c][3] < 0.6 * ss and stats[c][0] > n["x"] + 0.3 * ss}
            add("dot", cs, note=[n["x"], n["y"]])
        if n["kind"] in SHORT and id(n) not in in_group and "stem" in n and not n["grace"]:
            st = n["stem"]
            cs = comp_at(st["x1"] + 0.4 * ss, st["end"] + (0.6 if st["dir"] == "up" else -0.6) * ss, 0.6 * ss)
            add("flag-" + n["kind"], cs, stem=st["dir"], note=[n["x"], n["y"]])
    # the staff's start (clef, key, time) and the bar lines
    start = m["bars"][0]["x0"] if m["bars"] else 3 * ss
    edges = [b["x1"] for b in m["bars"]]
    for c in range(1, nlab):
        x, y, cw, ch, a = stats[c]
        if c in used or a < 0.08 * ss * ss:
            continue
        if x + cw / 2 < start - 0.2 * ss:
            add("start", [c])
        elif cw < 1.0 * ss and ch > 2.8 * ss and any(abs(x + cw / 2 - e) < 1.0 * ss for e in edges):
            add("barline", [c])
    # tuplet numbers: a small piece over or under a group that starts a tuplet
    for grp in groups(notes):
        if not any(n.get("tuplet") for n in grp):
            continue
        xs_ = [n["x"] for n in grp]
        ys_ = [n["y"] for n in grp] + [n["stem"]["end"] for n in grp if "stem" in n]
        top, bot = min(ys_), max(ys_)
        cands = []
        for c in range(1, nlab):
            x, y, cw, ch, a_ = stats[c]
            if c in used or cw > 1.3 * ss or ch > 1.6 * ss or a_ < 0.1 * ss * ss:
                continue
            cxc, cyc = x + cw / 2, y + ch / 2
            if min(xs_) - 0.8 * ss <= cxc <= max(xs_) + 0.8 * ss and (top - 2.2 * ss <= cyc < top - 0.2 * ss or bot + 0.2 * ss < cyc <= bot + 2.2 * ss):
                cands.append((abs(cxc - np.mean(xs_)), c))
        if cands:
            add("tuplet", [min(cands)[1]])
    # trills: the piece above a note marked with one
    for n in notes:
        if n.get("trill"):
            top = min(n["y"], n.get("stem", {}).get("end", n["y"]))
            cs = {c for c in comp_at(n["x"], top - 1.0 * ss, 1.0 * ss) if stats[c][1] + stats[c][3] < top}
            add("trill", cs, note=[n["x"], n["y"]])
    # rests: the biggest piece in the staff, between the rest's neighbours
    placed = sorted(notes, key=lambda n: n["x"])
    for r in rests:
        if r.get("kind") == "measure":
            lo, hi = r["x"] - 3 * ss, r["x"] + 3 * ss
        else:
            left = max([n["x"] for n in placed if n["x"] < r["x"]], default=r["x"] - 2.5 * ss)
            right = min([n["x"] for n in placed if n["x"] > r["x"]], default=r["x"] + 2.5 * ss)
            lo, hi = left + 0.4 * ss, right - 0.4 * ss
        best = None
        for c in range(1, nlab):
            x, y, cw, ch, a = stats[c]
            if c in used or a < 0.15 * ss * ss or not lo <= x + cw / 2 <= hi:
                continue
            if not 2.0 * ss <= y + ch / 2 <= 7.0 * ss or cw > 4.0 * ss or ch > 4.0 * ss or (ch > 2.8 * ss and cw < 1.0 * ss):
                continue
            if ch > 1.6 * ss and cw < 0.42 * ss:  # a bare stroke: a stem the head finder missed, not a rest
                continue
            if best is None or a > stats[best][4]:
                best = c
        if best is not None:
            s = add("rest-" + str(r.get("kind")), [best])
            r["x"] = int(stats[best][0] + stats[best][2] / 2)
            r["found"] = True
    # pieces touching a sorted symbol, or the lifted heads and stems, are part of it (there is almost no stray ink):
    # stem tips past the found end, beam ends, a sharp's broken stroke; repeated so chains of pieces join
    owner = np.zeros(nlab, np.int32) - 1
    for k, sym in enumerate(symbols):
        for c in sym["comps"]:
            owner[c] = k
    near_taken = cv2.dilate(taken, np.ones((5, 5), np.uint8)) > 0
    for _ in range(3):
        grown = False
        sorted_mask = np.isin(lab, [c for sym in symbols for c in sym["comps"]])
        near_sorted = cv2.dilate(sorted_mask.astype(np.uint8), np.ones((5, 5), np.uint8)) > 0
        for c in range(1, nlab):
            if c in used:
                continue
            x, y, cw, ch, a_ = stats[c]
            if cw > 2.0 * ss or ch > 2.5 * ss:
                continue  # big pieces are symbols of their own (slurs, words)
            region = lab[y:y + ch, x:x + cw] == c
            if near_sorted[y:y + ch, x:x + cw][region].any():
                ks = {int(owner[o]) for o in np.unique(lab[max(0, y - 3):y + ch + 3, max(0, x - 3):x + cw + 3]) if o and owner[o] >= 0}
                if ks:
                    k = min(ks)
                    symbols[k]["comps"].append(int(c))
                    owner[c] = k
                    used.add(c)
                    grown = True
            elif near_taken[y:y + ch, x:x + cw][region].any():
                taken[lab == c] = 1  # part of a head or stem
                used.add(c)
                grown = True
        if not grown:
            break
    # beyond the staff (half a space past its outer lines) and touching nothing sorted: words and the neighbours' ink
    rows = m["lines"]
    for c in range(1, nlab):
        x, y, cw, ch, a_ = stats[c]
        if c in used or a_ < 0.05 * ss * ss:
            continue
        if cw > 2.0 * ss and ch < 1.6 * ss and a_ < 0.5 * cw * ch:
            add("slur", [c])  # a slur or tie arching beyond the staff
        elif y > rows[-1] + 0.5 * ss or y + ch < rows[0] - 0.5 * ss:
            add("margin", [c])
    # tall thin strokes across the staff: bar lines, wherever they are
    for c in range(1, nlab):
        x, y, cw, ch, a_ = stats[c]
        if c not in used and cw < 1.0 * ss and ch > 3.0 * ss and y < 3.0 * ss and y + ch > 6.0 * ss:
            add("barline", [c])
    # the rest: slurs and ties, marks near notes, and what the label doesn't hold
    for c in range(1, nlab):
        if c in used:
            continue
        x, y, cw, ch, a = stats[c]
        if a < 0.2 * ss * ss and max(cw, ch) < 0.5 * ss and not (cw > 0.15 * ss and ch > 0.15 * ss):
            continue  # specks and scraps of lifted lines
        cy = y + ch / 2
        if cw > 2.0 * ss and ch < 1.6 * ss and a < 0.5 * cw * ch:
            add("slur", [c])
        elif not 0.8 * ss < cy < 8.2 * ss or (cy < 2.3 * ss or cy > 6.7 * ss) and cw > 1.8 * ss:
            add("margin", [c])  # words, the neighbours' ink
        elif cw < 0.45 * ss and ch < 0.45 * ss:
            add("dot-mark", [c])  # staccato, or a dot the label doesn't place
        else:
            add("other", [c])
    # how much ink is left unsorted ("other"): there is almost no stray ink, so this should be near zero
    total = int(on.sum())
    other = sum(int(stats[c][4]) for sym in symbols if sym["kind"] == "other" for c in sym["comps"])
    margin = sum(int(stats[c][4]) for sym in symbols if sym["kind"] == "margin" for c in sym["comps"])
    return {"key": key, "ss": ss, "symbols": symbols, "lab": lab, "taken": taken,
            "ink": total, "unsorted": other, "margins": margin}


def cut(g: np.ndarray, lab: np.ndarray, sym: dict, pad: int = 2) -> tuple[np.ndarray, int, int]:
    """A symbol's ink (only its own components), white elsewhere, and its top-left corner."""
    x0, y0, x1, y1 = sym["box"]
    x0, y0 = max(0, x0 - pad), max(0, y0 - pad)
    x1, y1 = min(g.shape[1], x1 + pad), min(g.shape[0], y1 + pad)
    mask = np.isin(lab[y0:y1, x0:x1], sym["comps"])
    mask = cv2.dilate(mask.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0
    out = np.full((y1 - y0, x1 - x0), 255, np.uint8)
    out[mask] = g[y0:y1, x0:x1][mask]
    return out, x0, y0


COLORS = {"beam": (200, 0, 200), "accidental": (0, 120, 255), "dot": (0, 200, 0), "flag": (255, 120, 0),
          "rest": (0, 160, 0), "slur": (0, 90, 160), "margin": (170, 170, 170), "dot-mark": (0, 200, 200), "other": (0, 0, 255),
          "start": (120, 60, 0), "barline": (60, 60, 60), "tuplet": (200, 160, 0), "trill": (200, 160, 0)}


def sheet(g: np.ndarray, seg: dict, m: dict) -> np.ndarray:
    vis = cv2.cvtColor(g, cv2.COLOR_GRAY2BGR)
    tint = vis.copy()
    tint[seg["taken"] > 0 & (g < 160)] = (0.5 * tint[seg["taken"] > 0 & (g < 160)] + 0.5 * np.array([150, 110, 70])).astype(np.uint8)
    for s in seg["symbols"]:
        col = COLORS.get(s["kind"].split("-")[0], (0, 0, 255))
        mask = np.isin(seg["lab"], s["comps"])
        tint[mask] = (0.4 * tint[mask] + 0.6 * np.array(col)).astype(np.uint8)
    return tint


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="+")
    ap.add_argument("--data", type=Path, default=align.ZEUS / "dataL2")
    ap.add_argument("--maps", type=Path, default=align.ZEUS / "maps")
    ap.add_argument("--glyphs", type=Path, default=align.ZEUS / "glyphs")
    ap.add_argument("--sheet", type=Path)
    a = ap.parse_args()
    rows, tally = [], {}
    for key in a.keys:
        mf = a.maps / f"{key.replace('/', '_')}.json"
        m = json.loads(mf.read_text()) if mf.exists() else align.map_staff(key, a.data)
        g = cv2.imread(str(a.data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
        seg = segment(key, m, g)
        tally["_ink"] = tally.get("_ink", 0) + seg["ink"]
        tally["_unsorted"] = tally.get("_unsorted", 0) + seg["unsorted"]
        tally["_margins"] = tally.get("_margins", 0) + seg["margins"]
        for s in seg["symbols"]:
            tally[s["kind"]] = tally.get(s["kind"], 0) + 1
            if s["kind"] in ("margin", "other"):
                continue
            img, x0, y0 = cut(g, seg["lab"], s)
            d = a.glyphs / HAND(key) / s["kind"]
            d.mkdir(parents=True, exist_ok=True)
            cv2.imwrite(str(d / f"{key.replace('/', '_')}_{x0}_{y0}.png"), img)
        # heads: the ink inside each sure head's oval, its stem left out
        ss = m["ss"]
        on = (align.ink_map(g, ss)[0] > 0.3)
        for b in m["bars"]:
            for n in b["symbols"]:
                if n.get("rest") or n.get("outside") or n["evidence"] < 0.5 or n["grace"]:
                    continue
                r = int(0.9 * ss)
                x0, y0 = max(0, n["x"] - r), max(0, n["y"] - r)
                x1, y1 = min(g.shape[1], n["x"] + r), min(g.shape[0], n["y"] + r)
                mask = np.zeros((y1 - y0, x1 - x0), np.uint8)
                hb = align.head_blob(on, n["x"], n["y"], ss) if n["kind"] not in align.HOLLOW else None
                if hb is not None:
                    msk, bx, by = hb
                    big = np.zeros(g.shape, np.uint8)
                    big[by:by + msk.shape[0], bx:bx + msk.shape[1]] = cv2.dilate(msk.astype(np.uint8), np.ones((3, 3), np.uint8))
                    mask = big[y0:y1, x0:x1]
                else:
                    cv2.ellipse(mask, (n["x"] - x0, n["y"] - y0), (int(0.72 * ss), int(0.56 * ss)), -25, 0, 360, 1, -1)
                keep = (mask > 0) & (g[y0:y1, x0:x1] < 200)
                img = np.full(mask.shape, 255, np.uint8)
                img[keep] = g[y0:y1, x0:x1][keep]
                kind = "head-hollow" if n["kind"] in align.HOLLOW else "head-filled"
                d = a.glyphs / HAND(key) / kind
                d.mkdir(parents=True, exist_ok=True)
                cv2.imwrite(str(d / f"{key.replace('/', '_')}_{n['x'] - (n['x'] - x0)}_{y0}.png"), img)
        mf.write_text(json.dumps(m))  # rests moved to where they were found
        (a.maps / f"{key.replace('/', '_')}.share.json").write_text(json.dumps(
            {"ink": seg["ink"], "unsorted": seg["unsorted"], "margins": seg["margins"]}))
        (a.maps / f"{key.replace('/', '_')}.symbols.json").write_text(
            json.dumps([{k: v for k, v in s.items() if k != "comps"} for s in seg["symbols"]]))
        if a.sheet:
            rows.append(sheet(g, seg, m))
    ink = tally.pop("_ink", 1)
    uns, mar = tally.pop("_unsorted", 0), tally.pop("_margins", 0)
    print(f"ink unsorted: {uns / ink:.1%}; in the margins (words, neighbours): {mar / ink:.1%}")
    print(json.dumps(dict(sorted(tally.items(), key=lambda kv: -kv[1]))))
    if rows:
        width = max(r.shape[1] for r in rows)
        cv2.imwrite(str(a.sheet), np.vstack([np.hstack([r, np.full((r.shape[0], width - r.shape[1], 3), 255, np.uint8)]) for r in rows]))


if __name__ == "__main__":
    main()
