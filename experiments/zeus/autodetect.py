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

--whole-page: pages whose paper is the whole image (a scan cropped to the
page), detected with the image's corners as the paper's, where
find_page_corners took a dark band inside the page for its edge and cut
the staves short (the Sibley scan of G. 213, page 1).

--score-layout: score pages by their ruling instead of by gaps, for full
scores whose sparse staves (a few rests) fail detection's empty-staff test,
which leaves a system three staves and loses all four; or whose systems
are spaced like their staves. Score pages are then detected with the
empty-staff test off, so every ruled staff is found; a staff less than half
within the page's median left and right ends is dropped (the edge of the
facing page), and so is a stub under a tenth of that width (a title), and
with --score-margin, a "staff" whose middle lies that near the image's top
or bottom (a library's heading or footer band). The
layout says, for a page with so many ruled staves, which of them (0 from
the top) make each system: "10:0-3,5-8|1-4,6-9;14:0-3,5-8,10-13" (several
layouts for one count separated by |). The staves no system takes must be
empty (under SEPARATOR_INK between their lines); of the layouts that pass,
the one with the least ink on them is taken; a page with another count, or
no layout that passes, is left out and logged. Without --score-layout
nothing changes.

--score-parts: a score system's parts, top to bottom (default vn1,vn2,va,vc):
"vn1,vn2,vc" for a trio's three-staff systems (the Montecassino op. 4
score). Grouping by gaps then keeps systems of that many staves; with
--score-layout, the staves of each system are dealt these parts in turn.

--leave-out: staves to leave out, as page:index (0 the top staff detection
found on the page), e.g. "20:0,22:0": a cue staff of another part (KHM 600's
cello part opens three pages with a two-staff system, the first violin's
cue above the cello).

--max-staves: a parts page where detection found more staves than this is
left out and logged: its staves are fragments (the Sibley op. 4 scan, where
some pages still break each staff into pieces after levelling).

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


SEPARATOR_INK = 0.01  # a ruled staff between systems: less ink than this between its lines


def staff_ink(g, s: dict) -> float:
    """Share of dark pixels (< 120) on the middle row of each of a staff's
    spaces, along its bend from its left end to its right (as detect.inner_ink,
    on the page)."""
    import numpy as np
    H, W = g.shape
    gap = (s["bottom"] - s["top"]) / 4
    xs = np.arange(int(s["left"] * W), int(s["right"] * W), 2)
    if not len(xs):
        return 0.0
    hits = 0
    for x in xs:
        y0 = s["top"] + labels.bend_at(s, x / W)
        for i in range(4):
            y = int(round((y0 + (i + 0.5) * gap) * H))
            hits += 0 <= y < H and g[y, x] < 120
    return hits / (4 * len(xs))


def score_layout(spec: str) -> dict[int, list[list[list[int]]]]:
    """"10:0-3,5-8|1-4,6-9;14:..." -> {10: [[[0,1,2,3],[5,6,7,8]], [[1,..],[6,..]]], 14: ...}."""
    out = {}
    for item in spec.split(";"):
        count, _, alts = item.partition(":")
        out[int(count)] = [[list(range(int(r.split("-")[0]), int(r.split("-")[1]) + 1)) for r in alt.split(",")]
                           for alt in alts.split("|")]
    return out


def by_layout(staves: list[dict], g, layouts: dict, margin: float = 0.0) -> tuple[list[list[dict]], str]:
    """A score page's systems by its ruling (--score-layout), and what was decided."""
    import statistics
    lo = statistics.median(s["left"] for s in staves) if staves else 0
    hi = statistics.median(s["right"] for s in staves) if staves else 0
    inside = lambda s: max(0.0, min(s["right"], hi) - max(s["left"], lo))
    mid = lambda s: (s["top"] + s["bottom"]) / 2
    ruled = [s for s in staves if inside(s) >= 0.5 * (s["right"] - s["left"])
             and s["right"] - s["left"] >= 0.1 * (hi - lo) and margin <= mid(s) <= 1 - margin]
    note = f"{len(ruled)} ruled" + (f" ({len(staves) - len(ruled)} dropped: beside the page, a stub, or in the margin)"
                                    if len(ruled) < len(staves) else "")
    if len(ruled) not in layouts:
        return [], note + ", no layout for that count"
    ink = [staff_ink(g, s) for s in ruled]
    passing = []
    for alt in layouts[len(ruled)]:
        taken = {i for sy in alt for i in sy}
        sep = [ink[i] for i in range(len(ruled)) if i not in taken]
        if max(sep, default=0.0) < SEPARATOR_INK:
            passing.append((sum(sep), alt))
    if not passing:
        return [], note + ", separators inked: " + " ".join(f"{1000 * v:.0f}" for v in ink)
    _, alt = min(passing, key=lambda p: p[0])
    return [[ruled[i] for i in sy] for sy in alt], note + f", systems {alt}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source", help="a labelled source of the edition")
    ap.add_argument("--pdf", type=Path, help="an unlabelled source")
    ap.add_argument("--name", help="with --pdf: what to call it")
    ap.add_argument("--pages", help="with --pdf: pages and their part, 5-31:vn1,... (or :score)")
    ap.add_argument("--whole-page", default="", help="pages (1,3-4) whose paper is the whole image")
    ap.add_argument("--score-layout", help="score pages' systems by their ruling: 10:0-3,5-8|1-4,6-9;14:...")
    ap.add_argument("--score-margin", type=float, default=0.0,
                    help="with --score-layout: drop a staff whose middle is this near the image's top or bottom "
                         "(a library's heading or footer band)")
    ap.add_argument("--score-parts", default=",".join(PARTS),
                    help="a score system's parts, top to bottom (vn1,vn2,vc for a trio)")
    ap.add_argument("--max-staves", type=int, help="leave out a parts page with more staves than this (fragments)")
    ap.add_argument("--leave-out", default="", help="staves to leave out, page:index from the top (20:0,22:0)")
    a = ap.parse_args()
    leave_out = {tuple(map(int, x.split(":"))) for x in a.leave_out.split(",") if x}
    score_parts = tuple(a.score_parts.split(","))
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
    whole = set(page_map(a.whole_page.replace(",", ":x,") + ":x")) if a.whole_page else set()
    for n, part in sorted(parts.items()):
        corners = [[0, 0], [1, 0], [1, 1], [0, 1]] if n in whole else None
        if part == "score" and a.score_layout:
            import detect
            import numpy as np
            keep, detect.EMPTY_INK = detect.EMPTY_INK, -1.0  # every ruled staff, the empty ones too
            try:
                d = src.detect(rel, n, corners=corners)
            finally:
                detect.EMPTY_INK = keep
            g = np.asarray(Image.open(src.render(rel, n)).convert("L"))
            groups, note = by_layout(sorted(d["systems"], key=lambda s: s["top"]), g, score_layout(a.score_layout),
                                     a.score_margin)
            staves = [s for gr in groups for s in gr]
            for k, s in enumerate(staves):
                s["part"] = score_parts[k % len(score_parts)]
            if not staves:
                print(f"  p{n} score: left out ({note})", flush=True)
                continue
            out["pages"][str(n)] = {"part": part, "systems": staves, "layout": note}
            print(f"  p{n} {part}: {len(staves)} staves ({note})", flush=True)
            continue
        d = src.detect(rel, n, corners=corners)
        staves = sorted(d["systems"], key=lambda s: s["top"])
        if part == "score":
            groups = systems(staves)
            staves = [s for g in groups if len(g) == len(score_parts) for s in g]
            for k, s in enumerate(staves):
                s["part"] = score_parts[k % len(score_parts)]
            if not staves:
                print(f"  p{n} score: no system of {len(score_parts)} staves ({[len(g) for g in groups]})", flush=True)
                continue
        else:
            for s in staves:
                s["part"] = part
        if a.max_staves and part != "score" and len(staves) > a.max_staves:
            print(f"  p{n} {part}: left out ({len(staves)} staves, over --max-staves {a.max_staves})", flush=True)
            continue
        if any(p == n for p, _ in leave_out):
            gone = [k for k in range(len(staves)) if (n, k) in leave_out]
            staves = [s for k, s in enumerate(staves) if (n, k) not in leave_out]
            print(f"  p{n}: left out staves {gone} (--leave-out)", flush=True)
        out["pages"][str(n)] = {"part": part, "systems": staves}
        print(f"  p{n} {part}: {len(staves)} staves", flush=True)
    dest = HERE / "auto" / f"{name}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    print("wrote", dest.relative_to(ROOT))


if __name__ == "__main__":
    main()
