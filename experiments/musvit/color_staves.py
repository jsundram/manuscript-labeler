# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Colour copies of training staves (dataset.py's folders), for reading in
colour (proto.py --color): the same staves, the same crop (compare.staff_crop
on a colour render of the page), the same labels.

    uv run experiments/musvit/color_staves.py <edition> dataL dataM=<results suffix> dataT=<results suffix> [--jobs 8]

Each FOLDER is under ~/.cache/manuscript-labeler/zeus and is copied to
FOLDER-color beside it: its samples files and labels as they are, each
staff's JPEG cut again in colour. A folder named alone holds labelled
sources (<source>/<sid>: the staff's box from the edition's bar export); one
named with a suffix holds autopair.py's staves (<source>/<staff>: the box
from results/autopair-<source><suffix>.json, the PDF from auto/<source>.json).
Pages are rendered once each, in parallel, and not kept (a colour render is
large).
"""

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parent / "zeus"
sys.path.insert(0, str(ZEUS))
import compare  # noqa: E402

CACHE = Path.home() / ".cache" / "manuscript-labeler" / "zeus"


def render(pdf: str, page: int) -> np.ndarray:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "p"
        subprocess.run(["pdftoppm", "-f", str(page), "-l", str(page), "-scale-to", str(compare.RENDER_PX), "-png",
                        "-singlefile", pdf, str(out)], check=True)
        return np.asarray(Image.open(f"{out}.png").convert("RGB")).astype(np.float32)


def cut_page(job) -> int:
    pdf, page, items = job  # items: [(system box, destination JPEG)]
    g = render(pdf, page)
    for s, dest in items:
        Image.open(io.BytesIO(compare.staff_crop(g, s))).convert("RGB").save(dest, quality=95)
    return len(items)


def where(edition: Path, folder: Path, suffix: str | None) -> dict:
    """{(source, stem): (pdf, page, box)} for the staves in a dataset folder."""
    out = {}
    listed = {l for f in folder.glob("samples.*.txt") for l in f.read_text().split()}  # the staves in use, not leftovers
    for src in sorted(p for p in folder.iterdir() if p.is_dir()):
        stems = {f.stem for f in src.glob("*.jpg") if f"{src.name}/{f.stem}" in listed}
        if not stems:
            continue
        if suffix is None:
            name = src.name  # a variant's folder (F-Pn_Vma-ms-1067-3-noslur) is its source's staves
            while not list(edition.glob(f"sources/*/{name}.pdf")) and "-" in name:
                name = name.rsplit("-", 1)[0]
            pdf = next(edition.glob(f"sources/*/{name}.pdf"))
            export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
            for st in stems:
                s = export["systems"][st]
                out[(src.name, st)] = (str(pdf), s["page"], s)
        else:
            res = json.loads((ZEUS / "results" / f"autopair-{src.name}{suffix}.json").read_text())
            auto = json.loads((ZEUS / "auto" / f"{src.name}.json").read_text())
            pdf = auto.get("pdf") or str(next(edition.glob(f"sources/*/{src.name}.pdf")))
            kept = {k["staff"]: k for k in res["kept"]}
            for st in stems:
                out[(src.name, st)] = (pdf, kept[st]["page"], kept[st]["system"])
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("folders", nargs="+", help="FOLDER (labelled sources) or FOLDER=<autopair results suffix>")
    ap.add_argument("--cache", type=Path, default=CACHE)
    ap.add_argument("--jobs", type=int, default=os.cpu_count())
    a = ap.parse_args()
    for spec in a.folders:
        name, _, suffix = spec.partition("=")
        src_dir, dst_dir = a.cache / name, a.cache / f"{name}-color"
        places = where(a.edition, src_dir, suffix or None)
        jobs = defaultdict(list)
        for (src, st), (pdf, page, box) in places.items():
            (dst_dir / src).mkdir(parents=True, exist_ok=True)
            shutil.copy(src_dir / src / f"{st}.lmx", dst_dir / src / f"{st}.lmx")
            jobs[(pdf, page)].append((box, str(dst_dir / src / f"{st}.jpg")))
        for f in src_dir.glob("samples.*.txt"):
            shutil.copy(f, dst_dir / f.name)
        with ProcessPoolExecutor(a.jobs) as ex:
            n = sum(ex.map(cut_page, [(pdf, page, items) for (pdf, page), items in sorted(jobs.items())]))
        print(f"{name}: {n} staves in colour from {len(jobs)} pages -> {dst_dir}", flush=True)


if __name__ == "__main__":
    main()
