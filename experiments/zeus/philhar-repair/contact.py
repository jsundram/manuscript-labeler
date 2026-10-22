# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Contact sheets of staves autopair.py --philhar paired, to check by eye:
each staff as dataset.py cuts it, under it the bars it was paired with
(quartet, movement, Philhar's bar numbers), the clef chosen, the measures
read against detection's bar boxes, and Philhar's first and last bar as
text (pitch:duration; R a bar rest).

    uv run experiments/zeus/philhar-repair/contact.py RESULTS.json OUT_PREFIX [--part va vc] [--only p3-4 ...]
        [--failed] [--per 12] [--every 3]

RESULTS is autopair.py's results (or one with the same "kept" records);
--failed draws its "not kept" staves with their reasons instead; --every N
takes every Nth staff (a sample); --list keeps only a staff list's staves,
--not-in only those not in another list. Writes OUT_PREFIX-01.png, -02.png ...

--lily: Philhar's lilypond/ folder (default boccherini-quartet-data's; the
works experiments/philhar-mss fetched are in philhar-site/lily). With
--print-bars, the encoding is a print's reading (print-omr/encode.py), its
measures' text in place of Philhar's bars. --labels DIR also writes the
label each staff has in that staff set (DIR/<source>/<staff>.lmx), bar by
bar, as compare.py reads it in its own clef, under the set's own image.
"""

import argparse
import io
import json
import os
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw

ZEUS = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ZEUS))
import compare  # noqa: E402

EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"
LILY = Path.home() / "Dropbox/Code/boccherini-quartet-data/lilypond"
W = 1600
_bars = {}


PRINT = None  # --print-bars: {part: {movement: [measure]}}


def philhar_bar(q: str, mvt: str, part: str, bar) -> str:
    if PRINT is not None:   # (movement, measure) of the print's reading: q is the movement, mvt the measure
        m = PRINT[part][q][int(mvt) - 1]
        return ("" if m["use"] else "[not agreed] ") + m["text"]
    if (q, mvt, part) not in _bars:
        r = subprocess.run(["uv", "run", str(ZEUS / "philhar.py"), str(EDITION), str(LILY), q, part, mvt, "--json"],
                           capture_output=True, text=True, check=True,
                           env={k: v for k, v in os.environ.items() if k != "UV_PYTHON_INSTALL_DIR"})
        _bars[(q, mvt, part)] = json.loads(r.stdout)["bars"]
    evs = _bars[(q, mvt, part)].get(str(bar), [])
    return " ".join(map(compare.text, compare.encoded(evs)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("out")
    ap.add_argument("--failed", action="store_true")
    ap.add_argument("--part", nargs="*")
    ap.add_argument("--only", nargs="*")
    ap.add_argument("--per", type=int, default=12)
    ap.add_argument("--every", type=int, default=1)
    ap.add_argument("--list", type=Path, help="only the staves in this staff list (samples.<source>.txt)")
    ap.add_argument("--not-in", type=Path, help="only the staves not in this staff list (the old set's)")
    ap.add_argument("--lily", type=Path, help="Philhar's lilypond/ folder (default boccherini-quartet-data's)")
    ap.add_argument("--print-bars", type=Path, help="the encoding is this print reading (print-omr/encode.py)")
    ap.add_argument("--labels", type=Path, help="a staff set: write each staff's label from DIR/<source>/<staff>.lmx")
    a = ap.parse_args()
    global LILY, PRINT
    if a.lily:
        LILY = a.lily
    if a.print_bars:
        PRINT = json.loads(a.print_bars.read_text())["parts"]
    res = json.loads(a.results.read_text())
    auto = json.loads((ZEUS / "auto" / f"{res['source']}.json").read_text())
    pdf = Path(auto["pdf"])
    systems = {f"p{n}-{k}": s for n, p in auto["pages"].items()
               for k, s in enumerate(sorted(p["systems"], key=lambda s: s["top"]))}
    rows = res["not kept"] if a.failed else res["kept"]
    rows = [r for r in rows if (not a.part or r["part"] in a.part) and (not a.only or r["staff"] in a.only)]
    if a.list:
        keep = {l.split("/")[-1] for l in a.list.read_text().split()}
        rows = [r for r in rows if r["staff"] in keep]
    if a.not_in and a.not_in.exists():
        old = {l.split("/")[-1] for l in a.not_in.read_text().split()}
        rows = [r for r in rows if r["staff"] not in old]
    rows = rows[::a.every]
    page = None
    for start in range(0, len(rows), a.per):
        tiles = []
        for r in rows[start:start + a.per]:
            n = int(r["staff"][1:].split("-")[0])
            if page is None or page[0] != n:
                page = (n, compare.page_image(pdf, n))
            jpg = a.labels / res["source"] / f"{r['staff']}.jpg" if a.labels else None
            if jpg is not None and jpg.exists():   # the staff set's own image (cut, if it was cut)
                im = Image.open(jpg).convert("L")
            else:
                im = Image.open(io.BytesIO(compare.staff_crop(page[1], r.get("system") or systems[r["staff"]]))).convert("L")
            im = im.resize((W, max(1, int(im.height * W / im.width))))
            head = f"{res['source']} {r['staff']} {r['part']}"
            lines = []
            if r.get("bars") and PRINT is not None:   # bars are (movement, measure)
                r = {**r, "bars": [[b[0], str(b[1]), ""] for b in r["bars"]]}
            if r.get("bars"):
                b0, b1 = r["bars"][0], r["bars"][-1]
                head += f"  {b0[0]} {b0[1]} {b0[2]} .. {b1[1]} {b1[2]} ({len(r['bars'])} bars"
                if "measures" in r:
                    head += f", {r['measures']} read, {r['bar_boxes']} boxes)  clef {r['clef']}  read {r.get('read_clefs')}"
                    head += "" if r["plain"] else "  NOT PLAIN"
                else:
                    head += ")"
                lines.append("first: " + philhar_bar(b0[0], b0[1], r["part"], b0[2])[:170])
                lines.append("last:  " + philhar_bar(b1[0], b1[1], r["part"], b1[2])[:170])
            if a.labels and (a.labels / res["source"] / f"{r['staff']}.lmx").exists():
                ms, clefs = compare.parse((a.labels / res["source"] / f"{r['staff']}.lmx").read_text())
                txt = " | ".join(" ".join(compare.text(compare.zeus_event(e, e["zclef"])) for e in m) for m in ms)
                txt = f"label ({'/'.join(dict.fromkeys(clefs))}): " + txt
                lines += [txt[i:i + 190] for i in range(0, min(len(txt), 570), 190)]
            if a.failed:
                lines.append("why: " + "; ".join(r["why"])[:180])
            lines.insert(0, head)
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
