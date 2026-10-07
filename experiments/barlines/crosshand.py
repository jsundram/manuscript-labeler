# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scikit-learn"]
# ///
"""How well does what's learned carry to a new copyist's hand, and how many
labelled pages of it does the learned filter need?

    uv run experiments/barlines/crosshand.py <corpus-dir> [--draws 3]

Three hands in the corpus: KHM (D-B KHM 602 and 603, one copyist), Paris A
(F-Po RES 507 (14) Violin I and Cello, one paper and hand) and Paris B (its
Violin II and Viola, another). Each hand is tested whole (every line), the
filter trained on others: KHM only; KHM and the other Paris hand; and KHM
plus k pages of the tested hand (k = 1, 2, 4; tested on that hand's other
pages; several random draws of pages, summed). The hand-tuned rules for
reference. Thresholds are chosen on a tenth of the training lines, never
the tested hand's test lines.
"""

import argparse
import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_learned  # noqa: E402
from crossval import classical  # noqa: E402
from harness import match  # noqa: E402

CACHE: dict = {}


def cached_labelled(corpus: Path, ls: list[dict], tol_frac: float):
    """run_learned.labelled, each line's candidates computed once."""
    missing = [l for l in ls if l["id"] not in CACHE]
    if missing:
        _, _, per = ORIGINAL(corpus, missing, tol_frac)
        CACHE.update(per)
    per = {l["id"]: CACHE[l["id"]] for l in ls}
    X = [[c[f] for f in run_learned.FEATURES] for cands, _ in per.values() for c in cands]
    y = [v for _, lab in per.values() for v in lab]
    return np.array(X), np.array(y), per


ORIGINAL = run_learned.labelled
run_learned.labelled = cached_labelled


def hand(l: dict) -> str:
    if l["source"].startswith("D-B"):
        return "KHM"
    return "Paris A" if l["part"] in ("vn1", "vc") else "Paris B"


def evaluate(corpus: Path, train: list[dict], test: list[dict], tol: float, widths: bool, seed: int = 0):
    """(found, false, missed) on `test`, the filter trained on `train`."""
    rng = random.Random(seed)
    train = train[:]
    rng.shuffle(train)
    val, fit_on = train[: len(train) // 10], train[len(train) // 10:]
    model, stage1, feats = run_learned.fit(corpus, fit_on, tol, widths)

    def preds(ls, th):
        _, _, per = cached_labelled(corpus, ls, tol)
        out = {}
        for l in ls:
            cands = per[l["id"]][0]
            if stage1 is not None:
                cands = run_learned.with_widths(stage1, l, cands)
            out[l["id"]] = run_learned.predict(model, l, cands, th, feats)
        return out

    def score(ls, p):
        return np.sum([match(p[l["id"]], [b["x"] for b in l["bars"]], tol * l["page_w"]) for l in ls], axis=0)

    best = (0.5, -1.0)
    for th in [i / 20 for i in range(1, 20)]:
        f, fp, m = score(val, preds(val, th))
        f1 = 2 * f / (2 * f + fp + m) if f else 0
        if f1 > best[1]:
            best = (th, f1)
    return score(test, preds(test, best[0]))


def line(name, s):
    f, fp, m = (int(v) for v in s)
    f1 = 2 * f / (2 * f + fp + m) if f else 0
    per100 = 100 * (fp + m) / (f + m) if f + m else 0
    print(f"  {name:44s} found {f:4d}  false {fp:3d}  missed {m:3d}  errors {fp + m:3d} ({per100:4.1f} per 100 bar lines)  F1 {f1:.3f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--draws", type=int, default=3)
    ap.add_argument("--paper", action="store_true", help="candidates with ink relative to the paper (as detect.py)")
    args = ap.parse_args()
    run_learned.NORMALIZE = args.paper
    c = json.loads((args.corpus / "corpus.json").read_text())
    tol = c["tolerance_frac"]
    by = {}
    for l in c["lines"]:
        by.setdefault(hand(l), []).append(l)
    print(f"settings: draws {args.draws}, ink {'relative to the paper' if args.paper else 'cutoff 120'}")
    for h, ls in by.items():
        print(f"{h}: {len(ls)} lines, {sum(len(l['bars']) for l in ls)} bar lines, "
              f"{len({(l['pdf'], l['page']) for l in ls})} pages")

    for target in ("Paris A", "Paris B"):
        other = "Paris B" if target == "Paris A" else "Paris A"
        test = by[target]
        print(f"\n{target} (all {len(test)} lines):")
        s = np.zeros(3)
        for l in test:
            g = np.asarray(Image.open(args.corpus / l["file"]).convert("L"), dtype=np.float32)
            s += match(classical(g, l), [b["x"] for b in l["bars"]], tol * l["page_w"])
        line("hand-tuned rules", s)
        for widths in (False, True):
            tag = " + widths" if widths else ""
            line(f"learned{tag}, trained on KHM", evaluate(args.corpus, by["KHM"], test, tol, widths))
            line(f"learned{tag}, trained on KHM + {other}", evaluate(args.corpus, by["KHM"] + by[other], test, tol, widths))

        # learning curve: KHM + k of the target hand's pages, tested on its other pages
        pages = sorted({(l["pdf"], l["page"]) for l in test})
        print(f"  {target}, KHM + k of its {len(pages)} pages, tested on the rest ({args.draws} draws, summed):")
        for k in (0, 1, 2, 4):
            for widths in (False, True):
                s = np.zeros(3)
                for d in range(args.draws):
                    rng = random.Random(100 + d)
                    pick = set(rng.sample(pages, k))
                    seen = [l for l in test if (l["pdf"], l["page"]) in pick]
                    rest = [l for l in test if (l["pdf"], l["page"]) not in pick]
                    s += evaluate(args.corpus, by["KHM"] + seen, rest, tol, widths, seed=d)
                line(f"k={k}{' + widths' if widths else ''}", s)


if __name__ == "__main__":
    main()
