# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scikit-learn"]
# ///
"""5-fold cross-validation over all labelled lines, for the cheap methods:
the classical detector and the learned filter. Every line is tested once;
each fold's learned filter trains on the other four (threshold chosen on a
tenth of its training lines).

    uv run experiments/barlines/crossval.py <corpus-dir>
"""

import json
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
import detect  # noqa: E402
from harness import match, staff_of  # noqa: E402
from run_learned import labelled, predict  # noqa: E402


def classical(g, line):
    st = staff_of(line)
    pad = int(line["space"] * 4)
    g = np.pad(g, ((0, 0), (pad, pad)), constant_values=230)
    w = g.shape[1]
    _, start, _ = detect.music_start(g, st, pad, w - pad)
    return [(b["x0"] + b["x1"]) / 2 - pad for b in detect.find_barlines(g, st, pad, w - pad + int(line["space"]), skip_to=start)]


def main():
    from sklearn.ensemble import HistGradientBoostingClassifier

    corpus = Path(sys.argv[1])
    c = json.loads((corpus / "corpus.json").read_text())
    tol = c["tolerance_frac"]
    ls = list(c["lines"])
    random.Random(3).shuffle(ls)
    folds = [ls[k::5] for k in range(5)]
    totals = {"classical": [], "learned": []}
    for k, test in enumerate(folds):
        rest = [l for j, f in enumerate(folds) if j != k for l in f]
        val, train = rest[: len(rest) // 10], rest[len(rest) // 10:]
        X, y, _ = labelled(corpus, train, tol)
        model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                               class_weight="balanced", random_state=0).fit(X, y)
        _, _, vl = labelled(corpus, val, tol)
        best = (0.5, -1)
        for th in [i / 20 for i in range(1, 20)]:
            s = np.sum([match(predict(model, l, vl[l["id"]][0], th), [b["x"] for b in l["bars"]], tol * l["page_w"]) for l in val], axis=0)
            f1 = 2 * s[0] / (2 * s[0] + s[1] + s[2])
            if f1 > best[1]:
                best = (th, f1)
        _, _, tl = labelled(corpus, test, tol)
        for name in totals:
            s = np.zeros(3)
            for l in test:
                pred = predict(model, l, tl[l["id"]][0], best[0]) if name == "learned" else \
                    classical(np.asarray(Image.open(corpus / l["file"]).convert("L"), dtype=np.float32), l)
                s += match(pred, [b["x"] for b in l["bars"]], tol * l["page_w"])
            totals[name].append(s)
            print(f"fold {k + 1} {name}: found {int(s[0])}, false {int(s[1])}, missed {int(s[2])}")
    for name, ss in totals.items():
        ss = np.array(ss)
        rec = ss[:, 0] / (ss[:, 0] + ss[:, 2])
        prec = ss[:, 0] / (ss[:, 0] + ss[:, 1])
        f, fp, m = ss.sum(axis=0)
        print(f"{name}: all {len(ls)} lines: found {int(f)}, false {int(fp)}, missed {int(m)}; recall "
              f"{rec.mean():.1%} ± {rec.std():.1%}, precision {prec.mean():.1%} ± {prec.std():.1%} (mean ± sd over folds)")


if __name__ == "__main__":
    main()
