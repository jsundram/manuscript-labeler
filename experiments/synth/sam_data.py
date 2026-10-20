# /// script
# requires-python = ">=3.11"
# dependencies = ["opencv-python-headless==4.10.0.84", "numpy"]
# ///
"""Training examples for Segment Anything from the classical map and segmenter, symbol by symbol: only symbols the
classical pass got right with some confidence, so a staff needn't be clean to give examples.

Windows are overlapping pairs of bars (1-2, 2-3, ...), padded half a space; each symbol lying wholly inside a window
gives an example there: its kind, a prompt (a point for a head or a stem, a box for anything else) and its mask.
Kept: filled heads with strong evidence and a head of plausible size; stems over 1.8 spaces; beams; bar lines with their
dots; and the cut glyphs curate.py kept or moved (rests, flags, accidentals, slurs, trills, tuplet numbers, dots).

With --strict, only symbols in bars the classical pass got all but perfect (good_bars).

    uv run experiments/synth/sam_data.py --maps DIR --glyphs GLYPHS/berlin --out DIR KEY [...] [--strict]

Writes OUT/<key>_w<i>.npz: image (the window, grey), kinds, prompts (x0 y0 x1 y1; a point repeats itself), masks.
"""
import argparse
import json
from pathlib import Path

import cv2
import numpy as np

import align
import segment

POINT = ("head", "stem")


def windows(m: dict, w: int, ss: float) -> list[tuple[int, int]]:
    xs = [(b["x0"], b["x1"]) for b in m["bars"]]
    pairs = [(xs[i][0], xs[i + 1][1]) for i in range(len(xs) - 1)] or xs
    return [(max(0, int(a - 0.5 * ss)), min(w, int(b + 0.5 * ss))) for a, b in pairs]


def good_bars(m: dict, g: np.ndarray, seg: dict, unsorted: float = 0.02) -> list[tuple[int, int]]:
    """The spans of the bars the classical pass got all but perfect: every note read with evidence, on its own line or
    space and with a head of its own; every rest found; and at most `unsorted` of the bar's ink left unsorted (staff
    lines, specks and the staff's opening aside). A quarter of Berlin's bars. (Glyphs curate.py threw out are dropped
    one by one in examples(): most bars have one.)"""
    ss = m["ss"]
    lab = seg["lab"]
    ink = align.ink_map(g, ss)[0] > 0.4
    n, cl, st, _ = cv2.connectedComponentsWithStats(ink.astype(np.uint8), 8)
    big = np.isin(cl, [i for i in range(1, n) if st[i][4] >= 0.2 * ss * ss])
    on_lines = np.zeros_like(ink)
    for r in m["lines"]:
        on_lines[max(0, r - 2):r + 3] = True
    margin = np.isin(lab, [c for s in seg["symbols"] if s["kind"] in ("margin", "start") for c in s["comps"]])
    counted = ink & big & ~margin & ~on_lines
    sorted_ = (seg["taken"] > 0) | np.isin(lab, [c for s in seg["symbols"] if s["kind"] not in ("other", "dot-mark")
                                                for c in s["comps"]])
    good = []
    for b in m["bars"]:
        notes = [n for n in b["symbols"] if not n.get("rest")]
        if any(n.get("outside") or n["evidence"] < 0.6 or n["grace"]
               or abs(n["y"] - align.height(n["step"], b["clef"], ss, m["lines"][0])) > 0.3 * ss for n in notes):
            continue
        if any(not n.get("found") for n in b["symbols"] if n.get("rest")):
            continue
        if any(abs(p["x"] - q["x"]) < 0.4 * ss and abs(p["y"] - q["y"]) < 0.4 * ss
               for i, p in enumerate(notes) for q in notes[i + 1:]):
            continue
        x0, x1 = int(b["x0"]), int(b["x1"])
        c = counted[:, x0:x1]
        if c.sum() and (c & ~sorted_[:, x0:x1]).sum() / c.sum() > unsorted:
            continue
        good.append((b["x0"], b["x1"]))
    return good


def examples(key: str, m: dict, g: np.ndarray, curated: dict, strict: bool = False) -> list[tuple[str, list[int], np.ndarray]]:
    """(kind, prompt, mask over the whole staff) for each confident symbol (in good_bars, if `strict`)."""
    ss = m["ss"]
    seg = segment.segment(key, m, g)
    lab = seg["lab"]
    ink = align.ink_map(g, ss)[0] > 0.4
    out = []
    notes = [n for b in m["bars"] for n in b["symbols"] if not n.get("rest") and not n.get("outside")]
    stem_key = key.replace("/", "_")
    for n in notes:
        head = None
        if n["kind"] not in align.HOLLOW and n["evidence"] >= 0.5 and not n["grace"]:
            hb = align.head_blob(ink, n["x"], n["y"], ss)
            if hb is not None:
                msk, x0, y0 = hb
                area = msk.sum() / (ss * ss)
                if 0.25 <= area <= 1.6:
                    head = np.zeros_like(ink)
                    head[y0:y0 + msk.shape[0], x0:x0 + msk.shape[1]] = msk
                    out.append(("head", [n["x"], n["y"], n["x"], n["y"]], head))
        st = n.get("stem")
        if st and 1.8 <= st["length"] <= 5.5:
            line = np.zeros(ink.shape, np.uint8)
            cv2.line(line, (st["x0"], n["y"]), (st["x1"], st["end"]), 1, max(3, int(0.32 * ss)))
            stem = (line > 0) & ink
            if head is not None:
                stem &= ~(cv2.dilate(head.astype(np.uint8), np.ones((3, 3), np.uint8)) > 0)
            if stem.sum() > 1.5 * ss:
                mid = ((st["x0"] + st["x1"]) // 2, (n["y"] + st["end"]) // 2)
                out.append(("stem", [mid[0], mid[1], mid[0], mid[1]], stem))
    for s in seg["symbols"]:
        k = s["kind"]
        if k in ("margin", "other", "dot-mark", "start"):
            continue
        if not (k.startswith("barline") or k == "beam"):
            _, x0, y0 = segment.cut(g, lab, s)
            c = curated.get(f"{k}/{stem_key}_{x0}_{y0}.png")
            if c is None or c["verdict"] == "out":
                continue
            k = c["kind"]
        mask = np.isin(lab, s["comps"])
        if mask.sum() < 4:
            continue
        x0, y0, x1, y1 = s["box"]
        out.append((k.split("-")[0] if k.startswith("barline") else k, [x0, y0, x1, y1], mask))
    if strict:  # a symbol counts if its prompt's middle is in a good bar
        good = good_bars(m, g, seg)
        out = [e for e in out if any(a <= (e[1][0] + e[1][2]) / 2 < b for a, b in good)]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("keys", nargs="+")
    ap.add_argument("--data", type=Path, default=align.ZEUS / "dataL2")
    ap.add_argument("--maps", type=Path, required=True)
    ap.add_argument("--glyphs", type=Path, required=True, help="GLYPHS/<hand>, with curate.py's curated.json")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--strict", action="store_true", help="only the bars the classical pass got all but perfect")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    curated = json.loads((a.glyphs / "curated.json").read_text())
    tally = {}
    nwin = 0
    for key in a.keys:
        stem_key = key.replace("/", "_")
        m = json.loads((a.maps / f"{stem_key}.json").read_text())
        g = cv2.imread(str(a.data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
        h, w = g.shape
        ex = examples(key, m, g, curated, a.strict)
        for i, (x0, x1) in enumerate(windows(m, w, m["ss"])):
            kinds, prompts, masks = [], [], []
            for k, (px0, py0, px1, py1), mask in ex:
                if px0 >= x0 and px1 < x1:
                    ys, xs = np.nonzero(mask)
                    if len(xs) and xs.min() >= x0 and xs.max() < x1:
                        kinds.append(k)
                        prompts.append([px0 - x0, py0, px1 - x0, py1])
                        masks.append(mask[:, x0:x1])
            if not kinds:
                continue
            np.savez_compressed(a.out / f"{stem_key}_w{i}.npz", image=g[:, x0:x1], kinds=np.array(kinds),
                                prompts=np.array(prompts, np.int32), masks=np.packbits(np.stack(masks), axis=-1),
                                width=x1 - x0)
            nwin += 1
            for k in kinds:
                tally[k] = tally.get(k, 0) + 1
    print(nwin, "windows", json.dumps(dict(sorted(tally.items(), key=lambda kv: -kv[1]))))


if __name__ == "__main__":
    main()
