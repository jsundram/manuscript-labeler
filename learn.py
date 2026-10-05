"""A learned bar-line filter, trained on the editor's reviewed pages.

detect.py proposes candidate strokes loosely (detect.candidates); this
module trains a gradient-boosted classifier to accept or reject them, from
every reviewed music page in an edition. In the bake-off
(experiments/barlines) it found 95% of bar lines at 98% precision under
cross-validation, against 88.5% / 98.7% for detect.py's hand-tuned tests,
training in seconds.

Training takes the same steps as detection (detect.detect_page with
`collect`), so the model sees what it will see: candidates on the
*detected* staves, labelled by matching the editor's bar lines on the same
staff within the labeler's tolerance (0.6% of the page width).
"""

import hashlib
import json
import pickle
import random
from pathlib import Path

import numpy as np

import detect

TOLERANCE = 0.006  # page widths, as tools/score_barlines.py
VERSION = 1        # bump when detect.FEATURES or the labelling changes


def reviewed_pages(edition: Path) -> list[tuple[Path, int, dict]]:
    """(pdf, page number, labels page) for every reviewed music page."""
    out = []
    for lp in sorted(edition.glob("sources/**/*.labels.json")):
        pdf = lp.with_name(lp.name.replace(".labels.json", ".pdf"))
        try:
            doc = json.loads(lp.read_text())
        except (ValueError, OSError):
            continue
        for n, p in sorted(doc.get("pages", {}).items(), key=lambda kp: int(kp[0])):
            if p.get("status") == "reviewed" and p.get("kind") == "music":
                out.append((pdf, int(n), p))
    return out


def key(pages: list) -> str:
    """Identifies the training data: changes when any reviewed page's staves
    or bar lines do."""
    h = hashlib.sha1(f"v{VERSION}:{detect.FEATURES}".encode())
    for pdf, n, p in pages:
        truth = [(round(s["top"], 4), sorted(round((b["x0"] + b["x1"]) / 2, 4) for b in s["barlines"]))
                 for s in p["systems"] if s.get("role", "part") == "part"]
        h.update(f"{pdf.name}:{n}:{truth}".encode())
    return h.hexdigest()[:16]


def examples(img, page: dict) -> tuple[list, list]:
    """Features and labels for one page's candidates. Each of the editor's
    bar lines labels its nearest candidate on the matching staff."""
    w = img.size[0]
    found: list = []
    detect.detect_page(img, collect=found)
    X, y = [], []
    staves = [s for s in page["systems"] if s.get("role", "part") == "part"]
    for top, bottom, cands in found:
        truth = min(staves, key=lambda s: abs(s["top"] - top), default=None)
        if truth is None or abs(truth["top"] - top) > 0.015:
            continue  # a staff the editor deleted: don't learn from it
        lab = [0] * len(cands)
        for b in truth["barlines"]:
            x = (b["x0"] + b["x1"]) / 2 * w
            near = [(abs(c["x"] - x), k) for k, c in enumerate(cands) if abs(c["x"] - x) <= TOLERANCE * w and not lab[k]]
            if near:
                lab[min(near)[1]] = 1
        X += [[c[f] for f in detect.FEATURES] for c in cands]
        y += lab
    return X, y


def train(pages: list, render) -> dict:
    """A model from (pdf, page, labels) pages; render(pdf, n) gives the page
    image as detection sees it. A tenth of the pages pick the threshold."""
    from sklearn.ensemble import HistGradientBoostingClassifier

    data = [(examples(render(pdf, n), p), pdf, n) for pdf, n, p in pages]
    order = list(range(len(data)))
    random.Random(0).shuffle(order)
    hold = set(order[: max(1, len(order) // 10)]) if len(order) >= 5 else set()

    def stack(idx):
        X = [x for i in idx for x in data[i][0][0]]
        y = [v for i in idx for v in data[i][0][1]]
        return np.array(X), np.array(y)

    fit = [i for i in order if i not in hold]
    X, y = stack(fit)
    if len(set(y)) < 2:
        raise ValueError("not enough reviewed bar lines to learn from")
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                         class_weight="balanced", random_state=0).fit(X, y)
    threshold = 0.5
    if hold:
        Xh, yh = stack(sorted(hold))
        p = clf.predict_proba(Xh)[:, 1]
        # F1 on the held-out candidates (before the spacing rule)
        best = -1.0
        for th in [i / 20 for i in range(1, 20)]:
            tp = int(((p >= th) & (yh == 1)).sum())
            fp = int(((p >= th) & (yh == 0)).sum())
            fn = int(((p < th) & (yh == 1)).sum())
            f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
            if f1 > best:
                best, threshold = f1, th
    return {"clf": clf, "threshold": threshold, "features": list(detect.FEATURES),
            "pages": len(pages), "candidates": int(len(y)), "bar_lines": int(y.sum())}


def load_or_train(edition: Path, cache: Path, render) -> dict | None:
    """The model for this edition's reviewed pages, from the cache if they
    haven't changed, else trained now. None if there's nothing to learn from."""
    pages = reviewed_pages(edition)
    if not pages:
        return None
    path = cache / "models" / f"barlines-{key(pages)}.pkl"
    if path.exists():
        try:
            return pickle.loads(path.read_bytes())
        except Exception:
            pass
    model = train(pages, render)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(pickle.dumps(model))
    tmp.replace(path)
    for old in path.parent.glob("barlines-*.pkl"):
        if old != path:
            old.unlink()
    return model
