"""Start KHM 587's labels from what the G. 213 pairing already found, so the
editor reviews in the labeler instead of labelling from scratch.

    uv run experiments/zeus/g213/to_labels.py            # what it would add
    uv run experiments/zeus/g213/to_labels.py --apply    # add it (reload the labeler's tab after)

For each page of the page map that the labels file doesn't have yet:
- the page's part and its usual clef;
- the staves and bar lines detection found (auto/G213-KHM587.json), all
  marked auto, as the labeler's own detection marks them;
- for the staves the pairing kept (results/autopair-G213-KHM587-final.json,
  one bar box to one bar of OSSQ's encoding): a closing bar line at the
  staff's end where detection missed it, a pickup's bar line counted 0,
  and a movement's last bar line marked as ending it.

Pages already in the labels file are left as they are. The file is written
atomically, refused if it changed while this ran, and backed up first.
"""

import argparse
import json
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
LABELER = HERE.parents[2]
sys.path.insert(0, str(LABELER))
import labels  # noqa: E402
import server  # noqa: E402

PDF = "archive:digitizations/G213/463058700_D-B/463058700_D-B.pdf"
ARCHIVE = Path.home() / "Dropbox/Code/boccherini-sources"
EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"
CLEF = {"vn1": "treble", "vn2": "treble", "va": "alto", "vc": "bass"}
SYSTEM_FIELDS = ("top", "bottom", "left", "right", "start", "bend", "above", "below")


def movement_ends(structure: Path) -> dict[str, int]:
    """Each movement's last bar number, from the G. 213 Structure.ily."""
    return {m: e["total"] for m, e in labels.parse_structure(structure.read_text()).items()}


def build(doc: dict, auto: dict, final: dict, ends: dict[str, int]) -> tuple[dict, list[str]]:
    kept = {k["staff"]: k for k in final["kept"]}
    out, notes = json.loads(json.dumps(doc)), []
    for n, page in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
        if n in out["pages"]:
            notes.append(f"p{n}: already labelled, left as it is")
            continue
        systems = []
        order = sorted(range(len(page["systems"])), key=lambda i: page["systems"][i]["top"])
        paired = ended = 0
        for k, i in enumerate(order, 1):
            s = page["systems"][i]
            sid = f"p{n}s{k}"
            bls = sorted(s["barlines"], key=lambda b: (b["x0"] + b["x1"]) / 2)
            barlines = [{"id": f"{sid}b{j}", "x0": b["x0"], "x1": b["x1"], "kind": b.get("kind", "single"),
                         "auto": True, "bar_count": 1, "ends_movement": False} for j, b in enumerate(bls, 1)]
            pair = kept.get(f"p{n}-{i}")
            if pair and len(pair["bars"]) == len(barlines) + 1:
                # the pairing counted a last bar running to the staff's end (autopair.boxes) and
                # kept the staff as whole bars: its closing bar line, which detection missed
                barlines.append({"id": f"{sid}b{len(barlines) + 1}", "x0": s["right"] - 0.002, "x1": s["right"] - 0.002,
                                 "kind": "single", "auto": True, "bar_count": 1, "ends_movement": False})
            if pair and len(pair["bars"]) == len(barlines):  # bar box j ends at bar line j
                paired += 1
                for b, (mvt, bar) in zip(barlines, pair["bars"]):
                    b["bar_count"] = 0 if bar == 0 else 1
                    if bar == ends.get(mvt):
                        b["ends_movement"] = True
                        ended += 1
            elif pair:
                notes.append(f"p{n}s{k}: paired with {len(pair['bars'])} bars but has {len(barlines)} bar lines; left unnumbered")
            systems.append({"id": sid, "auto": True, **{f: s[f] for f in SYSTEM_FIELDS if f in s}, "barlines": barlines})
        out["pages"][n] = {"status": "auto", "kind": "music", "part": page["part"], "clef": CLEF[page["part"]],
                           "notes": "", "systems": systems, "marks": []}
        notes.append(f"p{n} {page['part']}: {len(systems)} staves, {sum(len(s['barlines']) for s in systems)} bar lines; "
                     f"{paired} staves numbered from the pairing, {ended} movement ends")
    return out, notes


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--apply", action="store_true", help="write the labels file (default: only say what it would add)")
    a = ap.parse_args()
    ed = server.Edition(EDITION, Path.home() / ".cache/manuscript-labeler", archive=ARCHIVE)
    pdf = ed.pdf(PDF)
    lp = ed.labels_path(pdf)
    raw = lp.read_bytes() if lp.exists() else None
    doc = labels.migrate(json.loads(raw)) if raw else labels.new_doc(ed.info(PDF)["source"])
    auto = json.loads((HERE.parent / "auto/G213-KHM587.json").read_text())
    final = json.loads((HERE.parent / "results/autopair-G213-KHM587-final.json").read_text())
    sp = ed.structure_file(PDF, ed.info(PDF)["display"]["work"])
    if sp is None:
        sys.exit("no G. 213 Structure.ily (experiments/zeus/g213/structure.py writes it)")
    new, notes = build(doc, auto, final, movement_ends(sp))
    print("\n".join(notes))
    errs = labels.validate(new)
    if errs:
        sys.exit("not valid: " + "; ".join(errs[:5]))
    nb = labels.number_bars(new)
    by = {}
    for b in nb:
        by.setdefault((b["part"], b["movement"]), 0)
        by[(b["part"], b["movement"])] += b["count"]
    print("bars counted, by part and movement:", ", ".join(f"{p} {m} {c}" for (p, m), c in sorted(by.items())))
    print("expected from the structure:", ", ".join(f"{m} {t}" for m, t in movement_ends(sp).items()))
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
