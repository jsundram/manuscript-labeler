# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scikit-learn"]
# ///
"""The ensemble, end to end as the labeler would run it: staves detected on
whole pages, the learned filter (learn.py) choosing bar lines on them, and
detectors predicting on the detected staves cut out across the paper's
width (corpus.paper_band: the crops tools/predict_barlines.py caches),
kept within each staff's ends (a space past its right end), as the labeler would
use them; a bar line kept if most of them propose it. Scored on a
corpus's test lines; those lines' labels are hidden from the learned
filter's training (the other staves on their pages are not: the
three-hand corpus is split by line).

    uv run experiments/barlines/e2e_vote.py stage <corpus> <edition>
    uv run --with ultralytics --python 3.12 python experiments/barlines/e2e_vote.py \\
        predict <corpus> yolo <trained-corpus> yolo26n yolo-yolo26n <weights>
    uv run --with "transformers>=4.52" --with torch --with timm --with scipy python \\
        experiments/barlines/e2e_vote.py predict <corpus> dfine <trained-corpus> dfine dfine-dfine-small-coco <weights>
    uv run experiments/barlines/e2e_vote.py score <corpus> <method> <method> ...

stage: learn.train on every reviewed page with the corpus's test lines'
staves dropped (as run_labeler.py), detect_page on each test page; each test
line matched to the detected staff at its height; the learned filter's bar
lines written as result e2e-learned, and the detected staff cut out
(corpus.paper_band, with the editor's corners where set) to e2e/crops/.
predict: a trained detector (trainviz.py's loaders) on those crops at the
threshold it chose on its own validation lines: result e2e-<method>.
score: the majority vote of the given results (ensemble.vote): result
e2e-vote-<members>.
All results are in the test lines' coordinates, for harness.py and
ensemble.py. Each stage runs in the environment its models need.
"""

import json
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent.parent))

import labels  # noqa: E402
from detections import MATCH, REACH  # noqa: E402  (the labeler's own: its reach past a staff's end, staff matching)


def stage(corpus: Path, edition: Path):
    import time

    import numpy as np
    from PIL import Image

    import detect
    import learn
    from corpus import training_pages, paper_band, render
    from harness import write

    c = json.loads((corpus / "corpus.json").read_text())
    test = [l for l in c["lines"] if l["split"] == "test"]
    pages = training_pages(edition, c, test)  # test pages left out whole, worked out afresh

    out = corpus / "e2e" / "crops"
    out.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        def img_of(pdf, n):
            g = render(pdf, n, Path(tmp))
            return Image.fromarray(g).convert("RGB"), g

        t0 = time.perf_counter()
        model = learn.train(pages, lambda pdf, n: img_of(pdf, n)[0])
        train_s = time.perf_counter() - t0
        by_page = {}
        for l in test:
            by_page.setdefault((l["pdf"], l["page"]), []).append(l)
        learned, crops = {}, []
        for (rel, n), ls in by_page.items():
            img, g = img_of(edition / rel, n)
            h, w = g.shape
            page = json.loads(labels.labels_path(edition / rel).read_text())["pages"][str(n)]
            corners = page["corners"]["points"] if page.get("corners") and not page["corners"].get("auto") \
                else detect.find_page_corners(img)
            systems = detect.detect_page(img, model=model, corners=corners)
            for l in ls:
                s = min(systems, key=lambda s: abs(s["top"] - l["top_frac"]), default=None)
                if s is None or abs(s["top"] - l["top_frac"]) > MATCH:
                    learned[l["id"]] = []
                    continue
                learned[l["id"]] = [(b["x0"] + b["x1"]) / 2 * w - l["left"] for b in s["barlines"]]
                band, geo = paper_band(g, s, corners)
                Image.fromarray(band).save(out / f"{l['id']}.png")
                # crop x + offset = page x; page x - line's left = the line's x
                crops.append({"id": l["id"], "file": f"e2e/crops/{l['id']}.png", "width": band.shape[1],
                              "height": band.shape[0], "space": geo["space"], "offset": geo["x_off"] - l["left"],
                              # the detected staff's ends (a space past the right one), in the line's x
                              "lo": s["left"] * w - l["left"],
                              "hi": s["right"] * w - l["left"] + REACH * geo["space"]})
    (corpus / "e2e" / "crops.json").write_text(json.dumps(crops, indent=1))
    write(corpus, {"method": "e2e-learned", "train_s": train_s, "infer_s": 0.0, "lines": learned,
                   "notes": f"learn.py end to end on detected staves; {model['pages']} pages, test lines' labels hidden"})


def predict(corpus: Path, kind: str, trained: Path, run: str, method: str, weights: Path):
    import trainviz
    from common import run as run_lines
    from harness import write

    th = json.loads((trained / "results" / f"{method}.json").read_text())["threshold"]
    factory = {"yolo": trainviz.yolo_checkpoints, "mlx": trainviz.mlx_checkpoints,
               "dfine": trainviz.dfine_checkpoints, "detectron2": trainviz.detectron2_checkpoints}[kind]
    _, detector = factory(trained / "runs" / run)
    crops = json.loads((corpus / "e2e" / "crops.json").read_text())
    preds, per = run_lines(corpus, crops, detector(weights))
    by = {k["id"]: k for k in crops}
    c = json.loads((corpus / "corpus.json").read_text())
    lines = {l["id"]: [] for l in c["lines"] if l["split"] == "test"}
    for i, v in preds.items():
        k = by[i]
        lines[i] = [x + k["offset"] for x, cf in v if cf >= th and k["lo"] <= x + k["offset"] <= k["hi"]]
    write(corpus, {"method": f"e2e-{method}", "train_s": 0.0, "infer_s": per, "threshold": th, "lines": lines,
                   "notes": f"on the detected staves across the paper, within their ends (+{REACH} spaces); trained on {trained.name}, "
                            f"threshold {th} from its validation lines"})


def score(corpus: Path, methods: list[str]):
    from ensemble import vote
    from harness import write

    c = json.loads((corpus / "corpus.json").read_text())
    res = {m: json.loads((corpus / "results" / f"{m}.json").read_text()) for m in methods}
    need = len(methods) // 2 + 1
    lines = {l["id"]: vote({m: res[m]["lines"].get(l["id"], []) for m in methods}, c["tolerance_frac"] * l["page_w"], need)
             for l in c["lines"] if l["split"] == "test"}
    members = "+".join(m.removeprefix("e2e-").removeprefix("yolo-").split("-")[0] for m in methods)
    write(corpus, {"method": f"e2e-vote-{members}", "train_s": 0.0,
                   "infer_s": sum(r.get("infer_s", 0.0) for r in res.values()), "lines": lines,
                   "notes": f"kept if at least {need} of {', '.join(methods)} propose it"})


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "stage":
        stage(Path(sys.argv[2]), Path(sys.argv[3]))
    elif what == "predict":
        predict(Path(sys.argv[2]), sys.argv[3], Path(sys.argv[4]), sys.argv[5], sys.argv[6], Path(sys.argv[7]))
    elif what == "score":
        score(Path(sys.argv[2]), sys.argv[3:])
