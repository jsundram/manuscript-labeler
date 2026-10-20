# /// script
# requires-python = ">=3.10"
# dependencies = [
#   # the LMX writer Zeus uses, at Zeus's pin (dataset.py's labels are written with it)
#   "linearized-musicxml @ git+https://github.com/OMR-Research/lmx.git@87fca1c38bda83bc032596ab00af28412f92941d",
#   "numpy", "pillow",
# ]
# ///
"""All of Philhar's quartet encodings as staff-length lines of one part, written as our training labels are
(dataset.py's staff_part and its check), for drawing (philhar_render.py).

- Paired: the staves autopair.py kept and dataset.py built (dataM): their LMX as trained on, with the manuscript
  staff they came from (its length is drawn to).
- Unpaired: every bar of every part no dataM staff holds, cut into lines as the copyists cut theirs: bars per line
  drawn from the paired staves of the sources that hold the quartet (all sources' for a quartet none holds).
  A bar Philhar splits (a repeat sign inside it) is two boxes, so a line can end at the split: a mid-bar line break.

Each part's clef is read from the encoding (the staff position LilyPond gave each note; clefs.C is alto or tenor by
where its notes sit). Lines that fail dataset.py's check (a bar its durations don't fill, a clef change inside a bar,
a read-back that isn't the encoding) or that hold a token the reader doesn't know are left out, and counted.

    uv run experiments/synth/philhar_lines.py OUT [--jobs 6] [--seed 0]

Writes OUT/unpaired/<quartet>-<mvt>-<part>-<n>.lmx and OUT/lines.json (every line: paired and unpaired).
"""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor
from fractions import Fraction
from pathlib import Path

LAB = Path(__file__).resolve().parents[2]
ZEUS_DIR = LAB / "experiments" / "zeus"
sys.path.insert(0, str(ZEUS_DIR))
import dataset  # noqa: E402
import philhar  # noqa: E402

EDITION = Path.home() / "Dropbox/Code/boccherini-opus-48"
LILY = Path.home() / "Dropbox/Code/boccherini-quartet-data/lilypond"
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
PAIRING = "-any-count-musvit-C4-bocch-tf8-L-best"  # the pairing dataM was built from (overnight.py)
VOCAB = set(json.loads((Path.home() / ".cache/manuscript-labeler/models/musvit/musvit-D3@2026-10-18/vocab.json").read_text()))
PARTS = ("vn1", "vn2", "va", "vc")
STEPS = "CDEFGAB"
MIDDLE = {"treble": "B4", "alto": "C4", "tenor": "A3", "bass": "D3"}  # each clef's middle line


def dia(pitch: str) -> int:
    return int(pitch[-1]) * 7 + STEPS.index(pitch[0])


def clef_of(e: dict, last: str | None, part: str) -> str | None:
    """The clef an event is written in: from where its notes sit (staff_pos 0 is the middle line), else its glyph."""
    for n in e.get("notes") or []:
        if n.get("pitch") and n.get("staff_pos") is not None:
            mid = dia(re.sub(r"[^A-G0-9]", "", n["pitch"])) - n["staff_pos"]
            for clef, p in MIDDLE.items():
                if dia(p) == mid:
                    return clef
    g = e.get("clef") or ""
    if g.endswith(".G"):
        return "treble"
    if g.endswith(".F"):
        return "bass"
    if g.endswith(".C"):
        return last if last in ("alto", "tenor") else ("alto" if part == "va" else "tenor")
    return last


def load(job):
    q, mvt, part = job
    try:
        events = philhar.events_module(EDITION)
        bars, split, changes = philhar.read(EDITION, LILY / q, part, mvt)
        return job, {"bars": events.to_json(bars), "split": sorted(split),
                     "key_time": {str(b): list(kt) for b, kt in sorted(changes.items())}}, None
    except Exception as e:
        return job, None, f"{type(e).__name__}: {str(e)[:120]}"


def paired() -> tuple[list[dict], set, dict]:
    """dataM's staves (as lines), the (quartet, mvt, part, bar) they hold, and each quartet's bars per line."""
    lines, held, per_q = [], set(), defaultdict(list)
    for sf in sorted((CACHE / "dataM").glob("samples.*.txt")):
        src = sf.name[len("samples."):-len(".txt")]
        res = json.loads((ZEUS_DIR / "results" / f"autopair-{src}{PAIRING}.json").read_text())
        kept = {k["staff"]: k for k in res["kept"]}
        for sid in sf.read_text().split():
            k = kept[sid.split("/", 1)[1]]
            (q, mvt), part = {tuple(b[:2]) for b in k["bars"]}.pop(), k["part"]
            held.update((q, mvt, part, b) for _, _, b in k["bars"])
            per_q[q].append(len(k["bars"]))
            lines.append({"id": sid, "kind": "paired", "lmx": str(CACHE / "dataM" / f"{sid}.lmx"),
                          "jpg": str(CACHE / "dataM" / f"{sid}.jpg"), "quartet": q, "movement": mvt, "part": part,
                          "source": src, "bars": len(k["bars"])})
    return lines, held, per_q


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("--jobs", type=int, default=6)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    quartets = sorted(d.name for d in LILY.glob("Op*-*") if d.is_dir() and (d / "Trame.ily").exists())
    assert not any(q.startswith("Op48") for q in quartets), "Philhar's encodings hold no Op. 48"
    lines, held, per_q = paired()
    pooled = [n for v in per_q.values() for n in v]
    jobs = [(q, mvt, part) for q in quartets for mvt in philhar.movements(LILY / q) for part in PARTS]
    print(f"{len(quartets)} quartets, {len(jobs)} parts to read; {len(lines)} paired staves", flush=True)
    rng = random.Random(a.seed)
    (a.out / "unpaired").mkdir(parents=True, exist_ok=True)
    tally, bad, serial = Counter(), [], 0
    with ProcessPoolExecutor(a.jobs) as ex:
        for (q, mvt, part), d, err in ex.map(load, jobs):
            if d is None:
                tally["part LilyPond couldn't read"] += 1
                print("  skipped", q, mvt, part, err, flush=True)
                continue
            evs, mk, exp = d["bars"], dataset.marks(d["bars"]), dataset.philhar_structure(d["key_time"])
            nums = sorted(int(b) for b in evs)
            first = nums[0]
            mv = f"{q}-{mvt}"
            pick = [Fraction(e["pos"]) for e in evs.get("0", []) if e["grace"] == "0"]
            cut = min(pick) if pick else False
            split = {b: cut for b in d["split"]}
            # boxes in order: a split bar is two, its first half (count 1) then its upbeat (count 0)
            clef, boxes = None, []
            for b in nums:
                for count in ((1, 0) if b in split else (1,)):
                    box = {"part": part, "movement": mv, "bar": b, "count": count}
                    clefs = []
                    for e in dataset.box_events(box, evs, split) or []:
                        clef = clef_of(e, clef, part)
                        if clef and clef not in clefs:
                            clefs.append(clef)
                    box["clefs"] = clefs or [clef or {"vn1": "treble", "vn2": "treble", "va": "alto"}.get(part, "bass")]
                    boxes.append(box)
            # runs of boxes no paired staff holds, cut into lines of a copyist's length
            runs, cur = [], []
            for box in boxes:
                if (q, mvt, part, box["bar"]) in held:
                    if cur:
                        runs.append(cur)
                    cur = []
                else:
                    cur.append(box)
            if cur:
                runs.append(cur)
            dist = per_q.get(q) or pooled
            for run in runs:
                i = 0
                while i < len(run):
                    n = rng.choice(dist)
                    if len(run) - (i + n) < 2:  # no line of one bar at a run's end
                        n = len(run) - i
                    line = run[i:i + n]
                    i += n
                    serial += 1
                    sid = f"{q}-{mvt}-{part}-{serial:05d}"
                    lmx, why = dataset.build(line, evs, mk, exp, {(part, mv, first, 1)}, split, bad, sid)
                    if lmx is None:
                        tally[f"left out: {why}"] += 1
                        continue
                    if not set(lmx.split()) <= VOCAB:
                        tally["left out: a token the reader doesn't know"] += 1
                        continue
                    path = a.out / "unpaired" / f"{sid}.lmx"
                    path.write_text(lmx + "\n")
                    tally["unpaired lines"] += 1
                    tally["unpaired mid-bar breaks"] += line[-1]["count"] == 1 and line[-1]["bar"] in split
                    lines.append({"id": f"unpaired/{sid}", "kind": "unpaired", "lmx": str(path), "quartet": q,
                                  "movement": mvt, "part": part, "bars": len(line)})
    (a.out / "lines.json").write_text(json.dumps(lines, indent=0))
    print(f"{len(lines)} lines: {sum(l['kind'] == 'paired' for l in lines)} paired, "
          f"{sum(l['kind'] == 'unpaired' for l in lines)} unpaired", dict(tally), flush=True)
    for row in bad[:5]:
        print("  check failed:", row)


if __name__ == "__main__":
    main()
