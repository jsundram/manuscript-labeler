"""Shared by the detector runners: run a tile detector over whole lines,
merge across tiles, pick the confidence threshold on the validation lines
(never the test lines), and write a result for harness.py to score."""

import json
import time
from pathlib import Path

from PIL import Image

from harness import match, write
from tiles import TILE, windows


def lines(corpus: Path, which: str) -> list[dict]:
    c = json.loads((corpus / "corpus.json").read_text())
    val = set(json.loads((corpus / "tiles" / "val_ids.json").read_text()))
    if which == "val":
        return [l for l in c["lines"] if l["id"] in val]
    return [l for l in c["lines"] if l["split"] == which]


def run(corpus: Path, ls: list[dict], detect_tile) -> tuple[dict, float]:
    """{line id: [(x, conf)]} merged across tiles, and seconds per line.
    detect_tile(PIL image) -> [(x_center, conf)] in tile pixels."""
    out, t0 = {}, time.perf_counter()
    for line in ls:
        img = Image.open(corpus / line["file"]).convert("RGB")
        found = []
        for x in windows(line["width"]):
            tile = img.crop((x, 0, x + TILE, line["height"]))
            found += [(x + xc, conf) for xc, conf in detect_tile(tile)]
        # the same bar line seen in two tiles: keep the surer one
        tol = 0.3 * line["space"] * 2
        kept = []
        for xc, conf in sorted(found, key=lambda d: -d[1]):
            if all(abs(xc - k) > tol for k, _ in kept):
                kept.append((xc, conf))
        out[line["id"]] = sorted(kept)
    return out, (time.perf_counter() - t0) / max(1, len(ls))


def best_threshold(corpus: Path, preds: dict, ls: list[dict]) -> float:
    c = json.loads((corpus / "corpus.json").read_text())
    tol = c["tolerance_frac"]
    best = (0.5, -1)
    for th in [i / 20 for i in range(1, 20)]:
        f = fp = m = 0
        for line in ls:
            a, b, d = match([x for x, cf in preds[line["id"]] if cf >= th], [b["x"] for b in line["bars"]], tol * line["page_w"])
            f, fp, m = f + a, fp + b, m + d
        f1 = 2 * f / (2 * f + fp + m) if f else 0
        if f1 > best[1]:
            best = (th, f1)
    return best[0]


def finish(corpus: Path, method: str, detect_tile, train_s: float, notes: str):
    val = lines(corpus, "val")
    vpred, _ = run(corpus, val, detect_tile)
    th = best_threshold(corpus, vpred, val)
    tpred, per_line = run(corpus, lines(corpus, "test"), detect_tile)
    write(corpus, {"method": method, "train_s": train_s, "infer_s": per_line, "threshold": th,
                   "lines": {k: [x for x, cf in v if cf >= th] for k, v in tpred.items()},
                   "notes": f"{notes}; threshold {th:.2f} (chosen on val)"})
