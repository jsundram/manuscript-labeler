# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic", "numpy", "pillow", "scikit-learn"]
# ///
"""The labeler's automatic detection on every music page of a source, as if
nobody had opened it: the staves and bar lines it would propose, for
autopair.py to pair with the encoding.

    uv run experiments/zeus/autodetect.py <edition-repo> --source F-Po_RES-507-14
    uv run experiments/zeus/autodetect.py <edition-repo> --pdf <file.pdf> --name F-Po_RES-507-2 \\
        --pages 5-31:vn1,33-55:vn2,57-83:vc,85-105:va
    uv run experiments/zeus/autodetect.py <edition-repo> --pdf <file.pdf> --name F-Pn_MS-1292 --pages 4-118:score

Detection runs as the server's does (server.Edition.detect: the cached
detectors' vote, their staff ends). No page's room (the editor's
clef-and-key width) is passed. The cached detectors (YOLO) were trained on
every labelled source.

--source: a labelled source of the edition. Which pages are music, and
whose part, are taken from its labels. The learned bar-line filter is
trained without the source's own reviewed pages (in a cache of its own, so
the labeler's model is left alone).

--pdf: a source nobody has labelled. Which pages hold which part is given
by --pages; "score" pages hold every part, system by system: a page's
staves are grouped into systems by the gaps between them, and a system of
four staves is vn1, vn2, va, vc, top to bottom (any other is left out).
The filter is trained on every reviewed page.

Writes auto/<name>.json: {n: {part, systems}}, each staff with its "part".
"""

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path.insert(0, str(ROOT))
import labels  # noqa: E402
import learn  # noqa: E402
import server  # noqa: E402
from detections import cache_dir  # noqa: E402

PARTS = ("vn1", "vn2", "va", "vc")


def page_map(spec: str) -> dict[int, str]:
    """"5-31:vn1,33-55:vn2" -> {5: "vn1", ..., 55: "vn2"}."""
    out = {}
    for item in spec.split(","):
        pages, _, part = item.partition(":")
        a, _, b = pages.partition("-")
        for n in range(int(a), int(b or a) + 1):
            out[n] = part
    return out


def systems(staves: list[dict]) -> list[list[dict]]:
    """A score page's staves, top to bottom, in systems: a gap between
    staves more than 1.6 times the page's median gap starts a new one."""
    if len(staves) < 2:
        return [staves] if staves else []
    gaps = [b["top"] - a["bottom"] for a, b in zip(staves, staves[1:])]
    cut = 1.6 * sorted(gaps)[len(gaps) // 2]
    out = [[staves[0]]]
    for g, s in zip(gaps, staves[1:]):
        if g > cut:
            out.append([])
        out[-1].append(s)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source", help="a labelled source of the edition")
    ap.add_argument("--pdf", type=Path, help="an unlabelled source")
    ap.add_argument("--name", help="with --pdf: what to call it")
    ap.add_argument("--pages", help="with --pdf: pages and their part, 5-31:vn1,... (or :score)")
    a = ap.parse_args()
    edition = a.edition.resolve()
    cache = cache_dir()
    ed = server.Edition(edition, cache)
    if a.source:
        name = a.source
        pdf = next(edition.glob(f"sources/*/{a.source}.pdf"))
        doc = labels.migrate(json.loads(labels.labels_path(pdf).read_text()))
        parts = {int(n): p["part"] for n, p in doc["pages"].items() if p.get("kind") == "music" and p.get("part")}
    elif a.pdf and a.name and a.pages:
        name, pdf, parts = a.name, a.pdf.resolve(), page_map(a.pages)
    else:
        ap.error("give --source, or --pdf with --name and --pages")

    # the learned filter, from every labelled source but this one
    with tempfile.TemporaryDirectory() as tmp:
        data = Path(tmp) / "data"
        for lp, other in labels.labels_files(edition):
            if other.stem != name:
                dest = data / edition.name / lp.relative_to(labels.DATA / edition.name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy(lp, dest)

        def render(p, n):
            img = Image.open(ed.render(ed.rel(p), n))
            img.load()
            return img
        print("training the bar-line filter without", name, flush=True)
        model = learn.load_or_train(edition, HERE / "auto" / "cache" / name, render, data)
    if model is None:
        sys.exit(f"no reviewed pages but {name}'s to train the bar-line filter on")
    print(f"  from {model['pages']} reviewed pages ({model['bar_lines']} bar lines)", flush=True)

    # detection where the source is (an Edition rooted at its folder)
    src = ed if a.source else server.Edition(pdf.parent, cache)
    src.model = model
    rel = src.rel(pdf)
    out = {"source": name, "pdf": str(pdf), "filter_pages": model["pages"], "pages": {}}
    for n, part in sorted(parts.items()):
        d = src.detect(rel, n)
        staves = sorted(d["systems"], key=lambda s: s["top"])
        if part == "score":
            groups = systems(staves)
            staves = [s for g in groups if len(g) == 4 for s in g]
            for k, s in enumerate(staves):
                s["part"] = PARTS[k % 4]
            if not staves:
                print(f"  p{n} score: no system of 4 staves ({[len(g) for g in groups]})", flush=True)
                continue
        else:
            for s in staves:
                s["part"] = part
        out["pages"][str(n)] = {"part": part, "systems": staves}
        print(f"  p{n} {part}: {len(staves)} staves", flush=True)
    dest = HERE / "auto" / f"{name}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    print("wrote", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
