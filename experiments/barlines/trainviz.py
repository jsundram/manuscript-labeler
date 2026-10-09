# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["ultralytics", "numpy", "pillow"]
# ///
"""A detector's checkpoints, judged the way we judge it: did it find the bar
lines? For the model cards (cards.py).

    uv run experiments/barlines/trainviz.py <corpus-dir> yolo <run-name> [<card-key>]
    <venv-with-detectron2>/bin/python experiments/barlines/trainviz.py <corpus-dir> detectron2 detectron2
    uv run --with "transformers>=4.52" --with torch --with timm --with scipy --with numpy --with pillow \
        python experiments/barlines/trainviz.py <corpus-dir> dfine dfine
    uv run --with "yolo-mlx @ git+https://github.com/thewebAI/yolo-mlx" --with numpy --with pillow \
        python experiments/barlines/trainviz.py <corpus-dir> mlx yolo26n-mlx

For every saved checkpoint (Ultralytics' epochN.pt with --save-period,
Detectron2's model_NNNNNNN.pth), runs the model on the validation lines
(never the test lines) and records, at the confidence threshold best for
that checkpoint: bar lines found, false and missed (harness.py's matching).
For the last checkpoint, every detection's confidence and whether it was a
bar line. Draws one validation line per hand at the first, middle and last
checkpoints: found (green), false (red), missed (orange), with
confidences. Writes runs/<run>/trainviz.json and the drawings to
static/models/img/.
"""

import csv
import json
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cards import HANDS, hand  # noqa: E402
from common import cumulative_times, detectron2_tile, dfine_tile, lines, run as run_lines  # noqa: E402

IMG = HERE.parent.parent / "static" / "models" / "img"
THRESHOLDS = [i / 20 for i in range(1, 20)]


def pair(preds: list, truth: list, tol: float) -> tuple[list, list, list]:
    """(matched [(x, conf, truth x)], false [(x, conf)], missed [truth x]):
    surest predictions first, each to the nearest unclaimed bar line."""
    free, matched, false = sorted(truth), [], []
    for x, cf in sorted(preds, key=lambda p: -p[1]):
        near = min(free, key=lambda t: abs(t - x), default=None)
        if near is not None and abs(near - x) <= tol:
            free.remove(near)
            matched.append((x, cf, near))
        else:
            false.append((x, cf))
    return matched, false, free


def judge(c: dict, val: list, preds: dict) -> dict:
    """Best threshold on these lines, and found / false / missed there."""
    best = None
    for th in THRESHOLDS:
        f = fp = m = 0
        for l in val:
            a, b, d = pair([p for p in preds[l["id"]] if p[1] >= th], [bb["x"] for bb in l["bars"]], c["tolerance_frac"] * l["page_w"])
            f, fp, m = f + len(a), fp + len(b), m + len(d)
        if best is None or fp + m < best["false"] + best["missed"]:
            best = {"threshold": th, "found": f, "false": fp, "missed": m}
    return best


def draw(corpus: Path, l: dict, preds: list, th: float, tol: float, path: Path, caption: str):
    img = Image.open(corpus / l["file"]).convert("RGB")
    d = ImageDraw.Draw(img)
    h = img.size[1]
    matched, false, missed = pair([p for p in preds if p[1] >= th], [b["x"] for b in l["bars"]], tol)
    w = 1400
    k = max(1.0, img.size[0] / w)  # drawn at full size, shown at w: scale marks to stay legible
    font = ImageFont.load_default(size=int(15 * k))
    for x, cf, _ in matched:
        d.line([x, 0, x, h], fill=(46, 125, 50), width=int(2 * k))
        d.text((x + 3 * k, 1), f"{cf:.2f}", fill=(46, 125, 50), font=font)
    for x, cf in false:
        d.line([x, 0, x, h], fill=(198, 40, 40), width=int(2 * k))
        d.text((x + 3 * k, 1), f"{cf:.2f}", fill=(198, 40, 40), font=font)
    for x in missed:
        d.line([x, h * 0.55, x, h], fill=(217, 130, 43), width=int(3 * k))
    if img.size[0] > w:
        img = img.resize((w, int(h * w / img.size[0])))
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, quality=85)
    return {"file": f"img/{path.name}", "caption": caption, "found": len(matched), "false": len(false), "missed": len(missed)}


def yolo_checkpoints(run: Path):
    from ultralytics import YOLO
    rows = list(csv.DictReader(open(run / "results.csv")))
    eps = [int(float(r["epoch"])) for r in rows]
    minutes = {e: t / 60 for e, t in zip(eps, cumulative_times(eps, [float(r["time"]) for r in rows], run))}
    cks = sorted(run.glob("weights/epoch*.pt"), key=lambda p: int(re.findall(r"\d+", p.stem)[0]))
    out = []
    for p in cks:
        ep = int(re.findall(r"\d+", p.stem)[0]) + 1  # Ultralytics names them from 0
        out.append((f"epoch {ep}", minutes.get(ep, 0.0), p))

    def detector(p):
        m = YOLO(str(p))

        def tile(t):
            r = m.predict(t, imgsz=640, conf=0.05, device="mps", verbose=False)[0]
            return [(float((b[0] + b[2]) / 2), float(cf)) for b, cf, k in
                    zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), r.boxes.cls.tolist()) if int(k) == 0]  # bar lines only
        return tile
    return out, detector


def mlx_checkpoints(run: Path):
    from yolo26mlx import YOLO
    rows = list(csv.DictReader(open(run / "results.csv")))
    minutes = {int(float(r["epoch"])): float(r["time"]) / 60 for r in rows}
    cks = sorted(run.glob("epoch*.safetensors"), key=lambda p: int(re.findall(r"\d+", p.stem)[0]))
    out = [(f"epoch {int(re.findall(r'\d+', p.stem)[0])}", minutes.get(int(re.findall(r"\d+", p.stem)[0]), 0.0), p) for p in cks]

    def detector(p):
        m = YOLO(str(p))

        def tile(t):
            r = m.predict(t, conf=0.05, imgsz=640)[0]
            cls = r.boxes.cls.tolist() if hasattr(r.boxes, "cls") else [0] * len(r.boxes.conf.tolist())
            return [(float((b[0] + b[2]) / 2), float(cf)) for b, cf, k in
                    zip(r.boxes.xyxy.tolist(), r.boxes.conf.tolist(), cls) if int(k) == 0]  # bar lines only
        return tile
    return out, detector


def dfine_checkpoints(run: Path):
    rows = list(csv.DictReader(open(run / "log.csv")))
    minutes = {int(float(r["epoch"])): float(r["time"]) / 60 for r in rows}
    cks = sorted((p for p in run.glob("epoch*") if p.is_dir()), key=lambda p: int(re.findall(r"\d+", p.name)[0]))
    out = [(f"epoch {int(re.findall(r'\d+', p.name)[0])}", minutes.get(int(re.findall(r"\d+", p.name)[0]), 0.0), p) for p in cks]

    def detector(p):
        tile = dfine_tile(p, "mps")
        return lambda t: [((x0 + x1) / 2, c) for _, x0, x1, c in tile(t)]
    return out, detector


def detectron2_checkpoints(run: Path):
    recs = [json.loads(x) for x in (run / "metrics.json").read_text().splitlines() if x.strip()]
    sec = {r["iteration"]: r["iteration"] * r.get("time", 0) for r in recs if "time" in r}
    cks = sorted(run.glob("model_0*.pth"))
    out = []
    for p in cks:
        it = int(re.findall(r"\d+", p.stem)[0])
        near = min(sec, key=lambda i: abs(i - it))
        out.append((f"iteration {it + 1}", sec[near] / 60, p))

    def detector(p):
        tile = detectron2_tile(p, "mps")
        return lambda t: [((x0 + x1) / 2, c) for _, x0, x1, c in tile(t)]
    return out, detector


def main():
    corpus, kind, name = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    # the drawings' names: the card's key if given, else the corpus and run (runs in
    # different corpora share names: yolo26n)
    prefix = sys.argv[4] if len(sys.argv) > 4 else f"{corpus.name}-{name}"
    run = corpus / "runs" / name
    c = json.loads((corpus / "corpus.json").read_text())
    val = lines(corpus, "val")
    cks, detector = {"yolo": yolo_checkpoints, "mlx": mlx_checkpoints, "dfine": dfine_checkpoints,
                     "detectron2": detectron2_checkpoints}[kind](run)
    shown = {0, len(cks) // 2, len(cks) - 1}
    examples = {h: next(l for l in val if hand(l) == h) for h in HANDS if any(hand(l) == h for l in val)}
    out = {"checkpoints": [], "examples": [], "validation": {"lines": len(val), "bar_lines": sum(len(l["bars"]) for l in val)}}
    for k, (label, minutes, path) in enumerate(cks):
        preds, per = run_lines(corpus, val, detector(path))
        j = judge(c, val, preds)
        out["checkpoints"].append({"label": label, "minutes": minutes, **j})
        print(f"{label} ({minutes:.0f} min): threshold {j['threshold']}, found {j['found']}, false {j['false']}, missed {j['missed']}", flush=True)
        if k in shown:
            for h, l in examples.items():
                out["examples"].append({"hand": h, "checkpoint": label, "minutes": minutes, **draw(
                    corpus, l, preds[l["id"]], j["threshold"], c["tolerance_frac"] * l["page_w"],
                    IMG / f"{prefix}-{h.replace(' ', '').lower()}-{k}.jpg", f"{h}, {label}: {l['id']}")})
        if k == len(cks) - 1:
            hits, falses, missed = [], [], 0
            for l in val:
                a, b, d = pair(preds[l["id"]], [bb["x"] for bb in l["bars"]], c["tolerance_frac"] * l["page_w"])
                hits += [cf for _, cf, _ in a]
                falses += [cf for _, cf in b]
                missed += len(d)
            out["confidence"] = {"bar_lines": hits, "not_bar_lines": falses, "never_proposed": missed, "threshold": j["threshold"]}
    (run / "trainviz.json").write_text(json.dumps(out, indent=1))
    print(f"wrote {run / 'trainviz.json'}")


if __name__ == "__main__":
    main()
