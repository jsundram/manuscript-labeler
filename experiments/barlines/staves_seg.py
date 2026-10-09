# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["ultralytics", "numpy", "pillow"]
# ///
"""Can a segmentation model find the staves, their music start and their
crop better than detect.py's staff tracing and rules?

    uv run experiments/barlines/staves_seg.py build <edition> <out-dir>
    uv run experiments/barlines/staves_seg.py train <out-dir> [--model yolo26n-seg.pt] [--epochs 150]
    uv run experiments/barlines/staves_seg.py eval <out-dir> <edition>

build: every reviewed music page, rendered as the labeler renders it, with
three outlines per counted staff from the editor's labels, each following
the staff's bend: "staff" (left to right end, top to bottom line), "start"
(the clef-key-time region, left end to music start) and "crop" (the staff
widened by the editor's crop margins above and below). Split by page: all
of F-Pn Vma ms 1067 (1) and TEST_PER_SOURCE pages of each other source are
test, one page of each validation, the rest training (seed 1).
train: Ultralytics instance segmentation on whole pages (imgsz 1280, no
horizontal flips: a mirrored page puts the clef on the right).
eval: on the test pages, the model's staves and detect.detect_page's
against the editor's: staves found / missed / false, and the left end,
right end, music start, crop above and below, each in staff spaces.
"""

import json
import random
import shutil
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT), str(HERE)]

CLASSES = ["staff", "start", "crop"]
TEST_PER_SOURCE = 2
NEW_SOURCE = "F-Pn_Vma-ms-1067-1"  # unseen copy: every reviewed page is test
N = 16  # points along each edge of an outline


def outline(s: dict, x0: float, x1: float, above: float, below: float) -> list[tuple[float, float]]:
    """Polygon (page fractions) of the staff from x0 to x1, widened by
    above / below staff spaces, following its bend (labels.bend_at)."""
    import labels
    sp = (s["bottom"] - s["top"]) / 4
    xs = [x0 + (x1 - x0) * i / N for i in range(N + 1)]
    top = [(x, s["top"] + labels.bend_at(s, x) - above * sp) for x in xs]
    bot = [(x, s["bottom"] + labels.bend_at(s, x) + below * sp) for x in reversed(xs)]
    return top + bot


def build(edition: Path, out: Path):
    import labels
    import learn
    import server
    from PIL import Image

    ed = server.Edition(edition, Path.home() / ".cache" / "manuscript-labeler")
    pages = learn.reviewed_pages(edition)
    rng = random.Random(1)
    by_src = {}
    for pdf, n, p in pages:
        by_src.setdefault(pdf.stem, []).append((pdf, n, p))
    split = {}
    for src, ps in by_src.items():
        if src == NEW_SOURCE:
            for pdf, n, _ in ps:
                split[(src, n)] = "test"
            continue
        order = ps[:]
        rng.shuffle(order)
        for i, (pdf, n, _) in enumerate(order):
            split[(src, n)] = "test" if i < TEST_PER_SOURCE else "val" if i == TEST_PER_SOURCE else "train"
    if out.exists():
        shutil.rmtree(out)
    meta = []
    for pdf, n, p in pages:
        sp = split[(pdf.stem, n)]
        rel = str(pdf.relative_to(edition))
        img = Image.open(ed.render(rel, n)).convert("RGB")
        name = f"{pdf.stem}-p{n:02d}"
        (out / "images" / sp).mkdir(parents=True, exist_ok=True)
        (out / "labels" / sp).mkdir(parents=True, exist_ok=True)
        img.save(out / "images" / sp / f"{name}.jpg", quality=90)
        rows = []
        for s in labels.counted_systems(p):
            start = s.get("start", s["left"])
            space_w = (s["bottom"] - s["top"]) / 4 * img.size[1] / img.size[0]  # a staff space in page widths
            shapes = [(0, outline(s, s["left"], s["right"], 0, 0)),
                      (2, outline(s, s["left"], s["right"], s.get("above", 2.5), s.get("below", 2.5)))]
            if start - s["left"] >= 0.5 * space_w:  # a start region with nothing in it isn't one
                shapes.append((1, outline(s, s["left"], start, 0, 0)))
            for cls, poly in shapes:
                rows.append(f"{cls} " + " ".join(f"{min(1, max(0, x)):.5f} {min(1, max(0, y)):.5f}" for x, y in poly))
        (out / "labels" / sp / f"{name}.txt").write_text("\n".join(rows) + "\n")
        meta.append({"name": name, "pdf": rel, "page": n, "split": sp, "source": pdf.stem, "part": p.get("part"),
                     "w": img.size[0], "h": img.size[1]})
    (out / "data.yaml").write_text(f"path: {out}\ntrain: images/train\nval: images/val\nnames:\n"
                                   + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))
    (out / "pages.json").write_text(json.dumps(meta, indent=1))
    for sp in ("train", "val", "test"):
        print(f"{sp}: {sum(m['split'] == sp for m in meta)} pages")


def train(out: Path, model: str, epochs: int):
    from ultralytics import YOLO
    YOLO(model).train(data=str(out / "data.yaml"), epochs=epochs, imgsz=1280, batch=4, device="mps", patience=40,
                      project=str(out / "runs"), name=Path(model).stem, exist_ok=True, plots=False, verbose=False,
                      fliplr=0.0, save_period=10, workers=2,
                      # YOLO26-seg's losses went NaN within an epoch or two with mosaics (pages
                      # cut in quarters clip long staff outlines to slivers) and with mixed
                      # precision; YOLO11-seg trained with mosaics
                      mosaic=0.0 if "26" in model else 1.0, amp=False,
                      # one mask per outline: packed into one image (the default) the nested
                      # outlines (start inside staff inside crop) cut holes in each other
                      overlap_mask=False)


def edges(poly: np.ndarray) -> dict:
    """Left, right, top, bottom (page fractions) of a polygon (n, 2)."""
    return {"left": float(poly[:, 0].min()), "right": float(poly[:, 0].max()),
            "top": float(poly[:, 1].min()), "bottom": float(poly[:, 1].max())}


def bend_range(s: dict) -> tuple[float, float]:
    """The lowest and highest offset of a staff's bend along its length."""
    import labels
    b = [labels.bend_at(s, s["left"] + (s["right"] - s["left"]) * i / N) for i in range(N + 1)]
    return min(b), max(b)


def evaluate(out: Path, edition: Path, model: str):
    import detect
    import labels
    from PIL import Image
    from ultralytics import YOLO

    meta = [m for m in json.loads((out / "pages.json").read_text()) if m["split"] == "test"]
    seg = YOLO(str(out / "runs" / Path(model).stem / "weights" / "best.pt"))
    docs = {}
    stats = {"seg": [], "rules": []}
    counts = {"seg": [0, 0, 0], "rules": [0, 0, 0]}  # found, missed, false
    for m in meta:
        doc = docs.setdefault(m["pdf"], json.loads(labels.labels_path(edition / m["pdf"]).read_text()))
        truth = labels.counted_systems(doc["pages"][str(m["page"])])
        img = Image.open(out / "images" / "test" / f"{m['name']}.jpg")
        w, h = img.size
        # the model: each staff instance, with the start and crop instances overlapping it most
        r = seg.predict(img, imgsz=1280, conf=0.25, device="mps", verbose=False, retina_masks=False)[0]
        polys = {c: [] for c in range(3)}
        if r.masks is not None:
            for cls, xy in zip(r.boxes.cls.tolist(), r.masks.xyn):
                if len(xy) >= 3:
                    polys[int(cls)].append(edges(np.asarray(xy)))
        seg_staves = []
        for st in polys[0]:
            def near(c):
                cands = [e for e in polys[c] if min(e["bottom"], st["bottom"]) - max(e["top"], st["top"]) > 0]
                return min(cands, key=lambda e: abs((e["top"] + e["bottom"]) - (st["top"] + st["bottom"])), default=None)
            stt, crop = near(1), near(2)
            seg_staves.append({**st, "start": stt["right"] if stt else None,
                               "above": crop["top"] if crop else None, "below": crop["bottom"] if crop else None})
        # today's detection; crop edges, like a polygon's extent, at the
        # staff's highest and lowest point along its bend
        rules = [{"left": s["left"], "right": s["right"], "top": s["top"], "bottom": s["bottom"], "start": s.get("start"),
                  "above": s["top"] + bend_range(s)[0] - s["above"] * (s["bottom"] - s["top"]) / 4,
                  "below": s["bottom"] + bend_range(s)[1] + s["below"] * (s["bottom"] - s["top"]) / 4}
                 for s in detect.detect_page(img)]
        for name, found in (("seg", seg_staves), ("rules", rules)):
            used = set()
            for s in truth:
                sp = (s["bottom"] - s["top"]) / 4
                mid = (s["top"] + s["bottom"]) / 2
                cand = [(abs((f["top"] + f["bottom"]) / 2 - mid), i) for i, f in enumerate(found) if i not in used]
                d, i = min(cand, default=(1, -1))
                if i < 0 or d > 2 * sp:
                    counts[name][1] += 1
                    continue
                used.add(i)
                counts[name][0] += 1
                f = found[i]
                spw = sp * h / w  # a staff space in page widths
                row = {"left": abs(f["left"] - s["left"]) / spw, "right": abs(f["right"] - s["right"]) / spw}
                if f.get("start") is not None and s.get("start") is not None:
                    row["start"] = abs(f["start"] - s["start"]) / spw
                lo, hi = bend_range(s)
                ta = s["top"] + lo - s.get("above", 2.5) * sp
                tb = s["bottom"] + hi + s.get("below", 2.5) * sp
                if f.get("above") is not None:
                    row["crop above"] = abs(f["above"] - ta) / sp
                    row["crop below"] = abs(f["below"] - tb) / sp
                stats[name].append({**row, "source": m["source"]})
            counts[name][2] += len(found) - len(used)
    print(f"{len(meta)} test pages")
    for name in ("rules", "seg"):
        f, mi, fa = counts[name]
        print(f"\n{'detect.py (today)' if name == 'rules' else 'segmentation'}: staves found {f}, missed {mi}, false {fa}")
        for k in ("left", "right", "start", "crop above", "crop below"):
            v = np.array([s[k] for s in stats[name] if k in s])
            if len(v):
                print(f"  {k:11s} median {np.median(v):5.2f} spaces, within 1 space {np.mean(v <= 1):5.0%}, over 3 spaces {np.mean(v > 3):5.0%}")


if __name__ == "__main__":
    what = sys.argv[1]
    if what == "build":
        build(Path(sys.argv[2]), Path(sys.argv[3]))
    elif what == "train":
        model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "yolo26n-seg.pt"
        epochs = int(sys.argv[sys.argv.index("--epochs") + 1]) if "--epochs" in sys.argv else 150
        train(Path(sys.argv[2]), model, epochs)
    elif what == "eval":
        model = sys.argv[sys.argv.index("--model") + 1] if "--model" in sys.argv else "yolo26n-seg.pt"
        evaluate(Path(sys.argv[2]), Path(sys.argv[3]), model)
