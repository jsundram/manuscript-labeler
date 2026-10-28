# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Score detect.py's staves against the editors' reviewed labels.

    uv run tools/score_staves.py [--renders DIR] [--out FILE] [labels files...]

When: before and after changing how detect.py finds or traces staves
(find_staves, _staff_scores, _trace, straighten), to see whether the change
finds the staves the editors kept, invents ones they deleted, or follows the
lines better. Bar-line detection has its own scorer, tools/score_barlines.py;
the bar-line counts here are a check that a staff change didn't hurt them
(detection alone, without the learned model the editor uses).

Every reviewed music page of every labels file under data/ (or those given).
A staff the editor kept is *found* if a detected staff's top and bottom are
both within half a staff space of it, *a line off* if one sits a staff
space away instead, else *missed*. A detected staff no kept staff explains
is *extra*. Bends are not scored: the editor never sets one, so they are
detection's own.

Also, for each found staff, how sharp its lines come out when the page is
straightened along the traced path (find_staves' path, as detect_page uses
it): the mean height of the five line peaks in the straightened band's
profile over the paper between them, 0-1. A path that wanders off the lines
smears them. It needs no truth, so it is compared version against version.

Renders are cached in --renders (default $TMPDIR/score_staves-<render px>)
so a before/after pair renders once. All 111 reviewed Op. 48 pages take
about 90 s. On 2026-10-28: 864 staves, all found, none a line off, 42 extra
(ruled staves the editors deleted as empty or text-only), sharpness 0.220.
"""

import argparse
import concurrent.futures as cf
import json
import os
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import detect  # noqa: E402
from score_barlines import RENDER_PX, render, score_page, truth_systems  # noqa: E402

EDITIONS = Path.home() / "Dropbox" / "Code"


def pdf_for(labels: Path) -> Path:
    """data/<edition>/sources/.../X.labels.json -> <edition>/sources/.../X.pdf"""
    rel = labels.resolve().relative_to(ROOT / "data")
    return EDITIONS / rel.parent / (labels.name[: -len(".labels.json")] + ".pdf")


def sharpness(g: np.ndarray, st: dict) -> float:
    """How sharp a staff's lines are in its straightened band (0-1)."""
    band, y0 = detect.straighten(g, st, pad_gaps=1.0)
    xs = [p[0] for p in st["path"]]
    cols = slice(int(min(xs)), int(max(xs)) + 1)
    prof = (255.0 - band[:, cols].astype(np.float32)).mean(axis=1) / 255.0
    gap = st["gap"]
    at = lambda y: int(round(y - y0))
    peaks = [prof[max(0, at(y) - 1):at(y) + 2].max() for y in st["lines"]]
    paper = [prof[at(st["top"] + (i + 0.5) * gap)] for i in range(4)]
    return float(np.mean(peaks) - np.median(paper))


def score(truth: list[dict], found: list[dict]) -> dict:
    """Kept staves and detected ones, as page fractions ({top, bottom}) -> counts:
    staves, found, line_off, missed, extra."""
    out = {"staves": len(truth), "found": 0, "line_off": 0, "missed": 0, "extra": 0}
    used = set()
    for t in truth:
        space = (t["bottom"] - t["top"]) / 4
        best, kind = None, "missed"
        for i, d in enumerate(found):
            dt, db = d["top"] - t["top"], d["bottom"] - t["bottom"]
            if abs(dt) < 0.5 * space and abs(db) < 0.5 * space:
                best, kind = i, "found"
                break
            if abs(abs(dt) - space) < 0.5 * space and abs(abs(db) - space) < 0.5 * space and np.sign(dt) == np.sign(db):
                best, kind = i, "line_off"
        out[kind] += 1
        if best is not None:
            used.add(best)
    out["extra"] = sum(1 for i in range(len(found)) if i not in used)
    return out


def page_work(args):
    pdf, n, page, renders = args
    path = renders / f"{pdf.stem}-p{n}.jpg"
    img = Image.open(path) if path.exists() else render(pdf, n, renders)
    img.load()
    h = img.size[1]
    systems = detect.detect_page(img)
    truth = page["systems"]
    r = score([{"top": s["top"], "bottom": s["bottom"]} for s in truth],
              [{"top": s["top"], "bottom": s["bottom"]} for s in systems])
    g = detect._gray(img)
    staves = detect.find_staves(g)
    sharp = []
    for t in truth:  # each kept staff, by the found staff nearest it
        near = [st for st in staves if abs(st["top"] / h - t["top"]) < 0.5 * (t["bottom"] - t["top"]) / 4]
        sharp.append(round(sharpness(g, near[0]), 4) if near else None)
    bars = score_page(truth_systems(page), systems)
    return {"source": pdf.stem, "page": n, **r, "sharp": sharp, "bars": bars}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels", nargs="*", type=Path)
    ap.add_argument("--renders", type=Path,
                    default=Path(os.environ.get("TMPDIR", "/tmp")) / f"score_staves-{RENDER_PX}")
    ap.add_argument("--out", type=Path, help="write per-page results as JSON")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    a.renders.mkdir(parents=True, exist_ok=True)
    files = a.labels or sorted((ROOT / "data").glob("*/sources/**/*.labels.json"))
    jobs = []
    for f in files:
        L = json.loads(f.read_text())
        pdf = pdf_for(f)
        pages = [(int(n), p) for n, p in L["pages"].items() if p.get("status") == "reviewed" and p.get("kind") == "music"]
        if pages and not pdf.exists():
            print(f"skipped {f.name}: {len(pages)} reviewed pages, but no {pdf}", file=sys.stderr)
            continue
        jobs += [(pdf, n, p, a.renders) for n, p in sorted(pages, key=lambda np_: np_[0])]
    with cf.ThreadPoolExecutor(a.jobs) as pool:
        res = list(pool.map(page_work, jobs))
    if a.out:
        a.out.write_text(json.dumps(res, indent=1))
    keys = ("staves", "found", "line_off", "missed", "extra")
    by = {}
    for r in res:
        by.setdefault(r["source"], []).append(r)
    print(f"{'source':24s} pages " + " ".join(f"{k:>8s}" for k in keys)
          + "   sharp   bar lines found/false/missed (detection alone)")
    for src, rs in list(by.items()) + [("all", res)]:
        tot = [sum(r[k] for r in rs) for k in keys]
        sh = [x for r in rs for x in r["sharp"] if x is not None]
        b = np.sum([r["bars"] for r in rs], axis=0)
        print(f"{src:24s} {len(rs):5d} " + " ".join(f"{v:8d}" for v in tot)
              + f"   {np.mean(sh):.3f}   {b[0]}/{b[1]}/{b[2]}")


if __name__ == "__main__":
    main()
