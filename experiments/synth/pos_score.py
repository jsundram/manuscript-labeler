# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless==4.10.0.84", "numpy"]
# ///
"""The classical map (align.map_staff's steps) on pos_data.py's rendered staves, scored against their exact places, as
musvit/pointer.py's predictions are: the median error in staff spaces and the share within half a space, per kind.

The map is given what the labels give it on a real staff: the bar lines and where the opening ends (both exact here).
So its bar lines aren't scored; its rests are scored sideways only (it places them by x).

    uv run experiments/synth/pos_score.py DIR [...] [--json OUT] [--pred RUN_DIR]

--pred: a pointer.py run's predictions-<DIR name>.json, scored beside the map on the same symbols (those the map
placed), and on all.
"""
import argparse
import json
import math
from pathlib import Path

import cv2
import numpy as np

import align
import pos_data
import segment


def classical(g: np.ndarray, lmx: str, start: float | None, barlines: list[float]) -> dict:
    """align.map_staff with the bar edges given (not from the labels' file), then segment.py's rest finding (it moves
    each rest it finds to its ink; the map alone only spaces rests between the notes)."""
    h, w = g.shape
    rows = align.fit_lines(np.clip((1 - g.astype(np.float32) / 255 - 0.15) / 0.6, 0, 1), h / 9)
    ss = (rows[-1] - rows[0]) / 4
    bars = align.parse(lmx)
    edges = [start if start is not None else 4 * ss] + sorted(barlines)
    if len(edges) - 1 < len(bars):
        edges.append(w - ss)
    edges = list(zip(edges[:-1], edges[1:]))[: len(bars)]
    ink, rows, th = align.ink_map(g, ss)
    maps = align.head_maps(ink, ss)
    for x in barlines:  # no head on a bar line
        for mp in maps:
            mp[:, max(0, int(x - 0.5 * ss)):min(w, int(x + 0.5 * ss) + 1)] = -1.0
    out = {"ss": ss, "lines": rows, "bars": [],
           "barlines": [[int(x), int(rows[0]), int(x), int(rows[-1]), "single"] for x in barlines]}
    for bar, (x0, x1) in zip(bars, edges):
        notes = align.place_bar(bar["events"], x0, x1, maps, ss, bar["clef"], rows[0])
        align.refine_heads(notes, ink, ss)
        align.stems(notes, ink, ss)
        out["bars"].append({"x0": x0, "x1": x1, "clef": bar["clef"], "symbols": notes})
    segment.segment("D-B_rendered/staff", out, g)
    return out


def placed(m: dict, lmx: str) -> dict[int, tuple[str, float, float | None]]:
    """Each token's place by the map: notes (x, y), rests (x)."""
    out = {}
    for b, mb in zip(pos_data.walk(lmx), m["bars"]):
        voices = sorted({e["voice"] for e in b["events"] if e["type"] == "note"})
        evs = [e for v in voices for e in b["events"] if e["voice"] == v]
        if len(evs) != len(mb["symbols"]):
            continue
        for e, s in zip(evs, mb["symbols"]):
            if s.get("rest"):
                if s.get("found"):
                    out[e["tok"]] = ("rest", float(s["x"]), None)
            elif not s.get("outside"):
                out[e["tok"]] = ("note", float(s["x"]), float(s["y"]))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dirs", nargs="+", type=Path)
    ap.add_argument("--json", type=Path)
    ap.add_argument("--pred", type=Path, help="a pointer.py run's directory (predictions-<dir name>.json)")
    a = ap.parse_args()
    res = {}
    def err(kind, tx, ty, px, py, ss):
        ex = abs(px - tx) / ss
        return ex if kind in ("rest_x", "barline") else math.hypot(ex, abs(py - ty) / ss)

    def stats(v):
        return {"n": len(v), "median": round(float(np.median(v)), 3), "within_half": round(float(np.mean([e <= 0.5 for e in v])), 3)}

    for d in a.dirs:
        errs, missed = {}, {}
        pred = {}
        if a.pred and (a.pred / f"predictions-{d.name}.json").exists():
            pred = json.loads((a.pred / f"predictions-{d.name}.json").read_text())
        paired, ptr_all = {}, {}
        for f in sorted(d.glob("*.pos.json")):
            p = json.loads(f.read_text())
            name = f.name[: -len(".pos.json")]
            g = cv2.imread(str(d / f"{name}.jpg"), cv2.IMREAD_GRAYSCALE)
            lmx = (d / f"{name}.lmx").read_text()
            try:
                got = placed(classical(g, lmx, p["start"], p["barlines"]), lmx)
            except Exception:
                got = {}
            ss = p["ss"]
            mine = {t[0]: t for t in pred.get(f"{d.name}/{name}", {}).get("points", [])}
            for tok, kind, tx, ty in p["targets"]:
                if tok in mine:
                    ptr_all.setdefault(kind, []).append(err(kind, tx, ty, mine[tok][4], mine[tok][5], ss))
                if kind == "barline":
                    continue
                k = "rest_x" if kind == "rest" else kind
                if tok not in got:
                    missed[k] = missed.get(k, 0) + 1
                    continue
                _, px, py = got[tok]
                e = err(k, tx, ty, px, py, ss)
                errs.setdefault(k, []).append(e)
                if tok in mine:
                    paired.setdefault(k, []).append((e, err(k, tx, ty, mine[tok][4], mine[tok][5], ss)))
        res[d.name] = {k: {"n": len(v), "missed": missed.get(k, 0), "median": round(float(np.median(v)), 3),
                           "within_half": round(float(np.mean([e <= 0.5 for e in v])), 3)} for k, v in sorted(errs.items())}
        print(d.name, json.dumps(res[d.name]), flush=True)
        if pred:
            res[d.name + " pointer"] = {"all": {k: stats(v) for k, v in sorted(ptr_all.items())},
                                        "paired": {k: {"map": stats([c for c, _ in v]), "pointer": stats([q for _, q in v])}
                                                   for k, v in sorted(paired.items())}}
            print(d.name, "pointer", json.dumps(res[d.name + " pointer"]), flush=True)
    if a.json:
        a.json.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
