# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "scikit-learn"]
# ///
"""What the editor would still have to fix on each staff, with today's
detection: every reviewed music page detected again, its staves set
against the editor's.

    uv run tools/staff_edits.py [--out FILE] [--no-learned-crops] [labels files...]

The staff edits are the editor's largest share of work in the labeler
(the activity log, 2026-10 to 2026-11: 740 staff edits against 426 to
bar lines). Bar lines have their own scorer (tools/score_barlines.py).

Each page is detected as the labeler detects it, with the clef-and-key
room the editor set on their previous page of the part (static/app.js
roomFromPreviousPage), but without the learned parts the labeler adds,
which learned from these pages: the bar-line filter, the detectors' ends
(detections.py). The crop above and below is scored twice: today's rule
(detect.crop_margins) and the learned model (crops.py), trained on every
source but the page's, as experiments/crops/evaluate.py does.

A detected staff *matches* an editor's staff when both its top and bottom
are within half a staff space; an editor's staff none matches was
*missed* (the editor added it), a detected staff that matches none is
*false* (the editor deleted it). Then, each in staff spaces, against
what the editor set, an edit is counted where:
- *position*: the staff's top, bend included, is more than a quarter
  space off anywhere along it (the editor dragged or bent it);
- *left*: the left edge is more than a space off (SPEC's measure);
- *start*: the music start is more than 1.5 spaces off (SPEC's);
- *right*: the right end is more than a space off, where the editor
  would set it: a line running on past its last bar line, or detection's
  end well past or short of the editor's last bar line (an end near it
  the labeler moves to it once the bar lines are right);
- *above*, *below*: the crop is more than half a space off (crops.py's).
A staff with none of these needs no work.

Sources: every labels file under data/ (the edition's sources, the scan
archive's digitizations, and the paired manuscripts', under
data/paired/<path from home>), or those given.
"""

import argparse
import concurrent.futures as cf
import json
import os
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))
import crops  # noqa: E402
import detect  # noqa: E402
import labels  # noqa: E402
from score_barlines import RENDER_PX, render  # noqa: E402

HOME = Path.home()
EDITIONS = HOME / "Dropbox" / "Code"
EDITS = ("position", "left", "start", "right", "above", "below")
TOL = {"position": 0.25, "left": 1.0, "start": 1.5, "right": 1.0, "above": 0.5, "below": 0.5}


def pdf_for(lp: Path) -> Path:
    """A labels file's PDF: data/paired/<path from home>, else data/<edition>/<path in it>."""
    rel = lp.resolve().relative_to(ROOT / "data")
    base = HOME / Path(*rel.parts[1:]).parent if rel.parts[0] == "paired" else EDITIONS / rel.parent
    return base / (lp.name[: -len(".labels.json")] + ".pdf")


def room_before(doc: dict, n: int, aspect: float) -> float | None:
    """The clef-and-key room the editor set on their previous page of the part (app.js roomFromPreviousPage)."""
    for k in range(n - 1, 0, -1):
        p = doc["pages"].get(str(k))
        if p is None or p.get("kind") == "title":
            return None
        if p.get("kind") == "music" and p.get("status") != "auto":
            lines = sorted((s for s in p.get("systems", []) if (s.get("role") or "part") == "part"),
                           key=lambda s: s["top"])[1:]
            rooms = sorted(r for s in lines
                           if (r := ((s.get("start") or s["left"]) - s["left"]) / aspect / ((s["bottom"] - s["top"]) / 4)) > 1)
            return rooms[len(rooms) // 2] if rooms else None
    return None


def top_along(s: dict, xs) -> np.ndarray:
    return np.array([s["top"] + labels.bend_at(s, x) for x in xs])


def right_off(t: dict, d: dict, aspect: float, sp: float) -> float:
    """How far detection's right end is from where the editor would have to set it, in staff spaces. The
    labeler moves an end to the staff's last bar line itself once the bar lines are right (app.js
    followLastBarlines: within a quarter space short of it to a space past it), so a staff that ends
    there needs no staff edit even where detection's end differs; one that runs on past it (runs_on) does."""
    across = lambda a, b: abs(a - b) * aspect / sp
    last = max((b["x1"] for b in t.get("barlines", [])), default=None)
    if t.get("runs_on") or last is None:
        return across(t["right"], d["right"])
    past = (d["right"] - last) * aspect / sp  # detection's end beyond the editor's last bar line
    return 0.0 if -0.25 <= past <= 1.0 + TOL["right"] else across(t["right"], d["right"])


def compare(t: dict, d: dict, aspect: float) -> dict:
    """How far each of a detected staff's fields is from the editor's, in staff spaces."""
    sp = (t["bottom"] - t["top"]) / 4  # page heights
    xs = np.linspace(max(t["left"], d["left"]), min(t["right"], d["right"]), 9)
    across = lambda a, b: abs(a - b) * aspect / sp  # page widths -> staff spaces
    out = {"position": float(np.abs(top_along(t, xs) - top_along(d, xs)).max() / sp),
           "left": across(t["left"], d["left"]),
           "start": across(t.get("start") or t["left"], d.get("start") or d["left"]),
           "right": right_off(t, d, aspect, sp)}
    for side in ("above", "below"):
        if t.get(side) is not None:
            out[side] = abs(t[side] - d.get(side, 2.5))
            if f"learned_{side}" in d:
                out[f"learned_{side}"] = abs(t[side] - d[f"learned_{side}"])
    return out


def match(truth: list[dict], found: list[dict]) -> tuple[list, int, int]:
    """[(editor's staff, detected staff)], missed, false."""
    pairs, used = [], set()
    for t in truth:
        sp = (t["bottom"] - t["top"]) / 4
        i = next((i for i, d in enumerate(found) if i not in used and abs(d["top"] - t["top"]) < 0.5 * sp
                  and abs(d["bottom"] - t["bottom"]) < 0.5 * sp), None)
        if i is not None:
            used.add(i)
            pairs.append((t, found[i]))
    return pairs, len(truth) - len(pairs), len(found) - len(used)


def installed(pdf: Path, n: int, img: Image.Image) -> dict:
    """detect_page's learned parts as the labeler has them installed (server.Editor.detect): the
    bar-line filter and the detectors' cached votes and ends. They learned from the reviewed pages,
    these among them, so detection with them is the optimistic bound."""
    import detections
    import learn
    if "filter" not in INSTALLED:
        edition = EDITIONS / "boccherini-opus-48"
        rend = lambda f, k: Image.open(render(f, k, RENDERS))
        INSTALLED["filter"] = learn.load_or_train(edition, detections.cache_dir(), rend, labels.DATA,
                                                  EDITIONS / "boccherini-sources")
    edition = EDITIONS / "boccherini-opus-48"
    root, name = (edition, str(pdf.relative_to(edition))) if pdf.is_relative_to(edition) else (pdf.parent, pdf.name)
    preds = detections.page_predictions(root, name, n, detections.cache_dir())
    w, h = img.size
    return {"model": INSTALLED["filter"], "vote": detections.make_vote(preds, w, h) if preds else None,
            "ends": detections.make_ends(preds, w, h) if preds else None}


INSTALLED: dict = {}
RENDERS = Path(os.environ.get("TMPDIR", "/tmp")) / f"score_staves-{RENDER_PX}"


def page_work(args):
    pdf, n, page, room, renders, model, use_installed = args
    path = renders / f"{pdf.stem}-p{n}.jpg"
    img = Image.open(path) if path.exists() else render(pdf, n, renders)
    img.load()
    w, h = img.size
    # the editor's corners, as the labeler sends them once set, else detected
    corners = (page.get("corners") or {}).get("points") or detect.find_page_corners(img)
    systems = detect.detect_page(img, room, corners=corners, **(installed(pdf, n, img) if use_installed else {}))
    if model is not None and systems:
        learned = [dict(s) for s in systems]
        crops.propose(detect._gray(img), learned, model)
        for s, l in zip(systems, learned):
            s["learned_above"], s["learned_below"] = l["above"], l["below"]
    truth = [s for s in page["systems"] if (s.get("role") or "part") == "part"]
    pairs, missed, false = match(truth, systems)
    return {"source": pdf.stem, "page": n, "staves": len(truth), "missed": missed, "false": false,
            "found": [compare(t, d, h / w) for t, d in pairs]}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("labels", nargs="*", type=Path)
    ap.add_argument("--renders", type=Path,
                    default=Path(os.environ.get("TMPDIR", "/tmp")) / f"score_staves-{RENDER_PX}")
    ap.add_argument("--out", type=Path, help="write per-page results as JSON")
    ap.add_argument("--no-learned-crops", action="store_true")
    ap.add_argument("--installed", action="store_true",
                    help="with the labeler's installed bar-line filter and detectors (learned from these pages: optimistic)")
    ap.add_argument("--jobs", type=int, default=6)
    a = ap.parse_args()
    a.renders.mkdir(parents=True, exist_ok=True)
    files = a.labels or sorted((ROOT / "data").glob("**/*.labels.json"))
    pages = []  # (pdf, n, page, room)
    for f in files:
        doc = labels.migrate(json.loads(f.read_text()))
        pdf = pdf_for(f)
        mine = [(int(n), p) for n, p in doc["pages"].items() if p.get("status") == "reviewed" and p.get("kind") == "music"]
        if mine and not pdf.exists():
            print(f"skipped {f.name}: {len(mine)} reviewed pages, but no {pdf}", file=sys.stderr)
            continue
        for n, p in sorted(mine, key=lambda x: x[0]):
            path = a.renders / f"{pdf.stem}-p{n}.jpg"
            img = Image.open(path) if path.exists() else render(pdf, n, a.renders)
            pages.append((pdf, n, p, room_before(doc, n, img.size[1] / img.size[0])))

    # the learned crop model, one per source: trained on every other source's reviewed crops
    models = {}
    if not a.no_learned_crops:
        gray = lambda pdf, n: detect._gray(Image.open(a.renders / f"{pdf.stem}-p{n}.jpg"))
        with_crops = [(pdf, n, p) for pdf, n, p, _ in pages if any("above" in s and "below" in s for s in p["systems"])]
        for src in sorted({pdf.stem for pdf, *_ in pages}):
            rest = [x for x in with_crops if x[0].stem != src]
            models[src] = crops.train(rest, gray, crops.OLDER_CROPS) if rest else None
            print(f"crop model without {src}: {len(rest)} pages", file=sys.stderr, flush=True)

    if a.installed:  # trained (or loaded) once, before the pages go out to threads
        installed(*pages[0][:2], Image.open(a.renders / f"{pages[0][0].stem}-p{pages[0][1]}.jpg"))
    jobs = [(pdf, n, p, room, a.renders, models.get(pdf.stem), a.installed) for pdf, n, p, room in pages]
    with cf.ThreadPoolExecutor(a.jobs) as pool:
        res = list(pool.map(page_work, jobs))
    if a.out:
        a.out.write_text(json.dumps(res, indent=1, default=str))

    by = defaultdict(list)
    for r in res:
        by[r["source"]].append(r)
    cols = EDITS + (() if a.no_learned_crops else ("learned above", "learned below"))
    print(f"{'source':28s} pages staves missed false  " + " ".join(f"{c:>9s}" for c in cols) + "  no work")
    for src, rs in sorted(by.items()) + [("all", res)]:
        found = [f for r in rs for f in r["found"]]
        c = Counter()
        for f in found:
            for e in EDITS:
                c[e] += f.get(e, 0) > TOL[e]
            for side in ("above", "below"):
                c[f"learned {side}"] += f.get(f"learned_{side}", 0) > TOL[side]
        clean = sum(all(f.get(e, 0) <= TOL[e] for e in EDITS[:4]) and
                    all(f.get(k, 0) <= TOL[s] for s in ("above", "below")
                        for k in ([f"learned_{s}"] if not a.no_learned_crops else [s]))
                    for f in found)
        staves = sum(r["staves"] for r in rs)
        pct = lambda k: f"{100 * c[k] / max(1, len(found)):8.0f}%"
        print(f"{src:28s} {len(rs):5d} {staves:6d} {sum(r['missed'] for r in rs):6d} {sum(r['false'] for r in rs):5d}  "
              + " ".join(pct(k) for k in cols) + f"  {100 * clean / max(1, len(found)):6.0f}%")


if __name__ == "__main__":
    main()
