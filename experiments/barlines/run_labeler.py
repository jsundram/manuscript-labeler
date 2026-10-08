# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scikit-learn"]
# ///
"""The labeler's own learned filter (learn.py), end to end, on the corpus split.

    uv run experiments/barlines/run_labeler.py <corpus-dir> <edition-repo>

Unlike run_learned.py (trained and run on the corpus's straightened lines),
this is what the labeler does: learn.train on whole pages through
detect.detect_page, then detect_page with the model. The test lines'
labels are hidden from training (their staves are dropped from the pages'
labels, which learn.examples then skips), and only the test lines are
scored: each is matched to the staff detection found at its height, and
its bar lines are moved into the line's crop coordinates.
"""

import json
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))
sys.path.insert(0, str(HERE.parent.parent / "tools"))
import detect  # noqa: E402
import learn  # noqa: E402
from corpus import training_pages  # noqa: E402
from harness import write  # noqa: E402
from score_barlines import render  # noqa: E402


def main():
    corpus, edition = Path(sys.argv[1]), Path(sys.argv[2])
    rules_only = "--rules" in sys.argv  # the hand-tuned rules, end to end, for comparison
    c = json.loads((corpus / "corpus.json").read_text())
    test = [l for l in c["lines"] if l["split"] == "test"]
    pages = training_pages(edition, c, test)  # test pages left out whole, worked out afresh

    with tempfile.TemporaryDirectory() as tmp:
        # keep only the test pages, which are rendered again for scoring
        cache, keep = {}, {(edition / l["pdf"], l["page"]) for l in test}

        def r(pdf, n):
            if (pdf, n) in cache:
                return cache[(pdf, n)]
            img = render(pdf, n, Path(tmp))
            if (pdf, n) in keep:
                cache[(pdf, n)] = img
            return img

        t0 = time.perf_counter()
        model = None if rules_only else learn.train(pages, r)
        train_s = time.perf_counter() - t0

        preds, by_page = {}, {}
        for l in test:
            by_page.setdefault((l["pdf"], l["page"]), []).append(l)
        t1 = time.perf_counter()
        for (rel, n), lines in by_page.items():
            img = r(edition / rel, n)
            w = img.size[0]
            systems = detect.detect_page(img, model=model)
            for l in lines:
                s = min(systems, key=lambda s: abs(s["top"] - l["top_frac"]), default=None)
                if s is None or abs(s["top"] - l["top_frac"]) > 0.015:
                    preds[l["id"]] = []
                    continue
                preds[l["id"]] = [(b["x0"] + b["x1"]) / 2 * w - l["left"] for b in s["barlines"]]
        per_line = (time.perf_counter() - t1) / len(test)

    if rules_only:
        write(corpus, {"method": "classical-labeler", "train_s": 0.0, "infer_s": per_line, "lines": preds,
                       "notes": "the hand-tuned rules end to end: detect_page on whole pages (detected staves, "
                                "edges and music start); per line includes staff detection"})
        return
    write(corpus, {"method": "learned-labeler", "train_s": train_s, "infer_s": per_line, "lines": preds,
                   "notes": f"the labeler's learn.py end to end: trained on whole pages through detect_page "
                            f"(test lines' labels hidden), {model['pages']} pages, {model['bar_lines']} bar lines, "
                            f"threshold {model['threshold']:.2f}; per line includes staff detection on the page"})


if __name__ == "__main__":
    main()
