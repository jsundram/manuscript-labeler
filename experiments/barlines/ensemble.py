# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Do the bar-line finders make the same mistakes, and does voting help?

    uv run experiments/barlines/ensemble.py <corpus-dir> [method ...]

Uses the saved test-line predictions (results/*.json), no retraining.
Prints, per real bar line, how many methods miss it; per false proposal,
how many methods make it at the same place; pairwise overlap of misses;
then voting ensembles: every method's bar lines pooled, proposals within
the scoring tolerance of a group's first one merged, kept if at least k
methods propose them (scored by harness.py's rules; nothing is written).
The two learned filters share a first pass, so their votes aren't
independent.
"""

import itertools
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from harness import load, score  # noqa: E402

DEFAULT = ["detectron2-faster-rcnn-r50", "dfine-dfine-small-coco", "yolo-yolo11n",
           "learned-gbm-widths", "learned-gbm", "classical"]


def main():
    corpus = Path(sys.argv[1])
    methods = sys.argv[2:] or DEFAULT
    c = load(corpus)
    res = {m: json.loads((corpus / "results" / f"{m}.json").read_text()) for m in methods}
    test = [l for l in c["lines"] if l["split"] == "test"]

    missed_by = Counter()        # how many methods miss each real bar line
    false_by = Counter()         # how many methods make each false proposal (same place)
    missed_sets = {m: set() for m in methods}
    for line in test:
        tol = c["tolerance_frac"] * line["page_w"]
        true = [b["x"] for b in line["bars"]]
        for j, t in enumerate(true):
            who = [m for m in methods if not any(abs(p - t) <= tol for p in res[m]["lines"].get(line["id"], []))]
            missed_by[len(who)] += 1
            for m in who:
                missed_sets[m].add((line["id"], j))
        # false proposals, merged across methods within tolerance
        falses = sorted((p, m) for m in methods for p in res[m]["lines"].get(line["id"], [])
                        if not any(abs(p - t) <= tol for t in true))
        groups: list[list] = []
        for p, m in falses:
            if groups and p - groups[-1][0][0] <= tol:
                groups[-1].append((p, m))
            else:
                groups.append([(p, m)])
        for g in groups:
            false_by[len({m for _, m in g})] += 1

    n = len(methods)
    total = sum(missed_by.values())
    print(f"{len(methods)} methods, {total} real bar lines on the test lines")
    print("real bar lines missed by k methods:", {k: missed_by[k] for k in range(n + 1) if missed_by[k]})
    print("false proposals made by k methods: ", {k: false_by[k] for k in range(1, n + 1) if false_by[k]})
    print("\npairwise: misses in common / misses of either (Jaccard)")
    for a, b in itertools.combinations(methods, 2):
        A, B = missed_sets[a], missed_sets[b]
        if A or B:
            print(f"  {a[:24]:24s} {b[:24]:24s} {len(A & B):3d} / {len(A | B):3d}")

    print("\nvoting (kept if proposed by at least k of the methods):")
    for k in range(1, n + 1):
        lines = {}
        for line in test:
            tol = c["tolerance_frac"] * line["page_w"]
            pts = sorted((p, m) for m in methods for p in res[m]["lines"].get(line["id"], []))
            groups: list[list] = []
            for p, m in pts:
                if groups and p - groups[-1][0][0] <= tol:
                    groups[-1].append((p, m))
                else:
                    groups.append([(p, m)])
            lines[line["id"]] = [sum(p for p, _ in g) / len(g) for g in groups if len({m for _, m in g}) >= k]
        r = {"method": f"vote-{k}of{n}", "train_s": 0.0, "infer_s": sum(res[m]["infer_s"] for m in methods),
             "lines": lines, "notes": f"kept if at least {k} of {', '.join(methods)} propose it"}
        s = score(corpus, r)
        tag = " (majority, fixed in advance)" if k == n // 2 + 1 else ""
        print(f"  k={k}: found {s['found']}, false {s['false']}, missed {s['missed']}, errors {s['false'] + s['missed']}, "
              f"F1 {s['f1']:.3f}{tag}")


if __name__ == "__main__":
    main()
