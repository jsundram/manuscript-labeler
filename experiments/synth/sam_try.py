# /// script
# requires-python = ">=3.11"
# dependencies = ["torch==2.14.1", "torchvision", "transformers==5.20.1", "pillow", "numpy", "opencv-python-headless==4.10.0.84"]
# ///
"""Segment Anything 2.1 (small), untrained, on two-bar windows of a mapped staff: a point on each head, a box round
each other symbol the segmenter found; the masks drawn over the window, one colour each.

    uv run experiments/synth/sam_try.py D-B_KHM-602/p7s1 --maps DIR --out OUT.png [--bars 1 2]
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np
import torch
from PIL import Image
from transformers import Sam2Model, Sam2Processor

ZEUS = Path.home() / ".cache/manuscript-labeler/zeus"


def windows(m: dict, w: int, ss: float):
    """Overlapping pairs of bars (1-2, 2-3, ...), each padded half a space; a one-bar staff is its own window."""
    xs = [(b["x0"], b["x1"]) for b in m["bars"]]
    pairs = [(xs[i][0], xs[i + 1][1]) for i in range(len(xs) - 1)] or xs
    return [(max(0, int(a - 0.5 * ss)), min(w, int(b + 0.5 * ss))) for a, b in pairs]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("key")
    ap.add_argument("--maps", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--windows", type=int, nargs="*", default=[0, 1])
    a = ap.parse_args()
    dev = "mps" if torch.backends.mps.is_available() else "cpu"
    model = Sam2Model.from_pretrained("facebook/sam2.1-hiera-small").to(dev).eval()
    proc = Sam2Processor.from_pretrained("facebook/sam2.1-hiera-small")
    stem = a.key.replace("/", "_")
    m = json.loads((a.maps / f"{stem}.json").read_text())
    syms = json.loads((a.maps / f"{stem}.symbols.json").read_text())
    g = cv2.imread(str(ZEUS / "dataL2" / f"{a.key}.jpg"), cv2.IMREAD_GRAYSCALE)
    h, w = g.shape
    ss = m["ss"]
    rows = []
    rng = np.random.default_rng(0)
    for wi in a.windows:
        x0, x1 = windows(m, w, ss)[wi]
        img = cv2.cvtColor(g[:, x0:x1], cv2.COLOR_GRAY2RGB)
        heads = [n for b in m["bars"] for n in b["symbols"] if not n.get("rest") and not n.get("outside") and x0 <= n["x"] < x1]
        boxes = [s for s in syms if s["kind"] not in ("margin", "other", "dot-mark", "start") and x0 <= s["box"][0] and s["box"][2] < x1]
        vis = img.copy()
        # heads: one point each; other symbols: their box
        prompts = [("point", [n["x"] - x0, n["y"]]) for n in heads] + [("box", [s["box"][0] - x0, s["box"][1], s["box"][2] - x0, s["box"][3]]) for s in boxes]
        pil = Image.fromarray(img)
        for kind, p in prompts:
            if kind == "point":
                inp = proc(images=pil, input_points=[[[p]]], input_labels=[[[1]]], return_tensors="pt").to(dev)
            else:
                inp = proc(images=pil, input_boxes=[[p]], return_tensors="pt").to(dev)
            with torch.no_grad():
                out = model(**inp, multimask_output=False)
            mask = proc.post_process_masks(out.pred_masks.cpu(), inp["original_sizes"].cpu())[0][0, 0].numpy() > 0
            col = rng.integers(40, 230, 3)
            vis[mask] = (0.45 * vis[mask] + 0.55 * col).astype(np.uint8)
        rows.append(cv2.resize(vis, None, fx=2, fy=2, interpolation=cv2.INTER_NEAREST))
        rows.append(np.full((8, rows[-1].shape[1], 3), 255, np.uint8))
    width = max(r.shape[1] for r in rows)
    cv2.imwrite(str(a.out), np.vstack([np.hstack([r, np.full((r.shape[0], width - r.shape[1], 3), 255, np.uint8)]) for r in rows])[..., ::-1])
    print(a.out)


if __name__ == "__main__":
    main()
