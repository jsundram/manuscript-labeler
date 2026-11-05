# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""musvit-D5's own reading of a movement written into an edition copy's
note files, as the draft a checker corrects (check_read.py).

    uv run experiments/llm/d5_draft.py <edition-copy> <edition> [--parts vn1 vn2 va vc]

D5's reading is the run's d5/reading.json in the edition (from its
scripts/d5_measure.py; `zeus-score read`): each staff's tokens, and which
of its measures make each bar. (The run's d5/read/ is the Opus readers'
first reading, not D5's.) Each measure is parsed as compare.py parses it
for scoring, and its notes are put in the labels' clef, as the scoring
does. Each seed line of the copy's note file (encode.py seed: one a bar)
is replaced by its bar (its comment "% bar N: D5's reading"), and the file
is switched from \\relative to absolute pitches, so a bar can be corrected
without moving the octave of the bars after it. Each bar's length and line
go to <edition-copy>/build/d5-draft.json.

Written: notes, chords, rests, durations, dots, grace notes, tuplets,
accidentals (from the key and those D5 drew; one LilyPond wouldn't print
is forced with !), clefs, and several voices as << { } \\\\ { } >> with
spacers. Not written: beams (LilyPond's own), slurs, ties, marks; the
scoring counts none of them.
"""

import argparse
import json
import re
import sys
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "zeus"))
import compare  # noqa: E402  (parse, length, MIDDLE, num, name: the scoring's own reading of the tokens)

FILES = {"vn1": "01-Vn1", "vn2": "02-Vn2", "va": "03-Va", "vc": "04-Vc"}
MVT = {"I": 1, "II": 2, "III": 3}
VALUES = {"breve": "\\breve", "whole": "1", "half": "2", "quarter": "4", "8th": "8", "16th": "16", "32nd": "32",
          "64th": "64"}
CLEF_NAMES = {"G2": "treble", "C3": "alto", "C4": "tenor", "F4": "bass", "C1": "soprano", "G1": "french"}
SHARPS = "FCGDAEB"
ALTER = {"sharp": 1, "flat": -1, "natural": 0, "double-sharp": 2, "flat-flat": -2, "natural-sharp": 1,
         "natural-flat": -1}
LY_ALTER = {-2: "ff", -1: "f", 0: "", 1: "s", 2: "ss"}  # the edition's note names: \\language "english"


def key_alters(fifths: int) -> dict:
    """The key signature: letter -> alteration."""
    if fifths >= 0:
        return {SHARPS[i]: 1 for i in range(fifths)}
    return {SHARPS[::-1][i]: -1 for i in range(-fifths)}


def ly_pitch(letter: str, octave: int, alter: int) -> str:
    name = letter.lower() + LY_ALTER[alter]
    marks = octave - 3
    return name + ("'" * marks if marks > 0 else "," * -marks)


def lily_length(x: Fraction) -> str:
    """A length as a LilyPond duration (for whole-bar rests)."""
    for n in (1, 2, 4, 8, 16, 32, 64):
        for dots in (0, 1, 2):
            if Fraction(1, n) * (2 - Fraction(1, 2 ** dots)) == x:
                return f"{n}{'.' * dots}"
    return f"1*{x.numerator}/{x.denominator}"


def spacers(gap: Fraction) -> list[str]:
    """A gap as spacers: plain values, or one exact spacer when no plain
    values add up to it (a tuplet D5 read short)."""
    if gap.denominator & (gap.denominator - 1):
        return [f"s1*{gap.numerator}/{gap.denominator}"]
    out, n = [], 1
    while gap > 0 and n <= 128:
        if gap >= Fraction(1, n):
            out.append(f"s{n}")
            gap -= Fraction(1, n)
        else:
            n *= 2
    return out


def sounds(e: dict) -> Fraction:
    return Fraction(0) if e["grace"] else compare.length(e["dur_raw"], e["dots"], e["tuplet"])


class Bar:
    """A bar's events written in LilyPond, with the accidentals in force."""

    def __init__(self, clef: str, key: dict):
        self.clef, self.key, self.shown = clef, key, {}

    def note(self, e: dict) -> str:
        mid = compare.num(compare.MIDDLE[self.clef])
        accs = list(e["acc"])
        heads = []
        for pos in sorted(e["pos"]):
            n = compare.name(mid + pos)
            letter, octave = n[0], int(n[1:])
            current = self.shown.get((letter, octave), self.key.get(letter, 0))
            acc = accs.pop(0) if accs else None  # which head of a chord carries it isn't known; the count is
            if acc in ALTER:
                alter = ALTER[acc]
                forced = alter == current  # drawn where LilyPond wouldn't print it
                self.shown[(letter, octave)] = alter
            else:
                alter, forced = current, False
            heads.append(ly_pitch(letter, octave, alter) + ("!" if forced else ""))
        return heads[0] if len(heads) == 1 else "<" + " ".join(heads) + ">"

    def event(self, e: dict, bar_len: Fraction) -> str:
        if e["kind"] == "rest":
            if e["bar_rest"] or e["dur"] == "whole":
                return "R" + lily_length(bar_len)
            return "r" + VALUES.get(e["dur"], "4") + "." * e["dots"]
        return self.note(e) + VALUES.get(e["dur"], "4") + "." * e["dots"]


def voice_text(events: list[dict], bar: Bar, bar_len: Fraction, shift: Fraction) -> tuple[str, Fraction]:
    """One voice in time order, spacers in its gaps; and where it ends."""
    words, at, group, graces = [], Fraction(0), None, []
    for e in events:
        if e["grace"]:
            graces.append(bar.event(e, bar_len))
            continue
        onset = e["onset"] - shift
        tup = e["tuplet"]
        if group and (tup != group[0] or onset > at):
            words.append("}")
            group = None
        if onset > at:
            words += spacers(onset - at)
            at = onset
        if tup != 1 and not group:
            words.append(f"\\tuplet {tup.denominator}/{tup.numerator} {{")
            group = [tup, Fraction(0)]
        if graces:
            words.append("\\grace " + (graces[0] if len(graces) == 1 else "{ " + " ".join(graces) + " }"))
            graces = []
        words.append(bar.event(e, bar_len))
        step = bar_len if e["kind"] == "rest" and (e["bar_rest"] or e["dur"] == "whole") else sounds(e)
        at += step
        if group:  # a tuplet closes when what it holds sounds a plain value
            group[1] += step
            if group[1].denominator & (group[1].denominator - 1) == 0:
                words.append("}")
                group = None
    if group:
        words.append("}")
    if graces:
        words.append("\\grace " + " ".join(graces))
    end = at
    if at < bar_len:
        words += spacers(bar_len - at)
    return " ".join(words), end


def bar_text(events: list[dict], bar_len: Fraction, bar: Bar) -> str:
    """The bar's events, each voice filled out with spacers; a bar D5 read
    longer than the bar (an extra note, a missed bar line) squeezed into it
    with \\scaleDurations, which keeps the written values, so it doesn't
    spill into the bars after it."""
    if not events:
        return " ".join(spacers(bar_len))
    voices: dict[str, list] = {}
    for e in sorted(events, key=lambda e: e["onset"]):
        voices.setdefault(e["voice"], []).append(e)
    state = dict(bar.shown)
    end = max(voice_text(v, bar, bar_len, Fraction(0))[1] for v in voices.values())
    bar.shown = state
    texts = [voice_text(v, bar, max(end, bar_len), Fraction(0))[0] for _, v in sorted(voices.items())]
    text = texts[0] if len(texts) == 1 else "<< " + " \\\\ ".join("{ " + t + " }" for t in texts) + " >>"
    if end > bar_len:
        k = bar_len / end
        text = f"\\scaleDurations {k.numerator}/{k.denominator} {{ {text} }}"
    return text


def seed_length(line: str) -> Fraction:
    """A seed line's spacer ('s8 |', 's4. |', 's1*3/8 |') as a length."""
    m = re.match(r"\s*s(\d+)(\.*)(?:\*(\d+)/(\d+))?", line)
    n, dots = int(m.group(1)), len(m.group(2))
    length = Fraction(1, n) * (2 - Fraction(1, 2 ** dots))
    return length * (Fraction(int(m.group(3)), int(m.group(4))) if m.group(3) else 1)


def d5_bars(reading: dict, part: str, mvt: str, lengths: dict) -> dict:
    """bar -> [events in time order, across the bar's boxes]."""
    out = {}
    for s in reading["staves"]:
        if s["part"] != part or s["mvt"] != mvt or not s["pairing"]:
            continue
        ends: list = []
        measures, _ = compare.parse(" ".join(s["tokens"]), ends)
        pairing = s["pairing"]
        for i, p in enumerate(pairing):
            if not p["measures"]:
                continue
            if p["how"] == "split":  # one measure read for two bars: cut where the first bar ends
                k = p["measures"][0]
                first = i + 1 < len(pairing) and pairing[i + 1]["measures"] == p["measures"]
                cut = lengths[p["bar"]] if first else lengths[pairing[i - 1]["bar"]]
                evs = [{**e, "onset": e["onset"] - (0 if first else cut)} for e in measures[k]
                       if (e["onset"] < cut) == first]
            else:
                evs, offset = [], Fraction(0)
                for j in p["measures"]:
                    evs += [{**e, "onset": e["onset"] + offset} for e in measures[j]]
                    offset += ends[j]
            prev = out.get(p["bar"], [])
            if prev:  # the bar's second box (a split bar's upbeat) sounds after the first
                at = max(e["onset"] + sounds(e) for e in prev)
                evs = [{**e, "onset": e["onset"] + at} for e in evs]
            out[p["bar"]] = prev + evs
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("copy", type=Path)
    ap.add_argument("edition", type=Path)
    ap.add_argument("--parts", nargs="+", default=list(FILES))
    a = ap.parse_args()
    if Path.home() / "Dropbox" in a.copy.resolve().parents:
        raise SystemExit("d5_draft: give it a copy of the edition, not the edition")
    state = json.loads(next((a.copy / "build/encode").glob("*/state.json")).read_text())
    q, mvt, run = state["quartet"], state["mvt"], state["run"]
    reading = json.loads((a.edition / "build/encode" / run / "d5/reading.json").read_text())
    export = json.loads((a.edition / state["source"]["file"]).read_text())
    record = {part: {} for part in a.parts}
    for part in a.parts:
        mine = sorted((b for b in export["bars"] if b["part"] == part and b["movement"] == mvt), key=lambda b: b["bar"])
        clefs = {b["bar"]: b["clefs"] for b in mine}
        keys, fifths = {}, 0  # the labels' key (D5 misreads it, and its scoring doesn't count it)
        for b in mine:
            fifths = b["signature"].get("key", fifths)
            keys[b["bar"]] = fifths
        path = a.copy / q / f"{FILES[part]}-{MVT[mvt]}.ily"
        lines = path.read_text().split("\n")
        seeds = {int(s.group(1)): i for i, l in enumerate(lines) if (s := re.search(r"%% SEED bar (\d+)", l))}
        lengths = {b: seed_length(lines[i]) for b, i in seeds.items()}
        bars = d5_bars(reading, part, mvt, lengths)
        m = next(i for i, l in enumerate(lines) if re.match(r"(\\relative \S+ )?\{ \\clef", l))
        clef = re.search(r"\\clef (\w+)", lines[m]).group(1)
        lines[m] = re.sub(r"^\\relative \S+ \{", "{", lines[m])
        for b, i in sorted(seeds.items()):
            here = [CLEF_NAMES.get(c, c) for c in clefs.get(b) or [clef]]
            text = f"\\clef {here[0]} " if here[0] != clef else ""
            clef = here[0]
            text += bar_text(bars.get(b, []), lengths[b], Bar(clef, key_alters(keys.get(b, 0))))
            if here[-1] != clef:  # a clef change inside the bar: that bar isn't scored; the next ones are
                clef = here[-1]
                text += f" \\clef {clef}"
            lines[i] = text + f" |   % bar {b}: D5's reading" + ("" if b in bars else " (none: D5 read no measure)")
            record[part][b] = {"length": str(lengths[b]), "line": text + " |"}
        path.write_text("\n".join(lines))
        print(f"{part}: {sum(b in bars for b in seeds)} of {len(seeds)} bars from D5 into {path.relative_to(a.copy)}")
    out = a.copy / "build" / "d5-draft.json"  # each bar's length and D5's line, for check_read.py
    old = json.loads(out.read_text()) if out.exists() else {}
    out.write_text(json.dumps({**old, **record}, indent=1))


if __name__ == "__main__":
    main()
