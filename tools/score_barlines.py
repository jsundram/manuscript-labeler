# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Score detect.py's bar lines against an editor's reviewed labels.

    uv run tools/score_barlines.py <pdf> [pages...]

Reads the PDF's labels file (labels.labels_path) and treats the bar lines on its
reviewed pages (or the pages given) as the truth. For each page: how many
real bar lines detection finds, how many it proposes that aren't real, and
how many it misses. Use it before and after changing detect.py.
"""

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import detect  # noqa: E402
from labels import labels_path  # noqa: E402
from server import JPEG_QUALITY, RENDER_PX  # noqa: E402

TOLERANCE = 0.006  # page widths: a proposal this close to a real bar line counts


def mid(b):
    return (b["x0"] + b["x1"]) / 2


def render(pdf: Path, page: int, tmp: Path) -> Image.Image:
    # named by source too: several sources' pages share a temporary folder
    base = tmp / f"{pdf.stem}-p{page}"
    subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", str(RENDER_PX),
                    "-jpeg", "-jpegopt", f"quality={JPEG_QUALITY}", "-singlefile", str(pdf), str(base)],
                   check=True)
    img = Image.open(base.with_suffix(".jpg"))
    img.load()  # read it now, not lazily after the file may be gone
    return img


def truth_systems(page: dict) -> list[dict]:
    """A labels-file page as [{top, bottom, xs}]: counted staves and the
    middles of their bar lines. Also accepts the frozen test fixture, whose
    bar lines are already plain x values."""
    out = []
    for s in page["systems"]:
        if s.get("role") == "cue":
            continue
        xs = [b if isinstance(b, (int, float)) else mid(b) for b in s["barlines"]]
        out.append({"top": s["top"], "bottom": s["bottom"], "xs": xs})
    return out


def score_page(truth: list[dict], detected: list[dict]) -> tuple[int, int, int]:
    """(found, false, missed) for one page: truth from truth_systems, detected
    from detect.detect_page."""
    found = false = missed = 0
    for s in truth:
        cy = (s["top"] + s["bottom"]) / 2
        near = sorted((d for d in detected if abs((d["top"] + d["bottom"]) / 2 - cy) < 0.02),
                      key=lambda d: abs((d["top"] + d["bottom"]) / 2 - cy))
        dx = [mid(b) for b in near[0]["barlines"]] if near else []
        tx = s["xs"]
        found += sum(any(abs(x - t) < TOLERANCE for t in tx) for x in dx)
        false += sum(not any(abs(x - t) < TOLERANCE for t in tx) for x in dx)
        missed += sum(not any(abs(x - t) < TOLERANCE for x in dx) for t in tx)
    return found, false, missed


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    pdf = Path(sys.argv[1])
    labels = json.loads(labels_path(pdf).read_text())
    pages = [int(p) for p in sys.argv[2:]] or sorted(
        int(n) for n, p in labels["pages"].items() if p["status"] == "reviewed" and p["kind"] == "music")
    totals = [0, 0, 0]
    with tempfile.TemporaryDirectory() as tmp:
        for n in pages:
            f, fp, m = score_page(truth_systems(labels["pages"][str(n)]), detect.detect_page(render(pdf, n, Path(tmp))))
            print(f"page {n}: {f + m} bar lines, found {f}, false {fp}, missed {m}")
            totals = [a + b for a, b in zip(totals, (f, fp, m))]
    f, fp, m = totals
    print(f"all: {f + m} bar lines, found {f} ({f / max(1, f + m):.0%}), false {fp}, missed {m}")


if __name__ == "__main__":
    main()
