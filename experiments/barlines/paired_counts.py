# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scikit-learn", "anthropic"]
# ///
"""Bar-line detection scored by bar counts on the paired manuscripts, and a
filter trained on those counts.

    uv run experiments/barlines/paired_counts.py [--eval-pages 3] [--pseudo-pages 300] [--out DIR]

The paired staves in the training sets (dataM5, dataW4, dataP4, dataG213-4)
have labels whose measures are the staff's bars, as the pairing found and
checked them: a bar count per staff, in many copyists' hands, though not
where each bar line is. Detection's count is its bar boxes (bar lines past
the music start, and one more where music runs on past the last), as
autopair.boxes counts them.

Three bar-line filters, through the labeler's detection (detect.detect_page
with the filter, and the detectors' cached predictions voted in and their
staff ends, as server.Edition.detect does), on a held-out sample of pages
(--eval-pages per source):
  A  the filter each source was detected with (auto/cache/<source>/models),
  B  one trained on the editor's reviewed pages as they are now (learn.py),
  C  B's pages and --pseudo-pages more from the paired sources (none of the
     sample's): on each of their set staves, B's likeliest strokes, as many
     as the staff's bar count needs, taken for its bar lines (the count
     either way: that many with the last at the staff's end, or one fewer
     with music on past it; a staff where both or neither fit is left out).
"""

import argparse
import json
import pickle
import random
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

LAB = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(LAB), str(LAB / "tools")]
import detect  # noqa: E402
import detections  # noqa: E402
import learn  # noqa: E402
from score_barlines import render as render_page  # noqa: E402

ZEUS = LAB / "experiments" / "zeus"
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"
SETS = ("dataM5", "dataW4", "dataP4", "dataG213-4")
TOP = 0.015  # page heights: a detected staff matches a labelled one this close


def set_staves() -> dict:
    """{(source, page): {staff index: bar count}} for every staff in the sets, with each source's PDF."""
    out, pdfs = defaultdict(dict), {}
    for d in SETS:
        for folder in sorted(p for p in (CACHE / d).iterdir() if p.is_dir()):
            auto = ZEUS / "auto" / f"{folder.name}.json"
            if not auto.exists():
                continue
            pdfs[folder.name] = Path(json.loads(auto.read_text())["pdf"])
            for f in folder.glob("*.lmx"):
                n, k = f.stem[1:].split("-")
                out[(folder.name, int(n))][int(k)] = f.read_text().split().count("measure")
    return out, pdfs


def boxes(s: dict, aspect: float, xs: list[float] | None = None) -> int:
    """autopair.boxes: bar lines past the music start, and one more where music runs on past the last."""
    gap = (s["bottom"] - s["top"]) / 4 * aspect
    xs = sorted(x for x in (xs if xs is not None else [(b["x0"] + b["x1"]) / 2 for b in s["barlines"]])
                if x > s["start"] + gap)
    return len(xs) + (not xs or s["right"] - xs[-1] > 1.5 * gap)


class Pages:
    def __init__(self, tmp: Path):
        self.tmp, self.seen = tmp, {}

    def __call__(self, pdf: Path, n: int):
        if (pdf, n) not in self.seen:
            self.seen[(pdf, n)] = render_page(pdf, n, self.tmp)
        return self.seen[(pdf, n)]


def staves_of(source: str, n: int) -> list[dict]:
    return json.loads((ZEUS / "auto" / f"{source}.json").read_text())["pages"][str(n)]["systems"]


def detected(img, model, pdf: Path, n: int, collect=None) -> list[dict]:
    """As server.Edition.detect: the detectors' cached predictions voted in, their staff ends taken."""
    w, h = img.size
    preds = detections.page_predictions(pdf.parent, pdf.name, n, detections.cache_dir())
    vote = detections.make_vote(preds, w, h) if preds else None
    ends = detections.make_ends(preds, w, h) if preds else None
    return detect.detect_page(img, model=model, corners=detect.find_page_corners(img), vote=vote, ends=ends,
                              collect=collect)


def score(model, pages: list, truth: dict, pdfs: dict, render) -> Counter:
    c = Counter()
    for src, n in pages:
        img = render(pdfs[src], n)
        w, h = img.size
        found = detected(img, model, pdfs[src], n)
        labelled = staves_of(src, n)
        for k, m in truth[(src, n)].items():
            s = min(found, key=lambda f: abs(f["top"] - labelled[k]["top"]), default=None)
            if s is None or abs(s["top"] - labelled[k]["top"]) > TOP:
                c["staff not found"] += 1
                continue
            got = boxes(s, h / w)
            c["staves"] += 1
            c["count right"] += got == m
            c["too many"] += got > m
            c["too few"] += got < m
            c["bars off"] += abs(got - m)
    return c


def probabilities(model: dict, cands: list[dict], gap: float) -> np.ndarray:
    """detect.choose's probability for each candidate."""
    if model.get("stage1") is not None:
        p1 = model["stage1"].predict_proba(np.array([[c[f] for f in detect.FEATURES] for c in cands]))[:, 1]
        cands = detect.with_widths(cands, p1, gap)
    return model["clf"].predict_proba(np.array([[c[f] for f in model["features"]] for c in cands]))[:, 1]


def pseudo_page(model: dict, src: str, n: int, counts: dict, img, pdf: Path) -> dict | None:
    """A labels-like page whose set staves have, for bar lines, the model's likeliest strokes in the number
    their bar count needs; None if no staff fits."""
    w, h = img.size
    collected = []
    systems = detected(img, model, pdf, n, collect=collected)
    labelled = staves_of(src, n)
    out = []
    for k, m in counts.items():
        top = labelled[k]["top"]
        s = min(systems, key=lambda f: abs(f["top"] - top), default=None)
        col = min(collected, key=lambda f: abs(f[0] - top), default=None)
        if s is None or col is None or abs(s["top"] - top) > TOP or abs(col[0] - top) > TOP or not col[2]:
            continue
        _, _, cands, gap = col
        p = probabilities(model, cands, gap)
        order = []
        for i in np.argsort(-p):  # likeliest first, none closer than detect.MIN_BAR spaces to a likelier one
            if all(abs(cands[i]["x"] - cands[j]["x"]) >= detect.MIN_BAR * gap for j in order):
                order.append(int(i))
        fits = []
        for want in (m, m - 1):
            if 0 < want <= len(order):
                xs = [cands[i]["x"] / w for i in order[:want]]
                if boxes(s, h / w, xs) == m:
                    fits.append(xs)
        if len(fits) != 1:
            continue
        out.append({"top": col[0], "bottom": col[1], "role": "part",
                    "barlines": [{"x0": x, "x1": x} for x in sorted(fits[0])]})
    return {"systems": out} if out else None


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--eval-pages", type=int, default=3, help="held-out pages per source")
    ap.add_argument("--pseudo-pages", type=int, default=300)
    ap.add_argument("--out", type=Path, required=True, help="a scratch folder (renders, models, results)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    render = Pages(a.out)
    truth, pdfs = set_staves()
    rng = random.Random(0)
    by_src = defaultdict(list)
    for src, n in sorted(truth):
        if len(truth[(src, n)]) >= 2:
            by_src[src].append((src, n))
    held = [p for src in sorted(by_src) for p in rng.sample(by_src[src], min(a.eval_pages, len(by_src[src])))]
    rest = [p for src in sorted(by_src) for p in by_src[src] if p not in held]
    pseudo = rng.sample(rest, min(a.pseudo_pages, len(rest)))
    print(f"{len(held)} held-out pages ({sum(len(truth[p]) for p in held)} staves) from {len(by_src)} sources; "
          f"{len(pseudo)} pages for C", flush=True)

    reviewed = learn.reviewed_pages(EDITION)
    B = learn.load_or_train(EDITION, a.out / "B", lambda pdf, n: render(pdf, n))
    print(f"B: {B['pages']} reviewed pages, {B['bar_lines']} bar lines", flush=True)
    made = []
    for src, n in pseudo:
        pg = pseudo_page(B, src, n, truth[(src, n)], render(pdfs[src], n), pdfs[src])
        if pg:
            made.append((pdfs[src], n, pg))
    print(f"C: {len(made)} pages of counted staves ({sum(len(p['systems']) for _, _, p in made)} staves)", flush=True)
    C = learn.train(reviewed + made, lambda pdf, n: render(pdf, n))
    (a.out / "C.pkl").write_bytes(pickle.dumps(C))

    results = {}
    # A: each source's own filter, so scored source by source
    cA = Counter()
    for src in sorted({s for s, _ in held}):
        pk = sorted((ZEUS / "auto" / "cache" / src / "models").glob("barlines-*.pkl"))
        if len(pk) == 1:
            cA += score(pickle.loads(pk[0].read_bytes()), [p for p in held if p[0] == src], truth, pdfs, render)
    results["A (as detected)"] = cA
    results["B (reviewed pages now)"] = score(B, held, truth, pdfs, render)
    results["C (and paired counts)"] = score(C, held, truth, pdfs, render)
    for name, c in results.items():
        print(f"{name:24} staves {c['staves']:4}  count right {c['count right'] / c['staves']:.1%}  "
              f"too many {c['too many']}  too few {c['too few']}  bars off {c['bars off']}  (staff not found {c['staff not found']})")
    (a.out / "results.json").write_text(json.dumps({k: {f: int(x) for f, x in v.items()} for k, v in results.items()}, indent=1))


if __name__ == "__main__":
    main()
