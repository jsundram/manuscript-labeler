"""A window of the score's bars, read once from either score (G. 213's
MusicXML, or Philhar's encodings' events) into the same events, then written
for Opus as text or as LilyPond:

    head, bars = g213(part, mv, a, b)  or  philhar(lily, quartet, part, mv, a, b)
    as_text(head, bars), as_lily(head, bars)

An event: kind (note, rest, bar rest), pitches [(step, alter, octave)] as
sounding, type (quarter, 8th ...), dots, voice, grace, tuplet (actual,
normal) while in one, tuplet start/stop, tie, slur ("(" / ")"), dynamics,
words, hairpin, marks (staccato, trill, fermata ...), tremolo (the value the
strokes repeat: 16 = sixteenths), clef (where it changes).
"""

import subprocess
import tempfile
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import pair_check as pc

TYPES = {"breve": 0, "whole": 1, "half": 2, "quarter": 4, "eighth": 8, "8th": 8, "16th": 16, "32nd": 32, "64th": 64}
NAMES = {1: "whole", 2: "half", 4: "quarter", 8: "8th", 16: "16th", 32: "32nd", 64: "64th", 0: "breve"}
CLEFS = {("G", "2"): "treble", ("C", "3"): "alto", ("C", "4"): "tenor", ("F", "4"): "bass"}
PHILHAR_CLEF = {"clefs.G": ("G", "2"), "clefs.C": ("C", "3"), "clefs.F": ("F", "4")}
MARKS = {"staccato": "staccato", "staccatissimo": "staccatissimo", "tenuto": "tenuto", "accent": "accent",
         "trill": "trill", "trill-mark": "trill", "fermata": "fermata", "prall": "trill", "mordent": "mordent"}


def _ev(**kw) -> dict:
    e = {"kind": "note", "pitches": [], "type": 4, "dots": 0, "voice": 1, "grace": False, "tuplet": None,
         "tup_start": False, "tup_stop": False, "tie": False, "slur": [], "dyn": [], "words": [], "hair": None,
         "marks": [], "tremolo": None, "clef": None, "alt": None}
    e.update(kw)
    return e


# -- reading -------------------------------------------------------------------------------

def g213(part: str, mv: str, a: int, b: int) -> tuple[dict, dict[int, list[dict]]]:
    """({clef, fifths, time}, {bar: events}) for bars a..b of G. 213's MusicXML."""
    ms = pc.movements(part)[pc.ROMAN.index(mv)]
    at = pc.attributes_before(ms, a, sum(pc.movements(part)[:pc.ROMAN.index(mv)], []))
    head = {"clef": (at.findtext("clef/sign", "G"), at.findtext("clef/line", "2")),
            "fifths": int(at.findtext("key/fifths", "0")),
            "time": f"{at.findtext('time/beats')}/{at.findtext('time/beat-type')}",
            "notes": {i: "the rest of the bar before, after a repeat sign" for i in range(a, b + 1) if not (ms[i].get("number") or "").isdigit()}}
    bars = {}
    for i in range(a, b + 1):
        evs, pending, tup = [], {"dyn": [], "words": [], "hair": None}, None
        for el in ms[i]:
            if el.tag == "attributes" and i != a and el.find("clef") is not None:
                pending["clef"] = (el.findtext("clef/sign"), el.findtext("clef/line", ""))
            if el.tag == "direction":
                for d in el.iter("dynamics"):
                    pending["dyn"] += [c.tag for c in d]
                pending["words"] += [w.text for w in el.iter("words") if w.text]
                for w in el.iter("wedge"):
                    pending["hair"] = {"crescendo": "<", "diminuendo": ">", "stop": "!"}.get(w.get("type"))
            if el.tag != "note" or el.get("print-object") == "no":
                continue
            nt = el.find("notations")
            tups = [t.get("type") for t in (nt.findall("tuplet") if nt is not None else [])]
            tm = el.find("time-modification")
            if "start" in tups or (tm is not None and tup is None):
                tup = (int(tm.findtext("actual-notes")), int(tm.findtext("normal-notes"))) if tm is not None else None
            pitch = None if el.find("rest") is not None else (el.findtext("pitch/step"), int(float(el.findtext("pitch/alter", "0"))),
                                                               int(el.findtext("pitch/octave")))
            if el.find("chord") is not None and evs:
                evs[-1]["pitches"].append(pitch)
                continue
            trem = el.find("notations/ornaments/tremolo")
            typ = TYPES.get(el.findtext("type") or "", 4)
            whole_bar = el.find("rest") is not None and (el.find("rest").get("measure") == "yes" or el.findtext("type") is None)
            e = _ev(kind="bar rest" if whole_bar else "rest" if pitch is None else "note", pitches=[pitch] if pitch else [],
                    type=typ, dots=len(el.findall("dot")), voice=int(el.findtext("voice", "1")),
                    grace=el.find("grace") is not None, tuplet=tup if tm is not None else None,
                    tup_start="start" in tups, tup_stop="stop" in tups,
                    tie=any(t.get("type") == "start" for t in el.findall("tie")),
                    slur=["(" if s.get("type") == "start" else ")" for s in (nt.findall("slur") if nt is not None else [])
                          if s.get("type") in ("start", "stop")],
                    marks=[MARKS[m.tag] for m in (nt.iter() if nt is not None else []) if m.tag in MARKS],
                    tremolo=(typ or 1) * 2 ** int(trem.text or "1") if trem is not None and trem.get("type", "single") == "single" else None,
                    **pending)
            pending = {"dyn": [], "words": [], "hair": None}
            if "stop" in tups:
                tup = None
            evs.append(e)
        bars[i] = evs
    return head, bars


def philhar(lily: Path, quartet: str, part: str, mv: str, a: int, b: int) -> tuple[dict, dict[int, list[dict]]]:
    """The same for bars a..b of Philhar's encoding of a part's movement (philhar.encoding's events)."""
    import check_leftout as cl
    d = cl.philhar.encoding(cl.pp.EDITION, lily, quartet, part, mv)
    kt = [v for n, v in sorted(d["key_time"].items(), key=lambda kv: int(kv[0])) if int(n) <= a] or [[0, "4/4"]]
    ns = sorted(int(n) for n in d["bars"])
    clef = (next((e["clef"] for n in range(a, -1, -1) for e in d["bars"].get(str(n), []) if e["clef"]), None)
            or next((e["clef"] for n in ns for e in d["bars"][str(n)] if e["clef"]), "clefs.G"))  # rests at the
    # movement's start carry no clef: the first one the part has
    head = {"clef": PHILHAR_CLEF.get(clef, ("G", "2")), "fifths": kt[-1][0], "time": kt[-1][1],
            "notes": {n: "a repeat sign falls inside this bar" for n in range(a, b + 1) if n in d["split"]},
            "changes": {int(n): (v[0], v[1]) for n, v in d["key_time"].items() if a < int(n) <= b}}
    bars, tup, last = {}, None, None
    for n in range(a, b + 1):
        evs = []
        raw = [e for e in d["bars"].get(str(n)) or [cl.REST] if e["kind"] in ("note", "rest", "mmrest")]  # a bar a
        for e in raw:  # multi-bar rest covers isn't in the encoding
            stop = any(t[0] == "stop" for t in e["tup"])  # Philhar's stop: the tuplet ended before this event
            if stop and last and last["tuplet"]:
                last["tup_stop"] = True
            if stop:
                tup = None
            start = [t for t in e["tup"] if t[0] == "start"]
            if start:
                tup = (start[0][2], start[0][1])
            change = e["clef"] and e["clef"] != clef
            clef = e["clef"] or clef
            dur = e["dur"]
            evs.append(_ev(kind={"mmrest": "bar rest"}.get(e["kind"], e["kind"]),
                           pitches=[pc_split(p["pitch"]) for p in e["notes"]], type=TYPES.get(dur.rstrip("."), 4),
                           dots=dur.count("."), voice=e["voice"], grace=e["grace"] != "0", tuplet=tup,
                           tup_start=bool(start), tie=bool(e["tie"]), slur=list(e["slur"]), dyn=list(e["dyn"]),
                           words=[w for w in e["text"] if w.strip()],
                           hair={"start": {"<": "<", ">": ">"}.get(e["hair"][0][0]), "stop": "!"}.get(e["hair"][0][1]) if e["hair"] else None,
                           marks=[MARKS[m] for m in e["art"] if m in MARKS],
                           tremolo=int(e["tremolo"]) if "tremolo" in e else None,
                           clef=PHILHAR_CLEF.get(clef) if change else None))
            last = evs[-1]
        bars[n] = _two_note_tremolos(raw, evs)
    if tup and bars.get(b):  # a tuplet the window cuts off
        bars[b][-1]["tup_stop"] = True
    return head, bars


def _whole(dur: str) -> Fraction:
    """'half.' -> 3/4 (of a whole note)."""
    base = dur.rstrip(".")
    return Fraction(1, TYPES[base]) * (2 - Fraction(1, 2 ** dur.count("."))) if TYPES.get(base) else Fraction(2)


def _two_note_tremolos(raw: list[dict], evs: list[dict]) -> list[dict]:
    """LilyPond gives each note of a two-note tremolo (\\repeat tremolo 3 {g8 g'}: the two alternating)
    the whole tremolo's length, the second starting halfway: here one event, its `alt` the second note,
    alternating in 8ths (the encoding doesn't say; Boccherini's are)."""
    out, i = [], 0
    while i < len(evs):
        e, nx = raw[i], raw[i + 1] if i + 1 < len(raw) else None
        if (nx and e["kind"] == nx["kind"] == "note" and e["voice"] == nx["voice"] and e["dur"] == nx["dur"]
                and e["grace"] == nx["grace"] == "0" and Fraction(nx["pos"]) - Fraction(e["pos"]) == _whole(e["dur"]) / 2):
            out.append({**evs[i], "alt": evs[i + 1]["pitches"], "tremolo": 8, "slur": evs[i]["slur"] + evs[i + 1]["slur"]})
            i += 2
        else:
            out.append(evs[i])
            i += 1
    return out


def pc_split(name: str) -> tuple[str, int, int]:
    """'Eb3' -> ('E', -1, 3)."""
    step, rest = name[0], name[1:]
    acc = len(rest) - len(rest.lstrip("#b"))
    return step, rest[:acc].count("#") - rest[:acc].count("b"), int(rest[acc:])


# -- writing ---------------------------------------------------------------------------------

def _key(fifths: int) -> str:
    return f"{abs(fifths)} {'sharp' if fifths > 0 else 'flat'}{'s' if abs(fifths) != 1 else ''}" if fifths else "no sharps or flats"


def _pitch_text(p) -> str:
    step, alter, octave = p
    return step + {2: "##", 1: "#", 0: "", -1: "b", -2: "bb"}[alter] + str(octave)


TEXT_HEAD = ("Pitches are as they sound (letter, # or b, octave; middle C = C4), the key signature's sharps and flats "
             "included. ( and ) mark where a slur begins and ends; [p], [f] ... a dynamic; \"tied\" a note tied to the "
             "next; \"tremolo, 16ths\" a note written with strokes for repeated 16ths.")


def as_text(head: dict, bars: dict, relabel: bool = False) -> str:
    """With relabel, the bars numbered from 1 (not saying which of the score's they are)."""
    lines = [f"Clef {''.join(head['clef'])}, key signature {_key(head['fifths'])}, time {head['time']}. " + TEXT_HEAD]
    first = min(bars, default=0)
    for n, evs in bars.items():
        voices = {e["voice"] for e in evs}
        out = []
        for e in evs:
            s = ""
            if e["clef"]:
                s += f"[clef {''.join(e['clef'])}] "
            s += "".join(f"[{d}] " for d in e["dyn"]) + "".join(f'["{w}"] ' for w in e["words"])
            s += {"<": "[cresc. hairpin] ", ">": "[dim. hairpin] "}.get(e["hair"], "")
            if e["tup_start"] and e["tuplet"]:
                s += f"{{{e['tuplet'][0]} in the time of {e['tuplet'][1]}: "
            if "(" in e["slur"]:
                s += "("
            if e["kind"] == "bar rest":
                s += "rest for the whole bar"
            else:
                what = "rest" if e["kind"] == "rest" else "+".join(_pitch_text(p) for p in e["pitches"])
                s += ("grace " if e["grace"] else "") + what + " " + NAMES.get(e["type"], "?") + "." * e["dots"]
            s += "".join(f" {m}" for m in e["marks"])
            if e["alt"]:
                s += (f" alternating with {'+'.join(_pitch_text(p) for p in e['alt'])} as a two-note tremolo, "
                      f"{NAMES.get(e['tremolo'], '?')}s")
            elif e["tremolo"]:
                s += f" tremolo, {NAMES.get(e['tremolo'], str(e['tremolo']))}s"
            if e["tie"]:
                s += " tied"
            if len(voices) > 1:
                s += f" (voice {e['voice']})"
            if ")" in e["slur"]:
                s += ")"
            if e["tup_stop"]:
                s += "}"
            out.append(s)
        note = f" ({head['notes'][n]})" if n in head.get("notes", {}) else ""
        if n in head.get("changes", {}):
            fifths, time_ = head["changes"][n]
            out.insert(0, f"[key signature {_key(fifths)}, time {time_}]")
        lines.append(f"bar {n - first + 1 if relabel else n}{note}: " + ", ".join(out))
    return "\n".join(lines)


LILY_DYN = {"ppppp", "pppp", "ppp", "pp", "p", "mp", "mf", "f", "ff", "fff", "ffff", "fffff", "fp", "sf", "sff",
            "sp", "spp", "sfz", "rfz", "n"}  # LilyPond's own; any other (rf, fz ...) written as text
LILY_TONIC = ["ces", "ges", "des", "aes", "ees", "bes", "f", "c", "g", "d", "a", "e", "b", "fis", "cis"]


def _lily_pitch(p) -> str:
    step, alter, octave = p
    name = step.lower() + {2: "isis", 1: "is", 0: "", -1: "es", -2: "eses"}[alter]
    name = {"ees": "es", "aes": "as"}.get(name, name)
    return name + ("'" * (octave - 3) if octave >= 3 else "," * (3 - octave))


def _lily_dur(e) -> str:
    return ("\\breve" if e["type"] == 0 else str(e["type"])) + "." * e["dots"]


def _lily_voice(evs: list[dict], bar_len: str, unfold: bool = False) -> str:
    """With unfold, a two-note tremolo written out as notes, as copyists often wrote it."""
    out = []
    for i, e in enumerate(evs):
        s = ""
        if e["clef"]:
            s += f"\\clef {CLEFS.get(tuple(e['clef']), 'treble')} "
        if e["tup_start"] and e["tuplet"]:
            s += f"\\tuplet {e['tuplet'][0]}/{e['tuplet'][1]} {{ "
        if e["grace"]:
            s += "\\grace "
        if e["kind"] == "bar rest":
            s += f"R{bar_len}"
        elif e["kind"] == "rest":
            s += "r" + _lily_dur(e)
        elif e["alt"]:
            one = lambda ps: ps[0] if len(ps) == 1 else "<" + " ".join(ps) + ">"
            total = Fraction(1, e["type"] or 1) * (2 - Fraction(1, 2 ** e["dots"]))
            reps = total / Fraction(2, e["tremolo"])
            s += (f"\\repeat {'unfold' if unfold else 'tremolo'} {reps} {{ {one([_lily_pitch(p) for p in e['pitches']])}{e['tremolo']} "
                  f"{one([_lily_pitch(p) for p in e['alt']])}{e['tremolo']} }}")
        else:
            ps = [_lily_pitch(p) for p in e["pitches"]]
            s += (ps[0] if len(ps) == 1 else "<" + " ".join(ps) + ">") + _lily_dur(e)
        if e["tremolo"] and not e["alt"]:
            s += f":{e['tremolo']}"
        if e["tie"]:
            s += "~"
        s += "".join({"(": "(", ")": ")"}[c] for c in e["slur"] if c in "()")
        s += "".join(f"\\{d}" if d in LILY_DYN else f'_\\markup \\dynamic "{d}"' for d in e["dyn"])
        s += "".join(f'^"{w}"' for w in e["words"])
        s += {"<": "\\<", ">": "\\>", "!": "\\!"}.get(e["hair"], "")
        s += "".join({"staccato": "-.", "staccatissimo": "-!", "tenuto": "--", "accent": "->", "trill": "\\trill",
                      "fermata": "\\fermata", "mordent": "\\mordent"}.get(m, "") for m in e["marks"])
        if e["tup_stop"]:
            s += " }"
        out.append(s)
    return " ".join(out)


def _bar_len(time_: str) -> str:
    beats, beat_type = time_.split("/") if "/" in time_ else ("4", "4")
    return {"4/4": "1", "2/4": "2", "3/4": "2.", "2/2": "1", "6/8": "2.", "3/8": "4."}.get(time_, f"1*{beats}/{beat_type}")


def _length(evs: list[dict]) -> Fraction:
    """The music in a bar, of its first voice, in whole notes (grace notes take none)."""
    v = min((e["voice"] for e in evs), default=1)
    total = Fraction(0)
    for e in evs:
        if e["voice"] != v or e["grace"] or e["kind"] == "bar rest":
            continue
        d = Fraction(1, e["type"] or 1) * (2 - Fraction(1, 2 ** e["dots"]))
        total += d * e["tuplet"][1] / e["tuplet"][0] if e["tuplet"] else d
    return total


def as_lily(head: dict, bars: dict, score: bool = False, mark: tuple[int, int] | None = None,
            plain: bool = False, width_mm: float | None = None) -> str:
    """The bars in LilyPond, each after a comment with its number. With score, as a whole file for LilyPond
    to engrave: each bar numbered as here, a bar shorter than the time (an upbeat, or the rest of a bar
    after a repeat sign) given its own length, and with `mark` the bars mark[0]..mark[1] bracketed. With
    plain, on one line and without bar numbers (stacked under the manuscript's line), width_mm wide."""
    time_ = head["time"]
    lines = [f"\\clef {CLEFS.get(tuple(head['clef']), 'treble')} \\key {LILY_TONIC[head['fifths'] + 7]} \\major "
             f"\\time {time_}  % absolute pitches: c' is middle C"]
    for n, evs in bars.items():
        pre = ""
        if n in head.get("changes", {}):
            fifths, time_ = head["changes"][n]
            pre = f"\\key {LILY_TONIC[fifths + 7]} \\major \\time {time_} "
        bar_len = _bar_len(time_)
        voices = sorted({e["voice"] for e in evs})
        body = (_lily_voice(evs, bar_len, plain) if len(voices) <= 1 else
                "<< " + " \\\\ ".join("{ " + _lily_voice([e for e in evs if e["voice"] == v], bar_len, plain) + " }" for v in voices) + " >>")
        if score:
            beats, beat_type = (int(x) for x in time_.split("/"))
            full, have = Fraction(beats, beat_type), _length(evs)
            pre = f"\\set Score.currentBarNumber = #{n} " + pre
            short = have and have != full and not any(e["kind"] == "bar rest" for e in evs)
            if short and n == min(bars):  # an opening upbeat: LilyPond takes a bar's length at the start only so
                pre += f"\\partial 1*{have.numerator}/{have.denominator} "
            elif short:
                pre += f"\\set Timing.measureLength = #(ly:make-moment {have.numerator}/{have.denominator}) "
            else:
                pre += f"\\set Timing.measureLength = #(ly:make-moment {full.numerator}/{full.denominator}) "
            if mark and n == mark[0]:
                pre += f'\\textMark \\markup \\with-color "#c00" \\bold "[ bars {mark[0]}–{mark[1]}" '
            if mark and n == mark[1]:
                body += f' \\textEndMark \\markup \\with-color "#c00" \\bold "]"'
        note = f": {head['notes'][n]}" if n in head.get("notes", {}) else ""
        lines.append(f"% bar {n}{note}\n{pre}{body} |")
    if not score:
        return "\n".join(lines)
    out = LILY_FILE.replace("%MUSIC%", "\n".join(lines))
    plain_layout = LILY_PLAIN if width_mm is None else LILY_PLAIN.replace(
        "page-breaking = #ly:one-line-breaking", f"line-width = {width_mm:.1f}\\mm ragged-right = ##f system-count = 1")
    return out.replace("%LAYOUT%", plain_layout if plain else LILY_NUMBERED)


LILY_FILE = r"""\version "2.24.0"
\paper { indent = 0 ragged-right = ##f line-width = 180\mm print-page-number = ##f
         oddHeaderMarkup = ##f evenHeaderMarkup = ##f oddFooterMarkup = ##f evenFooterMarkup = ##f }
\header { tagline = ##f }
%LAYOUT%
{ \bar "" %MUSIC% }
"""
LILY_NUMBERED = r"""\layout { \context { \Score barNumberVisibility = #all-bar-numbers-visible
                     \override BarNumber.break-visibility = ##(#f #t #t) \override BarNumber.font-size = #0 } }"""
LILY_PLAIN = r"""\paper { page-breaking = #ly:one-line-breaking }
\layout { \context { \Score \remove Bar_number_engraver } }"""


def engrave(ly: str) -> bytes:
    """A LilyPond file as a PNG, cropped to its music."""
    with tempfile.TemporaryDirectory() as d:
        src = Path(d) / "bars.ly"
        src.write_text(ly)
        r = subprocess.run(["lilypond", "-dcrop", "-dno-point-and-click", "--png", "-dresolution=130", "-o",
                            str(Path(d) / "bars"), str(src)], capture_output=True, text=True)
        png = next(Path(d).glob("bars*.cropped.png"), None) or next(Path(d).glob("bars*.png"), None)
        if png is None or "error:" in r.stderr or "barcheck failed" in r.stderr:
            raise RuntimeError("LilyPond couldn't engrave the bars: " + r.stderr[-500:])
        return png.read_bytes()
