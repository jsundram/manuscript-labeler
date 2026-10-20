# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless==4.10.0.84", "numpy"]
# ///
"""Our copyists' clefs, cut from the start of their training staves, for
copyist.py to draw in place of a font's.

Every staff starts with a clef whose kind its LMX names (its first clef
token), at the staff's start. The cut starts at the first ink at the staff's left end and ends at the emptiest
column within the clef kind's range of widths (so a key signature after it
stays out). The staff lines are lifted off (each row's floor), ink far
above and below the staff (the neighbours') is dropped, and what's left is
kept as ink, the crop's full height (nine spaces, so the staff sits where
copyist.py's does). Paris B is left out: its continuation lines have no
clef.

    uv run experiments/synth/harvest_clefs.py [--data DIR] [--out DIR] [--labels DIR]

Only staves in training lists (D1's: --lists) are used, so the clean test
and the practice exam give nothing. Writes OUT/<hand>/<clef>/<source>_<staff>.png
and OUT/sheet.png to judge them by eye.
"""
import argparse
import json
import re
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

ZEUS = Path.home() / ".cache/manuscript-labeler/zeus"
LABELS = Path.home() / "Dropbox/Code/manuscript-labeler/data/boccherini-opus-48/sources"
SOURCES = {"D-B_KHM-602": "G226", "D-B_KHM-603": "G227", "F-Po_RES-507-14": "G228", "F-Pn_Vma-ms-1067-1": "G228",
           "F-Po_RES-507-17": "G230", "F-Pn_Vma-ms-1067-3": "G230"}
TRAIN = ["D-B_KHM-602-I", "D-B_KHM-603-II", "F-Pn_Vma-ms-1067-1-I", "F-Pn_Vma-ms-1067-1-II", "F-Pn_Vma-ms-1067-3-II",
         "F-Po_RES-507-14-I", "F-Po_RES-507-14-II", "F-Po_RES-507-17-II"]  # D1's Op. 48 training lists


def hand(source: str, part: str) -> str:
    if source.startswith("D-B_KHM"):
        return "berlin"
    if source.startswith("F-Po_RES-507"):
        return "parisA" if part in ("vn1", "vc") else "parisB"
    return "vma"


WIDTH = {"G2": (1.6, 2.8), "C3": (1.4, 2.6), "C4": (1.4, 2.6), "C1": (1.4, 2.6), "F4": (2.0, 3.4)}  # spaces
HAND_WIDTH = {("berlin", "G2"): (2.6, 3.8), ("berlin", "C3"): (2.2, 3.2), ("berlin", "F4"): (2.6, 3.8), ("vma", "G2"): (1.6, 2.2), ("vma", "C3"): (1.2, 2.0)}


def typical(ims: list, keep: float = 0.6) -> list:
    """The share of cuts most like their median (each resized alike): mis-cuts and mislabelled clefs drop out."""
    if len(ims) < 5:
        return ims
    size = (48, 96)
    v = np.stack([cv2.resize(i, size, interpolation=cv2.INTER_AREA).astype(np.float32).ravel() for i in ims])
    v -= v.mean(1, keepdims=True)
    v /= np.linalg.norm(v, axis=1, keepdims=True) + 1e-6
    med = np.median(v, 0)
    score = v @ (med / (np.linalg.norm(med) + 1e-6))
    order = np.argsort(-score)[: max(3, int(len(ims) * keep))]
    return [ims[k] for k in sorted(order)]


def cut(g: np.ndarray, clef: str, width=None):
    """The clef's ink at the staff's start, staff lines lifted off; None if it can't be found.
    It ends at the emptiest column in the clef kind's range of widths (before a key signature)."""
    h, w = g.shape
    ss = h / 9
    ink = np.clip((1 - g.astype(np.float32) / 255 - 0.2) / 0.8, 0, 1)
    region = ink[:, : int(9 * ss)]
    ink = np.clip(ink - np.percentile(region, 40, axis=1, keepdims=True) * 1.2, 0, 1)  # lines: each row's floor
    ink[: int(0.7 * ss)] = 0
    ink[int(8.3 * ss):] = 0  # the staves above and below
    profile = ink[int(2 * ss):int(7 * ss)].sum(0)
    on = profile > 0.15 * ss
    x0 = int(0.6 * ss)
    while x0 < min(w, 3 * ss) and not on[x0]:
        x0 += 1
    if x0 >= 3 * ss:
        return None
    lo, hi = width or WIDTH.get(clef, (1.4, 3.0))
    a, b = x0 + int(lo * ss), min(w - 1, x0 + int(hi * ss))
    if b <= a:
        return None
    x1 = a + int(np.argmin(np.convolve(profile[a:b], np.ones(3) / 3, "same")))
    if profile[x1] > 0.6 * ss:  # no clean break: something runs on
        return None
    patch = ink[:, max(0, x0 - 2):x1 + 1]
    if patch.mean() < 0.02:
        return None
    return (patch * 255).astype(np.uint8), ss


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", type=Path, default=ZEUS / "dataL2")
    ap.add_argument("--out", type=Path, default=ZEUS / "glyphs" / "clefs")
    ap.add_argument("--labels", type=Path, default=LABELS)
    ap.add_argument("--lists", nargs="+", default=TRAIN)
    a = ap.parse_args()
    parts = {}
    for src, g in SOURCES.items():
        pages = json.loads((a.labels / g / f"{src}.labels.json").read_text())["pages"]
        parts[src] = {k: p.get("part") for k, p in pages.items()}
    got = defaultdict(list)
    for name in a.lists:
        for key in (a.data / f"samples.{name}.txt").read_text().split():
            src, staff = key.split("/")
            base = re.sub(r"-noslur$", "", src)
            toks = (a.data / f"{key}.lmx").read_text().split()
            clef = next((t.split(":")[1] for t in toks if t.startswith("clef:")), None)
            if clef is None:
                continue
            h = hand(base, parts[base].get(re.match(r"p(\d+)", staff).group(1)))
            if h == "parisB":
                continue  # its continuation lines have no clef
            r = cut(cv2.imread(str(a.data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE), clef, HAND_WIDTH.get((h, clef)))
            if r is not None:
                got[(h, clef)].append((f"{base}_{staff}", 255 - r[0]))
    rows = []
    for (h, clef), cuts in sorted(got.items()):
        if len(cuts) < 8:
            print(h, clef, f"left out: only {len(cuts)}")
            continue
        kept = typical([im for _, im in cuts])
        ids = {id(im) for im in kept}
        d = a.out / h / clef
        d.mkdir(parents=True, exist_ok=True)
        for name, im in cuts:
            if id(im) in ids:
                cv2.imwrite(str(d / f"{name}.png"), im)
        ims = kept
        print(h, clef, f"{len(ims)} kept of {len(cuts)}")
        strip = np.hstack([cv2.resize(i, (int(i.shape[1] * 90 / i.shape[0]), 90)) for i in ims[:24]])
        label = np.full((90, 160), 255, np.uint8)
        cv2.putText(label, f"{h} {clef}", (4, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, 0, 1, cv2.LINE_AA)
        rows.append(np.hstack([label, strip]))
    width = max(r.shape[1] for r in rows)
    sheet = np.vstack([np.hstack([r, np.full((90, width - r.shape[1]), 255, np.uint8)]) for r in rows])
    cv2.imwrite(str(a.out / "sheet.png"), sheet)


if __name__ == "__main__":
    main()
