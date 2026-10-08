# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Build the bar-line corpus: one straightened image per labelled staff line.

    uv run experiments/barlines/corpus.py <edition-repo> <out-dir> [--test 0.2] [--test-source STEM] [--paper]

Every counted staff line on the *reviewed* music pages of every source whose
labels file exists becomes one example: the staff, straightened along the
editor's bend, cropped from the staff's left to right edge and 3 staff
spaces above and below, at the labeler's render size (pdftoppm -scale-to
2800). Its labels are the editor's bar lines, as x in the crop (pixels at
the staff's middle) plus the lean. Lines are split into train / test by
page, so no page is on both sides, and for good: a page's side comes from
a hash of its source and number (about --test of the pages are test), so
it never changes as more pages are reviewed and models trained on earlier
corpora can be compared on later ones. The pages in test_pages.json are
always test (pages no model saw, annotated for measuring), and so is every
page of a --test-source (an unseen copy).

Writes <out>/lines/<id>.png and <out>/corpus.json:
  {"lines": [{"id", "source", "pdf", "page", "part", "split", "file",
              "width", "height", "space", "staff_top", "staff_bottom",
              "page_w", "page_h", "left", "top_frac", "bars": [{"x", "x0", "x1"}]}]}
x0/x1 are where the bar line crosses the top / bottom staff line (crop px).
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
import detect  # noqa: E402
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


def held_out_pages() -> dict[str, list[int]]:
    """test_pages.json: {source (pdf stem): [pages]} held out of every corpus."""
    return json.loads((Path(__file__).resolve().parent / "test_pages.json").read_text())["pages"]


def page_hash(source: str, page: int, salt: str = "") -> float:
    """A page's fixed place in [0, 1): by source and page number, so the
    same in every corpus however many pages are reviewed. `salt` gives an
    independent one (validation, folds)."""
    return int(hashlib.sha1(f"{salt}{source}:{page}".encode()).hexdigest()[:8], 16) / 16 ** 8


def test_page(source: str, page: int, share: float, test_sources: list[str], held: dict) -> bool:
    """Whether a page is a test page, the same in every corpus: one of
    test_pages.json's, of a held-out source, or one whose hash falls in the
    test share."""
    return page in held.get(source, []) or source in test_sources or page_hash(source, page) < share


def paper_band(g: np.ndarray, s: dict, corners: list) -> tuple[np.ndarray, dict]:
    """straight_band across the paper's whole width at the staff's height
    (its corners: find_page_corners or the editor's): what the bar-line
    detectors' cached predictions are made on, so a staff's ends, where
    detection and the editor most often disagree, don't limit them."""
    h, w = g.shape
    lo, hi = detect.paper_x(corners, (s["top"] + s["bottom"]) / 2, w)
    return straight_band(g, s, max(0, lo), min(w, max(hi, lo + 1)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edition", type=Path)
    ap.add_argument("out", type=Path)
    ap.add_argument("--test", type=float, default=0.2, help="share of pages held out for testing (by a hash of each page)")
    ap.add_argument("--paper", action="store_true",
                    help="cut each staff across the paper's width (paper_band, as the labeler's cache does) "
                         "and record its left end, music start and right end, for landmark classes")
    ap.add_argument("--test-source", action="append", default=[],
                    help="put every line of this source (pdf stem) in the test split: an unseen copy")
    args = ap.parse_args()
    # a corpus is built once: tiles, runs and results from an earlier split
    # would mix with this one (thresholds chosen on what is now test, ...)
    stale = [d for d in ("tiles", "runs", "results", "e2e", "logs") if (args.out / d).exists()]
    if stale:
        sys.exit(f"{args.out} already holds {', '.join(stale)} from an earlier corpus: build into a new directory")
    (args.out / "lines").mkdir(parents=True, exist_ok=True)
    reviewed: set[tuple[str, int]] = set()  # (source, page) of every reviewed music page

    lines = []
    with tempfile.TemporaryDirectory() as tmp:
        for lp in sorted(args.edition.glob("sources/**/*.labels.json")):
            pdf = lp.with_name(lp.name.replace(".labels.json", ".pdf"))
            doc = json.loads(lp.read_text())
            for n, p in sorted(doc["pages"].items(), key=lambda kp: int(kp[0])):
                if p["status"] != "reviewed" or p["kind"] != "music":
                    continue
                reviewed.add((pdf.stem, int(n)))
                g = render(pdf, int(n), Path(tmp))
                h, w = g.shape
                if args.paper:  # the editor's corners if they set them, else detected: as the labeler's cache
                    cs = p.get("corners")
                    corners = cs["points"] if cs and not cs.get("auto") else detect.find_page_corners(Image.fromarray(g))
                for k, s in enumerate(sorted(p["systems"], key=lambda s: s["top"])):
                    if s.get("role", "part") != "part" or not s["barlines"]:
                        continue
                    if args.paper:
                        band, geo = paper_band(g, s, corners)
                    else:
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
                    if args.paper:  # the staff's ends and (where the editor set one) music start, crop pixels
                        lines[-1].update({"staff_left": s["left"] * w - geo["x_off"],
                                          "staff_right": s["right"] * w - geo["x_off"]})
                        if s.get("start") is not None and s["start"] > s["left"]:
                            lines[-1]["music_start"] = s["start"] * w - geo["x_off"]
                print(f"{pdf.stem} p{n}: {sum(1 for l in lines if l['page'] == int(n) and l['source'] == pdf.stem)} lines")

    held = held_out_pages()
    for src, pgs in held.items():
        missing = [n for n in pgs if (src, n) not in reviewed]
        if missing:
            print(f"test_pages.json: {src} pages {missing} not reviewed yet: nothing held out from them")
    for l in lines:
        l["split"] = "test" if test_page(l["source"], l["page"], args.test, args.test_source, held) else "train"
    # every reviewed test page (with or without lines here), for what trains on
    # whole pages (learn.py, via run_labeler and e2e_vote): none of them may
    test_pages = sorted([src, n] for src, n in reviewed if test_page(src, n, args.test, args.test_source, held))
    (args.out / "corpus.json").write_text(json.dumps(
        {"split": {"by": "page", "share": args.test, "test_sources": args.test_source,
                   "held_pages": sum(len(v) for v in held.values())},
         "test_pages": test_pages, "tolerance_frac": 0.006, "lines": lines}, indent=1))
    for split in ("train", "test"):
        ls = [l for l in lines if l["split"] == split]
        print(f"{split}: {len(ls)} lines, {sum(len(l['bars']) for l in ls)} bar lines, "
              f"{dict((s, sum(1 for l in ls if l['source'] == s)) for s in sorted({l['source'] for l in ls}))}")


if __name__ == "__main__":
    main()
