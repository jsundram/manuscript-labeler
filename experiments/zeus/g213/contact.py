# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Contact sheets of the staves autopair.py --musicxml kept (or didn't), to
check by eye: each staff as dataset.py cuts it, under it the bars it was
paired with (movement, the score's bar numbers), the clef chosen and the
encoding's, and the encoding's first and last bar as text.

    uv run experiments/zeus/g213/contact.py RESULTS.json SCORE.musicxml OUT_PREFIX [--failed] [--per 12]

Writes OUT_PREFIX-01.png, -02.png ... (--failed: the detected staves that
weren't kept, with nothing paired).
"""

import argparse
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ZEUS = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ZEUS), str(ZEUS / "ossq")]
import compare  # noqa: E402
import mxl  # noqa: E402

ROMAN = ["I", "II", "III", "IV", "V", "VI"]
W = 1600


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("score", type=Path)
    ap.add_argument("out")
    ap.add_argument("--failed", action="store_true")
    ap.add_argument("--per", type=int, default=12)
    ap.add_argument("--only", nargs="*", help="these staves (p3-4 ...)")
    a = ap.parse_args()
    res = json.loads(a.results.read_text())
    auto = json.loads((ZEUS / "auto" / f"{res['source']}.json").read_text())
    pdf = Path(auto["pdf"])
    mv = mxl.movements(a.score)
    rows = []
    if a.failed:
        kept = {k["staff"] for k in res["kept"]}
        for n, p in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
            for k, s in enumerate(sorted(p["systems"], key=lambda s: s["top"])):
                if f"p{n}-{k}" not in kept:
                    rows.append({"staff": f"p{n}-{k}", "part": s.get("part", p["part"]), "page": int(n), "system": s})
    else:
        rows = res["kept"]
    if a.only:
        rows = [r for r in rows if r["staff"] in a.only]
    pages = {}
    for start in range(0, len(rows), a.per):
        tiles = []
        for r in rows[start:start + a.per]:
            if r["page"] not in pages:
                pages = {r["page"]: compare.page_image(pdf, r["page"])}
            im = Image.open(io.BytesIO(compare.staff_crop(pages[r["page"]], r["system"]))).convert("L")
            im = im.resize((W, max(1, int(im.height * W / im.width))))
            lines = [f"{res['source']} {r['staff']} {r['part']}"]
            if "bars" in r:
                part = mv[r["part"]]
                b0, b1 = r["bars"][0], r["bars"][-1]
                m0, m1 = part[ROMAN.index(b0[0])][b0[1]], part[ROMAN.index(b1[0])][b1[1]]
                enc_clefs = sorted({part[ROMAN.index(b[0])][b[1]]["clef"] for b in r["bars"]})
                lines[0] += (f"  {b0[0]} {m0['number']}..{b1[0]} {m1['number']} ({len(r['bars'])} bars,"
                             f" {r['measures']} read, {r['bar_boxes']} boxes)  clef {r['clef']} / enc {enc_clefs}"
                             f"{'' if r['plain'] else '  NOT PLAIN'}")
                lines.append("first: " + " ".join(map(compare.text, m0["events"]))[:150])
                lines.append("last:  " + " ".join(map(compare.text, m1["events"]))[:150])
            tile = Image.new("L", (W, im.height + 16 * len(lines) + 6), 255)
            tile.paste(im, (0, 0))
            d = ImageDraw.Draw(tile)
            for i, t in enumerate(lines):
                d.text((4, im.height + 2 + 16 * i), t, fill=0)
            tiles.append(tile)
        sheet = Image.new("L", (W, sum(t.height + 8 for t in tiles)), 160)
        y = 0
        for t in tiles:
            sheet.paste(t, (0, y))
            y += t.height + 8
        out = Path(f"{a.out}-{start // a.per + 1:02d}.png")
        sheet.save(out)
        print(out)


if __name__ == "__main__":
    main()
