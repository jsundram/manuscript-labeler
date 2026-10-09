# /// script
# requires-python = ">=3.11,<3.14"
# dependencies = ["ultralytics", "numpy", "pillow"]
# ///
"""Bar-line detectors' predictions for every page of an edition, cached for
the labeler (which votes them with its learned filter when present).

    uv run tools/predict_barlines.py <edition-repo> [--install NAME WEIGHTS THRESHOLD] [--notes TEXT] [--retry] [--only SOURCE]
    uv run --with "transformers>=4.52" --with timm --with scipy tools/predict_barlines.py <edition-repo> --kind dfine ...
    <detectron2 venv>/bin/python tools/predict_barlines.py <edition-repo> --kind detectron2 ...

Each run predicts with the installed detectors of one kind (--kind: yolo,
the default; dfine; detectron2, which has no Mac wheels and runs in a venv
built for it, see experiments/barlines/run_detectron2.py). Detectors live
in the cache (~/.cache/manuscript-labeler/models/detectors/<name>/: its
weights, best.pt, model.pth or D-FINE's model/ folder, and manifest.json,
written by --install, which copies the weights in and records their kind,
where they came from and the confidence threshold they chose on their
validation lines).

For each page: the staves as the labeler detects them (detect.detect_page,
on the server's renders), each cut out straightened across the paper's
whole width at its height (experiments/barlines/corpus.paper_band, with the
editor's page corners if they set them): so the predictions don't depend on
where a staff's ends are, which detection gets wrong most often and the
editor edits most. Each detector runs on it in 640 px tiles; every
detection at confidence >= MIN_CONF is kept, in page fractions, with the
staff's top, bottom and bend to match it to the labeler's staves by height;
with a detector that also learned the staff's ends ("start" and "end"
boxes, corpus.py --paper), its surest of each too.

One cache per detector (its name, weights and threshold in the folder's
key: a retrain or new threshold gets a new folder; adding a detector
doesn't redo the others; layout and keys in detections.py, which the
labeler reads them with), one file per edition and PDF, which records the
PDF's size and modification time: a changed PDF is predicted afresh.
Pages already done are skipped; a page that fails is recorded with its
error and skipped too (--retry tries those again).
"""

import argparse
import hashlib
import json
import shutil
import sys
import time
import traceback
from datetime import date
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "experiments" / "barlines")]
import detect  # noqa: E402
from common import detectron2_tile, dfine_tile, read_line, yolo_tile  # noqa: E402
from corpus import paper_band  # noqa: E402
from detections import cache_dir, cache_file, detectors, pdf_identity  # noqa: E402

MIN_CONF = 0.05


def cached(s: dict, reading: tuple, x_off: float, w: int) -> dict:
    """One staff's predictions in page fractions: its bar lines [x, conf],
    and if the detector has the classes, its surest start box [left end,
    music start, conf] and end [right end, conf]; with the staff's height
    and bend, to match it to the labeler's staves."""
    bars, start, end = reading
    f = lambda x: round((x + x_off) / w, 5)
    out = {**{k: s[k] for k in ("top", "bottom", "left", "right", "bend")},
           "bars": [[f(x), round(c, 3)] for x, c in bars]}
    if start:
        out["start"] = [f(start[0]), f(start[1]), round(start[2], 3)]
    if end:
        out["end"] = [f(end[0]), round(end[1], 3)]
    return out


KINDS = {"yolo": "best.pt", "detectron2": "model.pth", "dfine": "model"}  # kind: its weights in the cache


def install(name: str, weights: Path, threshold: float, notes: str, kind: str = "yolo"):
    """Copy a detector's weights (a file, or D-FINE's folder) into the cache,
    with a manifest naming its kind, threshold and where it came from."""
    d = cache_dir() / "models" / "detectors" / name
    d.mkdir(parents=True, exist_ok=True)
    dest = d / KINDS[kind]
    h = hashlib.sha1()
    if weights.is_dir():
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(weights, dest)
        for f in sorted(dest.rglob("*")):
            if f.is_file():
                h.update(f.name.encode() + f.read_bytes())
    else:
        shutil.copy2(weights, dest)
        h.update(dest.read_bytes())
    sha = h.hexdigest()[:16]
    (d / "manifest.json").write_text(json.dumps({
        "name": name, "kind": kind, "weights_file": KINDS[kind], "threshold": threshold, "sha": sha,
        "source": str(weights), "installed": date.today().isoformat(), "notes": notes}, indent=1))
    print(f"installed {name} ({kind}, {sha}), threshold {threshold}")


def tile_function(d: dict, device: str):
    """A detector as read_line's predict_tile: [(cls, x0, x1, conf)] per tile
    (the loaders shared with the experiments, common.py). Detectron2 and
    D-FINE detect bar lines only (class 0)."""
    kind = d.get("kind", "yolo")
    if kind == "yolo":
        from ultralytics import YOLO
        return yolo_tile(YOLO(str(d["weights"])), device, MIN_CONF)
    if kind == "detectron2":
        return detectron2_tile(d["weights"], device, MIN_CONF)
    if kind == "dfine":
        return dfine_tile(d["weights"], device, MIN_CONF)
    raise ValueError(f"{d['name']}: unknown kind {kind!r}")


def weights_kind(weights: Path) -> str:
    """What a detector's weights are, from their form: D-FINE's a folder,
    Detectron2's a .pth, YOLO's a .pt."""
    return "dfine" if weights.is_dir() else "detectron2" if weights.suffix == ".pth" else "yolo"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edition", type=Path)
    ap.add_argument("--install", nargs=3, action="append", metavar=("NAME", "WEIGHTS", "THRESHOLD"),
                    help="copy a trained detector into the cache first")
    ap.add_argument("--notes", default="", help="with --install: where the weights came from")
    ap.add_argument("--retry", action="store_true", help="predict pages that failed before again")
    ap.add_argument("--kind", choices=sorted(KINDS), default="yolo",
                    help="the kind of detector to install and run (each in its own environment: yolo with uv, "
                         "detectron2 in its source-built venv, dfine with transformers)")
    ap.add_argument("--only", action="append", default=[], metavar="SOURCE",
                    help="predict only this source (the PDF's name without .pdf); repeatable")
    args = ap.parse_args()
    for name, weights, th in args.install or []:
        if weights_kind(Path(weights)) != args.kind:  # a mismatch would break every later run of this kind
            sys.exit(f"{weights} looks like {weights_kind(Path(weights))} weights, not {args.kind}: give --kind")
        install(name, Path(weights), float(th), args.notes, args.kind)

    import server
    import torch

    dets = [d for d in detectors() if d.get("kind", "yolo") == args.kind]
    if not dets:
        sys.exit(f"no {args.kind} detectors installed (--install NAME WEIGHTS THRESHOLD --kind {args.kind})")
    device = "mps" if torch.backends.mps.is_available() else "cuda" if torch.cuda.is_available() else "cpu"
    models = [(d, tile_function(d, device)) for d in dets]
    ed = server.Edition(args.edition, cache_dir())
    print(f"detectors {', '.join(d['key'] for d in dets)} on {device}")
    for pdf in sorted(args.edition.glob("sources/**/*.pdf")):
        if args.only and pdf.stem not in args.only:
            continue
        rel = str(pdf.relative_to(args.edition))
        ident = pdf_identity(pdf)
        lp = pdf.with_name(pdf.name.replace(".pdf", ".labels.json"))
        corners = {}
        if lp.exists():
            for n, p in json.loads(lp.read_text()).get("pages", {}).items():
                if p.get("corners") and not p["corners"].get("auto"):
                    corners[int(n)] = p["corners"]["points"]
        docs = {}
        for d, _ in models:
            f = cache_file(d, args.edition, rel)
            doc = json.loads(f.read_text()) if f.exists() else None
            if not doc or doc.get("pdf_identity") != ident:  # new, or the PDF has changed
                doc = {"detector": {x: d[x] for x in ("name", "sha", "threshold", "key")}, "pdf": rel,
                       "pdf_identity": ident, "min_conf": MIN_CONF, "pages": {}}
            docs[d["key"]] = (f, doc)
        t0, n_done = time.perf_counter(), 0
        for page in range(1, ed.num_pages(pdf) + 1):
            todo = [(d, tile) for d, tile in models
                    if str(page) not in docs[d["key"]][1]["pages"]
                    or (args.retry and "error" in docs[d["key"]][1]["pages"][str(page)])]
            if not todo:
                continue
            try:
                img = Image.open(ed.render(rel, page))
                img.load()
                g = np.asarray(img.convert("L"))
                h, w = g.shape
                cs = corners.get(page) or detect.find_page_corners(img)
                staves = detect.detect_page(img, corners=cs)
                bands = [paper_band(g, s, cs) for s in staves]
                for d, tile in todo:
                    docs[d["key"]][1]["pages"][str(page)] = {"staves": [
                        cached(s, read_line(Image.fromarray(band).convert("RGB"), geo["space"], tile), geo["x_off"], w)
                        for s, (band, geo) in zip(staves, bands)]}
            except Exception as e:  # record it and carry on: one bad page mustn't stop the rest
                for d, _ in todo:
                    docs[d["key"]][1]["pages"][str(page)] = {"error": f"{type(e).__name__}: {e}"}
                print(f"{rel} p{page}: failed: {traceback.format_exc(limit=1).strip()}", flush=True)
            n_done += 1
            for f, doc in docs.values():  # page by page: an interrupted run resumes where it stopped
                f.parent.mkdir(parents=True, exist_ok=True)
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(doc))
                tmp.replace(f)
        if n_done:
            print(f"{rel}: {n_done} pages, {(time.perf_counter() - t0) / n_done:.1f} s a page", flush=True)
    print(f"wrote {cache_dir() / 'detections'}")


if __name__ == "__main__":
    main()
