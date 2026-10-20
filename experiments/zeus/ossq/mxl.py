"""OSSQ's MusicXML, system by system: for each part, each system's bars, each
bar's events as compare.py compares them (a chord as one, a rest, a grace
note; voices merged), with the clef in force at the bar's start and
whether the clef changes inside it. Systems start where the first part's
measure has <print new-system|new-page="yes">."""

import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import compare  # noqa: E402

PARTS = ("vn1", "vn2", "va", "vc")
TYPES = {"breve": "breve", "whole": "whole", "half": "half", "quarter": "quarter", "eighth": "8th",
         "16th": "16th", "32nd": "32nd", "64th": "64th"}


def bars(part: ET.Element) -> list[dict]:
    out, clef, div = [], "G2", 1
    for m in part.findall("measure"):
        t, events, start_clef, changes = Fraction(0), [], clef, 0
        last = None
        for el in m:
            if el.tag == "attributes":
                if el.findtext("divisions"):
                    div = int(el.findtext("divisions"))
                for c in el.findall("clef"):
                    clef = c.findtext("sign", "G") + c.findtext("line", "")
                    if clef == "G":
                        clef = "G2"
                    if events:
                        changes += 1
                    else:
                        start_clef = clef
            elif el.tag in ("backup", "forward"):
                d = Fraction(int(el.findtext("duration", "0")), div)
                t += -d if el.tag == "backup" else d
            elif el.tag == "note":
                dur = Fraction(int(el.findtext("duration", "0")), div)
                chord = el.find("chord") is not None
                if chord and last is not None:
                    if el.find("pitch") is not None and el.get("print-object") != "no":
                        last["pitches"].append(el.findtext("pitch/step") + el.findtext("pitch/octave"))
                        if el.findtext("accidental"):
                            last["acc"].append(el.findtext("accidental"))
                    continue
                if el.get("print-object") == "no" or el.find("cue") is not None:
                    t += dur
                    last = None
                    continue
                grace = el.find("grace") is not None
                rest = el.find("rest")
                kind = el.findtext("type")
                dots = len(el.findall("dot"))
                onset = t
                if rest is not None:
                    bar_rest = rest.get("measure") == "yes" or kind in (None, "whole")
                    e = {"kind": "rest", "pitches": [], "dur": "bar" if bar_rest else TYPES.get(kind),
                         "dots": 0 if bar_rest else dots, "grace": False, "acc": []}
                else:
                    e = {"kind": "note", "pitches": [el.findtext("pitch/step") + el.findtext("pitch/octave")],
                         "dur": TYPES.get(kind), "dots": dots, "grace": grace,
                         "acc": [el.findtext("accidental")] if el.findtext("accidental") else []}
                e.update(onset=onset, voice=el.findtext("voice", "1"))
                events.append(e)
                last = e
                if not grace:
                    t += dur
        for e in events:
            e["pitches"] = tuple(sorted(e["pitches"]))
            e["acc"] = tuple(sorted(e["acc"]))
        p = m.find("print")
        new = p is not None and (p.get("new-system") == "yes" or p.get("new-page") == "yes")
        out.append({"number": m.get("number"), "events": compare.merge(events), "clef": start_clef,
                    "clef_change": changes > 0, "new_system": new})
    return out


def systems(path: Path) -> list[dict]:
    """[{part: [bar, ...]}, ...], one per system of the source."""
    parts = ET.parse(path).getroot().findall("part")
    assert len(parts) == 4, len(parts)
    per = [bars(p) for p in parts]
    starts = [i for i, b in enumerate(per[0]) if i == 0 or b["new_system"]]
    ends = starts[1:] + [len(per[0])]
    return [{name: per[k][a:b] for k, name in enumerate(PARTS)} for a, b in zip(starts, ends)]


def movements(path: Path) -> dict[str, list[list[dict]]]:
    """{part: [[bar, ...] per movement]}: a movement starts where the bar
    numbers start again (a numbered bar no higher than the last numbered
    one; MuseScore's X1, X2 ... are bars left out of the count). Every
    <measure> is a bar here: a bar a repeat splits is two measures."""
    parts = ET.parse(path).getroot().findall("part")
    assert len(parts) == 4, len(parts)
    out = {}
    for name, p in zip(PARTS, parts):
        mvts, last = [], None
        for b in bars(p):
            n = int(b["number"]) if (b["number"] or "").isdigit() else None
            if not mvts or (n is not None and last is not None and n <= last):
                mvts.append([])
                last = None
            mvts[-1].append(b)
            last = n if n is not None else last
        out[name] = mvts
    return out


if __name__ == "__main__":
    s = systems(Path(sys.argv[1]))
    print(len(s), "systems;", sum(len(x["vn1"]) for x in s), "bars")
    for x in s[:3]:
        for p in PARTS:
            print(p, x[p][0]["clef"], [" ".join(map(compare.text, b["events"])) for b in x[p][:2]])
