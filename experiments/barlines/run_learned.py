# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scikit-learn"]
# ///
"""A learned filter on detect.py's own candidate strokes.

    uv run experiments/barlines/run_learned.py <corpus-dir>

detect.py's search (every column, tried at many leans, scored by how much
of the staff's height it covers) proposes candidate strokes with a loose
threshold, so faint bar lines are among them. Each candidate is described
by a few measurements, and a gradient-boosted classifier, trained on the
editor's labels for the training lines, decides which are bar lines. Its
threshold is chosen on the validation lines; the test lines are scored by
harness.py like every other method. The candidates' recall (bar lines
with any candidate near them) is the ceiling for this approach.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
import detect  # noqa: E402
from harness import match, staff_of, write  # noqa: E402

LOOSE = 0.5  # candidate threshold on staff coverage (detect.py's own is 0.88)
FEATURES = ["cover", "cover_top", "cover_mid", "cover_bot", "lean", "width", "attach", "dark",
            "above", "below", "busy_left", "busy_right", "gap_prev", "gap_next", "from_start", "rel_x"]


def candidates(g: np.ndarray, line: dict) -> list[dict]:
    """Candidate strokes with their measurements, x in crop pixels."""
    st = staff_of(line)
    pad = int(line["space"] * 4)
    g = np.pad(g, ((0, 0), (pad, pad)), constant_values=230)
    w = g.shape[1]
    top, bottom, gap = st["top"], st["bottom"], st["gap"]
    ink = g < 120
    left, right = pad, w - pad
    _, start, _ = detect.music_start(g, st, left, right)
    ys = np.arange(top, bottom + 1)
    best = np.zeros(right - left)
    slope_at = np.zeros(right - left)
    for slope in np.linspace(-detect.LEAN, detect.LEAN, 2 * int(detect.LEAN / 0.03) + 1):
        shifts = np.round((ys - (top + bottom) / 2) * slope).astype(int)
        acc = np.zeros(right - left)
        for y, s in zip(ys, shifts):
            row = ink[y, left + s:right + s]
            r = row.copy()
            r[1:] |= row[:-1]
            r[:-1] |= row[1:]
            acc += r
        cover = acc / len(ys)
        better = cover > best
        best[better] = cover[better]
        slope_at[better] = slope
    runs = []
    for i in np.flatnonzero(best > LOOSE):
        if runs and i - runs[-1][-1] <= 3:
            runs[-1].append(int(i))
        else:
            runs.append([int(i)])
    out = []
    thirds = np.array_split(ys, 3)
    for r in runs:
        i = r[int(np.argmax(best[r]))]
        slope, x = slope_at[i], left + i
        xs_at = lambda yy: np.clip(np.round(x + (yy - (top + bottom) / 2) * slope).astype(int), 0, w - 1)
        col = lambda yy: ink[yy, xs_at(yy)].mean() if len(yy) else 0.0

        def beyond(y0, y1):
            yy = np.arange(max(0, y0), min(g.shape[0], y1))
            return col(yy)
        band = g[top:bottom + 1]
        lw, rw = int(gap * 1.0), int(gap * 1.0)
        out.append({
            "x": float(x - pad),
            "cover": float(best[i]),
            "cover_top": float(col(thirds[0])), "cover_mid": float(col(thirds[1])), "cover_bot": float(col(thirds[2])),
            "lean": float(abs(slope)), "width": len(r) / gap,
            "attach": float(detect.attachment(ink, st, x, slope)),
            "dark": float(255 - np.mean(g[ys, xs_at(ys)])),
            "above": float(beyond(int(top - 1.6 * gap), int(top - 0.6 * gap))),
            "below": float(beyond(int(bottom + 0.6 * gap), int(bottom + 1.6 * gap))),
            "busy_left": float((band[:, max(0, x - lw - 3):x - 3] < 120).mean()) if x - 3 > 0 else 0.0,
            "busy_right": float((band[:, x + 4:x + rw + 4] < 120).mean()),
            "from_start": float((x - start) / gap), "rel_x": float((x - pad) / line["width"]),
        })
    for k, c in enumerate(out):
        c["gap_prev"] = (c["x"] - out[k - 1]["x"]) / gap if k else 99.0
        c["gap_next"] = (out[k + 1]["x"] - c["x"]) / gap if k + 1 < len(out) else 99.0
    return out


def labelled(corpus: Path, ls: list[dict], tol_frac: float):
    X, y, per_line = [], [], {}
    for line in ls:
        g = np.asarray(Image.open(corpus / line["file"]).convert("L"), dtype=np.float32)
        cands = candidates(g, line)
        tol = tol_frac * line["page_w"]
        true = [b["x"] for b in line["bars"]]
        # one-to-one: each bar line labels its nearest candidate within tolerance
        lab = [0] * len(cands)
        for t in true:
            near = [(abs(c["x"] - t), k) for k, c in enumerate(cands) if abs(c["x"] - t) <= tol and not lab[k]]
            if near:
                lab[min(near)[1]] = 1
        per_line[line["id"]] = (cands, lab)
        X += [[c[f] for f in FEATURES] for c in cands]
        y += lab
    return np.array(X), np.array(y), per_line


def predict(model, line: dict, cands: list[dict], th: float) -> list[float]:
    if not cands:
        return []
    p = model.predict_proba(np.array([[c[f] for f in FEATURES] for c in cands]))[:, 1]
    # of candidates closer than detect.MIN_BAR spaces, keep the likelier
    kept = []
    for k in np.argsort(-p):
        if p[k] < th:
            break
        if all(abs(cands[k]["x"] - cands[j]["x"]) >= detect.MIN_BAR * line["space"] for j in kept):
            kept.append(k)
    return sorted(cands[k]["x"] for k in kept)


def main():
    from sklearn.ensemble import HistGradientBoostingClassifier

    corpus = Path(sys.argv[1])
    c = json.loads((corpus / "corpus.json").read_text())
    tol = c["tolerance_frac"]
    val_ids = set(json.loads((corpus / "tiles" / "val_ids.json").read_text()))
    train = [l for l in c["lines"] if l["split"] == "train" and l["id"] not in val_ids]
    val = [l for l in c["lines"] if l["id"] in val_ids]
    test = [l for l in c["lines"] if l["split"] == "test"]

    t0 = time.perf_counter()
    X, y, _ = labelled(corpus, train, tol)
    model = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                           class_weight="balanced", random_state=0).fit(X, y)
    train_s = time.perf_counter() - t0

    _, _, vlines = labelled(corpus, val, tol)
    best = (0.5, -1)
    for th in [i / 20 for i in range(1, 20)]:
        f = fp = m = 0
        for line in val:
            a, b, d = match(predict(model, line, vlines[line["id"]][0], th), [bb["x"] for bb in line["bars"]], tol * line["page_w"])
            f, fp, m = f + a, fp + b, m + d
        f1 = 2 * f / (2 * f + fp + m) if f else 0
        if f1 > best[1]:
            best = (th, f1)
    th = best[0]

    t1 = time.perf_counter()
    preds, ceiling, total = {}, 0, 0
    for line in test:
        g = np.asarray(Image.open(corpus / line["file"]).convert("L"), dtype=np.float32)
        cands = candidates(g, line)
        preds[line["id"]] = predict(model, line, cands, th)
        for b in line["bars"]:
            total += 1
            ceiling += any(abs(cc["x"] - b["x"]) <= tol * line["page_w"] for cc in cands)
    per_line = (time.perf_counter() - t1) / len(test)
    write(corpus, {"method": "learned-gbm", "train_s": train_s, "infer_s": per_line, "threshold": th, "lines": preds,
                   "notes": f"gradient boosting on detect.py's loose candidates (cover > {LOOSE}); "
                            f"{len(y)} training candidates, {int(y.sum())} bar lines; candidates reach "
                            f"{ceiling}/{total} test bar lines; threshold {th:.2f} (chosen on val)"})


if __name__ == "__main__":
    main()
