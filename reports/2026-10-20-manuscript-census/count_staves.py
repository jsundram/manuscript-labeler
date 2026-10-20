# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Count music staves on every page of a PDF with the labeler's own staff
detection (detect.find_staves, then detect_page's empty-staff test).

    uv run count_staves.py out.jsonl file.pdf [file.pdf ...]

Appends one JSON line per page: {pdf, page, staves, ruled, gap, tops, inks}.
Pages already in out.jsonl are skipped, so it can be rerun.
"""
import json, os, subprocess, sys, tempfile, time
from pathlib import Path

sys.path.insert(0, str(Path.home() / "Dropbox/Code/manuscript-labeler"))
import detect  # noqa: E402
from PIL import Image  # noqa: E402

RENDER_PX = 2800


def npages(pdf):
    out = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True).stdout
    for line in out.splitlines():
        if line.startswith("Pages:"):
            return int(line.split()[1])
    return 0


def count_page(img):
    g = detect._gray(img)
    h, w = g.shape
    corners = detect.find_page_corners(img)
    ruled, tops, inks = 0, [], []
    for st in detect.find_staves(g):
        ruled += 1
        band, y0 = detect.straighten(g, st)
        local = {**st, "top": st["top"] - y0, "bottom": st["bottom"] - y0,
                 "lines": [y - y0 for y in st["lines"]]}
        paper = detect.paper_x(corners, (st["top"] + st["bottom"]) / 2 / h, w)
        left, right = detect.staff_extent(band, local, paper)
        ink = detect.inner_ink(band, local, left, right)
        inks.append(round(ink, 4))
        if ink < detect.EMPTY_INK:
            continue
        tops.append([round(st["top"] / h, 4), round(st["bottom"] / h, 4),
                     round(left / w, 3), round(right / w, 3)])
    gap = None
    return {"staves": len(tops), "ruled": ruled, "tops": tops, "inks": inks, "w": w, "h": h}


def main():
    out = Path(sys.argv[1])
    done = set()
    if out.exists():
        for line in out.open():
            r = json.loads(line)
            done.add((r["pdf"], r["page"]))
    tmp = Path(tempfile.mkdtemp(dir=os.environ.get("TMPDIR")))
    with out.open("a") as f:
        for pdf in sys.argv[2:]:
            n = npages(pdf)
            for p in range(1, n + 1):
                if (pdf, p) in done:
                    continue
                t = time.time()
                base = tmp / "r"
                subprocess.run(["pdftoppm", "-f", str(p), "-l", str(p), "-scale-to", str(RENDER_PX),
                                "-singlefile", str(pdf), str(base)], check=True, capture_output=True)
                img = Image.open(base.with_suffix(".ppm"))
                img.load()
                r = count_page(img)
                base.with_suffix(".ppm").unlink()
                f.write(json.dumps({"pdf": pdf, "page": p, **r, "sec": round(time.time() - t, 2)}) + "\n")
                f.flush()
            print(pdf, n, "pages", flush=True)


if __name__ == "__main__":
    main()
