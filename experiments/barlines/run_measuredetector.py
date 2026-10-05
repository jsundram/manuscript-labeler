# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["tensorflow", "numpy", "pillow"]
# ///
"""MeasureDetector (OMR-Research, Pacha et al.), pretrained, used off the shelf.

    uv run experiments/barlines/run_measuredetector.py <corpus-dir> <edition-repo> [--model resnet50.pb]

Retraining isn't possible here (it needs TensorFlow 1.13, Python 3.6/3.7,
the TF Object Detection API: none exist for Apple silicon), so this tests
the released 2019 models as they are. They find measures on whole pages;
each measure box's edges on a line become bar lines there (the first box's
left edge, the line's start, isn't one). Model weights from
https://github.com/OMR-Research/MeasureDetector/releases/tag/v1.0
"""

import argparse
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
from common import best_threshold, lines  # noqa: E402
from harness import write  # noqa: E402

MEASURE_CLASSES = {1, 2}  # system_measure, stave_measure (one staff per system here)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("edition", type=Path)
    ap.add_argument("--model", default="resnet50.pb")
    args = ap.parse_args()
    import tensorflow as tf

    graph_def = tf.compat.v1.GraphDef()
    graph_def.ParseFromString((args.corpus / "runs" / "measuredetector" / args.model).read_bytes())
    graph = tf.Graph()
    with graph.as_default():
        tf.import_graph_def(graph_def, name="")
    sess = tf.compat.v1.Session(graph=graph)
    fetch = {k: graph.get_tensor_by_name(f"{k}:0") for k in ("detection_boxes", "detection_scores", "detection_classes", "num_detections")}
    image_tensor = graph.get_tensor_by_name("image_tensor:0")

    def detect_page(pdf: Path, page: int, tmp: Path):
        base = tmp / f"{pdf.stem}-p{page}"
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", "2800", "-jpeg",
                        "-singlefile", str(pdf), str(base)], check=True)
        img = np.asarray(Image.open(base.with_suffix(".jpg")).convert("RGB"))
        out = sess.run(fetch, feed_dict={image_tensor: img[None]})
        n = int(out["num_detections"][0])
        h, w = img.shape[:2]
        boxes = [(float(b[1] * w), float(b[0] * h), float(b[3] * w), float(b[2] * h), float(s))
                 for b, s, c in zip(out["detection_boxes"][0][:n], out["detection_scores"][0][:n], out["detection_classes"][0][:n])
                 if int(c) in MEASURE_CLASSES]
        return boxes

    def predict(ls):
        by_page, preds = {}, {}
        for line in ls:
            by_page.setdefault((line["pdf"], line["page"]), []).append(line)
        t0 = time.perf_counter()
        with tempfile.TemporaryDirectory() as tmp:
            for (pdf, page), group in by_page.items():
                boxes = detect_page(args.edition / pdf, page, Path(tmp))
                for line in group:
                    y = line["top_frac"] * line["page_h"] + 2 * line["space"]  # the staff's middle
                    mine = sorted((b for b in boxes if b[1] <= y <= b[3]), key=lambda b: b[0])
                    edges = [(b[2] - line["left"], b[4]) for b in mine]
                    edges += [(b[0] - line["left"], b[4]) for b in mine[1:]]
                    tol = 0.006 * line["page_w"] / 2
                    kept = []
                    for x, conf in sorted(edges, key=lambda e: -e[1]):
                        if all(abs(x - k) > tol for k, _ in kept):
                            kept.append((x, conf))
                    preds[line["id"]] = sorted(kept)
        return preds, (time.perf_counter() - t0) / max(1, len(ls))

    val = lines(args.corpus, "val")
    vpred, _ = predict(val)
    th = best_threshold(args.corpus, vpred, val)
    tpred, per_line = predict(lines(args.corpus, "test"))
    write(args.corpus, {"method": f"measuredetector-{Path(args.model).stem}", "train_s": 0.0, "infer_s": per_line,
                        "threshold": th, "lines": {k: [x for x, cf in v if cf >= th] for k, v in tpred.items()},
                        "notes": f"pretrained 2019 model off the shelf (no fine-tuning possible), whole pages, CPU; "
                                 f"threshold {th:.2f} (chosen on val)"})


if __name__ == "__main__":
    main()
