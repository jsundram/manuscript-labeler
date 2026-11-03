# /// script
# requires-python = ">=3.11"
# dependencies = ["pymupdf", "pillow"]
# ///
"""Staves the new pairing rules gained or lost, to check by eye: each staff's
crop with its detected bar lines, and its bars under the old pairing and the
new one (data.json, read by index.html's builder below).

    uv run reports/2026-11-03-pairing-recheck/build.py <old results dir> > reports/2026-11-03-pairing-recheck/index.html

<old results dir>: experiments/zeus/results as it was at 1ea3e2f, re-run with
the same options (a worktree's). The new results are the repo's.
"""

import base64
import io
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

import fitz
from PIL import Image

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parents[1] / "experiments" / "zeus"
EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"
ARCHIVE = Path.home() / "Dropbox/Code/boccherini-sources"
LABELER = "http://localhost:8050/"
PICK = {"an end measure shorter than its bar": 4, "an end measure longer than its bar": 4,
        "below a mis-measured staff on its page": 3, "mis-measured": 2, "extra": 1}
LOST = 7


def why(nk):
    return nk["why"][0].split(" [")[0].split(": ")[0].split(" at ")[0]


def source_id(pdf: Path) -> str:
    """The labeler's name for a source (server.py rel)."""
    p = pdf.resolve()
    if p.is_relative_to(EDITION):
        return p.relative_to(EDITION).as_posix()
    if p.is_relative_to(ARCHIVE):
        return "archive:" + p.relative_to(ARCHIVE).as_posix()
    return "paired:" + p.relative_to(Path.home()).as_posix()


def staves(auto):
    """Staff name -> its detected system, and every staff in page order."""
    geo, order = {}, []
    for n in sorted(auto["pages"], key=int):
        page = auto["pages"][n]
        for k, s in enumerate(sorted(page["systems"], key=lambda s: s["top"])):
            name = f"p{n}-{k}"
            geo[name] = dict(s, page=int(n), part=s.get("part") or page.get("part"))
            order.append(name)
    return geo, order


def label(bars, cont=False):
    if not bars:
        return "—"
    m, first = bars[0][-2:]
    last = bars[-1][-1]
    s = f"{m} {first}" if first == last else f"{m} {first}–{last}"
    return s + (" →" if cont else "")


def measures(rec):
    """The bars of each measure the reader read, as labels."""
    if rec is None:
        return None
    if "boxes" in rec:
        return [label(b["bars"], b.get("continues")) for b in rec["boxes"]]
    return [label([b]) for b in rec.get("bars", [])]


def crop(doc, s, width=1500):
    page = doc[s["page"] - 1]
    r = page.rect
    h = s["bottom"] - s["top"]
    box = (max(0, s["left"] - 0.015), max(0, s["top"] - 1.1 * h), min(1, s["right"] + 0.015), min(1, s["bottom"] + 1.1 * h))
    clip = fitz.Rect(r.x0 + box[0] * r.width, r.y0 + box[1] * r.height, r.x0 + box[2] * r.width, r.y0 + box[3] * r.height)
    zoom = width / clip.width
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), clip=clip, colorspace=fitz.csGRAY)
    im = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=62, optimize=True)
    xs = [((b["x0"] + b["x1"]) / 2 - box[0]) / (box[2] - box[0]) for b in s.get("barlines", [])]
    start = (s.get("start", s["left"]) - box[0]) / (box[2] - box[0])
    right = (s["right"] - box[0]) / (box[2] - box[0])
    return {"src": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(),
            "w": pix.width, "h": pix.height, "barlines": [round(x, 4) for x in xs],
            "start": round(start, 4), "right": round(right, 4)}


def describe(rec, kept):
    if rec is None:
        return {"status": "absent"}
    if kept:
        return {"status": "kept", "measures": measures(rec), "steps": rec.get("steps"),
                "worst": rec.get("worst"), "bar_boxes": rec.get("bar_boxes")}
    return {"status": "not kept", "measures": measures(rec), "steps": rec.get("steps"), "why": rec.get("why")}


def main(old_dir: Path):
    rng = random.Random(20261103)
    gained, lost = defaultdict(list), []
    runs = {}
    for f in sorted(old_dir.glob("autopair-*musvit-D3S-h96.json")):  # one reader per source
        new = ZEUS / "results" / f.name
        o, w = json.loads(f.read_text()), json.loads(new.read_text())
        if "not kept" not in o or "not kept" not in w:
            continue
        runs[f.name] = (o, w)
        ko = {x["staff"]: x for x in o["kept"]}
        kn = {x["staff"]: x for x in w["kept"]}
        oo = {x["staff"]: x for x in o["not kept"]}
        nn = {x["staff"]: x for x in w["not kept"]}
        for s in sorted(set(kn) - set(ko)):
            gained[why(oo[s])].append((f.name, s))
        for s in sorted(set(ko) - set(kn)):
            lost.append((f.name, s, why(nn[s])))

    def spread(items, n):
        """n items, from as many sources as can be."""
        by = defaultdict(list)
        for it in items:
            by[it[0]].append(it)
        for v in by.values():
            rng.shuffle(v)
        keys = sorted(by)
        rng.shuffle(keys)
        out = []
        while len(out) < n and any(by.values()):
            for k in keys:
                if by[k] and len(out) < n:
                    out.append(by[k].pop())
        return out

    picks = [("gained", r, it) for r, n in PICK.items() for it in spread(gained[r], n)]
    picks += [("lost", it[2], it) for it in spread(lost, LOST)]

    docs, autos, items = {}, {}, []
    for kind, reason, (fname, staff, *_) in picks:
        o, w = runs[fname]
        src = w["source"]
        if src not in autos:
            autos[src] = json.loads((ZEUS / "auto" / f"{src}.json").read_text())
            autos[src]["geo"], autos[src]["order"] = staves(autos[src])
            docs[src] = fitz.open(autos[src]["pdf"])
        a = autos[src]
        geo = a["geo"]

        ko = {x["staff"]: x for x in o["kept"]}; oo = {x["staff"]: x for x in o["not kept"]}
        kn = {x["staff"]: x for x in w["kept"]}; nn = {x["staff"]: x for x in w["not kept"]}
        ro, rn = ko.get(staff) or oo.get(staff), kn.get(staff) or nn.get(staff)
        bars = (rn or ro or {}).get("bars") or []
        items.append({"kind": kind, "reason": reason, "source": src, "staff": staff, "part": geo[staff]["part"],
                      "page": geo[staff]["page"], "work": bars[0][0] if bars and len(bars[0]) == 3 else "",
                      "link": f"{LABELER}#pdf={quote(source_id(Path(a['pdf'])), safe='/:')}&page={geo[staff]['page']}",
                      "old": describe(ro, staff in ko), "new": describe(rn, staff in kn),
                      "img": crop(docs[src], geo[staff])})
        print(f"{kind} {src} {staff}", file=sys.stderr)

    totals = {"gained": sum(len(v) for v in gained.values()), "lost": len(lost),
              "gained_by": sorted(((k, len(v)) for k, v in gained.items()), key=lambda kv: -kv[1])}
    page = (HERE / "page.html").read_text()
    print(page.replace("/*DATA*/null", json.dumps({"items": items, "totals": totals})))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
