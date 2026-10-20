# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Add the staves autopair kept to a bar-line corpus, as training lines:
detection's own bar lines, on staves whose reading paired with the
encoding bar for bar.

    uv run experiments/zeus/pseudo_lines.py <corpus-dir> results/autopair-<src>-any-count-<model>.json ...

<corpus-dir> is built by experiments/barlines/corpus.py --paper. Only a
kept staff with as many bar boxes as Zeus read measures is added (with
--any-count the two may differ, and then a bar line may be missing or
extra). A staff kept in more than one results file (the same source
detected two ways) is added once, from the first file that has it. The
staff's ends and music start are detection's too: they aren't checked.
Every added line is a training line ("pseudo": true); the PDF is the one
autodetect.py read (auto/<source>.json).

Then: experiments/barlines/tiles.py <corpus-dir>, and train as usual.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent.parent), str(HERE.parent / "barlines")]
import detect  # noqa: E402
from corpus import paper_band, render  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("corpus", type=Path)
    ap.add_argument("results", type=Path, nargs="+")
    a = ap.parse_args()
    c = json.loads((a.corpus / "corpus.json").read_text())
    if any(l.get("pseudo") for l in c["lines"]):
        sys.exit(f"{a.corpus} already has pseudo lines")
    sp = c.get("split")
    if not isinstance(sp, dict) or "test_pages" not in c:
        sys.exit(f"{a.corpus} records no test pages to keep out; rebuild it with corpus.py --paper")
    test = {(src, n) for src, n in c["test_pages"]}  # the corpus's reviewed test pages, by pdf stem

    staves: dict[tuple[str, int], dict[str, dict]] = {}  # (source, page) -> {staff: kept}
    for f in a.results:
        d = json.loads(f.read_text())
        for k in d["kept"]:
            if k["measures"] == k["bar_boxes"]:
                staves.setdefault((d["source"], k["page"]), {}).setdefault(k["staff"], k)
    print(f"{sum(len(v) for v in staves.values())} staves on {len(staves)} pages")

    added, skipped = [], 0
    with tempfile.TemporaryDirectory() as tmp:
        for (source, n), kept in sorted(staves.items()):
            pdf = json.loads((HERE / "auto" / f"{source}.json").read_text())["pdf"]
            if pdf is None:
                sys.exit(f"auto/{source}.json names no PDF; leave {source} out")
            pdf = Path(pdf)
            if (pdf.stem, n) in test or pdf.stem in sp["test_sources"]:  # never train on a test page
                skipped += len(kept)
                continue
            link = Path(tmp) / f"{source}.pdf"  # render names its file by the stem: no dots in it
            if not link.exists():
                link.symlink_to(pdf)
            g = render(link, n, Path(tmp))
            h, w = g.shape
            corners = detect.find_page_corners(Image.fromarray(g))
            for staff, k in sorted(kept.items()):
                s = k["system"]
                band, geo = paper_band(g, s, corners)
                lid = f"{source}-p{n:03d}-{staff.split('-')[1]}"
                Image.fromarray(band).save(a.corpus / "lines" / f"{lid}.png")
                bars = []
                for b in s["barlines"]:
                    x0, x1 = b["x0"] * w - geo["x_off"], b["x1"] * w - geo["x_off"]
                    bars.append({"x": (x0 + x1) / 2, "x0": x0, "x1": x1})
                line = {
                    "id": lid, "source": source, "pdf": str(pdf), "page": n, "part": k["part"],
                    "file": f"lines/{lid}.png", "width": band.shape[1], "height": band.shape[0],
                    "space": geo["space"], "staff_top": geo["staff_top"], "staff_bottom": geo["staff_bottom"],
                    "page_w": w, "page_h": h, "left": geo["x_off"], "top_frac": s["top"],
                    "bars": sorted(bars, key=lambda b: b["x"]), "split": "train", "pseudo": True,
                    "staff_left": s["left"] * w - geo["x_off"], "staff_right": s["right"] * w - geo["x_off"],
                }
                if s.get("start") is not None and s["start"] > s["left"]:
                    line["music_start"] = s["start"] * w - geo["x_off"]
                added.append(line)
            print(f"{source} p{n}: {len(kept)} lines", flush=True)
    c["lines"] += added
    c["pseudo"] = {"results": [str(f) for f in a.results], "lines": len(added)}
    (a.corpus / "corpus.json").write_text(json.dumps(c, indent=1))
    print(f"added {len(added)} lines, {sum(len(l['bars']) for l in added)} bar lines; "
          f"{skipped} on test pages left out")


if __name__ == "__main__":
    main()
