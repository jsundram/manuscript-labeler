# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless==4.10.0.84", "numpy", "lxml", "pillow",
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""Philhar's lines (philhar_lines.py) drawn two ways, for the hand-or-music test: the same staves, the same music,
staff length and staff space, only the drawing differs.

- copyist: copyist.draw in a hand (the hands in gen.py's proportions, each given music as dense as its own staves;
  a line too dense or too sparse for every copyist goes to the generic hand);
- plain: Verovio's engraving of the same staff in a printed font (Leipzig or Bravura), black on white, staff lines
  grey: no redrawing, slant, warp, paper, clefs or stray marks.

A paired line is drawn at its manuscript staff's length, an unpaired one at its hand's. A row is kept only if both
drawings succeed and fit the reader, so the two sets hold the same staves. With fewer lines than --rows, lines are
drawn again (another seed: another staff space, length and font); with more, a sample is drawn.

    uv run experiments/synth/philhar_render.py LINES_DIR OUT_COPYIST OUT_PLAIN [--rows 10790] [--jobs 6] [--seed 7]

Writes each OUT/P/<row>.jpg and .lmx, OUT/samples.P.txt, and OUT/rows.json (each row's line and hand).
"""
import argparse
import json
import random
import sys
from collections import Counter
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import cv2

sys.path.insert(0, str(Path(__file__).parent))
import copyist  # noqa: E402
from gen import DENSITY, HANDS, MAX_ASPECT, events  # noqa: E402

PRINTED = ("Leipzig", "Bravura")


def pick_hand(lmx: str, rng: random.Random) -> str:
    n = events(lmx)
    fits = [h for h in HANDS if h == "generic" or DENSITY[h][0] <= n <= DENSITY[h][1]]
    return rng.choice(fits)  # HANDS repeats each hand by its share


def plain(lmx: str, hand: str, seed: int, width: float | None):
    """The staff copyist.draw would make for this seed, engraved and nothing more."""
    p = copyist.sample(copyist.HANDS[hand], random.Random(seed))  # draw()'s first draw: the same staff space, length
    xml = copyist.lmx_to_musicxml(lmx)
    svg = copyist.engrave(xml, PRINTED[seed % 2], width or p["width"])
    copyist.check(svg, lmx, xml)
    return copyist.plain(svg, p["ss"])


def one(job):
    row, line, seed, hand = job
    lmx = Path(line["lmx"]).read_text().strip()
    width = None
    if line.get("jpg"):
        h, w = cv2.imread(line["jpg"], cv2.IMREAD_GRAYSCALE).shape
        width = w / h * 9 - 2  # gen.py --real-width
    try:
        a = copyist.draw(lmx, hand, seed=seed, width=width)
        b = plain(lmx, hand, seed, width)
    except ValueError as e:
        return row, None, None, "skipped: " + str(e).split(",")[0][:40]
    except Exception as e:
        return row, None, None, f"failed: {type(e).__name__}: {str(e)[:60]}"
    if max(a.shape[1] / a.shape[0], b.shape[1] / b.shape[0]) > MAX_ASPECT:
        return row, None, None, "skipped: longer than the reader takes"
    return row, a, b, "ok"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("lines", type=Path)
    ap.add_argument("out_copyist", type=Path)
    ap.add_argument("out_plain", type=Path)
    ap.add_argument("--rows", type=int, default=10790)  # SF1's synthetic staves (dataS3)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    lines = json.loads((a.lines / "lines.json").read_text())
    rng = random.Random(a.seed)
    # more rows than lines are wanted, and some drawings fail: deal the lines out in shuffled rounds, a few spare
    order = []
    while len(order) < int(a.rows * 1.04):
        deck = list(range(len(lines)))
        rng.shuffle(deck)
        order += deck
    jobs = []
    for i, li in enumerate(order[: int(a.rows * 1.04)]):
        lmx = Path(lines[li]["lmx"]).read_text()
        jobs.append((f"P/r{i:05d}", lines[li], a.seed * 1_000_003 + i * 31, pick_hand(lmx, rng)))
    for out in (a.out_copyist, a.out_plain):
        (out / "P").mkdir(parents=True, exist_ok=True)
    tally, kept, rows = Counter(), [], {}
    by_row = {j[0]: j for j in jobs}
    with ProcessPoolExecutor(a.jobs) as ex:
        for n, (row, img_c, img_p, res) in enumerate(ex.map(one, jobs, chunksize=8)):
            tally[res] += 1
            if res == "ok" and len(kept) < a.rows:
                _, line, seed, hand = by_row[row]
                lmx = Path(line["lmx"]).read_text().strip() + "\n"
                for out, img in ((a.out_copyist, img_c), (a.out_plain, img_p)):
                    cv2.imwrite(str(out / f"{row}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    (out / f"{row}.lmx").write_text(lmx)
                kept.append(row)
                rows[row] = {"line": line["id"], "kind": line["kind"], "hand": hand, "seed": seed}
                tally[line["kind"]] += 1
                tally[hand] += 1
            if n % 1000 == 0:
                print(n, dict(tally.most_common(8)), flush=True)
    for out in (a.out_copyist, a.out_plain):
        (out / "samples.P.txt").write_text("\n".join(kept) + "\n")
        (out / "rows.json").write_text(json.dumps(rows, indent=0))
    print(f"{len(kept)} rows of {len(jobs)} drawn; {len({r['line'] for r in rows.values()})} distinct lines",
          dict(tally.most_common()), flush=True)


if __name__ == "__main__":
    main()
