# /// script
# requires-python = ">=3.11"
# dependencies = ["yolo-mlx @ git+https://github.com/thewebAI/yolo-mlx", "numpy", "pillow"]
# ///
"""YOLO26 in MLX (github.com/thewebAI/yolo-mlx, AGPL-3.0), fine-tuned on the
bar-line tiles: the same model as run_yolo.py --model yolo26n.pt, trained
natively on Apple silicon (Metal) instead of PyTorch's MPS backend.

    uv run experiments/barlines/run_yolo_mlx.py <corpus-dir> --weights yolo26n.npz [--epochs 25] [--skip-train]

The starting weights, converted once from Ultralytics' yolo26n.pt:
    uv run --with "yolo-mlx[convert] @ git+https://github.com/thewebAI/yolo-mlx" \\
        yolo-mlx converters convert yolo26n.pt -o yolo26n.npz --verify
Keeps a checkpoint every 5 epochs (for trainviz.py) and writes the epoch log
as runs/yolo26n-mlx/results.csv in Ultralytics' column names, for cards.py.
Its training augments with colour, flips, scale and shift; unlike
Ultralytics it doesn't make mosaics.
"""

import argparse
import csv
import logging
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import finish  # noqa: E402
from tiles import tile_classes  # noqa: E402

NAME = "yolo26n-mlx"
EPOCH = re.compile(r"Epoch (\d+)/\d+: loss=([\d.]+), mAP50=([\d.]+), mAP50-95=([\d.]+), P=([\d.]+), R=([\d.]+), time=([\d.]+)s")


class EpochLog(logging.Handler):
    """Collects yolo-mlx's per-epoch lines into rows."""

    def __init__(self):
        super().__init__()
        self.rows, self.elapsed = [], 0.0

    def emit(self, record):
        m = EPOCH.search(record.getMessage())
        if m:
            ep, loss, m50, m5095, p, r, t = m.groups()
            self.elapsed += float(t)
            self.rows.append({"epoch": int(ep), "time": round(self.elapsed, 1), "train/loss": float(loss),
                              "metrics/precision(B)": float(p), "metrics/recall(B)": float(r),
                              "metrics/mAP50(B)": float(m50), "metrics/mAP50-95(B)": float(m5095)})


def write_rows(run: Path, rows: list[dict]):
    if not rows:
        raise SystemExit("no epoch lines recognised in yolo-mlx's output: has its log format changed?")
    with open(run / "results.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--skip-train", action="store_true")
    ap.add_argument("--from-log", type=Path,
                    help="with --skip-train: rebuild results.csv from this run's printed output (if training was cut off)")
    args = ap.parse_args()
    from yolo26mlx import YOLO

    runs = args.corpus / "runs"
    run = runs / NAME
    tiles = args.corpus / "tiles" / "yolo"
    data = runs / f"{NAME}-data.yaml"
    runs.mkdir(parents=True, exist_ok=True)
    if len(tile_classes(args.corpus)) > 1:
        raise SystemExit("these tiles also hold start and end boxes (corpus.py --paper): "
                         "yolo-mlx is set up for bar lines only; build the tiles without --paper")
    data.write_text(f"path: {tiles}\ntrain: images/train\nval: images/val\nnc: 1\nnames: ['barline']\n")

    # (yolo-mlx's checkpoints hold the weights only, not the optimiser or the
    # epoch, so a cut-off run can't truly resume: size --epochs to the time)
    if args.skip_train:
        if args.from_log:
            log = EpochLog()
            for line in args.from_log.read_text().splitlines():
                log.emit(logging.makeLogRecord({"msg": line}))
            write_rows(run, log.rows)
        train_s = float(list(csv.DictReader(open(run / "results.csv")))[-1]["time"])
    else:
        log = EpochLog()
        logging.getLogger("yolo26mlx").addHandler(log)
        logging.getLogger("yolo26mlx").setLevel(logging.INFO)
        YOLO(str(args.weights)).train(data=str(data), epochs=args.epochs, imgsz=640, batch=16, patience=25,
                                     save_period=5, project=str(runs), name=NAME, exist_ok=True)
        write_rows(run, log.rows)
        train_s = log.elapsed

    best = YOLO(str(run / "best.safetensors"))

    def detect_tile(tile):
        r = best.predict(tile, conf=0.05, imgsz=640)[0]
        cls = r.boxes.cls.tolist() if hasattr(r.boxes, "cls") else [0] * len(r.boxes.conf.tolist())
        return [(float((b[0] + b[2]) / 2), float(c)) for b, c, k in zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), cls)
                if int(k) == 0]  # bar lines only

    finish(args.corpus, f"yolo-mlx-{NAME.removesuffix('-mlx')}", detect_tile, train_s,
           "yolo-mlx (MLX on Metal), yolo26n converted from Ultralytics' COCO weights, imgsz 640 tiles")


if __name__ == "__main__":
    main()
