# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Build the bar-line corpus: one straightened image per labelled staff line.

    uv run experiments/barlines/corpus.py <edition-repo> <out-dir> [--test 0.2] [--seed 1]

Every counted staff line on the *reviewed* music pages of every source whose
labels file exists becomes one example: the staff, straightened along the
editor's bend, cropped from the staff's left to right edge and 3 staff
spaces above and below, at the labeler's render size (pdftoppm -scale-to
2800). Its labels are the editor's bar lines, as x in the crop (pixels at
the staff's middle) plus the lean. Lines are split into train / test at
random (fixed seed), stratified by source, so both copyists and all parts
are on both sides.

Writes <out>/lines/<id>.png and <out>/corpus.json:
  {"lines": [{"id", "source", "pdf", "page", "part", "split", "file",
              "width", "height", "space", "staff_top", "staff_bottom",
              "page_w", "page_h", "left", "top_frac", "bars": [{"x", "x0", "x1"}]}]}
x0/x1 are where the bar line crosses the top / bottom staff line (crop px).
"""

import argparse
import json
import random
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
import labels  # noqa: E402
from server import JPEG_QUALITY, RENDER_PX  # noqa: E402

MARGIN = 3.0  # staff spaces kept above and below the staff


def render(pdf: Path, page: int, tmp: Path) -> np.ndarray:
    base = tmp / f"{pdf.stem}-p{page}"
    subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", str(RENDER_PX),
                    "-jpeg", "-jpegopt", f"quality={JPEG_QUALITY}", "-singlefile", str(pdf), str(base)], check=True)
    return np.asarray(Image.open(base.with_suffix(".jpg")).convert("L"))


def straight_band(g: np.ndarray, s: dict, x0: int | None = None, x1: int | None = None) -> tuple[np.ndarray, dict]:
    """The staff from left to right (or from pixel x0 to x1), MARGIN
    spaces above and below, each column shifted by the staff's bend so the
    lines run level (beyond the staff's ends, the bend at its nearer end)."""
    h, w = g.shape
    top, bottom = s["top"] * h, s["bottom"] * h
    space = (bottom - top) / 4
    if x0 is None or x1 is None:
        x0, x1 = int(round(s["left"] * w)), int(round(s["right"] * w))
    xs = np.arange(x0, x1)
    shift = np.array([labels.bend_at(s, x / w) * h for x in xs])
    y_top = top - MARGIN * space
    rows = np.arange(int(round(y_top)), int(round(bottom + MARGIN * space)) + 1)
    ys = np.clip(rows[:, None] + np.round(shift)[None, :].astype(int), 0, h - 1)
    band = g[ys, xs[None, :]]
    geo = {"x_off": x0, "y_top": float(rows[0]), "space": float(space),
           "staff_top": float(top - rows[0]), "staff_bottom": float(bottom - rows[0])}
    return band, geo


def paper_band(g: np.ndarray, s: dict, corners: list) -> tuple[np.ndarray, dict]:
    """straight_band across the paper's whole width at the staff's height
    (its corners: find_page_corners or the editor's): what the bar-line
    detectors' cached predictions are made on, so a staff's ends, where
    detection and the editor most often disagree, don't limit them."""
    sys.path.insert(0, str(HERE.parent.parent))
    import detect
    h, w = g.shape
    lo, hi = detect.paper_x(corners, (s["top"] + s["bottom"]) / 2, w)
    return straight_band(g, s, max(0, lo), min(w, max(hi, lo + 1)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edition", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--test", type=float, default=0.2, help="share of lines held out for testing")
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args()
    (args.out / "lines").mkdir(parents=True, exist_ok=True)

    lines = []
    with tempfile.TemporaryDirectory() as tmp:
        for lp in sorted(args.edition.glob("sources/**/*.labels.json")):
            pdf = lp.with_name(lp.name.replace(".labels.json", ".pdf"))
            doc = json.loads(lp.read_text())
            for n, p in sorted(doc["pages"].items(), key=lambda kp: int(kp[0])):
                if p["status"] != "reviewed" or p["kind"] != "music":
                    continue
                g = render(pdf, int(n), Path(tmp))
                h, w = g.shape
                for k, s in enumerate(sorted(p["systems"], key=lambda s: s["top"])):
                    if s.get("role", "part") != "part" or not s["barlines"]:
                        continue
                    band, geo = straight_band(g, s)
                    lid = f"{pdf.stem}-p{int(n):02d}-l{k + 1:02d}"
                    Image.fromarray(band).save(args.out / "lines" / f"{lid}.png")
                    bars = []
                    for b in s["barlines"]:
                        # page fractions -> crop pixels (x at the staff's middle)
                        x0, x1 = b["x0"] * w - geo["x_off"], b["x1"] * w - geo["x_off"]
                        bars.append({"x": (x0 + x1) / 2, "x0": x0, "x1": x1})
                    lines.append({
                        "id": lid, "source": pdf.stem, "pdf": str(pdf.relative_to(args.edition)),
                        "page": int(n), "part": p["part"], "file": f"lines/{lid}.png",
                        "width": band.shape[1], "height": band.shape[0], "space": geo["space"],
                        "staff_top": geo["staff_top"], "staff_bottom": geo["staff_bottom"],
                        "page_w": w, "page_h": h, "left": geo["x_off"], "top_frac": s["top"],
                        "bars": sorted(bars, key=lambda b: b["x"]),
                    })
                print(f"{pdf.stem} p{n}: {sum(1 for l in lines if l['page'] == int(n) and l['source'] == pdf.stem)} lines")

    # split by line, stratified by source
    rng = random.Random(args.seed)
    for src in sorted({l["source"] for l in lines}):
        ids = [l for l in lines if l["source"] == src]
        rng.shuffle(ids)
        k = round(len(ids) * args.test)
        for i, l in enumerate(ids):
            l["split"] = "test" if i < k else "train"
    (args.out / "corpus.json").write_text(json.dumps({"seed": args.seed, "tolerance_frac": 0.006, "lines": lines}, indent=1))
    for split in ("train", "test"):
        ls = [l for l in lines if l["split"] == split]
        print(f"{split}: {len(ls)} lines, {sum(len(l['bars']) for l in ls)} bar lines, "
              f"{dict((s, sum(1 for l in ls if l['source'] == s)) for s in sorted({l['source'] for l in ls}))}")


if __name__ == "__main__":
    main()
