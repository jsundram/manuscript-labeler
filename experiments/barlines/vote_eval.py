# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["numpy", "pillow", "scikit-learn"]
# ///
"""Which detectors should vote: the labeler's own detection, end to end,
with different sets of cached detectors, on pages no model saw.

    uv run experiments/barlines/vote_eval.py <corpus> <edition> <pool-cache> CONFIG ...

<corpus> is built with corpus.py --paper and holds test_pages.json's pages
as test pages; only those are scored (other test pages may be in an
installed detector's training data). <pool-cache> is a labeler cache with
every candidate detector installed and its predictions made
(tools/predict_barlines.py, each --kind in its environment). A CONFIG is
NAME=det1+det2[:need], e.g. today=yolo26n+yolo11n or
four=yolo26n+yolo11n+detectron2:2 (need: voters that must agree, default a
majority of the staff's voters, the labeler's own bar lines and the
detectors that have a staff there).

Each config runs in its own cache holding just its detectors (linked from
the pool). The learned filter is trained afresh without the test pages,
so no voter has seen them. Per test source: bar line errors (false,
missed), and the share of the editor's bar lines found.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent.parent), str(HERE)]
import labels  # noqa: E402


def main():
    corpus, edition, pool = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]).resolve()  # linked from a temp dir
    configs = []
    for a in sys.argv[4:]:
        name, _, spec = a.partition("=")
        dets, _, need = spec.partition(":")
        configs.append((name, dets.split("+"), int(need) if need else None))
    from PIL import Image

    import detections
    import learn
    import server
    from corpus import held_out_pages, training_pages
    from harness import match

    c = json.loads((corpus / "corpus.json").read_text())
    held = held_out_pages()
    test = [l for l in c["lines"] if l["split"] == "test"]
    scored = [l for l in test if l["page"] in held.get(l["source"], [])]
    ed0 = server.Edition(edition, pool)

    def render(pdf, n):
        img = Image.open(ed0.render(ed0.rel(pdf), n))
        img.load()
        return img
    model = learn.train(training_pages(edition, c, test), render)  # without the test pages
    print(f"learned filter: {model['pages']} pages, none of the {len({(l['source'], l['page']) for l in test})} test pages")
    for name, dets, need in configs:
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp)
            (cache / "models" / "detectors").mkdir(parents=True)
            (cache / "detections").mkdir()
            os.symlink(pool / "renders", cache / "renders")
            for d in detections.detectors(pool):
                if d["name"] in dets:
                    os.symlink(pool / "models" / "detectors" / d["name"], cache / "models" / "detectors" / d["name"])
                    os.symlink(pool / "detections" / d["key"], cache / "detections" / d["key"])
            missing = set(dets) - {d["name"] for d in detections.detectors(cache)}
            if missing:
                sys.exit(f"{name}: not in the pool: {', '.join(sorted(missing))}")
            # each detector must have predictions for every scored page, or it
            # would drop out of the vote without a word
            for pdf, n in sorted({(l["pdf"], l["page"]) for l in scored}):
                have = {d["name"] for d, _ in detections.page_predictions(edition, pdf, n, cache)}
                if set(dets) - have:
                    sys.exit(f"{name}: no predictions for {pdf} p{n} from {', '.join(sorted(set(dets) - have))}")
            detections.VOTE_NEED = need
            ed = server.Edition(edition, cache)
            ed.model = model
            pages, tally = {}, {}
            for l in scored:
                key = (l["pdf"], l["page"])
                if key not in pages:
                    doc = json.loads(labels.labels_path(edition / l["pdf"]).read_text())
                    p = doc["pages"][str(l["page"])]
                    cs = p["corners"]["points"] if p.get("corners") and not p["corners"].get("auto") else None
                    w = Image.open(ed.render(l["pdf"], l["page"])).size[0]
                    pages[key] = (ed.detect(l["pdf"], l["page"], None, cs)["systems"], w)
                systems, w = pages[key]
                s = min(systems, key=lambda s: abs(s["top"] - l["top_frac"]), default=None)
                got = ([((b["x0"] + b["x1"]) / 2) * w - l["left"] for b in s["barlines"]]
                       if s and abs(s["top"] - l["top_frac"]) <= detections.MATCH else [])
                f, fa, mi = match(got, [b["x"] for b in l["bars"]], c["tolerance_frac"] * l["page_w"])
                t = tally.setdefault(l["source"], [0, 0, 0])
                tally[l["source"]] = [t[0] + f, t[1] + fa, t[2] + mi]
            detections.VOTE_NEED = None
        line = "  ".join(f"{src}: {fa + mi} errors ({fa} false, {mi} missed) of {f + mi}, {f / (f + mi):.1%} found"
                         for src, (f, fa, mi) in sorted(tally.items()))
        print(f"{name:12s} {'+'.join(dets)}{f' (need {need})' if need else ''}\n  {line}")


if __name__ == "__main__":
    main()
