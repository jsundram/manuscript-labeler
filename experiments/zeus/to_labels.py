"""Start a paired archive manuscript's labels from what the pairing found,
so the editor reviews in the labeler instead of labelling from scratch.

    uv run experiments/zeus/to_labels.py G213-KHM587            # what it would add
    uv run experiments/zeus/to_labels.py G213-KHM587 --apply    # add it (reload the labeler's tab after)

Input: auto/<source>.json (autodetect.py: the staves and bar lines detection
found, the page's part) and the pairing's results (autopair.py's kept
staves with "boxes": the bars each bar box holds; by default
results/autopair-<source>-final.json). The PDF must be in the archive
(boccherini-sources): the labeler's --archive mode.

For each part page the labels file doesn't have yet (with --redo-auto, also
each page still as detection left it, status auto):
- the page's part and its usual clef;
- the staves and bar lines detection found, all marked auto, as the
  labeler's own detection marks them;
- on each staff the pairing kept whose bar boxes match its bar lines, each
  bar line's count from the bars its box holds: a pickup or the second half
  of a bar a repeat splits counts 0, a multi-bar rest its bars; the
  movement's last bar line marked as ending it;
- where the staff's last box runs on to the next staff (a bar the line
  breaks), the staff runs on (on a staff the pairing didn't keep, too); where its last bar ends at the staff's end
  and detection missed the closing bar line, one on the stroke there, if
  there is a stroke (detect.snap_barline).

Pages already in the labels file are left as they are (but --redo-auto).
The file is written atomically, refused if it changed while this ran, and
backed up first.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELER = HERE.parents[1]
sys.path.insert(0, str(LABELER))
import detect  # noqa: E402
import labels  # noqa: E402
import server  # noqa: E402

ARCHIVE = Path.home() / "Dropbox/Code/boccherini-sources"
EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"
CLEF = {"vn1": "treble", "vn2": "treble", "va": "alto", "vc": "bass", "va2": "alto"}
SYSTEM_FIELDS = ("top", "bottom", "left", "right", "start", "bend", "above", "below")


def number_staff(s: dict, boxes: list[dict], space: float) -> tuple[list[dict], bool, str | None]:
    """A kept staff's bar lines numbered from its boxes; whether it runs on
    (else the music ends at its last bar line); and why it couldn't be
    numbered (None if it was). Bar boxes as
    autopair.boxes finds them: one per bar line past the music start, and one
    more when music runs on past the last. Where they don't match, as the
    editor fixed them on KHM 587: a bar line stacked on another (within 1.5
    staff spaces) is one; a box holding both halves of a bar a repeat splits
    may have the repeat's bar line inside it; and staff past the last bar
    line may be empty, the music ended."""
    mid = lambda b: (b["x0"] + b["x1"]) / 2
    bls = []
    for b in sorted(s["barlines"], key=mid):
        if not bls or mid(b) - mid(bls[-1]) >= 1.5 * space:
            bls.append(b)
    counted = [b for b in bls if mid(b) > s["start"] + space]
    trailing = not counted or s["right"] - mid(counted[-1]) > 1.5 * space
    halves = []
    for box in boxes:
        halves += [{**box, "ends_movement": False}, {**box, "count": 0}] if box.get("join") else [box]
    tries = [(boxes, trailing), (halves, trailing)]
    if trailing and counted:
        tries += [(boxes, False), (halves, False)]
    for bx, trail in tries:
        if len(counted) + trail == len(bx):
            break
    else:
        return bls, False, f"{len(boxes)} boxes paired, {len(counted) + trailing} found"
    for b in bls:
        b["bar_count"], b["ends_movement"] = 0, False  # a bar line at the music start counts none
    for b, box in zip(counted, bx):
        b["bar_count"], b["ends_movement"] = box["count"], box["ends_movement"]
    runs_on = False
    if trail:
        last = bx[-1]
        if last["continues"]:
            runs_on = True
        elif last["count"] or last["ends_movement"]:
            bls.append({"x0": s["right"], "x1": s["right"], "kind": "single", "auto": True,
                        "bar_count": last["count"], "ends_movement": last["ends_movement"], "closing": True})
    return bls, runs_on, None


def build(doc: dict, auto: dict, final: dict, gray, redo_auto: bool) -> tuple[dict, list[str]]:
    """The labels with the pairing's pages added; `gray(page)` the page's
    grayscale image, for the closing bar lines' strokes."""
    kept = {k["staff"]: k for k in final["kept"]}
    not_kept = {k["staff"]: k for k in final["not kept"]}
    out, notes = json.loads(json.dumps(doc)), []
    for n, page in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
        if n in out["pages"] and not (redo_auto and out["pages"][n].get("status") == "auto"):
            notes.append(f"p{n}: already labelled, left as it is")
            continue
        if page["part"] not in CLEF:
            notes.append(f"p{n}: a {page['part']} page, left for the labeler")
            continue
        g = None
        systems = []
        order = sorted(range(len(page["systems"])), key=lambda i: page["systems"][i]["top"])
        paired = ended = closed = no_stroke = 0
        for k, i in enumerate(order, 1):
            s = page["systems"][i]
            sid = f"p{n}s{k}"
            st = {"id": sid, "auto": True, **{f: s[f] for f in SYSTEM_FIELDS if f in s}}
            bls = [{"x0": b["x0"], "x1": b["x1"], "kind": b.get("kind", "single"), "auto": True,
                    "bar_count": 1, "ends_movement": False} for b in s["barlines"]]
            pair = kept.get(f"p{n}-{i}")
            if pair and "boxes" in pair:
                g = gray(int(n)) if g is None else g
                h, w = g.shape
                space = (s["bottom"] - s["top"]) / 4 * h / w  # a staff space, in page widths
                found = bls
                bls, runs_on, why = number_staff({**s, "barlines": bls}, pair["boxes"], space)
                if why:
                    notes.append(f"{sid}: {why}; left unnumbered")
                    bls = found
                else:
                    paired += 1
                    ends_at_line = not runs_on
                    if runs_on:
                        st["runs_on"] = True
                    for b in [b for b in bls if b.pop("closing", False)]:
                        r = detect.snap_barline(g, s["top"] * h, s["bottom"] * h, b["x0"] * w, b["x1"] * w, reach=1.0)
                        if r:
                            b["x0"], b["x1"] = r["x0"] / w, r["x1"] / w
                            closed += 1
                        else:  # no stroke at the end: leave it for the editor
                            bls.remove(b)
                            no_stroke += 1
                            ends_at_line = False
                            notes.append(f"{sid}: its last bar ends at the staff's end, but no stroke there")
                    if ends_at_line and bls:  # the staff too, as the labeler's End at last bar line
                        st["right"] = min(1.0, max(max(b["x0"], b["x1"]) for b in bls) + 0.5 * space)
                    ended += sum(b["ends_movement"] for b in bls)
            elif pair:
                notes.append(f"{sid}: paired, but the pairing has no boxes (re-run autopair.py)")
            elif (nk := not_kept.get(f"p{n}-{i}")) and nk.get("boxes") and nk["boxes"][-1]["continues"]:
                # not kept, its bars unsure; but its last bar runs on to the next staff's
                st["runs_on"] = True
            bls.sort(key=lambda b: (b["x0"] + b["x1"]) / 2)
            st["barlines"] = [{"id": f"{sid}b{j}", **b} for j, b in enumerate(bls, 1)]
            systems.append(st)
        out["pages"][n] = {"status": "auto", "kind": "music", "part": page["part"], "clef": CLEF[page["part"]],
                           "notes": "", "systems": systems, "marks": []}
        notes.append(f"p{n} {page['part']}: {len(systems)} staves, {sum(len(s['barlines']) for s in systems)} bar lines; "
                     f"{paired} numbered from the pairing, {closed} closing bar lines added"
                     + (f" ({no_stroke} without a stroke left out)" if no_stroke else "") + f", {ended} movement ends")
    return out, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source", help="auto/<source>.json")
    ap.add_argument("--results", type=Path, help="the pairing (default: results/autopair-<source>-final.json)")
    ap.add_argument("--redo-auto", action="store_true",
                    help="also redo the pages still as detection left them (status auto)")
    ap.add_argument("--apply", action="store_true", help="write the labels file (default: only say what it would add)")
    a = ap.parse_args()
    auto = json.loads((HERE / "auto" / f"{a.source}.json").read_text())
    final = json.loads((a.results or HERE / "results" / f"autopair-{a.source}-final.json").read_text())
    ed = server.Edition(EDITION, Path.home() / ".cache/manuscript-labeler", archive=ARCHIVE)
    pdf = Path(auto.get("pdf", ""))
    if not ed.archived(pdf):
        sys.exit(f"{a.source}: its PDF is not in the archive ({ARCHIVE})")
    rel = ed.rel(pdf)
    lp = ed.labels_path(pdf)
    raw = lp.read_bytes() if lp.exists() else None
    doc = labels.migrate(json.loads(raw)) if raw else labels.new_doc(ed.info(rel)["source"])
    new, notes = build(doc, auto, final, lambda n: ed.gray(rel, n), a.redo_auto)
    print("\n".join(notes))
    errs = labels.validate(new)
    if errs:
        sys.exit("not valid: " + "; ".join(errs[:5]))
    by = {}
    for b in labels.number_bars(new):
        by[(b["part"], b["movement"])] = by.get((b["part"], b["movement"]), 0) + b["count"]
    print("bars counted, by part and movement:", ", ".join(f"{p} {m} {c}" for (p, m), c in sorted(by.items())))
    if not a.apply:
        print("(not written: --apply writes it)")
        return
    if (lp.read_bytes() if lp.exists() else None) != raw:
        sys.exit("the labels file changed while this ran; not written")
    if raw:
        bk = ed.cache / "backups" / "to_labels"
        bk.mkdir(parents=True, exist_ok=True)
        shutil.copy(lp, bk / time.strftime(f"{lp.stem}-%Y%m%d-%H%M%S.json"))
    lp.parent.mkdir(parents=True, exist_ok=True)
    server.atomic_write(lp, server.dump(labels.round_floats(new)))
    server.atomic_write(ed.bars_path(pdf), server.dump(labels.round_floats(labels.bars_export(new))))
    print(f"wrote {lp}: reload the labeler's tab")


if __name__ == "__main__":
    main()
