# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["ultralytics", "numpy", "pillow", "scikit-learn"]
# ///
"""A staff's left end, music start and right end, from the line detector's
"start" and "end" classes, against detect.py and the editor.

    uv run experiments/barlines/landmarks.py <corpus> <edition> [--run yolo26n]

The corpus is built with corpus.py --paper (each staff cut across the
paper's width, its ends and music start recorded) and its tiles with the
start and end classes (tiles.py); the model is runs/<run>/weights/best.pt.
On each test line: the model's surest "start" box (its left edge is the
staff's left end, its right edge the music start) and surest "end" box
(its centre the right end); detect.py's, from the labeler's own detection
of the page (server.Edition.detect: the learned filter, and the vote with
the cached detectors' predictions where there are any, both of which move
where a staff's right end is trimmed; the editor's corners, and the room
from their previous page of the part, as the labeler passes them) and its
staff at that height. The learned filter learns from every reviewed page,
these test pages included, which flatters detect.py. Both are scored on the lines where both give an answer (and
music starts only where the editor set one); each one's missing answers
are counted, and the labeler's bar lines are scored too. Errors against the
editor's, in staff spaces, for the familiar hands and for any source held
out whole (corpus.py --test-source).
"""

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent.parent), str(HERE)]
from common import read_line, yolo_tile  # noqa: E402
from harness import match  # noqa: E402

MATCH = 0.015


def room_from_previous_page(doc: dict, n: int, aspect: float):
    """The labeler's hint for the music start (static/app.js roomFromPreviousPage):
    on the editor's previous page of this part, the median distance from
    left end to music start, in staff spaces, of its lines after the first."""
    prev = None
    for k in range(n - 1, 0, -1):
        p = doc["pages"].get(str(k))
        if not p or p.get("kind") == "title":
            return None
        if p.get("kind") == "music" and p.get("status") != "auto":
            prev = p
            break
    if not prev:
        return None
    lines = sorted((s for s in prev.get("systems", []) if s.get("role", "part") == "part"), key=lambda s: s["top"])[1:]
    rooms = sorted(r for r in ((s.get("start", s["left"]) - s["left"]) / ((s["bottom"] - s["top"]) / 4 * aspect)
                              for s in lines) if r > 1)
    return rooms[len(rooms) // 2] if rooms else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("edition", type=Path)
    ap.add_argument("--run", default="yolo26n")
    ap.add_argument("--no-ends", action="store_true",
                    help="the labeler's detection without the cached starts and ends (the vote kept)")
    args = ap.parse_args()
    import detections
    import learn
    import server
    from detections import cache_dir
    from ultralytics import YOLO

    ed = server.Edition(args.edition, cache_dir())
    if args.no_ends:
        detections.make_ends = lambda preds, w, h: (lambda st: {})

    def render(pdf, n):
        img = Image.open(ed.render(ed.rel(pdf), n))
        img.load()
        return img
    ed.model = learn.load_or_train(ed.root, ed.cache, render)  # as the server does, waited for

    c = json.loads((args.corpus / "corpus.json").read_text())
    test = [l for l in c["lines"] if l["split"] == "test" and "staff_left" in l]
    held = {l["source"] for l in c["lines"]} - {l["source"] for l in c["lines"] if l["split"] == "train"}
    import torch
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    tile = yolo_tile(YOLO(str(args.corpus / "runs" / args.run / "weights" / "best.pt")), device)
    rows = []
    pages = {}
    bars = {}  # group -> [found, false, missed]: the labeler's bar lines on the line's staff
    told = {}  # group -> [staves, with a cached start, with a cached end] (detections.make_ends)
    for l in test:
        sp = l["space"]
        truth = {"left end": l["staff_left"], "right end": l["staff_right"]}
        if "music_start" in l:  # only where the editor set one
            truth["music start"] = l["music_start"]
        _, start, end = read_line(Image.open(args.corpus / l["file"]).convert("RGB"), sp, tile)
        pred = {}
        if start:
            pred["left end"], pred["music start"] = start[0], start[1]
        if end:
            pred["right end"] = end[0]
        key = (l["pdf"], l["page"])
        if key not in pages:
            doc = json.loads((args.edition / l["pdf"].replace(".pdf", ".labels.json")).read_text())
            p = doc["pages"][str(l["page"])]
            page_img = Image.open(ed.render(l["pdf"], l["page"]))
            cs = p["corners"]["points"] if p.get("corners") and not p["corners"].get("auto") else None
            room = room_from_previous_page(doc, l["page"], page_img.size[1] / page_img.size[0])
            preds = detections.page_predictions(ed.root, l["pdf"], l["page"], ed.cache)
            pages[key] = (ed.detect(l["pdf"], l["page"], room, cs)["systems"], page_img.size[0],
                          detections.make_ends(preds, *page_img.size), page_img.size[1])
        systems, w, ends, h = pages[key]
        s = min(systems, key=lambda s: abs(s["top"] - l["top_frac"]), default=None)
        rule = {}
        if s is not None and abs(s["top"] - l["top_frac"]) <= MATCH:
            rule = {"left end": s["left"] * w - l["left"], "music start": s["start"] * w - l["left"],
                    "right end": s["right"] * w - l["left"]}
        group = l["source"] if l["source"] in held else "familiar hands"
        e = ends({"top": s["top"] * h}) if rule else {}
        told[group] = [a + b for a, b in zip(told.get(group, [0, 0, 0]), [1, "start" in e, "right" in e])]
        got = [((b["x0"] + b["x1"]) / 2) * w - l["left"] for b in s["barlines"]] if rule else []
        tally = match(got, [b["x"] for b in l["bars"]], c["tolerance_frac"] * l["page_w"])
        bars[group] = [a + b for a, b in zip(bars.get(group, [0, 0, 0]), tally)]
        for name, t in truth.items():
            rows.append({"group": group, "what": name,
                         "model": abs(pred[name] - t) / sp if name in pred else None,
                         "detect.py": abs(rule[name] - t) / sp if name in rule else None})
    for group in sorted({r["group"] for r in rows}):
        n = sum(1 for l in test if (l["source"] if l["source"] in held else "familiar hands") == group)
        print(f"\n{group} ({n} test lines): errors in staff spaces, median / within 1 / over 3, "
              f"on the lines where both give an answer; then how many lines each gave none")
        for what in ("left end", "music start", "right end"):
            rs = [r for r in rows if r["group"] == group and r["what"] == what]
            both = [r for r in rs if r["model"] is not None and r["detect.py"] is not None]
            cells = []
            for who in ("detect.py", "model"):
                v = np.array([r[who] for r in both])
                cells.append(f"{who}: {np.median(v):4.2f} / {np.mean(v <= 1):4.0%} / {np.mean(v > 3):4.0%}" if len(v) else f"{who}: -")
            miss = {who: sum(r[who] is None for r in rs) for who in ("detect.py", "model")}
            print(f"  {what:12s} ({len(both)} lines) " + "   ".join(cells)
                  + f"   (none: detect.py {miss['detect.py']}, model {miss['model']})")
        f, fa, mi = bars[group]
        print(f"  the labeler's bar lines: {fa + mi} errors ({fa} false, {mi} missed) of {f + mi}")
        n_st, n_s, n_e = told[group]
        print(f"  cached starts / ends sure enough to use: {n_s} / {n_e} of {n_st} staves"
              + (" (not used: --no-ends)" if args.no_ends else ""))


if __name__ == "__main__":
    main()
