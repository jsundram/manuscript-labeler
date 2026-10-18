# /// script
# requires-python = ">=3.11"
# dependencies = ["modal", "numpy", "pillow", "torch", "transformers", "peft"]
# ///
"""Score a MuSViT reader on the clean test with compare.py, as Zeus is scored.

    uv run experiments/musvit/read.py <edition-repo> --run stage2-J [--file reader.pt]
        [--source D-B_KHM-603] [--movements I] [--device mps|cpu]

Cuts each staff of the source's bar export exactly as compare.py does (its
staff_crop, the crop dataset.py trained on, saved as JPEG at quality 95 as
dataset.py saves it), has the run's reader read them on Modal
(modal_app.read), and writes the readings into compare.py's cache,
answers/<source>-musvit-<run>.json, keyed by staff and crop as compare.py
keys them. With --device, the reader reads here instead (the Mac's GPU:
mps), into answers/<source>-musvit-<run>-<device>.json. With --beam K, the reader gives up to K readings of each staff
(beam search) and the one kept is the likeliest after a penalty of
--rerank (in log-probability) for each bar that doesn't fit: a bar box
whose length (the labels' time signature) differs from its measure's, or
a measure too many or too few; --rerank 0 keeps the beam's best. The
readings are kept in answers/<source>-<name>.nbest.json. Then runs compare.py with --model named musvit-<run>: every
staff is cached, so Zeus isn't loaded, and the result lands in
experiments/zeus/results/ beside Zeus's.
"""

import argparse
import hashlib
import io
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parent / "zeus"
sys.path.insert(0, str(ZEUS))
import compare  # noqa: E402


def misfits(lmx: str, boxes: list[dict], times: dict, all_boxes: Counter) -> int:
    """Bars of a reading that don't fit the labels: each measure too many or
    too few, and each whole bar whose length isn't the time signature's."""
    try:
        ends: list = []
        measures, _ = compare.parse(lmx, ends)
    except Exception:
        return 99
    want = compare.wanted(boxes, times, all_boxes)
    if len(measures) != len(want):
        return 1 + abs(len(measures) - len(want))
    return sum(w["exact"] and e != w["len"] and not compare.bar_rest(m) for m, e, w in zip(measures, ends, want))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--run", required=True)
    ap.add_argument("--file", default="reader.pt")
    ap.add_argument("--source", default="D-B_KHM-603")
    ap.add_argument("--movements", nargs="+", default=["I"])
    ap.add_argument("--beam", type=int, default=0)
    ap.add_argument("--rerank", type=float, default=0.0)
    ap.add_argument("--device", help="read here, on this torch device (mps, cpu), not on Modal")
    a = ap.parse_args()
    if a.beam and a.device:
        ap.error("--beam reads on Modal only")
    name = f"musvit-{a.run}" + ("" if a.file == "reader.pt" else f"-{Path(a.file).stem}") + (f"-{a.device}" if a.device else "")
    if a.beam:
        name += f"-beam{a.beam}" + (f"-rr{a.rerank:g}" if a.rerank else "")

    # the staves and their crops, as compare.main makes them
    pdf = next(a.edition.glob(f"sources/*/{a.source}.pdf"))
    export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
    boxes = {}
    for b in export["bars"]:
        if b["part"] in ("vn1", "vn2", "va", "vc") and b["movement"] in a.movements:
            boxes.setdefault(b["system"], []).append(b)
    sids = list(boxes)
    times, now = {}, {}  # the time signature in force at each bar, as compare.main finds it
    for b in export["bars"]:
        pm = (b["part"], b["movement"])
        now[pm] = b["signature"].get("time", now.get(pm, "4/4"))
        times[(b["part"], b["movement"], b["bar"])] = now[pm]
    all_boxes = Counter((b["part"], b["movement"], b["bar"]) for bs in boxes.values() for b in bs)
    cache_file = ZEUS / "answers" / f"{a.source}-{name}.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    nbest_file = ZEUS / "answers" / f"{a.source}-{name.split('-rr')[0]}.nbest.json"
    nbest = json.loads(nbest_file.read_text()) if a.beam and nbest_file.exists() else {}
    crops, keys, page = {}, {}, (None, None)
    for sid in sids:
        s = export["systems"][sid]
        if page[0] != s["page"]:
            page = (s["page"], compare.page_image(pdf, s["page"]))
        png = compare.staff_crop(page[1], s)
        key = keys[sid] = f"{sid}:{hashlib.sha1(png).hexdigest()[:10]}"
        if key not in (nbest if a.beam else cache):
            buf = io.BytesIO()
            Image.open(io.BytesIO(png)).convert("L").save(buf, "JPEG", quality=95)
            crops[key] = buf.getvalue()
    print(f"{len(sids)} staves; {len(crops)} to read " + (f"here ({a.device})" if a.device else "on Modal"), flush=True)

    if crops and a.device:
        sys.path.insert(0, str(HERE))
        import time
        import proto
        t0 = time.time()
        cache.update(proto.read_crops(a.run, a.file, crops, a.device))
        print(f"read in {time.time() - t0:.0f} s ({(time.time() - t0) / len(crops):.2f} s a staff)", flush=True)
    elif crops:
        import modal
        sys.path.insert(0, str(HERE))
        from modal_app import app, read, read_nbest
        with modal.enable_output(), app.run():
            if a.beam:
                nbest.update(read_nbest.remote(a.run, a.file, crops, a.beam))
            else:
                cache.update(read.remote(a.run, a.file, crops))
        if a.beam:
            nbest_file.write_text(json.dumps(nbest, indent=1, sort_keys=True))
    if a.beam:
        changed = 0
        for sid in sids:
            options = nbest[keys[sid]]
            best = max(options, key=lambda o: o[1] - a.rerank * misfits(o[0], boxes[sid], times, all_boxes))
            changed += best is not options[0]
            cache[keys[sid]] = best[0]
        print(f"beam {a.beam}, rerank {a.rerank:g}: {changed} of {len(sids)} staves kept a reading other than the likeliest")
    cache_file.parent.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(cache, indent=1, sort_keys=True))

    subprocess.run(["uv", "run", str(ZEUS / "compare.py"), str(a.edition), "--source", a.source,
                    "--movements", *a.movements, "--model", str(Path("/nonexistent") / name)], check=True)


if __name__ == "__main__":
    main()
