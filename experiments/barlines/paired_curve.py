# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scikit-learn", "anthropic"]
# ///
"""The bar-line filter's learning curve: trained on a quarter, a half and
all of the editor's reviewed pages, each scored by bar counts on
paired_counts.py's held-out sample of paired pages.

    uv run experiments/barlines/paired_curve.py --out DIR
"""
import argparse
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paired_counts as pc  # noqa: E402

import learn  # noqa: E402  (paired_counts put the labeler on the path)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--out", type=Path, required=True, help="a scratch folder (renders)")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    render = pc.Pages(a.out)
    truth, pdfs = pc.set_staves()
    rng, by_src = random.Random(0), defaultdict(list)
    for src, n in sorted(truth):
        if len(truth[(src, n)]) >= 2:
            by_src[src].append((src, n))
    held = [p for src in sorted(by_src) for p in rng.sample(by_src[src], min(3, len(by_src[src])))]
    reviewed = learn.reviewed_pages(pc.EDITION)
    print(len(reviewed), "reviewed pages", flush=True)
    for frac in (0.25, 0.5, 1.0):
        for seed in ((0, 1) if frac < 1 else (0,)):
            sub = random.Random(seed).sample(reviewed, max(5, int(len(reviewed) * frac)))
            c = pc.score(learn.train(sub, lambda pdf, n: render(pdf, n)), held, truth, pdfs, render)
            print(f"{len(sub):4} pages (seed {seed}): count right {c['count right'] / c['staves']:.1%}  "
                  f"too many {c['too many']}  too few {c['too few']}  bars off {c['bars off']}", flush=True)


if __name__ == "__main__":
    main()
