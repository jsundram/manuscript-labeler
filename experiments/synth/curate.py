# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless==4.10.0.84", "numpy"]
# ///
"""Sort a hand's cut glyphs (segment.py's GLYPHS/<hand>/<kind>/) by quality, not by quota.

Each kind gets a typical shape: the median of its cuts, squashed alike (ink
cropped, padded square, 40 x 40), recomputed from the half most like it.
Then every cut, from every kind, is compared with every kind's typical
shape and size:
- like its own kind (shape at least --keep, size within the kind's range): kept;
- more like another kind, and like it enough: moved there (a stem the rest
  finder took is a stem; a slur the accidental finder took is a slur);
- like nothing well enough: thrown out.

Writes GLYPHS/<hand>/curated.json: per file its kind, its verdict (kept,
moved from, out) and its scores. rebuild.py doesn't read it yet: it draws from every cut glyph.

    uv run experiments/synth/curate.py GLYPHS/berlin [--keep 0.55]
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

SIZE = 40
# kinds a cut may be moved into (not "start" or "barline": those are many symbols, or easy to draw)
# where a cut found as one kind may move: a staff's opening holds accidentals; bar lines and beams go nowhere
MOVES = {"start": ("accidental-sharp", "accidental-flat", "accidental-natural"), "barline": (), "beam": ()}
TARGETS = ("head-filled", "head-hollow", "rest-quarter", "rest-eighth", "rest-16th", "flag-eighth", "flag-16th",
           "accidental-sharp", "accidental-natural", "accidental-flat", "slur", "trill", "dot")


def vec(img: np.ndarray) -> tuple[np.ndarray, float, float]:
    """The cut's ink, cropped and squashed to SIZE x SIZE (unit length, mean zero), its log area and its aspect."""
    ink = 255 - img.astype(np.float32)
    ys, xs = np.nonzero(ink > 60)
    if len(xs) < 4:
        return np.zeros(SIZE * SIZE, np.float32), 0.0, 1.0
    c = ink[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    s = max(c.shape)
    pad = np.zeros((s, s), np.float32)
    pad[(s - c.shape[0]) // 2:(s - c.shape[0]) // 2 + c.shape[0], (s - c.shape[1]) // 2:(s - c.shape[1]) // 2 + c.shape[1]] = c
    v = cv2.resize(pad, (SIZE, SIZE), interpolation=cv2.INTER_AREA).ravel()
    v -= v.mean()
    return v / (np.linalg.norm(v) + 1e-6), float(np.log(len(xs))), c.shape[1] / c.shape[0]


def typical(V: np.ndarray, rounds: int = 3) -> np.ndarray:
    med = np.median(V, 0)
    for _ in range(rounds):
        med /= np.linalg.norm(med) + 1e-6
        sc = V @ med
        med = np.median(V[sc >= np.median(sc)], 0)
    return med / (np.linalg.norm(med) + 1e-6)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hand_dir", type=Path)
    ap.add_argument("--keep", type=float, default=0.55, help="the least shape likeness to keep or move a cut")
    a = ap.parse_args()
    cuts = {}
    for d in sorted(p for p in a.hand_dir.iterdir() if p.is_dir()):
        if d.name in ("dot-mark",):
            continue
        cuts[d.name] = [(f, *vec(cv2.imread(str(f), cv2.IMREAD_GRAYSCALE))) for f in sorted(d.glob("*.png"))]
    protos, sizes = {}, {}
    for k, items in cuts.items():
        if k not in TARGETS or len(items) < 5:
            continue
        V = np.stack([v for _, v, _, _ in items])
        protos[k] = typical(V)
        sc = V @ protos[k]
        good = np.array([s for (_, _, s, _), x in zip(items, sc) if x >= np.median(sc)])
        sizes[k] = (float(np.percentile(good, 5)) - 0.4, float(np.percentile(good, 95)) + 0.4)
    names = list(protos)
    P = np.stack([protos[k] for k in names])
    out, tally = {}, {}
    for k, items in cuts.items():
        for f, v, s, asp in items:
            sc = P @ v
            fits = {n: float(x) for n, x in zip(names, sc) if sizes[n][0] <= s <= sizes[n][1]}
            allowed = MOVES.get(k, names)
            fits = {n: x for n, x in fits.items() if n == k or n in allowed}
            own = fits.get(k, -1.0)
            best = max(fits, key=fits.get) if fits else None
            keep = a.keep - 0.1 if len(items) < 40 else a.keep  # few cuts: a rougher typical shape
            if k == "slur":  # slurs vary too much for one shape: long, thin, curved
                ink = cv2.imread(str(f), cv2.IMREAD_GRAYSCALE) < 160
                ys, xs = np.nonzero(ink)
                wd, ht = (xs.max() - xs.min() + 1, ys.max() - ys.min() + 1) if len(xs) else (1, 1)
                ok = wd > 2.5 * ht and ink.sum() < 0.45 * wd * ht
                verdict, kind = ("kept", k) if ok else ("out", k)
            elif k in protos and own >= keep and (best == k or own >= fits[best] - 0.05):
                verdict, kind = "kept", k
            elif best and best != "slur" and fits[best] >= a.keep + 0.05 and best != k:
                verdict, kind = f"moved from {k}", best
            elif k not in protos and k not in ("start", "barline", "margin", "other"):
                verdict, kind = "kept", k  # too few to judge
            else:
                verdict, kind = "out", k
            out[str(f.relative_to(a.hand_dir))] = {"kind": kind, "verdict": verdict, "own": round(own, 3),
                                                   "best": best, "best_score": round(fits.get(best, 0), 3) if best else None}
            tally.setdefault(kind, {"kept": 0, "moved in": 0}).__setitem__(
                "kept" if verdict == "kept" else "moved in", tally.get(kind, {}).get("kept" if verdict == "kept" else "moved in", 0) + (verdict != "out"))
            if verdict == "out":
                tally.setdefault(k, {"kept": 0, "moved in": 0})
                tally[k]["out"] = tally[k].get("out", 0) + 1
    (a.hand_dir / "curated.json").write_text(json.dumps(out, indent=0))
    for k in sorted(tally):
        print(k, tally[k])


if __name__ == "__main__":
    main()
