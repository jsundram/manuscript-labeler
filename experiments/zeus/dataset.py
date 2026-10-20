# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@main",
#   "tensorflow-macos==2.12.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "numpy", "pillow",
# ]
# [tool.uv]
# override-dependencies = ["tensorflow; sys_platform != 'darwin' or platform_machine != 'arm64'"]
# ///
"""Training data for Zeus from the edition's encoding: each staff of a
source, cut as compare.py cuts it for Zeus, with the encoding's notes for
its bars written as Zeus's LMX.

    uv run experiments/zeus/dataset.py <edition-repo> --source D-B_KHM-602 --movements I II --out DIR
    uv run experiments/zeus/dataset.py <edition-repo> --pairs F-Pn_RES-507-2 --philhar <lilypond-dir> \\
        --quartets Op33-1,...,Op33-6 --out DIR

Writes DIR/<source>/<staff>.jpg and .lmx, and DIR/samples.<name>.txt
(Zeus's dataset index; `--name`, default the source and movements).

The notes come from the edition's scripts/events.py (as LilyPond reads the
note file), written as one MusicXML part per staff and encoded by the lmx
library as Zeus's own data is (the same header normalizations as Zeus's
convert_musicxml). In it:
- the clef is the labels' (the manuscript's), at the staff's start and
  where a bar starts in another;
- the key is Structure.ily's, written on every staff;
- the time is written where the movement starts or changes it;
- notes, rests, chords, grace notes, dots, tuplets, accidentals as
  printed, beams, ties, slurs, staccato, trill and fermata are all
  written; stems aren't (the encoding doesn't say where they point).
A bar split across two boxes (a section's short last bar and the next
one's upbeat, one number) is cut where its upbeat starts: LilyPond counts
the bar's positions on through both, and the upbeat is as long as the
movement's opening pickup. A bar with two voices (double stops the
encoding writes as voices) is written as Zeus's data writes it: each voice
in turn, a <backup> between. Left out, and counted: staves where that cut
doesn't fall between two notes (or the movement has no pickup), a clef
change inside a bar, or two voices in a split bar.

Every staff kept is checked: its LMX, read back as compare.py reads
Zeus's, must equal the encoding bar for bar.

--pairs takes the staves autopair.py kept on a source nobody labelled
(results/autopair-<name>.json), with Philhar's encoding (philhar.py):
only its plain staves (every measure one bar), in the clef autopair.py
chose, the key and time Philhar's Trame.ily gives. With --musicxml, the
staves autopair.py --musicxml kept, cut from that score (musicxml_pairs):

    uv run experiments/zeus/dataset.py <edition-repo> --pairs G213-Sibley --musicxml sq8454356_cleaned.musicxml \\
        --results experiments/zeus/results/autopair-G213-Sibley-musvit-D3S-h96.json --out DIR
"""

import argparse
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
if (HERE.parent.parent / "labels.py").exists():  # a labeler checkout (in zeus-score, labels.py is beside this)
    sys.path.insert(0, str(HERE.parent.parent))
import compare  # noqa: E402
import labels  # noqa: E402
import structure  # noqa: E402

DIV = 48  # divisions of a quarter: 32nds, triplets and 64ths are whole numbers
FLAGS = {"8th": 1, "16th": 2, "32nd": 3, "64th": 4}
XML_TYPE = {"breve": "breve", "whole": "whole", "half": "half", "quarter": "quarter", "8th": "eighth",
            "16th": "16th", "32nd": "32nd", "64th": "64th"}
LEN = {"breve": Fraction(2), "whole": Fraction(1), "half": Fraction(1, 2), "quarter": Fraction(1, 4),
       "8th": Fraction(1, 8), "16th": Fraction(1, 16), "32nd": Fraction(1, 32), "64th": Fraction(1, 64)}
CLEF = {"treble": ("G", "2"), "alto": ("C", "3"), "tenor": ("C", "4"), "bass": ("F", "4")}
ALTER = {"": 0, "#": 1, "##": 2, "x": 2, "b": -1, "bb": -2}


def sub(parent, tag, text=None, **attrib):
    e = ET.SubElement(parent, tag, {k.replace("_", "-"): v for k, v in attrib.items()})
    if text is not None:
        e.text = str(text)
    return e


def mark(mk: dict, b: int, e: dict) -> dict:
    """An event's marks (marks()): by bar, label and voice, since events.py
    labels a moment, which notes in two voices share."""
    return mk.get((b, e["label"], e.get("voice", "1")), {})


def marks(events_by_bar: dict) -> dict:
    """Per event (bar, label, voice): its tuplet ratio and whether it starts
    or ends a tuplet, beam levels, tie stop. Read across the movement, in
    order, each voice on its own."""
    out = {}
    seq = [(int(b), e) for b in sorted(events_by_bar, key=int) for e in events_by_bar[b]]
    for v in dict.fromkeys(e.get("voice", "1") for _, e in seq):  # each voice its own tuplets and beams
        voice_marks([(b, e) for b, e in seq if e.get("voice", "1") == v], out)
    # ties: the note a tie ends on
    for b, e in seq:
        if e["tie"] and e["tie_to"]:
            out.setdefault((e["tie_to"][0], f"n{e['tie_to'][1]}", e.get("voice", "1")), {})["tie_stop"] = True
    return out


def voice_marks(seq: list, out: dict):
    """marks' tuplets and beams for one voice's events, in order."""
    # tuplets: a "stop" closes the open group before this event, a "start" opens one on it
    group, groups = None, []
    for b, e in seq:
        for t in e["tup"]:
            if t[0] == "stop":
                group = None
            elif t[0] == "start":
                group = {"ratio": (t[2], t[1]), "members": []}
                groups.append(group)
        if group is not None and e["grace"] == "0":
            group["members"].append((b, e["label"], e.get("voice", "1")))
    for g in groups:
        for i, k in enumerate(g["members"]):
            out.setdefault(k, {})["tuplet"] = g["ratio"]
        if g["members"]:
            out.setdefault(g["members"][0], {})["tuplet_start"] = True
            out.setdefault(g["members"][-1], {})["tuplet_stop"] = True
    # beams: from a "start" to its "stop", levels from each note's flags
    beam = None
    for b, e in seq:
        if "start" in e["beam"]:
            beam = []
        if beam is not None:
            beam.append((b, e))
        if "stop" in e["beam"] and beam is not None:
            fl = [FLAGS.get(x["dur"].rstrip("."), 0) for _, x in beam]
            for i, (bb, x) in enumerate(beam):
                levels = []
                for lv in range(1, fl[i] + 1):
                    prev = i > 0 and fl[i - 1] >= lv
                    nxt = i < len(beam) - 1 and fl[i + 1] >= lv
                    levels.append("continue" if prev and nxt else "begin" if nxt else "end" if prev
                                  else "forward hook" if i == 0 else "backward hook")
                out.setdefault((bb, x["label"], x.get("voice", "1")), {})["beams"] = levels
            beam = None


def note_elements(m: ET.Element, b: int, e: dict, mk: dict, measure_len: Fraction, voice: int = 1) -> Fraction:
    """The event's notes (a chord's heads) or rest, in `voice`; the length
    written (none for a grace)."""
    info = mark(mk, b, e)
    dur = e["dur"] or ""
    kind = dur.rstrip(".")
    dots = dur.count(".")
    if e["kind"] == "mmrest":
        n = sub(m, "note")
        sub(n, "rest", measure="yes")
        sub(n, "duration", int(measure_len * 4 * DIV))
        sub(n, "voice", voice)
        return measure_len
    length = LEN[kind] * (2 - Fraction(1, 2 ** dots))
    if "tuplet" in info:
        length *= Fraction(info["tuplet"][1], info["tuplet"][0])
    heads = e["notes"] or [None]
    for i, h in enumerate(heads):
        n = sub(m, "note")
        if e["grace"] != "0":
            sub(n, "grace")
        if i:
            sub(n, "chord")
        if h is None:
            sub(n, "rest")
        else:
            p = sub(n, "pitch")
            mm = re.fullmatch(r"([A-G])([#xb]*)(-?\d+)", h["pitch"])
            sub(p, "step", mm[1])
            if ALTER[mm[2]]:
                sub(p, "alter", ALTER[mm[2]])
            sub(p, "octave", mm[3])
        if e["grace"] == "0":
            sub(n, "duration", int(length * 4 * DIV))
        if e["tie"] and h is not None:
            sub(n, "tie", type="start")
        sub(n, "voice", voice)
        sub(n, "type", XML_TYPE[kind])
        for _ in range(dots):
            sub(n, "dot")
        if h is not None and h["acc"]:
            sub(n, "accidental", h["acc"])
        if "tuplet" in info:
            tm = sub(n, "time-modification")
            sub(tm, "actual-notes", info["tuplet"][0])
            sub(tm, "normal-notes", info["tuplet"][1])
        if i == 0:
            for lv, kindb in enumerate(info.get("beams", []), 1):
                sub(n, "beam", kindb, number=str(lv))
        nt = ET.Element("notations")
        if h is not None and e["tie"]:
            sub(nt, "tied", type="start")
        if h is not None and info.get("tie_stop"):
            sub(nt, "tied", type="stop")
        if i == 0:
            if info.get("tuplet_start"):
                sub(nt, "tuplet", type="start")
            if info.get("tuplet_stop"):
                sub(nt, "tuplet", type="stop")
            for s in e["slur"]:
                sub(nt, "slur", type="stop" if s == ")" else "start")
            if "fermata" in e["art"]:
                sub(nt, "fermata")
            if "staccato" in e["art"]:
                sub(sub(nt, "articulations"), "staccato")
            if "trill" in e["art"]:
                sub(sub(nt, "ornaments"), "trill-mark")
        if len(nt):
            n.append(nt)
    return length if e["grace"] == "0" else Fraction(0)


def box_events(box: dict, events: dict, split: dict) -> list[dict] | None:
    """The encoding's events in a bar box: the whole bar's, or, for one half
    of a split bar, those before or after its upbeat (graces go with the
    note they lead into). None if the cut isn't between two notes."""
    evs = [e for e in events.get(str(box["bar"]), []) if e["kind"] in ("note", "rest", "mmrest")]
    cut = split.get(box["bar"])
    if cut is None:
        return evs
    if cut is False:
        return None
    if not any(Fraction(e["pos"]) == cut for e in evs) or any(
            Fraction(e["pos"]) < cut < Fraction(e["pos"]) + LEN.get((e["dur"] or "").rstrip("."), Fraction(0))
            for e in evs if e["grace"] == "0"):
        return None
    return [e for e in evs if (Fraction(e["pos"]) >= cut) == (box["count"] == 0)]


def staff_part(boxes: list[dict], events: dict, mk: dict, exp: dict, first_of_mvt: set,
               split: dict, bar_events: list[list[dict]] | None = None,
               clef_changes: dict | None = None) -> ET.Element:
    """The staff's bars as one MusicXML part. `bar_events`, if given, holds
    each box's events in place of the encoding's (box_events);
    `clef_changes` the clefs a bar changes to inside it, {box index: {index
    of the event the clef comes before: clef}} (tools/zeus_score.py)."""
    part = ET.Element("part", id="P1")
    clef = None
    for k, box in enumerate(boxes):
        m = sub(part, "measure", number=str(k + 1))
        key, time = compare.in_force(exp, "key", box), compare.in_force(exp, "time", box)
        beats, beat_type = structure.meter(time)
        measure_len = Fraction(beats, beat_type)
        prev = boxes[k - 1] if k else None
        attrs = ET.Element("attributes")
        if k == 0:
            sub(attrs, "divisions", DIV)
        if k == 0 or key != compare.in_force(exp, "key", prev):
            sub(sub(attrs, "key"), "fifths", key)
        if (box["part"], box["movement"], box["bar"], box["count"]) in first_of_mvt or \
                (prev and time != compare.in_force(exp, "time", prev)):
            t = sub(attrs, "time")
            sub(t, "beats", beats)
            sub(t, "beat-type", beat_type)
        if box["clefs"][0] != clef:
            clef = box["clefs"][0]
            c = sub(attrs, "clef")
            sub(c, "sign", CLEF[clef][0])
            sub(c, "line", CLEF[clef][1])
        if len(attrs):
            m.append(attrs)
        evs = bar_events[k] if bar_events is not None else box_events(box, events, split)
        if bar_events is None and len({e.get("voice", "1") for e in evs if e["grace"] == "0"}) > 1:
            two_voices(m, box["bar"], evs, mk, measure_len)
            continue
        changes = (clef_changes or {}).get(k, {})
        for i, e in enumerate(evs):
            if i in changes:
                clef = changes[i]
                c = sub(sub(m, "attributes"), "clef")
                sub(c, "sign", CLEF[clef][0])
                sub(c, "line", CLEF[clef][1])
            note_elements(m, box["bar"], e, mk, measure_len)
    return part


def lines(evs: list[dict], mk: dict | None = None, b: int = 0) -> list[int]:
    """Which line each event of a bar goes on, 1 or 2. LilyPond opens voices
    only where two lines sound (voices 3 and 4 for a few beats, then back to
    voice 2), so a voice's number doesn't say which line it is: an event
    goes on line 2 where it sounds against an event of a lower-numbered
    voice, else on line 1. A grace note goes with the next note of its
    voice."""
    def span(e):
        start = Fraction(e["pos"])
        if e["grace"] != "0":
            return start, start
        d = (e["dur"] or "").rstrip(".")
        dots = (e["dur"] or "").count(".")
        n = LEN.get(d, Fraction(0)) * (2 - Fraction(1, 2 ** dots))
        ratio = mark(mk or {}, b, e).get("tuplet")
        return start, start + (n * Fraction(ratio[1], ratio[0]) if ratio else n)

    line = [None] * len(evs)
    for i, e in enumerate(evs):
        if e["grace"] == "0":
            a, z = span(e)
            under = any(f["grace"] == "0" and int(f["voice"]) < int(e["voice"]) and span(f)[0] < z and a < span(f)[1]
                        for f in evs)
            line[i] = 2 if under else 1
    for i, e in enumerate(evs):
        if line[i] is None:
            nxt = next((k for k in range(i + 1, len(evs)) if line[k] is not None and evs[k]["voice"] == e["voice"]), None)
            line[i] = line[nxt] if nxt is not None else 1
    return line


def two_voices(m: ET.Element, b: int, evs: list[dict], mk: dict, measure_len: Fraction):
    """A bar where two lines sound, as Zeus's own data writes it: line 1
    (lines()), a <backup> to the bar's start, line 2, a <forward> over each
    gap inside a line."""
    where = lines(evs, mk, b)
    for n in (1, 2):
        at = Fraction(0)
        if n > 1:
            if 2 not in where:
                break
            sub(sub(m, "backup"), "duration", int(reached * 4 * DIV))
        for e in (e for e, w in zip(evs, where) if w == n):
            gap = Fraction(e["pos"]) - at
            if gap > 0:
                fw = sub(m, "forward")
                sub(fw, "duration", int(gap * 4 * DIV))
                sub(fw, "voice", n)
                at += gap
            at += note_elements(m, b, e, mk, measure_len, n)
        reached = at


def fills(part: ET.Element, boxes: list[dict], exp: dict, split: dict, last: int) -> bool:
    """LilyPond's bar check on the MusicXML written: each whole bar's notes
    and rests (not graces, not a chord's other heads) fill it exactly, so a
    tuplet left open or a duration miswritten can't pass into training. Not
    a pickup, half a split bar, or the movement's `last` bar, which may be
    short."""
    for m, box in zip(part.findall("measure"), boxes):
        if box["bar"] in (0, last) or box["count"] != 1 or box["bar"] in split:
            continue
        total = 0  # the first voice: everything before a <backup>
        for n in m:
            if n.tag == "backup":
                break
            if n.tag == "forward" or (n.tag == "note" and n.find("grace") is None and n.find("chord") is None):
                total += int(n.findtext("duration") or 0)
        beats, beat_type = structure.meter(compare.in_force(exp, "time", box))
        if Fraction(total, 4 * DIV) != Fraction(beats, beat_type):
            return False
    return True


def encode(part: ET.Element) -> str:
    from lmx.musicxml.omitted_staff_header.normalize_invisible_header_clef import normalize_invisible_header_clef
    from lmx.musicxml.omitted_staff_header.normalize_invisible_key_signature import normalize_invisible_key_signature
    from lmx.musicxml.omitted_staff_header.normalize_invisible_time_signature import normalize_invisible_time_signature
    from lmx.musicxml.pitch.Clef import G_CLEF
    from lmx.tokenization.Encoder import Encoder

    part = normalize_invisible_header_clef(part_element=part, desired_clef=G_CLEF, when_clef_visible="dont-normalize")
    part = normalize_invisible_key_signature(part_element=part, desired_key=0, when_key_visible="dont-normalize")
    part = normalize_invisible_time_signature(part_element=part, desired_time=None, when_time_visible="dont-normalize")
    enc = Encoder(errout=None)
    enc.process_part(part)
    return " ".join(enc.output_tokens)


def build(boxes: list[dict], evs: dict, mk: dict, exp: dict, first_of_mvt: set, split: dict,
          bad: list, sid: str) -> tuple[str | None, str]:
    """A staff's LMX, checked, or None and why it's left out."""
    if any(box_events(b, evs, split) is None for b in boxes):
        return None, "a split bar that can't be cut"
    if any(len(b["clefs"]) > 1 for b in boxes):
        return None, "a clef change inside a bar"
    if any(b["bar"] in split and len({e["voice"] for e in evs.get(str(b["bar"]), []) if e["grace"] == "0"}) > 1
           for b in boxes):
        return None, "two voices in a split bar"
    xml = staff_part(boxes, evs, mk, exp, first_of_mvt, split)
    if not fills(xml, boxes, exp, split, max(int(k) for k in evs)):
        return None, "a bar its durations don't fill"
    lmx = encode(xml)
    # the check: read back as compare.py reads Zeus, it is the encoding
    measures, _ = compare.parse(lmx)
    ok = len(measures) == len(boxes)
    for b, ms in zip(boxes, measures):
        zs = [compare.zeus_event(e, b["clefs"][0]) for e in ms]
        enc = compare.encoded(box_events(b, evs, split))
        if not (len(zs) == len(enc) and all(map(compare.same, enc, zs))):
            ok = False
            bad.append((sid, b["bar"], " ".join(map(compare.text, enc)), " ".join(map(compare.text, zs))))
    return (lmx, "") if ok else (None, "failed the check")


def save(out: Path, sid: str, page, s: dict, lmx: str):
    from PIL import Image
    import io
    img = Image.open(io.BytesIO(compare.staff_crop(page, s))).convert("L")
    img.save(out / f"{sid}.jpg", quality=95)
    (out / f"{sid}.lmx").write_text(lmx + "\n")


def philhar_structure(key_time: dict) -> dict:
    """Philhar's key and time changes (philhar.py) as Structure.ily's are
    read (compare.in_force): the first in force from the start."""
    ch = sorted((int(b), kt) for b, kt in key_time.items())
    return {"key": ch[0][1][0], "time": ch[0][1][1],
            "changes": [{"bar": b, "on_bar_line": True, "key": k, "time": t} for b, (k, t) in ch[1:]]}


def pairs(a):
    """--pairs: the staves autopair.py kept on an unlabelled source, every
    measure one bar (its "plain" staves), with Philhar's encoding."""
    import os
    res = json.loads((a.results or HERE / "results" / f"autopair-{a.pairs}{'-any-count' if a.any_count else ''}.json").read_text())
    pdf = Path(json.loads((HERE / "auto" / f"{a.pairs}.json").read_text())["pdf"])
    allowed = set(a.quartets.split(","))
    env = {k: v for k, v in os.environ.items() if k != "UV_PYTHON_INSTALL_DIR"}
    loaded = {}

    def load(q, mvt, part):
        if (q, mvt, part) not in loaded:
            r = subprocess.run(["uv", "run", str(HERE / "philhar.py"), str(a.edition), str(a.philhar), q, part, mvt,
                                "--json"], capture_output=True, text=True, check=True, env=env)
            d = json.loads(r.stdout)
            loaded[(q, mvt, part)] = (d["bars"], marks(d["bars"]), philhar_structure(d["key_time"]),
                                      min(int(k) for k in d["bars"]))
        return loaded[(q, mvt, part)]

    out = a.out / a.pairs
    out.mkdir(parents=True, exist_ok=True)
    left_out, kept, bad = Counter(), [], []
    page = None
    for k in res["kept"]:
        where = {tuple(b[:2]) for b in k["bars"]}
        if not k["plain"]:
            left_out["not plain"] += 1
            continue
        if len(where) > 1:
            left_out["two movements"] += 1
            continue
        (q, mvt), part = where.pop(), k["part"]
        if q not in allowed:
            left_out["another quartet"] += 1
            continue
        evs, mk, exp, first = load(q, mvt, part)
        mv = f"{q}-{mvt}"
        boxes = [{"part": part, "movement": mv, "bar": b, "count": 1, "clefs": [k["clef"]]} for _, _, b in k["bars"]]
        lmx, why = build(boxes, evs, mk, exp, {(part, mv, first, 1)}, {}, bad, k["staff"])
        if lmx is None:
            left_out[why] += 1
            continue
        if page is None or page[0] != k["page"]:
            page = (k["page"], compare.page_image(pdf, k["page"]))
        save(out, k["staff"], page[1], k["system"], lmx)
        kept.append(f"{a.pairs}/{k['staff']}")
    name = a.name or a.pairs
    (a.out / f"samples.{name}.txt").write_text("\n".join(kept) + "\n")
    print(f"{a.pairs}: {len(kept)} staves kept of {len(res['kept'])}; left out: {dict(left_out)}")
    for row in bad[:8]:
        print("  check failed:", row)


MXL_CLEF = {"G2": "treble", "C3": "alto", "C4": "tenor", "F4": "bass"}
VOCAB = Path.home() / ".cache/manuscript-labeler/models/musvit/musvit-D4@2026-10-20/vocab.json"
# tokens dropped rather than refusing the staff, as experiments/ossq/ossq_modal.py drops them
SOFT = re.compile(r"^(stem:.*|beam:continue|arpeggiate|staff:\d+|tremolo:unmeasured|staccatissimo|spiccato|breath-mark|caesura)$")


def musicxml_pairs(a):
    """--pairs with --musicxml: the staves autopair.py --musicxml kept, each
    cut from the score's part as experiments/ossq/ossq_modal.py writes OSSQ's
    staves (lmx's slice_part_to_systems: divisions, key and clef on every
    staff, time where the music has it; no stems; tokens the reader's
    vocabulary lacks dropped if minor, else the staff left out). Only plain
    staves (every measure one bar, or two measures of a bar a repeat splits
    read as one) within one movement, whose clef as autopair.py chose it is
    the encoding's at every bar (--clef chosen: the chosen clef written in
    place of the encoding's, for a copy whose clefs differ, or a score that
    leaves a part's clef changes out, as OSSQ's G. 213 does; then the
    encoding has one clef on the staff and the reading wrote that clef and
    no other). With --max-unlike, a staff any of whose measures is further
    than that from its bar (autopair.py's "worst") is left out: where the
    print abbreviates what the score writes out, or the reverse. A viola or
    cello staff with a note more than 9 steps from the middle line in the
    clef written is left out (the copy changes clef there; the score has
    none); so are the staves listed in --drop (checked by eye)."""
    import copy
    import io
    from lmx.musicxml.slice_part_to_systems import slice_part_to_systems
    from lmx.tokenization.Encoder import Encoder
    sys.path.insert(0, str(HERE / "ossq"))
    import mxl

    res = json.loads(a.results.read_text())
    pdf = Path(json.loads((HERE / "auto" / f"{a.pairs}.json").read_text())["pdf"])
    mvts = mxl.movements(a.musicxml)
    parts = dict(zip(mxl.PARTS, ET.parse(a.musicxml).getroot().findall("part")))
    roman = ["I", "II", "III", "IV", "V", "VI"]
    vocab = set(json.loads(VOCAB.read_text()))
    # staves left out by eye: {staff: why}, from --drop FILE (lines "p57-5 why ...")
    dropped = {}
    if a.drop:
        for line in a.drop.read_text().splitlines():
            if line.strip() and not line.startswith("#"):
                sid, _, why = line.strip().partition(" ")
                dropped[sid] = why
    out = a.out / a.pairs
    out.mkdir(parents=True, exist_ok=True)
    left_out, kept, bad, notes = Counter(), [], [], []
    page = None
    for k in res["kept"]:
        part, sid = k["part"], k["staff"]
        where = {b[0] for b in k["bars"]}
        if not set(k.get("steps", {"one": 1})) <= {"one", "join"}:
            left_out["not plain"] += 1
            continue
        if len(where) > 1:
            left_out["two movements"] += 1
            continue
        if a.max_unlike is not None and k.get("worst", 0) > a.max_unlike:
            left_out["a measure unlike its bar"] += 1
            notes.append(f"{sid} {part}: a measure {k['worst']} from its bar")
            continue
        mvt = roman.index(where.pop())
        idx = [b[1] for b in k["bars"]]
        if idx != list(range(idx[0], idx[-1] + 1)):
            left_out["bars not consecutive"] += 1
            continue
        bars = mvts[part][mvt][idx[0]:idx[-1] + 1]
        enc_clefs = {MXL_CLEF.get(b["clef"], b["clef"]) for b in bars} | \
            ({"(changes inside a bar)"} if any(b["clef_change"] for b in bars) else set())
        if a.clef == "encoding" and enc_clefs != {k["clef"]}:
            left_out["clef chosen isn't the encoding's"] += 1
            notes.append(f"{sid} {part} {roman[mvt]} bars {bars[0]['number']}-{bars[-1]['number']}: "
                         f"chosen {k['clef']}, encoding {sorted(enc_clefs)}")
            continue
        if a.clef == "chosen" and len(enc_clefs) > 1:
            left_out["the encoding's clef changes on the staff"] += 1
            continue
        read = {MXL_CLEF.get(c, c) for c in k.get("read_clefs", [])}
        if a.clef == "chosen" and read != {k["clef"]}:
            left_out["the reading wrote another clef"] += 1
            notes.append(f"{sid} {part}: chosen {k['clef']}, read {sorted(read)}")
            continue
        # the measures' place in the whole part: a system break before the first and after the last
        start = sum(len(m) for m in mvts[part][:mvt]) + idx[0]
        end = start + len(idx)
        # a bar the score splits in two at a key change (MuseScore's X measure) where the print
        # draws no bar line (G. 213 IV, X2): the label would have a measure the image hasn't
        ms = parts[part].findall("measure")
        if any(not (ms[i].get("number") or "").isdigit() and ms[i].find("attributes/key") is not None
               for i in range(start, end) if i):
            left_out["a bar split at a key change"] += 1
            continue
        p = copy.deepcopy(parts[part])
        for i, m in enumerate(p.findall("measure")):
            pr = m.find("print")
            if pr is not None:
                pr.attrib.pop("new-system", None)
                pr.attrib.pop("new-page", None)
            if i in (start, end):
                if pr is None:
                    pr = ET.Element("print")
                    m.insert(0, pr)
                pr.set("new-system", "yes")
        systems = [s.part for pg in slice_part_to_systems(p) for s in pg.systems]
        staff = next(s for s in systems if len(s.findall("measure")) == len(idx)
                     and s.find("measure").get("number") == bars[0]["number"]
                     and sum(len(x.findall("measure")) for x in systems[:systems.index(s)]) == start)
        for note in staff.iter("note"):
            for st in note.findall("stem"):
                note.remove(st)
        # a hidden rest (OSSQ fills a second voice with them) is a <forward>: time passes, nothing shown
        for m in staff.findall("measure"):
            for i, el in enumerate(list(m)):
                if el.tag == "note" and el.get("print-object") == "no" and el.find("rest") is not None \
                        and el.find("chord") is None:
                    fw = ET.Element("forward")
                    sub(fw, "duration", el.findtext("duration"))
                    if el.findtext("voice"):
                        sub(fw, "voice", el.findtext("voice"))
                    m.remove(el)
                    m.insert(i, fw)
        if a.clef == "chosen" and enc_clefs != {k["clef"]}:
            for c in staff.iter("clef"):
                for ch in list(c):
                    if ch.tag in ("sign", "line"):
                        c.remove(ch)
                sub(c, "sign", CLEF[k["clef"]][0])
                sub(c, "line", CLEF[k["clef"]][1])
            notes.append(f"{sid} {part}: clef written {k['clef']} (encoding {sorted(enc_clefs)})")
        err = io.StringIO()
        enc = Encoder(errout=err, fail_on_unknown_tokens=False)
        try:
            enc.process_part(staff)
        except Exception as e:
            left_out[f"encoder {type(e).__name__}"] += 1
            continue
        toks = enc.output_tokens
        missing = re.findall(r"Token '([^']+)' not in the vocabulary", err.getvalue())
        unknown = [t for t in toks if t not in vocab]
        hard = [t for t in missing + unknown if not SOFT.match(t)]
        if hard:
            left_out[f"vocabulary lacks {sorted(set(hard))[0]}"] += 1
            continue
        if "print-object:no" in toks:
            left_out["a hidden object"] += 1
            continue
        lmx = " ".join(t for t in toks if t in vocab)
        # the check: read back as compare.py reads a reading (each note in its own clef), it is the encoding
        measures, _ = compare.parse(lmx)
        ok = len(measures) == len(bars)
        for b, ms in zip(bars, measures):
            zs = [compare.zeus_event(e, e["zclef"]) for e in ms]
            if not (len(zs) == len(b["events"]) and all(map(compare.same, b["events"], zs))):
                ok = False
                bad.append((sid, b["number"], " ".join(map(compare.text, b["events"])), " ".join(map(compare.text, zs))))
        if not ok:
            left_out["failed the check"] += 1
            continue
        # the viola's and cello's clef changes, which OSSQ's score leaves out: a note more than 9
        # steps from the middle line in the clef written (past 2-3 ledger lines) says the copy
        # changed clef there
        if part in ("va", "vc") and any(abs(p) > 9 for m in measures for e in m for p in e["pos"]):
            left_out["notes far off the staff in the clef written"] += 1
            notes.append(f"{sid} {part}: notes far off the staff in {k['clef']}")
            continue
        if sid in dropped:
            left_out["left out by eye"] += 1
            notes.append(f"{sid} {part}: left out by eye: {dropped[sid]}")
            continue
        if page is None or page[0] != k["page"]:
            page = (k["page"], compare.page_image(pdf, k["page"]))
        save(out, sid, page[1], k["system"], lmx)
        kept.append(f"{a.pairs}/{sid}")
    name = a.name or a.pairs
    (a.out / f"samples.{name}.txt").write_text("\n".join(kept) + "\n")
    print(f"{a.pairs}: {len(kept)} staves kept of {len(res['kept'])}; left out: {dict(left_out)}")
    for row in notes:
        print("  " + row)
    for row in bad[:20]:
        print("  check failed:", row)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source")
    ap.add_argument("--movements", nargs="+")
    ap.add_argument("--pairs", help="autopair.py's results for an unlabelled source")
    ap.add_argument("--philhar", type=Path, help="with --pairs: Philhar's lilypond/ folder")
    ap.add_argument("--quartets", help="with --pairs: the quartets to take staves from (Op33-1,...)")
    ap.add_argument("--musicxml", type=Path, help="with --pairs and --results: autopair.py --musicxml's score (OSSQ's)")
    ap.add_argument("--drop", type=Path, help="with --musicxml: staves to leave out, checked by eye (lines: staff why)")
    ap.add_argument("--max-unlike", type=float, help="with --musicxml: leave out a staff with a measure this unlike its bar")
    ap.add_argument("--clef", choices=("encoding", "chosen"), default="encoding",
                    help="with --musicxml: keep a staff only where autopair.py's clef is the encoding's, "
                         "or write autopair.py's clef")
    ap.add_argument("--any-count", action="store_true", help="with --pairs: autopair.py --any-count's results")
    ap.add_argument("--results", type=Path, help="with --pairs: this results file instead (e.g. several merged)")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--name")
    a = ap.parse_args()
    if a.pairs and a.musicxml:
        return musicxml_pairs(a)
    if a.pairs:
        return pairs(a)
    if not (a.source and a.movements):
        ap.error("give --source and --movements, or --pairs")

    pdf = next(a.edition.glob(f"sources/*/{a.source}.pdf"))
    export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
    quartet = f"Op48-{export['source']['gerard'] - 225}"
    expected = structure.expected((a.edition / quartet / "Structure.ily").read_text())
    parts = ("vn1", "vn2", "va", "vc")
    staves: dict[str, list] = {}
    for b in export["bars"]:
        if b["part"] in parts and b["movement"] in a.movements:
            staves.setdefault(b["system"], []).append(b)
    boxes_per_bar = Counter((b["part"], b["movement"], b["bar"]) for bs in staves.values() for b in bs)
    first_of_mvt = set()
    for b in export["bars"]:
        key = (b["part"], b["movement"])
        if key not in {k[:2] for k in first_of_mvt}:
            first_of_mvt.add((b["part"], b["movement"], b["bar"], b["count"]))

    events, mks, splits = {}, {}, {}
    for part, mvt in sorted({(b["part"], b["movement"]) for bs in staves.values() for b in bs}):
        r = subprocess.run(["uv", "run", "--offline", str(a.edition / "scripts" / "events.py"), quartet, part, mvt, "--json"],
                           capture_output=True, text=True, check=True)
        events[(part, mvt)] = json.loads(r.stdout)
        mks[(part, mvt)] = marks(events[(part, mvt)])
        # split bars: where each one's upbeat starts (False: unknown, no opening pickup)
        pick = [Fraction(e["pos"]) for e in events[(part, mvt)].get("0", []) if e["grace"] == "0"]
        cut = min(pick) if pick else False  # the pickup starts where a short bar would end
        splits[(part, mvt)] = {bar: cut for (p, m, bar), n in boxes_per_bar.items() if p == part and m == mvt and n > 1}

    name = a.name or f"{a.source}-{'-'.join(a.movements)}"
    out = a.out / a.source
    out.mkdir(parents=True, exist_ok=True)
    left_out, kept, bad = Counter(), [], []
    page = None
    for sid, boxes in staves.items():
        part, mvt = boxes[0]["part"], boxes[0]["movement"]
        if {b["movement"] for b in boxes} != {mvt}:
            left_out["two movements"] += 1
            continue
        lmx, why = build(boxes, events[(part, mvt)], mks[(part, mvt)], expected[mvt], first_of_mvt,
                         splits[(part, mvt)], bad, sid)
        if lmx is None:
            left_out[why] += 1
            continue
        s = export["systems"][sid]
        if page is None or page[0] != s["page"]:
            page = (s["page"], compare.page_image(pdf, s["page"]))
        save(out, sid, page[1], s, lmx)
        kept.append(f"{a.source}/{sid}")
    (a.out / f"samples.{name}.txt").write_text("\n".join(kept) + "\n")
    print(f"{a.source} {' '.join(a.movements)}: {len(kept)} staves kept of {len(staves)}; left out: {dict(left_out)}")
    for row in bad[:8]:
        print("  check failed:", row)

if __name__ == "__main__":
    main()
