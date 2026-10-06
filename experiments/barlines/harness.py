# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Score bar-line finders on the corpus's test lines (see corpus.py).

    uv run experiments/barlines/harness.py <corpus-dir> classical
    uv run experiments/barlines/harness.py <corpus-dir> table

Every method gets the same input, a straightened staff line with its staff
position known, and returns bar lines as x in the crop (pixels, at the
staff's middle). A predicted bar line is found if it lies within the
labeler's tolerance (0.6% of the page width) of a true one, matched one to
one; otherwise false. True ones left unmatched are missed.

Each method writes <corpus>/results/<method>.json:
  {"method", "train_s", "infer_s", "lines": {id: [x, ...]}, "notes"}
`classical` runs detect.py's own clef / music start and bar-line search on
the crops; `table` prints every method's scores.
"""

import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))


def load(corpus: Path) -> dict:
    return json.loads((corpus / "corpus.json").read_text())


def staff_of(line: dict) -> dict:
    """The line's staff in detect.py's terms (band coordinates)."""
    top, gap = line["staff_top"], line["space"]
    lines = [int(round(top + i * gap)) for i in range(5)]
    return {"top": lines[0], "bottom": lines[-1], "gap": gap, "lines": lines}


def match(pred: list[float], true: list[float], tol: float) -> tuple[int, int, int]:
    """(found, false, missed), greedy one-to-one by distance."""
    pairs = sorted((abs(p - t), i, j) for i, p in enumerate(pred) for j, t in enumerate(true) if abs(p - t) <= tol)
    used_p, used_t = set(), set()
    for _, i, j in pairs:
        if i not in used_p and j not in used_t:
            used_p.add(i)
            used_t.add(j)
    return len(used_t), len(pred) - len(used_p), len(true) - len(used_t)


# The labeler's bar-width hints (static/app.js, oddBars): a bar over 1.8x or
# under 0.4x its line's typical width (median, the line's first bar left
# out), or music after the last bar line longer than half a typical bar.
ODD_WIDE, ODD_NARROW, ODD_TAIL = 1.8, 0.4, 0.5


def flagged_bars(pred: list[float], width: float) -> list[tuple[float, float]]:
    """Intervals (x from, x to) the hints would outline, given the bar lines
    a method proposed on a line of this width."""
    xs = sorted(pred)
    if len(xs) < 4:
        return []
    bars = list(zip(xs, xs[1:]))
    med = float(np.median([b - a for a, b in bars]))
    out = [(a, b) for a, b in bars if b - a > ODD_WIDE * med or b - a < ODD_NARROW * med]
    if width - xs[-1] > ODD_TAIL * med:
        out.append((xs[-1], width))
    return out


def hinted(pred: list[float], true: list[float], width: float, tol: float) -> tuple[int, int]:
    """Of a method's errors on one line, how many the width hints point at:
    (missed bar lines inside a flagged bar, false ones at a flagged bar's edge)."""
    flags = flagged_bars(pred, width)
    missed = [t for t in true if not any(abs(p - t) <= tol for p in pred)]
    false = [p for p in pred if not any(abs(p - t) <= tol for t in true)]
    m = sum(any(a + tol < t < b - tol for a, b in flags) for t in missed)
    f = sum(any(abs(p - a) < 1 or abs(p - b) < 1 for a, b in flags) for p in false)
    return m, f


def score(corpus: Path, result: dict) -> dict:
    c = load(corpus)
    out = {"found": 0, "false": 0, "missed": 0, "by_source": {}}
    for line in c["lines"]:
        if line["split"] != "test":
            continue
        pred = result["lines"].get(line["id"], [])
        tol = c["tolerance_frac"] * line["page_w"]
        true = [b["x"] for b in line["bars"]]
        f, fp, m = match(pred, true, tol)
        hm, hf = hinted(pred, true, line["width"], tol)
        out["hinted"] = out.get("hinted", 0) + hm + hf
        for d in (out, out["by_source"].setdefault(line["source"], {"found": 0, "false": 0, "missed": 0})):
            d["found"] += f
            d["false"] += fp
            d["missed"] += m
    t = out["found"] + out["missed"]
    out["recall"] = out["found"] / t if t else 0.0
    p = out["found"] + out["false"]
    out["precision"] = out["found"] / p if p else 0.0
    out["f1"] = 2 * out["recall"] * out["precision"] / (out["recall"] + out["precision"]) if p and t else 0.0
    return out


def classical(corpus: Path):
    import detect

    c = load(corpus)
    preds, t0 = {}, time.perf_counter()
    test = [l for l in c["lines"] if l["split"] == "test"]
    for line in test:
        g = np.asarray(Image.open(corpus / line["file"]).convert("L"), dtype=np.float32)
        st = staff_of(line)
        # blank paper either side, as on a page: the slanted search looks
        # past the ends and counts rows off the image as empty
        pad = int(line["space"] * 4)
        g = np.pad(g, ((0, 0), (pad, pad)), constant_values=230)
        w = g.shape[1]
        _, start, _ = detect.music_start(g, st, pad, w - pad)
        bars = detect.find_barlines(g, st, pad, w - pad + int(line["space"]), skip_to=start)
        preds[line["id"]] = [(b["x0"] + b["x1"]) / 2 - pad for b in bars]
    dt = time.perf_counter() - t0
    write(corpus, {"method": "classical", "train_s": 0.0, "infer_s": dt / len(test), "lines": preds,
                   "notes": "detect.py: music_start + find_barlines on the crop; no training"})


def write(corpus: Path, result: dict):
    (corpus / "results").mkdir(exist_ok=True)
    (corpus / "results" / f"{result['method']}.json").write_text(json.dumps(result, indent=1))
    s = score(corpus, result)
    print(f"{result['method']}: found {s['found']}, false {s['false']}, missed {s['missed']} "
          f"(recall {s['recall']:.1%}, precision {s['precision']:.1%}, F1 {s['f1']:.3f}); "
          f"train {result['train_s']:.0f} s, {result['infer_s'] * 1000:.0f} ms per line")


def table(corpus: Path):
    rows = []
    for f in sorted((corpus / "results").glob("*.json")):
        r = json.loads(f.read_text())
        rows.append((r, score(corpus, r)))
    rows.sort(key=lambda rs: (rs[1]["false"] + rs[1]["missed"] - rs[1].get("hinted", 0), -rs[1]["f1"]))
    print("| method | found | false | missed | recall | precision | F1 | errors | flagged by width hints | silent errors | train | per line |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for r, s in rows:
        err = s["false"] + s["missed"]
        print(f"| {r['method']} | {s['found']} | {s['false']} | {s['missed']} | {s['recall']:.1%} | "
              f"{s['precision']:.1%} | {s['f1']:.3f} | {err} | {s.get('hinted', 0)} | {err - s.get('hinted', 0)} | "
              f"{r['train_s'] / 60:.1f} min | {r['infer_s'] * 1000:.0f} ms |")


if __name__ == "__main__":
    corpus, what = Path(sys.argv[1]), sys.argv[2]
    {"classical": classical, "table": table}[what](corpus)
