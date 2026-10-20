# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless==4.10.0.84", "numpy"]
# ///
"""The glyph map: per kind, how many the labels hold, how many were cut, kept,
moved in and thrown out (curate.py), with samples of each; and heads shown in
their place on the staff, the found oval drawn over them.

    uv run experiments/synth/glyph_sheet.py GLYPHS/berlin COUNTS.json MAPS OUT.png
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import cv2
import numpy as np

import align

KINDS = ["head-filled", "head-hollow", "rest-quarter", "rest-eighth", "rest-16th", "flag-eighth", "flag-16th",
         "accidental-sharp", "accidental-flat", "accidental-natural", "dot", "slur", "trill"]
H, W, LAB = 50, 1600, 230


def strip(text, ims, shade=255, n=22, tags=None):
    rng = random.Random(4)
    order = list(range(len(ims)))
    rng.shuffle(order)
    order = order[:n]
    lab = np.full((H, LAB), shade, np.uint8)
    for k, line in enumerate(text.split("\n")):
        cv2.putText(lab, line, (6, 20 + 18 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.45, 30, 1, cv2.LINE_AA)
    cells = []
    for i in order:
        im = ims[i]
        im = cv2.resize(im, (max(1, int(im.shape[1] * (H - 12) / im.shape[0])), H - 12), interpolation=cv2.INTER_AREA)
        cell = np.full((H, im.shape[1] + 10), shade, np.uint8)
        cell[:H - 12, 5:5 + im.shape[1]] = np.minimum(im, shade)
        if tags:
            cv2.putText(cell, tags[i][:9], (2, H - 2), cv2.FONT_HERSHEY_PLAIN, 0.7, 90, 1)
        cells.append(cell)
    row = np.hstack([lab] + cells)[:, :W] if cells else lab
    return np.hstack([row, np.full((H, W - row.shape[1]), shade, np.uint8)])


def heads_in_place(maps: Path, data: Path, n_good=22, n_bad=22) -> list[np.ndarray]:
    """Heads in their patch of staff (1.6 spaces each side), the found oval in red: strong evidence, then weak."""
    good, weak = [], []
    for f in sorted(maps.glob("*.json")):
        if f.name.endswith(".symbols.json"):
            continue
        m = json.loads(f.read_text())
        key = "/".join(f.stem.rsplit("_", 1))
        g = cv2.imread(str(data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
        ss = m["ss"]
        for b in m["bars"]:
            for nt in b["symbols"]:
                if nt.get("rest") or nt.get("outside"):
                    continue
                r = int(1.6 * ss)
                x0, y0 = max(0, nt["x"] - r), max(0, nt["y"] - r)
                patch = cv2.cvtColor(g[y0:nt["y"] + r, x0:nt["x"] + r], cv2.COLOR_GRAY2BGR)
                cv2.ellipse(patch, (nt["x"] - x0, nt["y"] - y0), (int(0.62 * ss), int(0.48 * ss)), -25, 0, 360, (0, 0, 230), 1)
                (good if nt["evidence"] >= 0.5 else weak).append(patch)
    rng = random.Random(9)
    rows = []
    for name, items, n in (("heads in place, strong evidence", good, n_good), ("heads in place, weak evidence", weak, n_bad)):
        pick = rng.sample(items, min(n, len(items)))
        hh = 64
        cells = [cv2.resize(p, (int(p.shape[1] * hh / p.shape[0]), hh)) for p in pick]
        lab = np.full((hh, LAB, 3), 255, np.uint8)
        cv2.putText(lab, name.split(",")[0], (6, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)
        cv2.putText(lab, name.split(",")[1].strip() + f" ({len(items)})", (6, 44), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (30, 30, 30), 1, cv2.LINE_AA)
        row = np.hstack([lab] + [np.hstack([c, np.full((hh, 6, 3), 255, np.uint8)]) for c in cells])[:, :W]
        rows.append(np.hstack([row, np.full((hh, W - row.shape[1], 3), 255, np.uint8)]))
        rows.append(np.full((6, W, 3), 210, np.uint8))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("hand_dir", type=Path)
    ap.add_argument("counts", type=Path, help="per kind [in the labels, cut] (the counts script's output)")
    ap.add_argument("maps", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--data", type=Path, default=align.ZEUS / "dataL2")
    a = ap.parse_args()
    cur = json.loads((a.hand_dir / "curated.json").read_text())
    counts = json.loads(a.counts.read_text())
    groups = defaultdict(lambda: {"kept": [], "moved": [], "out": []})
    tags = defaultdict(list)
    for rel, c in cur.items():
        im = cv2.imread(str(a.hand_dir / rel), cv2.IMREAD_GRAYSCALE)
        if c["verdict"] == "kept":
            groups[c["kind"]]["kept"].append(im)
        elif c["verdict"].startswith("moved"):
            groups[c["kind"]]["moved"].append(im)
            tags[c["kind"]].append(c["verdict"].split("from ")[1])
        else:
            groups[rel.split("/")[0]]["out"].append(im)
    rows = [cv2.cvtColor(r, cv2.COLOR_BGR2GRAY) for r in heads_in_place(a.maps, a.data)]
    for k in KINDS:
        gk = groups[k]
        lab_n, cut_n = counts.get(k, [0, 0])
        head = f"{k}\nlabels {lab_n} cut {cut_n} kept {len(gk['kept'])}"
        rows.append(strip(head, gk["kept"]))
        if gk["moved"]:
            rows.append(strip(f"  moved in {len(gk['moved'])}\n  (from: under each)", gk["moved"], 244, tags=tags[k]))
        if gk["out"]:
            rows.append(strip(f"  thrown out {len(gk['out'])}", gk["out"], 226))
        rows.append(np.full((8, W), 190, np.uint8))
    cv2.imwrite(str(a.out), np.vstack(rows))
    print(a.out)


if __name__ == "__main__":
    main()
