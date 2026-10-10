# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@main",
#   "tensorflow-macos==2.12.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "numpy", "pillow",
# ]
# [tool.uv]
# # Zeus pins tensorflow 2.12, which has no wheel for Apple silicon; Apple's
# # tensorflow-macos 2.12 is the same version
# override-dependencies = ["tensorflow; sys_platform != 'darwin' or platform_machine != 'arm64'"]
# ///
"""Zeus against the edition's encoding, bar by bar: how much of a source it
reads as the edition has it.

    uv run experiments/zeus/compare.py <edition-repo> [--source D-B_KHM-602] [--movements I II] [--model DIR]

Every staff of the source's bar export, cut from its left end to its right
(a staff space beyond each, 2.5 above and below), straightened along its
bend, paper brightened to white, is read by Zeus (OmniOMR; the solo-staff
snapshot in ~/.cache/manuscript-labeler/models/zeus/ by default). Its
reading is cached in answers/ by staff and crop, so a rerun reads only
what changed.

Zeus's clefs are wrong on our hands (experiments/barlines/results.md), so
its clefs are only used to place each note on the staff; the pitch is read
from that place in the clef the labels give the bar. Its measures are
paired with the staff's bar boxes in order, where it found as many; a
staff where it didn't is counted, not compared. A bar whose boxes are on
two staves (a short bar and the next section's upbeat) is compared whole.

The encoding (the edition's scripts/events.py, as LilyPond reads it) is
taken as right. Each bar's events, in order (a chord as one, a rest, a
grace note), are aligned with Zeus's by edit distance, and scored:
- the bar entirely right, right in rhythm (notes, rests, durations, dots,
  graces), right in pitch (each note's letter and octave; accidentals
  are scored apart, as shown);
- per encoded event: right, wrong pitch (an octave out, or a step),
  wrong duration, a note for a rest or the reverse, missed; and Zeus's
  extra events.
Multi-voice bars are compared in each side's order, which differs.
"""

import argparse
import hashlib
import io
import json
import re
import subprocess
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent))
import labels  # noqa: E402

MODEL = Path.home() / ".cache" / "manuscript-labeler" / "models" / "zeus" / "ayce-2026-08-03.model"
RENDERS = Path.home() / ".cache" / "manuscript-labeler" / "zeus" / "renders"
RENDER_PX = 2800  # the labeler's: its staff geometry was set on renders this size

STEPS = "CDEFGAB"
# the pitch on the middle line, in Zeus's clefs and in the labels'
MIDDLE = {"G1": "D5", "G2": "B4", "G3": "G4", "G4": "E4", "G5": "C4", "F1": "C4", "F2": "A3", "F3": "F3",
          "F4": "D3", "F5": "B2", "C1": "G4", "C2": "E4", "C3": "C4", "C4": "A3", "C5": "F3",
          "treble": "B4", "alto": "C4", "tenor": "A3", "bass": "D3"}
TYPES = {"breve": "breve", "whole": "whole", "half": "half", "quarter": "quarter", "eighth": "8th",
         "16th": "16th", "32nd": "32nd", "64th": "64th"}
ACCIDENTALS = {"sharp", "flat", "natural", "double-sharp", "flat-flat", "natural-sharp", "natural-flat"}
PITCH = re.compile(r"([A-G])(\d)")


def num(pitch: str) -> int:
    m = re.fullmatch(r"([A-G])\D*?(-?\d+)", pitch)
    return int(m[2]) * 7 + STEPS.index(m[1])


def name(n: int) -> str:
    return f"{STEPS[n % 7]}{n // 7}"


# -- the staves --------------------------------------------------------------------

def page_image(pdf: Path, n: int) -> np.ndarray:
    out = RENDERS / pdf.stem / f"p{n:03d}.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["pdftoppm", "-f", str(n), "-l", str(n), "-scale-to", str(RENDER_PX), "-gray", "-png",
                        "-singlefile", str(pdf), str(out.with_suffix(""))], check=True)
    return np.asarray(Image.open(out).convert("L")).astype(np.float32)


def staff_crop(g: np.ndarray, s: dict) -> bytes:
    """The staff, straightened along its bend, as Zeus reads a staff."""
    H, W = g.shape
    sp = (s["bottom"] - s["top"]) / 4 * H
    x0, x1 = int(max(0, s["left"] * W - sp)), int(min(W, s["right"] * W + sp))
    up, dn = int(2.5 * sp), int(2.5 * sp)
    h = int((s["bottom"] - s["top"]) * H) + up + dn
    out = np.full((h, x1 - x0), 255.0, np.float32)
    for x in range(x0, x1):
        y0 = int(round((s["top"] + labels.bend_at(s, x / W)) * H)) - up
        a, b = max(0, y0), min(H, y0 + h)
        if b > a:
            out[a - y0:b - y0, x - x0] = g[a:b, x]
    out = np.clip(out / max(np.percentile(out, 90), 1) * 255, 0, 255).astype(np.uint8)
    buf = io.BytesIO()
    Image.fromarray(out).save(buf, "PNG")
    return buf.getvalue()


# -- Zeus's reading ---------------------------------------------------------------------

WHOLE = {"breve": Fraction(2), "whole": Fraction(1), "half": Fraction(1, 2), "quarter": Fraction(1, 4),
         "eighth": Fraction(1, 8), "16th": Fraction(1, 16), "32nd": Fraction(1, 32), "64th": Fraction(1, 64)}
TUPLET = re.compile(r"(\d+)in(\d+)")


def length(kind: str | None, dots: int, tuplet: Fraction = Fraction(1)) -> Fraction:
    d = WHOLE.get(kind or "", Fraction(0))
    return d * (2 - Fraction(1, 2 ** dots)) * tuplet


def parse(lmx: str, ends: list | None = None) -> tuple[list[list[dict]], list[str]]:
    """Zeus's measures, each a list of events in time order: a note (its
    staff positions, from Zeus's own clef), a rest; with its duration,
    dots, grace, the accidental shown, its onset and voice. Zeus writes a
    double stop as two voices (the second after a `backup`); notes that
    start together with the same duration are one chord, as the encoding
    has them. And the clefs Zeus wrote. `ends`, if given, gets each
    measure's length as written: the latest time any voice reaches, an
    invisible `forward` included."""
    measures, clefs = [], []
    clef, flags = None, set()
    cur = move = None        # the event being read; a backup/forward being read
    member = False           # reading a chord's other head
    t_now, voice, reach, reached = Fraction(0), "1", Fraction(0), []

    def settle():
        nonlocal cur, move, t_now, reach
        if cur is not None and not cur["grace"] and not cur.get("settled"):
            t_now += length(cur["dur_raw"], cur["dots"], cur["tuplet"])
            cur["settled"] = True
        if move is not None:
            t_now += move["sign"] * length(move["kind"], move["dots"])
            move = None
        reach = max(reach, t_now)

    for t in lmx.split() + ["measure"]:
        if t == "measure":
            settle()
            if measures:
                measures[-1] = merge(measures[-1])
                reached.append(reach)
            measures.append([])
            cur, t_now, member, reach = None, Fraction(0), False, Fraction(0)
            continue
        if t.startswith("clef:"):
            clef = t[5:]
            clefs.append(clef)
            continue
        if t.startswith("voice:"):
            voice = t[6:]
            if cur is not None and not member:
                cur["voice"] = voice
            continue
        if t in ("backup", "forward"):
            settle()
            cur, member = None, False
            move = {"sign": -1 if t == "backup" else 1, "kind": None, "dots": 0}
            continue
        if move is not None:
            if t in WHOLE and move["kind"] is None:
                move["kind"] = t
                continue
            if t == "dot":
                move["dots"] += 1
                continue
        if t in ("grace", "chord"):
            flags.add(t)
            continue
        if t == "rest:measure":  # in place of a rest's type: the whole bar
            if cur is not None and cur["kind"] == "rest":
                cur["bar_rest"] = True
            continue
        m = PITCH.fullmatch(t)
        if m or t == "rest":
            pos = num(t) - num(MIDDLE.get(clef or "G2", "B4")) if m else None
            if m and "chord" in flags and measures[-1] and measures[-1][-1]["kind"] == "note":
                measures[-1][-1]["pos"].append(pos)
                member = True
            else:
                settle()
                cur = {"kind": "note" if m else "rest", "bar_rest": False, "pos": [pos] if m else [],
                       "dur_raw": None, "dur": None, "dots": 0, "tuplet": Fraction(1), "grace": "grace" in flags, "acc": [],
                       "onset": t_now, "voice": voice, "zclef": clef or "G2"}
                measures[-1].append(cur)
                member = False
            flags.clear()
            continue
        if cur is None:
            continue
        if t in ACCIDENTALS:
            cur["acc"].append(t)
        elif member:
            continue  # a chord's other heads repeat its duration
        elif t in WHOLE and cur["dur_raw"] is None:
            cur["dur_raw"], cur["dur"] = t, TYPES[t]
        elif t == "dot":
            cur["dots"] += 1
        elif TUPLET.fullmatch(t):
            a, b = map(int, TUPLET.fullmatch(t).groups())
            cur["tuplet"] = Fraction(b, a)
    measures.pop()  # the one opened by the closing sentinel
    while measures and not measures[-1]:
        measures.pop()
    if ends is not None:
        ends[:] = reached[:len(measures)]
    return measures, clefs


def merge(events: list[dict]) -> list[dict]:
    """In time order, notes that start together with the same duration in
    different voices made one chord (`pos` or `pitches` joined), and a rest
    in one voice under another's note dropped."""
    key = "pos" if events and "pos" in events[0] else "pitches"
    out: list[dict] = []
    for e in sorted(events, key=lambda e: e["onset"]):
        if e["grace"]:
            out.append(e)
            continue
        twin = next((o for o in out if not o["grace"] and o["onset"] == e["onset"] and o["voice"] != e["voice"]
                     and o["kind"] == e["kind"] == "note" and (o["dur"], o["dots"]) == (e["dur"], e["dots"])), None)
        if twin is not None:
            twin[key] = (type(twin[key]))(sorted(list(twin[key]) + list(e[key])))
            twin["acc"] = (type(twin["acc"]))(sorted(list(twin["acc"]) + list(e["acc"])))
            continue
        out.append(e)
    notes = {(o["onset"], o["voice"]) for o in out if o["kind"] == "note"}
    return [o for o in out if not (o["kind"] == "rest" and any(on == o["onset"] and v != o["voice"] for on, v in notes))]


def zeus_event(e: dict, clef: str) -> dict:
    """A Zeus event in the bar's clef (the labels'), as the encoding's are compared."""
    if e["kind"] == "rest":
        bar_rest = e["bar_rest"] or e["dur"] == "whole"
        return {"kind": "rest", "pitches": (), "dur": "bar" if bar_rest else e["dur"],
                "dots": 0 if bar_rest else e["dots"], "grace": e["grace"], "acc": ()}
    mid = num(MIDDLE[clef])
    return {"kind": "note", "pitches": tuple(sorted(name(mid + p) for p in e["pos"])), "dur": e["dur"],
            "dots": e["dots"], "grace": e["grace"], "acc": tuple(sorted(e["acc"]))}


def encoded_event(e: dict) -> dict:
    """An event of events.py, as compared."""
    dur = e["dur"] or ""
    where = {"onset": Fraction(e["pos"]), "voice": e["voice"]}  # a grace note: its note's, kept before it
    if e["kind"] in ("rest", "mmrest"):
        bar_rest = e["kind"] == "mmrest"
        return {"kind": "rest", "pitches": (), "dur": "bar" if bar_rest else dur.rstrip("."),
                "dots": 0 if bar_rest else dur.count("."), "grace": e["grace"] != "0", "acc": (), **where}
    return {"kind": "note", "pitches": tuple(sorted(re.sub(r"^([A-G])\D*?(-?\d+)$", r"\1\2", n["pitch"]) for n in e["notes"])),
            "dur": dur.rstrip("."), "dots": dur.count("."), "grace": e["grace"] != "0",
            "acc": tuple(sorted(n["acc"] for n in e["notes"] if n["acc"])), **where}


def encoded(evs: list[dict]) -> list[dict]:
    """A bar of events.py, as compared: its notes and rests (not the spacer
    or mark columns that carry a dynamic or text), voices merged."""
    return merge([encoded_event(e) for e in evs if e["kind"] in ("note", "rest", "mmrest")])


def in_force(exp: dict, field: str, box: dict):
    """Structure.ily's key or time for a bar box: the movement's, then each
    change before it. A change on a bar line holds from that bar (both
    halves of a split bar); one off the bar line, from the upbeat (count 0)
    box of its bar."""
    v = exp.get(field)
    for c in exp.get("changes", []):
        if field in c and (box["bar"] > c["bar"] or (box["bar"] == c["bar"] and
                                                       (c["on_bar_line"] or box["count"] == 0))):
            v = c[field]
    return v


def text(e: dict) -> str:
    if e["kind"] == "rest":
        return "R" if e["dur"] == "bar" else "r" + (e["dur"] or "?") + "." * e["dots"]
    p = e["pitches"][0] if len(e["pitches"]) == 1 else "<" + " ".join(e["pitches"]) + ">"
    return ("g" if e["grace"] else "") + p + ":" + (e["dur"] or "?") + "." * e["dots"]


# -- comparing ----------------------------------------------------------------------------

def same(a: dict, b: dict) -> bool:
    return all(a[k] == b[k] for k in ("kind", "pitches", "dur", "dots", "grace"))


def align(enc: list[dict], zeus: list[dict]) -> list[tuple]:
    """Edit-distance pairs (i, j): i or j None for missed and extra events."""
    n, m = len(enc), len(zeus)
    d = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        for j in range(m + 1):
            if i == 0 or j == 0:
                d[i][j] = i + j
            else:
                d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1,
                              d[i - 1][j - 1] + (0 if same(enc[i - 1], zeus[j - 1]) else 1))
    out, i, j = [], n, m
    while i or j:
        if i and j and d[i][j] == d[i - 1][j - 1] + (0 if same(enc[i - 1], zeus[j - 1]) else 1):
            out.append((i - 1, j - 1))
            i, j = i - 1, j - 1
        elif i and d[i][j] == d[i - 1][j] + 1:
            out.append((i - 1, None))
            i -= 1
        else:
            out.append((None, j - 1))
            j -= 1
    return out[::-1]


def what_differs(a: dict, b: dict) -> list[str]:
    if a["kind"] != b["kind"]:
        return ["note for rest" if b["kind"] == "note" else "rest for note"]
    out = []
    if a["pitches"] != b["pitches"]:
        if len(a["pitches"]) != len(b["pitches"]):
            out.append("chord size")
        elif all(num(x) % 7 == num(y) % 7 for x, y in zip(a["pitches"], b["pitches"])):
            out.append("octave")
        else:
            out.append("pitch")
    if (a["dur"], a["dots"]) != (b["dur"], b["dots"]):
        out.append("duration")
    if a["grace"] != b["grace"]:
        out.append("grace")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source", default="D-B_KHM-602")
    ap.add_argument("--model", type=Path, default=MODEL)
    ap.add_argument("--movements", nargs="+", help="only these movements (default: all)")
    a = ap.parse_args()
    pdf = next(a.edition.glob(f"sources/*/{a.source}.pdf"))
    export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
    quartet = f"Op48-{export['source']['gerard'] - 225}"

    # the staves and their bar boxes, in reading order
    staves: dict[str, list[dict]] = {}
    for b in export["bars"]:
        if b["part"] in ("vn1", "vn2", "va", "vc") and (not a.movements or b["movement"] in a.movements):
            staves.setdefault(b["system"], []).append(b)
    cache_file = HERE / "answers" / f"{a.source}-{a.model.name}.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    crops, keys = {}, {}
    pages = {}
    for sid in staves:
        s = export["systems"][sid]
        if s["page"] not in pages:
            pages = {s["page"]: page_image(pdf, s["page"])}  # one page at a time, in order
        crops[sid] = staff_crop(pages[s["page"]], s)
        keys[sid] = f"{sid}:{hashlib.sha1(crops[sid]).hexdigest()[:10]}"
    todo = [sid for sid in staves if keys[sid] not in cache]
    if todo:
        from zeus import InferenceOptions, Zeus
        model = Zeus.load(a.model)
        print(f"Zeus reads {len(todo)} staves ...", flush=True)
        for sid, lmx in zip(todo, model.predict([crops[sid] for sid in todo], InferenceOptions(batch_size=8))):
            cache[keys[sid]] = lmx
    current = set(keys.values())
    cache = {k: v for k, v in cache.items() if k.split(":")[0] not in staves or k in current}
    cache_file.parent.mkdir(exist_ok=True)
    cache_file.write_text(json.dumps(cache, indent=1, sort_keys=True))

    # Zeus's events by bar (part, movement, number), where its measures pair with the boxes
    zeus_bars: dict[tuple, list] = defaultdict(list)
    boxes_seen: Counter = Counter()
    unpaired, clef_read = [], Counter()
    for sid, boxes in staves.items():
        measures, clefs = parse(cache[keys[sid]])
        written = boxes[0]["clefs"][0] if boxes[0]["clefs"] else "?"
        clef_read[(written, clefs[0] if clefs else "none")] += 1
        if len(measures) != len(boxes):
            unpaired.append((sid, boxes[0]["part"], len(boxes), len(measures)))
            continue
        for b, ms in zip(boxes, measures):
            key = (b["part"], b["movement"], b["bar"])
            if len(b["clefs"]) != 1:  # a clef change inside the bar: where it falls isn't known
                continue
            boxes_seen[key] += 1
            zeus_bars[key] += [zeus_event(e, b["clefs"][0]) for e in ms]
    all_boxes = Counter((b["part"], b["movement"], b["bar"]) for bs in staves.values() for b in bs)

    # the encoding
    enc_bars: dict[tuple, list] = {}
    for part, mvt in sorted({(b["part"], b["movement"]) for bs in staves.values() for b in bs}):
        r = subprocess.run(["uv", "run", "--offline", str(a.edition / "scripts" / "events.py"), quartet, part, mvt, "--json"],
                           capture_output=True, text=True, check=True)
        for bar, evs in json.loads(r.stdout).items():
            enc_bars[(part, mvt, int(bar))] = encoded(evs)

    tally: dict[str, Counter] = defaultdict(Counter)
    rows = []
    for key, n in sorted(all_boxes.items(), key=lambda kv: (kv[0][1], kv[0][0], kv[0][2])):
        part = key[0]
        if boxes_seen[key] != n or key not in enc_bars:
            for g in ("all", part, key[1]):
                tally[g]["bars not compared"] += 1
            continue
        enc, zs = enc_bars[key], zeus_bars[key]
        pairs = align(enc, zs)
        rhythm = lambda es: [(e["kind"], e["dur"], e["dots"], e["grace"]) for e in es]
        pitch = lambda es: [e["pitches"] for e in es if e["kind"] == "note"]
        row = {"part": part, "movement": key[1], "bar": key[2], "encoded": " ".join(map(text, enc)),
               "zeus": " ".join(map(text, zs)), "exact": len(enc) == len(zs) and all(map(same, enc, zs)),
               "rhythm": rhythm(enc) == rhythm(zs), "pitch": pitch(enc) == pitch(zs), "errors": []}
        for g in ("all", part, key[1]):
            t = tally[g]
            t["bars"] += 1
            t["bars exact"] += row["exact"]
            t["bars right in rhythm"] += row["rhythm"]
            t["bars right in pitch"] += row["pitch"]
            t["events"] += len(enc)
        for i, j in pairs:
            if i is None:
                kinds = ["extra"]
            elif j is None:
                kinds = ["missed"]
            elif same(enc[i], zs[j]):
                kinds = ["right"]
                if enc[i]["kind"] == "note":
                    for g in ("all", part, key[1]):
                        tally[g]["notes right"] += 1
                        tally[g]["accidental shown as encoded"] += enc[i]["acc"] == zs[j]["acc"]
            else:
                kinds = what_differs(enc[i], zs[j])
            row["errors"] += [k for k in kinds if k != "right"]
            for g in ("all", part, key[1]):
                for k in kinds:
                    tally[g]["event: " + k] += 1
        rows.append(row)

    out = HERE / "results" / f"{a.source}{'-' + '-'.join(a.movements) if a.movements else ''}-{a.model.name}.json"
    out.parent.mkdir(exist_ok=True)
    out.write_text(json.dumps({"tally": tally, "unpaired staves": unpaired,
                               "clefs (labelled, Zeus's first)": {f"{k[0]} -> {k[1]}": v for k, v in clef_read.items()},
                               "bars": rows}, indent=1))
    print(f"{a.source} against {quartet}: {len(staves)} staves, {len(unpaired)} where Zeus's measures "
          f"don't pair with the bar boxes")
    print("clefs (labelled -> Zeus's first):", dict(clef_read.most_common()))
    for g in ["all", "vn1", "vn2", "va", "vc", "I", "II", "III"]:
        t = tally[g]
        if not t["bars"]:
            continue
        pct = lambda k, of: f"{t[k]}/{t[of]} ({100 * t[k] / max(t[of], 1):.0f}%)"
        print(f"\n{g}: {t['bars']} bars compared, {t['bars not compared']} not")
        print(f"  bars exact {pct('bars exact', 'bars')}, right in rhythm {pct('bars right in rhythm', 'bars')}, "
              f"right in pitch {pct('bars right in pitch', 'bars')}")
        print(f"  events right {pct('event: right', 'events')}; "
              + ", ".join(f"{k[7:]} {t[k]}" for k in sorted(t) if k.startswith("event: ") and k != "event: right"))
        print(f"  accidentals shown as encoded, on right notes: {pct('accidental shown as encoded', 'notes right')}")
    print(f"\nwrote {out.relative_to(HERE.parent.parent)}")


if __name__ == "__main__":
    main()
