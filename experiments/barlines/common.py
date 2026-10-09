"""Shared by the detector runners: run a tile detector over whole lines,
merge across tiles, pick the confidence threshold on the validation lines
(never the test lines), and write a result for harness.py to score."""

import json
import time
from pathlib import Path

from PIL import Image

from harness import match, write
from tiles import TILE, windows


def cumulative_times(epochs: list[int], times: list[float], run: Path | None = None) -> list[float]:
    """Seconds since the run began, per logged epoch. Ultralytics (and our
    D-FINE runner's log) restart the clock when a run resumes: a restart is
    where run/resumes.txt (written by --resume) says one happened, or else
    where the clock goes backwards (missing a resume after a single slow
    epoch, which only resumes.txt catches)."""
    marks = set()
    if run is not None and (run / "resumes.txt").exists():
        marks = {int(x) for x in (run / "resumes.txt").read_text().split()}
    out, offset, prev = [], 0.0, 0.0
    for i, (ep, t) in enumerate(zip(epochs, times)):
        if i and (ep - 1 in marks or t < times[i - 1]):
            offset = prev
        prev = t + offset
        out.append(prev)
    return out


def lines(corpus: Path, which: str) -> list[dict]:
    c = json.loads((corpus / "corpus.json").read_text())
    val = set(json.loads((corpus / "tiles" / "val_ids.json").read_text()))
    if which == "val":
        return [l for l in c["lines"] if l["id"] in val]
    return [l for l in c["lines"] if l["split"] == which]


def detect_line(img: Image.Image, space: float, detect_tile) -> list[tuple[float, float]]:
    """[(x, conf)] along one straightened line image, from its TILE-wide
    windows, the same bar line seen in two tiles kept once (the surer).
    detect_tile(PIL image) -> [(x_center, conf)] in tile pixels."""
    found = []
    for x in windows(img.size[0]):
        tile = img.crop((x, 0, x + TILE, img.size[1]))
        found += [(x + xc, conf) for xc, conf in detect_tile(tile)]
    return merge_bars(found, space)


def merge_bars(found: list[tuple[float, float]], space: float) -> list[tuple[float, float]]:
    """Bar lines [(x, conf)] from overlapping tiles: one seen twice kept once (the surer)."""
    tol = 0.3 * space * 2
    kept = []
    for xc, conf in sorted(found, key=lambda d: -d[1]):
        if all(abs(xc - k) > tol for k, _ in kept):
            kept.append((xc, conf))
    return sorted(kept)


def yolo_tile(model, device: str, conf: float = 0.05):
    """An Ultralytics model as read_line's predict_tile: [(cls, x0, x1, conf)]."""
    def tile(t):
        r = model.predict(t, imgsz=640, conf=conf, device=device, verbose=False)[0]
        return [(int(k), float(b[0]), float(b[2]), float(c)) for b, c, k in
                zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist())]
    return tile


def detectron2_tile(weights, device: str, conf: float = 0.05):
    """A Detectron2 Faster R-CNN, as run_detectron2.py trains it (bar lines
    only), as read_line's predict_tile: [(0, x0, x1, conf)]."""
    import numpy as np
    from detectron2 import model_zoo
    from detectron2.config import get_cfg
    from detectron2.engine import DefaultPredictor
    cfg = get_cfg()
    cfg.merge_from_file(model_zoo.get_config_file("COCO-Detection/faster_rcnn_R_50_FPN_3x.yaml"))
    cfg.MODEL.ROI_HEADS.NUM_CLASSES = 1
    cfg.MODEL.ANCHOR_GENERATOR.ASPECT_RATIOS = [[2.0, 4.0, 8.0]]  # tall, thin bar lines (as trained)
    cfg.INPUT.MIN_SIZE_TEST, cfg.INPUT.MAX_SIZE_TEST = 192, 640
    cfg.MODEL.DEVICE = device
    cfg.MODEL.WEIGHTS = str(weights)
    cfg.MODEL.ROI_HEADS.SCORE_THRESH_TEST = conf
    pred = DefaultPredictor(cfg)

    def tile(t):
        inst = pred(np.asarray(t)[:, :, ::-1])["instances"].to("cpu")
        return [(0, float(b[0]), float(b[2]), float(c)) for b, c in zip(inst.pred_boxes.tensor.numpy(), inst.scores.numpy())]
    return tile


def dfine_tile(weights, device: str, conf: float = 0.05):
    """A D-FINE model, as run_dfine.py trains it (bar lines only), as
    read_line's predict_tile: [(0, x0, x1, conf)]."""
    import torch
    from transformers import AutoImageProcessor, DFineForObjectDetection

    import dfine_patch  # noqa: F401  (the Mac GPU workaround)
    proc = AutoImageProcessor.from_pretrained("ustc-community/dfine-small-coco")
    m = DFineForObjectDetection.from_pretrained(weights).to(device).eval()

    def tile(t):
        with torch.no_grad():
            enc = proc(images=t, return_tensors="pt", size={"height": 192, "width": 640})
            o = m(pixel_values=enc["pixel_values"].to(device))
        r = proc.post_process_object_detection(o, threshold=conf, target_sizes=[(t.height, t.width)])[0]
        return [(0, float(b[0]), float(b[2]), float(c)) for b, c in zip(r["boxes"].tolist(), r["scores"].tolist())]
    return tile


def read_line(img: Image.Image, space: float, predict_tile) -> tuple[list, tuple | None, tuple | None]:
    """A line detector's whole reading of one straightened line: its bar
    lines [(x, conf)] (as detect_line), its surest "start" box (x0, x1,
    conf: the staff's left end and music start) and surest "end" box (x,
    conf: the staff's right end), or None for a class it didn't find.
    predict_tile(PIL image) -> [(cls, x0, x1, conf)] in tile pixels. A
    start or end box against a tile's edge (not the line's) may be cut off
    there, so its edges aren't the staff's: a whole one is preferred."""
    width = img.size[0]
    bars, best, cut = [], {}, {}
    for x in windows(width):
        for k, x0, x1, conf in predict_tile(img.crop((x, 0, x + TILE, img.size[1]))):
            if not k:
                bars.append((x + (x0 + x1) / 2, conf))
                continue
            whole = (x0 > 2 or x == 0) and (x1 < TILE - 2 or x + TILE >= width)
            pick = best if whole else cut
            if k not in pick or conf > pick[k][2]:
                pick[k] = (x + x0, x + x1, conf)
    got = {**cut, **best}
    start = got.get(1)
    end = ((got[2][0] + got[2][1]) / 2, got[2][2]) if 2 in got else None
    return merge_bars(bars, space), start, end


def run(corpus: Path, ls: list[dict], detect_tile) -> tuple[dict, float]:
    """{line id: [(x, conf)]} merged across tiles, and seconds per line."""
    out, t0 = {}, time.perf_counter()
    for line in ls:
        out[line["id"]] = detect_line(Image.open(corpus / line["file"]).convert("RGB"), line["space"], detect_tile)
    return out, (time.perf_counter() - t0) / max(1, len(ls))


def best_threshold(corpus: Path, preds: dict, ls: list[dict]) -> float:
    c = json.loads((corpus / "corpus.json").read_text())
    tol = c["tolerance_frac"]
    best = (0.5, -1)
    for th in [i / 20 for i in range(1, 20)]:
        f = fp = m = 0
        for line in ls:
            a, b, d = match([x for x, cf in preds[line["id"]] if cf >= th], [b["x"] for b in line["bars"]], tol * line["page_w"])
            f, fp, m = f + a, fp + b, m + d
        f1 = 2 * f / (2 * f + fp + m) if f else 0
        if f1 > best[1]:
            best = (th, f1)
    return best[0]


def finish(corpus: Path, method: str, detect_tile, train_s: float, notes: str):
    val = lines(corpus, "val")
    vpred, _ = run(corpus, val, detect_tile)
    th = best_threshold(corpus, vpred, val)
    tpred, per_line = run(corpus, lines(corpus, "test"), detect_tile)
    write(corpus, {"method": method, "train_s": train_s, "infer_s": per_line, "threshold": th,
                   "lines": {k: [x for x, cf in v if cf >= th] for k, v in tpred.items()},
                   "notes": f"{notes}; threshold {th:.2f} (chosen on val)"})
