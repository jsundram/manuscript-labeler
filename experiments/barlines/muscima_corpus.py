# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""MUSCIMA++ as a bar-line corpus, for pretraining the line detector.

    uv run experiments/barlines/muscima_corpus.py <muscima-dir> <out-dir>

<muscima-dir> holds MUSCIMA++ v2.0's annotations (v2.0/data/annotations/
*.xml; github.com/OMR-Research/muscima-pp, CC BY-NC-SA 4.0) and the 140
CVC-MUSCIMA images they annotate (fulls/*.png; the "CVC_MUSCIMA_PP_
Annotated-Images" set): 20 pages each rewritten by 50 musicians, modern
pens on printed staff paper, scanned to black and white.

Each annotated staff becomes a line in corpus.py's format (corpus.json,
lines/*.png): the page's full width, 3 staff spaces above and below; its
bar lines (barline, barlineHeavy) and its clef-key-time region from the
staff's left end to the right edge of its opening clef, key and time
signature (corpus.py --paper's "music_start"); and the staff's right end,
where its printed lines stop ("staff_right"). A system's opening line,
annotated as a bar line, is left out, as the editor's labels leave it.
The images are white ink on black (checked): drawn as ink (70) on paper
(210) with a little
blur and noise, nearer the manuscripts' grey scans. All lines are
"train"; tiles.py takes a tenth for validation.
"""

import json
import random
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

MARGIN = 3.0
OPENING = {"gClef", "fClef", "cClef", "keySignature", "timeSignature", "timeSigCommon", "timeSigCutCommon"}
BARS = {"barline", "barlineHeavy"}
MUSIC = {"noteheadFull", "noteheadHalf", "noteheadWhole", "restQuarter", "restEighth", "restHalf", "restWhole",
         "rest16th", "multiMeasureRest"}


def nodes(xml: Path) -> list[dict]:
    out = []
    for n in ET.parse(xml).getroot().iter("Node"):
        g = {c.tag: c.text for c in n}
        out.append({"cls": g["ClassName"], "top": int(g["Top"]), "left": int(g["Left"]),
                    "bottom": int(g["Top"]) + int(g["Height"]), "right": int(g["Left"]) + int(g["Width"])})
    return out


def main():
    src, out = Path(sys.argv[1]), Path(sys.argv[2])
    (out / "lines").mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(0)
    lines = []
    for xml in sorted((src / "v2.0" / "data" / "annotations").glob("*.xml")):
        img_path = src / "fulls" / (xml.stem + ".png")
        if not img_path.exists():
            continue
        ink = np.asarray(Image.open(img_path).convert("1"), dtype=bool)
        page = np.where(ink, 70.0, 210.0)
        page = np.asarray(Image.fromarray(page.astype(np.uint8)).filter(ImageFilter.GaussianBlur(0.8)), dtype=np.float32)
        page = np.clip(page + rng.normal(0, 8, page.shape), 0, 255).astype(np.uint8)
        h, w = page.shape
        ns = nodes(xml)
        staves = sorted((n for n in ns if n["cls"] == "staff"), key=lambda n: n["top"])
        for k, st in enumerate(staves):
            space = (st["bottom"] - st["top"]) / 4
            over = lambda n: min(n["bottom"], st["bottom"]) - max(n["top"], st["top"]) > 0.5 * space
            # a system's opening line (at the staff's left end) is annotated as a bar
            # line; the editor's labels don't count it
            bars = sorted(x for x in ((n["left"] + n["right"]) / 2 for n in ns if n["cls"] in BARS and over(n))
                          if x > st["left"] + space)
            music = [n["left"] for n in ns if n["cls"] in MUSIC and over(n)]
            first = min(music + bars, default=st["right"])
            opening = [n["right"] for n in ns if n["cls"] in OPENING and over(n) and n["left"] < first]
            y0 = max(0, int(st["top"] - MARGIN * space))
            y1 = min(h, int(st["bottom"] + MARGIN * space) + 1)
            band = page[y0:y1]
            lid = f"{xml.stem.replace('CVC-MUSCIMA_', '').replace('_D-ideal', '')}-l{k + 1:02d}"
            Image.fromarray(band).save(out / "lines" / f"{lid}.png")
            line = {"id": lid, "source": "MUSCIMA++", "pdf": xml.stem, "page": 1, "part": None,
                    "file": f"lines/{lid}.png", "width": w, "height": y1 - y0, "space": space,
                    "staff_top": st["top"] - y0, "staff_bottom": st["bottom"] - y0, "page_w": w, "page_h": h,
                    "left": 0, "top_frac": st["top"] / h, "split": "train",
                    "bars": [{"x": x, "x0": x, "x1": x} for x in bars], "staff_left": st["left"],
                    "staff_right": st["right"]}
            if opening:
                line["music_start"] = max(opening)
            lines.append(line)
    (out / "corpus.json").write_text(json.dumps({"seed": 0, "tolerance_frac": 0.006, "lines": lines}, indent=1))
    print(f"{len(lines)} lines, {sum(len(l['bars']) for l in lines)} bar lines, "
          f"{sum('music_start' in l for l in lines)} with a clef-key-time region, from "
          f"{len({l['pdf'] for l in lines})} pages")


if __name__ == "__main__":
    main()
