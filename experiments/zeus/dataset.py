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
movement's opening pickup. Left out, and counted: staves where that cut
doesn't fall between two notes (or the movement has no pickup), a clef
change inside a bar, or two voices.

Every staff kept is checked: its LMX, read back as compare.py reads
Zeus's, must equal the encoding bar for bar.
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


def marks(events_by_bar: dict) -> dict:
    """Per event (bar, label): its tuplet ratio and whether it starts or ends
    a tuplet, beam levels, tie stop. Read across the movement, in order."""
    out = {}
    seq = [(int(b), e) for b in sorted(events_by_bar, key=int) for e in events_by_bar[b]]
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
            group["members"].append((b, e["label"]))
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
                out.setdefault((bb, x["label"]), {})["beams"] = levels
            beam = None
    # ties: the note a tie ends on
    for b, e in seq:
        if e["tie"] and e["tie_to"]:
            out.setdefault((e["tie_to"][0], f"n{e['tie_to'][1]}"), {})["tie_stop"] = True
    return out


def note_elements(m: ET.Element, b: int, e: dict, mk: dict, measure_len: Fraction):
    info = mk.get((b, e["label"]), {})
    dur = e["dur"] or ""
    kind = dur.rstrip(".")
    dots = dur.count(".")
    if e["kind"] == "mmrest":
        n = sub(m, "note")
        sub(n, "rest", measure="yes")
        sub(n, "duration", int(measure_len * 4 * DIV))
        sub(n, "voice", 1)
        return
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
        sub(n, "voice", 1)
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
               split: dict) -> ET.Element:
    """The staff's bars as one MusicXML part."""
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
        for e in box_events(box, events, split):
            note_elements(m, box["bar"], e, mk, measure_len)
    return part


def fills(part: ET.Element, boxes: list[dict], exp: dict, split: dict, last: int) -> bool:
    """LilyPond's bar check on the MusicXML written: each whole bar's notes
    and rests (not graces, not a chord's other heads) fill it exactly, so a
    tuplet left open or a duration miswritten can't pass into training. Not
    a pickup, half a split bar, or the movement's `last` bar, which may be
    short."""
    for m, box in zip(part.findall("measure"), boxes):
        if box["bar"] in (0, last) or box["count"] != 1 or box["bar"] in split:
            continue
        total = sum(int(n.findtext("duration") or 0) for n in m.findall("note")
                    if n.find("grace") is None and n.find("chord") is None)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source", required=True)
    ap.add_argument("--movements", nargs="+", required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--name")
    a = ap.parse_args()
    from PIL import Image
    import io

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
        evs = events[(part, mvt)]
        split = splits[(part, mvt)]
        if any(box_events(b, evs, split) is None for b in boxes):
            left_out["a split bar that can't be cut"] += 1
            continue
        if any(len(b["clefs"]) > 1 for b in boxes):
            left_out["a clef change inside a bar"] += 1
            continue
        if any(len({e["voice"] for e in evs.get(str(b["bar"]), []) if e["grace"] == "0"}) > 1 for b in boxes):
            left_out["two voices"] += 1
            continue
        xml = staff_part(boxes, evs, mks[(part, mvt)], expected[mvt], first_of_mvt, split)
        if not fills(xml, boxes, expected[mvt], split, max(int(k) for k in evs)):
            left_out["a bar its durations don't fill"] += 1
            continue
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
        if not ok:
            left_out["failed the check"] += 1
            continue
        s = export["systems"][sid]
        if page is None or page[0] != s["page"]:
            page = (s["page"], compare.page_image(pdf, s["page"]))
        img = Image.open(io.BytesIO(compare.staff_crop(page[1], s))).convert("L")
        img.save(out / f"{sid}.jpg", quality=95)
        (out / f"{sid}.lmx").write_text(lmx + "\n")
        kept.append(f"{a.source}/{sid}")
    (a.out / f"samples.{name}.txt").write_text("\n".join(kept) + "\n")
    print(f"{a.source} {' '.join(a.movements)}: {len(kept)} staves kept of {len(staves)}; left out: {dict(left_out)}")
    for row in bad[:8]:
        print("  check failed:", row)


if __name__ == "__main__":
    main()
