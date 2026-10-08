"""Bar-line detectors' cached predictions, and the vote that uses them.

tools/predict_barlines.py runs the installed detectors (YOLO) on every page
ahead of time and writes their predictions to the cache; detection in the
labeler (detect.detect_page, `vote`) then votes them with its own bar lines
(the learned filter's, or the hand-tuned rules' before any page is
reviewed), staff by staff, before the staff's end is decided: a bar line
is kept if most of the voters propose it. It needs at least two detectors
(three voters, as measured); without them, or without cached predictions
for a page, detection is unchanged. Measured end to end in experiments/barlines
(e2e_vote.py, results.md): any vote with a YOLO halves the errors on
familiar hands and cuts them by about three-quarters on a new copy.

Cache layout (under ~/.cache/manuscript-labeler or $MANUSCRIPT_LABELER_CACHE):
  models/detectors/<name>/best.pt, manifest.json   {name, sha, threshold, ...}
  detections/<key>/<edition>/<pdf path>.json       one detector, one PDF
where <key> names the detector, its weights and threshold, and VERSION.
"""

import hashlib
import json
import os
from pathlib import Path

import labels

VERSION = 3       # of the crops and the files: bump when either changes (3: staves' starts and ends)
TOLERANCE = 0.006  # page widths: proposals this close are one bar line (as the bake-off scores)
REACH = 1.0       # staff spaces past a staff's right end a detector's bar line may be
                  # (none before its left end: a bar line doesn't precede the clef)
MATCH = 0.015     # page heights: a cached staff and a detected one this close are the same
ENDS_CONF = 0.25  # a detector's start or end box this sure sets a staff's ends


def cache_dir() -> Path:
    return Path(os.environ.get("MANUSCRIPT_LABELER_CACHE", Path.home() / ".cache" / "manuscript-labeler"))


def detectors(cache: Path | None = None) -> list[dict]:
    """The installed detectors' manifests, each with its cache `key`."""
    out = []
    for m in sorted(((cache or cache_dir()) / "models" / "detectors").glob("*/manifest.json")):
        try:
            d = json.loads(m.read_text())
        except (ValueError, OSError):
            continue
        d["weights"] = m.parent / "best.pt"
        d["key"] = f"{d['name']}-{d['sha'][:8]}-t{d['threshold']}-v{VERSION}"
        out.append(d)
    return out


def pdf_identity(pdf: Path) -> str:
    st = pdf.stat()
    return f"{st.st_size}:{st.st_mtime_ns}"


def cache_file(det: dict, edition: Path, rel: str, cache: Path | None = None) -> Path:
    """The predictions of one detector for one PDF of one edition."""
    root = edition.resolve()
    ed = f"{root.name}-{hashlib.sha1(str(root).encode()).hexdigest()[:8]}"
    return (cache or cache_dir()) / "detections" / det["key"] / ed / (rel.replace("/", "__") + ".json")


_DOCS: dict[Path, tuple[int, dict]] = {}  # parsed cache files, by path, with their mtime


def _load(f: Path) -> dict | None:
    try:
        mtime = f.stat().st_mtime_ns
    except OSError:
        return None
    hit = _DOCS.get(f)
    if hit and hit[0] == mtime:
        return hit[1]
    try:
        doc = json.loads(f.read_text())
    except (ValueError, OSError):
        return None
    if len(_DOCS) > 64:
        _DOCS.clear()
    _DOCS[f] = (mtime, doc)
    return doc


def page_predictions(edition: Path, rel: str, page: int, cache: Path | None = None) -> list[tuple[dict, list]]:
    """[(detector, its cached staves)] for one page: only detectors whose
    file is for this very PDF (same size and date) and has the page."""
    ident = pdf_identity(edition / rel)
    out = []
    for d in detectors(cache):
        doc = _load(cache_file(d, edition, rel, cache))
        pages = doc.get("pages") if isinstance(doc, dict) else None
        p = pages.get(str(page)) if isinstance(pages, dict) else None
        if doc and doc.get("pdf_identity") == ident and isinstance(p, dict) and isinstance(p.get("staves"), list):
            out.append((d, p["staves"]))
    return out


def has_predictions(edition: Path, cache: Path | None = None) -> list[str]:
    """The installed detectors with cached predictions for some PDF of this edition."""
    out = []
    for d in detectors(cache):
        folder = cache_file(d, edition, "x.pdf", cache).parent
        if folder.is_dir() and any(folder.glob("*.json")):
            out.append(d["name"])
    return out


def vote(proposals: dict[str, list[float]], tol: float, need: int) -> list[float]:
    """Bar lines (x) proposed by at least `need` of the voters: their
    proposals pooled, those within `tol` of a group's first one merged, a
    group kept at its mean if `need` voters are in it."""
    pts = sorted((x, m) for m, xs in proposals.items() for x in xs)
    groups: list[list] = []
    for x, m in pts:
        if groups and x - groups[-1][0][0] <= tol:
            groups[-1].append((x, m))
        else:
            groups.append([(x, m)])
    return [sum(x for x, _ in g) / len(g) for g in groups if len({m for _, m in g}) >= need]


def make_vote(preds: list[tuple[dict, list]], w: int, h: int):
    """detect.detect_page's `vote` step for one page, from its cached
    predictions (page_predictions); `w`, `h` the page's size in pixels.

    For a staff: its own bar lines (straightened-staff pixels) and, from the
    cached staff at its height, each detector's bar lines above its
    threshold, from the staff's left end to a staff space past its right
    end (and within the paper). With fewer than three voters the staff's
    own bar lines stand. A bar line kept by the vote is its own bar line
    (position, lean and kind) if one is within the tolerance, each used
    once; otherwise it's fitted to the stroke (detect.snap_barline), or
    upright where there's none, and dropped if it lands on one already
    kept."""
    import detect

    tol = TOLERANCE * w

    def mid(b):
        return (b["x0"] + b["x1"]) / 2

    def step(st, band, local, bars, left, right, paper):
        voters = {"own": [mid(b) for b in bars]}
        lo, hi = left, min(right + REACH * st["gap"], paper[1])
        for d, staves in preds:
            c = _matched(staves, st, h)
            if c is None or not isinstance(c.get("bars"), list):
                continue
            voters[d["name"]] = [x * w for x, conf in c["bars"] if conf >= d["threshold"] and lo <= x * w <= hi]
        if len(voters) < 3:
            return bars
        out, used = [], set()
        for x in vote(voters, tol, len(voters) // 2 + 1):
            mine = [(abs(mid(b) - x), i) for i, b in enumerate(bars) if i not in used and abs(mid(b) - x) <= tol]
            if mine:
                i = min(mine)[1]
                used.add(i)
                out.append(bars[i])
                continue
            fit = detect.snap_barline(band, local["top"], local["bottom"], x, x)
            out.append({"x0": fit["x0"], "x1": fit["x1"], "kind": "single", "new": True} if fit
                       else {"x0": x, "x1": x, "kind": "single", "new": True})
        # a fitted bar line can land on another kept one: one each, its own first
        kept: list[dict] = []
        for b in sorted(out, key=mid):
            if kept and abs(mid(b) - mid(kept[-1])) <= tol:
                if kept[-1].get("new") and not b.get("new"):
                    kept[-1] = b
                continue
            kept.append(b)
        return [{k: v for k, v in b.items() if k != "new"} for b in kept]
    return step


def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _matched(staves: list, st: dict, h: int) -> dict | None:
    """The cached staff at the height of a detected one, if any."""
    near = [c for c in staves if isinstance(c, dict) and isinstance(c.get("top"), (int, float))]
    c = min(near, key=lambda c: abs(c["top"] - st["top"] / h), default=None)
    return c if c is not None and abs(c["top"] - st["top"] / h) <= MATCH else None


def make_ends(preds: list[tuple[dict, list]], w: int, h: int):
    """detect.detect_page's `ends` step for one page, from its cached
    predictions: for a staff, {"left", "start", "right"} in pixels, each
    from the surest detector's box at the staff's height (at least
    ENDS_CONF): "start" boxes give the left end and music start, "end"
    boxes the right end. Empty where no detector has a sure one; only
    detectors that learned the staff's ends (corpus.py --paper) have them.
    A start with the same detector's sure bar lines before it is mid-line
    (a new movement's clef and key) and not the staff's: taking it would
    drop every bar line before it. The rules' start stands there. (A
    distance from the rules' left end, tried first, also turned away good
    starts wherever the rules began a staff at a text or brace.)"""
    def ends(st: dict) -> dict:
        out, sure = {}, {}
        for d, staves in preds:
            c = _matched(staves, st, h)
            if c is None:
                continue
            s, e = c.get("start"), c.get("end")
            nums = lambda v, n: isinstance(v, list) and len(v) == n and all(_num(x) for x in v)
            bars = c["bars"] if isinstance(c.get("bars"), list) else []
            before = nums(s, 3) and any(nums(b, 2) and b[1] >= d.get("threshold", 0)
                                        and b[0] * w < s[0] * w - st.get("gap", 0) for b in bars)
            if nums(s, 3) and not before and s[2] >= ENDS_CONF and s[2] > sure.get("start", 0):
                sure["start"] = s[2]
                out["left"], out["start"] = s[0] * w, s[1] * w
            if nums(e, 2) and e[1] >= ENDS_CONF and e[1] > sure.get("end", 0):
                sure["end"] = e[1]
                out["right"] = e[0] * w
        return out
    return ends
