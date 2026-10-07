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
from run_learned import FEATURES, fit, labelled, predict, with_widths  # noqa: E402


def classical(g, line):
    st = staff_of(line)
    pad = int(line["space"] * 4)
    g = np.pad(g, ((0, 0), (pad, pad)), constant_values=230)
    w = g.shape[1]
    _, start, _ = detect.music_start(g, st, pad, w - pad)
    return [(b["x0"] + b["x1"]) / 2 - pad for b in detect.find_barlines(g, st, pad, w - pad + int(line["space"]), skip_to=start)]


def main():

    corpus = Path(sys.argv[1])
    c = json.loads((corpus / "corpus.json").read_text())
    tol = c["tolerance_frac"]
    ls = list(c["lines"])
    random.Random(3).shuffle(ls)
    folds = [ls[k::5] for k in range(5)]
    totals = {"classical": [], "learned": [], "learned+widths": []}
    by_source = {}
    for k, test in enumerate(folds):
        rest = [l for j, f in enumerate(folds) if j != k for l in f]
        val, train = rest[: len(rest) // 10], rest[len(rest) // 10:]
        models = {}
        # one fit gives both: the two-pass model's first pass is the plain filter
        model2, stage1, feats2 = fit(corpus, train, tol, True)
        _, _, vl0 = labelled(corpus, val, tol)
        for name, (model, s1, feats) in (("learned", (stage1, None, FEATURES)),
                                         ("learned+widths", (model2, stage1, feats2))):
            vl = vl0 if s1 is None else {l["id"]: (with_widths(s1, l, vl0[l["id"]][0]), vl0[l["id"]][1]) for l in val}
            best = (0.5, -1)
            for th in [i / 20 for i in range(1, 20)]:
                s = np.sum([match(predict(model, l, vl[l["id"]][0], th, feats), [b["x"] for b in l["bars"]], tol * l["page_w"]) for l in val], axis=0)
                f1 = 2 * s[0] / (2 * s[0] + s[1] + s[2])
                if f1 > best[1]:
                    best = (th, f1)
            models[name] = (model, s1, feats, best[0])
        _, _, tl = labelled(corpus, test, tol)
        for name in totals:
            s = np.zeros(3)
            for l in test:
                if name == "classical":
                    pred = classical(np.asarray(Image.open(corpus / l["file"]).convert("L"), dtype=np.float32), l)
                else:
                    model, stage1, feats, th = models[name]
                    cands = tl[l["id"]][0] if stage1 is None else with_widths(stage1, l, tl[l["id"]][0])
                    pred = predict(model, l, cands, th, feats)
                one = match(pred, [b["x"] for b in l["bars"]], tol * l["page_w"])
                s += one
                by_source.setdefault((name, l["source"]), np.zeros(3))
                by_source[(name, l["source"])] += one
            totals[name].append(s)
            print(f"fold {k + 1} {name}: found {int(s[0])}, false {int(s[1])}, missed {int(s[2])}")
    for name, ss in totals.items():
        ss = np.array(ss)
        rec = ss[:, 0] / (ss[:, 0] + ss[:, 2])
        prec = ss[:, 0] / (ss[:, 0] + ss[:, 1])
        f, fp, m = ss.sum(axis=0)
        print(f"{name}: all {len(ls)} lines: found {int(f)}, false {int(fp)}, missed {int(m)}; recall "
              f"{rec.mean():.1%} ± {rec.std():.1%}, precision {prec.mean():.1%} ± {prec.std():.1%} (mean ± sd over folds)")
        for (n, src), (f, fp, m) in sorted(by_source.items()):
            if n == name:
                print(f"    {src}: found {int(f)}, false {int(fp)}, missed {int(m)}, errors {int(fp + m)}")


if __name__ == "__main__":
    main()
