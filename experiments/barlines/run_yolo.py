# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["ultralytics", "numpy", "pillow"]
# ///
"""YOLO11 (Ultralytics, AGPL-3.0) fine-tuned on the bar-line tiles.

    uv run experiments/barlines/run_yolo.py <corpus-dir> [--model yolo11n.pt] [--epochs 150]

Starts from COCO-pretrained weights, trains on the Mac's GPU (MPS),
stops early when validation stops improving, then runs on the test lines.
"""

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import cumulative_times, finish  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--model", default="yolo11n.pt")
    ap.add_argument("--epochs", type=int, default=150)
    ap.add_argument("--resume", action="store_true", help="continue the run from its last.pt (after the job time limit)")
    ap.add_argument("--save-period", type=int, default=5,
                    help="keep the weights every this many epochs (for trainviz.py)")
    ap.add_argument("--skip-train", action="store_true",
                    help="score the saved best.pt; training time from the run's results.csv")
    args = ap.parse_args()
    from ultralytics import YOLO

    runs = args.corpus / "runs"
    model = YOLO(str(runs / args.model) if (runs / args.model).exists() else args.model)
    run = runs / Path(args.model).stem
    def total_seconds():
        import csv
        rows = list(csv.DictReader(open(run / "results.csv")))
        return cumulative_times([int(float(r["epoch"])) for r in rows], [float(r["time"]) for r in rows], run)[-1]

    if args.skip_train:
        train_s = total_seconds()
    elif args.resume:
        import csv
        done = len(list(csv.DictReader(open(run / "results.csv"))))
        with open(run / "resumes.txt", "a") as f:  # where the clock will restart
            f.write(f"{done}\n")
        YOLO(str(run / "weights" / "last.pt")).train(resume=True)
        train_s = total_seconds()
    else:
        t0 = time.perf_counter()
        model.train(data=str(args.corpus / "tiles" / "data.yaml"), epochs=args.epochs, imgsz=640, batch=16,
                    device="mps", patience=25, project=str(runs), name=Path(args.model).stem, exist_ok=True,
                    plots=False, verbose=False, workers=2, fliplr=0.5, mosaic=1.0, save_period=args.save_period)
        train_s = time.perf_counter() - t0
    best = YOLO(str(run / "weights" / "best.pt"))

    def detect_tile(tile):
        r = best.predict(tile, imgsz=640, conf=0.05, device="mps", verbose=False)[0]
        return [(float((b[0] + b[2]) / 2), float(c)) for b, c in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist())]

    finish(args.corpus, f"yolo-{Path(args.model).stem}", detect_tile, train_s,
           f"Ultralytics {Path(args.model).stem}, COCO-pretrained, MPS, imgsz 640 tiles")


if __name__ == "__main__":
    main()
