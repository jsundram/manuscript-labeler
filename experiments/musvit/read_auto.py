# /// script
# requires-python = ">=3.11"
# dependencies = ["modal", "numpy", "pillow"]
# ///
"""Read every staff detection found on a source (experiments/zeus/auto/<source>.json,
from autodetect.py) with a MuSViT reader, into the cache autopair.py reads, so
autopair.py pairs that source with the reader's readings instead of Zeus's.

    uv run experiments/musvit/read_auto.py --run C4-bocch-tf8-L --file best.pt SOURCE...

Staves are named, ordered and cut as autopair.py does (p<page>-<k>, k by
height on the page; compare.staff_crop, saved as JPEG at quality 95 as
dataset.py saves its training staves). The readings go to
experiments/zeus/answers/<source>-auto-musvit-<run>[-<file>].json, keyed by
staff and crop; then run autopair.py with --model .../musvit-<run>[-<file>]
(a path that needn't exist: every staff is cached, so Zeus isn't loaded).
"""

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parent / "zeus"
sys.path.insert(0, str(ZEUS))
import compare  # noqa: E402


EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"


def crops(source: str) -> dict[str, bytes]:
    """The source's detected staves, {autopair key: JPEG}. A labelled source's
    detections don't name the PDF: it is the edition's, as autopair.py finds it."""
    auto = json.loads((ZEUS / "auto" / f"{source}.json").read_text())
    pdf = Path(auto["pdf"]) if "pdf" in auto else next(EDITION.glob(f"sources/*/{source}.pdf"))
    out = {}
    for n, p in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
        g = None
        for k, s in enumerate(sorted(p["systems"], key=lambda s: s["top"])):
            g = compare.page_image(pdf, int(n)) if g is None else g
            png = compare.staff_crop(g, s)
            buf = io.BytesIO()
            Image.open(io.BytesIO(png)).convert("L").save(buf, "JPEG", quality=95)
            out[f"p{n}-{k}:{hashlib.sha1(png).hexdigest()[:10]}"] = buf.getvalue()
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--run", required=True)
    ap.add_argument("--file", default="reader.pt")
    ap.add_argument("--again", action="store_true", help="re-check sources already read (new detections)")
    a = ap.parse_args()
    name = f"musvit-{a.run}" + ("" if a.file == "reader.pt" else f"-{Path(a.file).stem}")
    import modal
    sys.path.insert(0, str(HERE))
    from modal_app import app, read
    with modal.enable_output(), app.run():
        for src in a.sources:
            cache_file = ZEUS / "answers" / f"{src}-auto-{name}.json"
            if cache_file.exists() and not a.again:  # written only once a source is read whole
                print(f"{src}: already read -> {cache_file.name}", flush=True)
                continue
            cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
            todo = {k: v for k, v in crops(src).items() if k not in cache}
            if todo:
                cache.update(read.remote(a.run, a.file, todo))
                cache_file.write_text(json.dumps(cache, indent=1, sort_keys=True))
            print(f"{src}: {len(cache)} staves read ({len(todo)} new) -> {cache_file.name}", flush=True)
    print(f"now: autopair.py ... --model /nonexistent/{name}")


if __name__ == "__main__":
    main()
