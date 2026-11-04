# /// script
# requires-python = ">=3.11"
# dependencies = ["modal", "numpy", "pillow"]
# ///
"""Read a source's staves one bar box at a time: each detected staff cut at
its detected bar lines, the staff's opening (clef, key, time: everything
before its music starts) put before each piece, each piece read by a MuSViT
reader, and the pieces' readings joined into the staff's. A reader then
can't run two bars together, or invent one, where detection found the bar
lines; where it missed one, the box holds two bars and the reader may still
read both.

    uv run experiments/musvit/read_boxes.py --run D5-B6k-d11-op48x3-s1 --name D5-boxes SOURCE...

Staves are named and cut as read_auto.py does, so the staff's reading is
cached under the key autopair.py looks for: experiments/zeus/answers/
<source>-auto-musvit-<name>.json; then autopair.py --model .../musvit-<name>.
Each piece's own reading goes to <source>-auto-musvit-<name>-pieces.json.
A piece is the music between two bar lines, both included (or the staff's
start or end), left out if under 1.5 staff spaces wide; the last ends at the
staff's right end. In every piece after the first, the opening's clef, key
and time the reader writes again are dropped.

Tried with musvit-D5 on KHM 587 (reports/2026-11-04-bar-box-reading): worse
than reading whole staves (123 staves kept against 171), even where detection
is exactly right. Kept as the record of what was tried.
"""

import argparse
import hashlib
import io
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parent / "zeus"
sys.path.insert(0, str(ZEUS))
sys.path.insert(0, str(HERE))
import compare  # noqa: E402
from read_auto import EDITION  # noqa: E402

OPENING = ("key:", "clef:", "time", "beats:", "beat-type:")


def jpeg(a: np.ndarray) -> bytes:
    buf = io.BytesIO()
    Image.fromarray(a).convert("L").save(buf, "JPEG", quality=95)
    return buf.getvalue()


def pieces(png: bytes, s: dict, W: int) -> list[bytes]:
    """The staff crop (compare.staff_crop) cut into its bar boxes, each after the staff's opening."""
    g = np.array(Image.open(io.BytesIO(png)))
    sp = (s["bottom"] - s["top"]) / 4  # a staff space, in page heights; the crop's x is in page widths
    x0 = max(0.0, s["left"] - sp * s["_aspect"])  # as staff_crop: a staff space past each end
    px = lambda x: int(round((x - x0) * W))
    sp_px = sp * s["_aspect"] * W
    start = px(s.get("start", s["left"]))
    lines = sorted(s["barlines"], key=lambda b: b["x0"])
    pad = int(0.1 * sp_px)  # a hair past each bar line: further, the reader takes the next bar's first note as a bar
    lefts = [start] + [px(b["x0"]) - pad for b in lines]
    rights = [px(b["x1"]) + pad for b in lines] + [px(s["right"])]
    head = g[:, :start]
    out = []
    for a, b in zip(lefts, rights):
        a, b = max(start, a), min(g.shape[1], b)
        if b - a < 1.5 * sp_px:
            continue
        out.append(jpeg(np.concatenate([head, g[:, a:b]], axis=1)))
    return out


def join(readings: list[str]) -> str:
    """The pieces' readings as one staff's: the opening's tokens dropped after the first piece."""
    out = []
    for i, r in enumerate(readings):
        t = r.split()
        if i:
            first = next((j for j, w in enumerate(t[1:], 1) if w == "measure"), len(t))
            t = [w for j, w in enumerate(t) if j >= first or not w.startswith(OPENING)]
        out += t
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--run", required=True)
    ap.add_argument("--file", default="reader.pt")
    ap.add_argument("--name", required=True, help="the readings' name: answers/<source>-auto-musvit-<name>.json")
    a = ap.parse_args()
    import modal
    from modal_app import app, read
    with modal.enable_output(), app.run():
        for src in a.sources:
            auto = json.loads((ZEUS / "auto" / f"{src}.json").read_text())
            pdf = Path(auto["pdf"]) if "pdf" in auto else next(EDITION.glob(f"sources/*/{src}.pdf"))
            todo, keys = {}, {}
            for n, p in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
                g = compare.page_image(pdf, int(n))
                for k, s in enumerate(sorted(p["systems"], key=lambda s: s["top"])):
                    png = compare.staff_crop(g, s)
                    key = f"p{n}-{k}:{hashlib.sha1(png).hexdigest()[:10]}"
                    cut = pieces(png, dict(s, _aspect=g.shape[0] / g.shape[1]), g.shape[1])
                    keys[key] = len(cut)
                    todo |= {f"{key}#{i}": c for i, c in enumerate(cut)}
            print(f"{src}: {len(keys)} staves, {len(todo)} pieces", flush=True)
            got = read.remote(a.run, a.file, todo)
            staves = {key: join([got[f"{key}#{i}"] for i in range(m)]) for key, m in keys.items() if m}
            base = ZEUS / "answers" / f"{src}-auto-musvit-{a.name}"
            Path(f"{base}-pieces.json").write_text(json.dumps(got, indent=1, sort_keys=True))
            Path(f"{base}.json").write_text(json.dumps(staves, indent=1, sort_keys=True))
            print(f"{src}: -> {base.name}.json", flush=True)
    print(f"now: autopair.py ... --model /nonexistent/musvit-{a.name}")


if __name__ == "__main__":
    main()
