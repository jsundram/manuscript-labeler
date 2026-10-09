# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scikit-learn"]
# ///
"""Learned crop edges (crops.py) against today's rule (detect.crop_margins),
scored on the editor's reviewed crops, leaving out one source at a time.

    uv run experiments/crops/evaluate.py <edition-repo> [--older A,B ...]

Every staff on a reviewed page whose crop the editor set, each side:
the labeler's model trained on every other source (as crops.train would,
older sources as in the edition's sources/labeler.json unless --older
names them) picks an edge, scored against the editor's: within half a
staff space, too tight (more than half a space inside it) or too wide.
By source, over all, and on the held-out test pages
(experiments/barlines/test_pages.json), the newest crops. Pages come from
the labeler's render cache (the server's key), else pdftoppm.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))
import crops  # noqa: E402
import detect  # noqa: E402

RENDER_PX, JPEG_QUALITY = 2800, 90  # server.py's
CACHE = Path.home() / ".cache" / "manuscript-labeler" / "renders"


def gray(pdf: Path, page: int, tmp: Path) -> np.ndarray:
    st = pdf.stat()
    key = hashlib.sha1(f"{pdf}:{st.st_size}:{st.st_mtime_ns}:{RENDER_PX}:{JPEG_QUALITY}".encode()).hexdigest()[:16]
    p = CACHE / key / f"p{page:03d}.jpg"
    if not p.exists():
        p = tmp / f"{pdf.stem}-{page}.jpg"
        if not p.exists():
            subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", str(RENDER_PX), "-jpeg",
                            "-jpegopt", f"quality={JPEG_QUALITY}", "-singlefile", str(pdf), str(p.with_suffix(""))],
                           check=True, capture_output=True)
    return detect._gray(Image.open(p))


def line(name: str, ex: list[dict], pick) -> str:
    out = []
    for side in ("above", "below"):
        e = np.array([pick(x) - x["truth"] for x in ex if x["side"] == side])
        if len(e):
            out.append(f"{side} {np.mean(np.abs(e) <= 0.5):.0%} (tight {np.mean(e < -0.5):.0%}, wide {np.mean(e > 0.5):.0%})")
    return f"  {name:8} " + "   ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--older", help="comma-separated sources whose accepted crops aren't learned from")
    a = ap.parse_args()
    older = set(a.older.split(",")) if a.older else crops.older_sources(a.edition)
    test = json.loads((ROOT / "experiments" / "barlines" / "test_pages.json").read_text())["pages"]
    ex = []
    with tempfile.TemporaryDirectory() as tmp:
        for pdf, n, p in crops.reviewed_pages(a.edition):
            for e in crops.examples(gray(pdf, n, Path(tmp)), p, pdf.stem in older):
                ex.append({**e, "source": pdf.stem, "test": n in test.get(pdf.stem, [])})
    print(f"{len(ex)} sides; older sources: {', '.join(sorted(older)) or 'none'}")
    for held in sorted({e["source"] for e in ex}):
        model = crops.fit([e for e in ex if e["source"] != held])
        for e in ex:
            if e["source"] == held:
                e["learned"] = crops.choose(model, e["cands"], e["X"])
    groups = [(s, [e for e in ex if e["source"] == s]) for s in sorted({e["source"] for e in ex})]
    groups += [("all", ex), ("test pages", [e for e in ex if e["test"]])]
    print("within half a staff space of the editor's edge (too tight, too wide)")
    for name, g in groups:
        print(f"{name} ({len(g) // 2} staves)")
        print(line("today", g, lambda x: x["today"]))
        print(line("learned", g, lambda x: x["learned"]))


if __name__ == "__main__":
    main()
