"""A Structure.ily for the labeler from a MusicXML score: each movement's
time, key and bars as spacers, so the labeler can count an archive
source's bars against it (server.py --archive reads
data/<archive>/structure/G<n>/Structure.ily).

    uv run experiments/zeus/g213/structure.py SCORE.musicxml --out data/boccherini-sources/structure/G213/Structure.ily

Movements start where the bar numbers start again (as ossq/mxl.movements).
A bar's length is the first part's: a full bar of its time, or, for an
implicit measure (a pickup, or the half of a bar a section break splits,
MuseScore's X1, X2 …), the music in it. OSSQ's cleaned scores carry no
repeats or tempo marks, so the file has none: the labeler checks bar
counts, keys and times, not repeats.
"""

import argparse
import sys
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
import labels  # noqa: E402

MAJOR = {-7: "ces", -6: "ges", -5: "des", -4: "aes", -3: "ees", -2: "bes", -1: "f", 0: "c",
         1: "g", 2: "d", 3: "a", 4: "e", 5: "b", 6: "fis", 7: "cis"}
MINOR = {-7: "aes", -6: "ees", -5: "bes", -4: "f", -3: "c", -2: "g", -1: "d", 0: "a",
         1: "e", 2: "b", 3: "fis", 4: "cis", 5: "gis", 6: "dis", 7: "ais"}
ROMAN = ["I", "II", "III", "IV", "V", "VI", "VII", "VIII"]


def spacer(length: Fraction) -> str:
    """A length in whole notes as one spacer: s1, s2., s2.., s8, or s1*3/8."""
    for base in (1, 2, 4, 8, 16, 32):
        for dots in range(3):
            if Fraction(1, base) * (2 - Fraction(1, 2 ** dots)) == length:
                return f"s{base}{'.' * dots}"
    return f"s1*{length.numerator}/{length.denominator}"


def measures(path: Path) -> list[list[dict]]:
    """The first part's measures, by movement: number, length (whole notes),
    and the time and key set at its start."""
    part = ET.parse(path).getroot().find("part")
    mvts, last, div, time = [], None, 1, Fraction(1)
    for m in part.findall("measure"):
        n = m.get("number") or ""
        if not mvts or (n.isdigit() and last is not None and int(n) <= last):
            mvts.append([])
            last = None
        bar = {"number": n, "implicit": m.get("implicit") == "yes"}
        t = longest = Fraction(0)
        for el in m:
            if el.tag == "attributes":
                div = int(el.findtext("divisions") or div)
                for k in el.findall("key"):
                    bar["key"] = (int(k.findtext("fifths")), k.findtext("mode") or "major")
                for ts in el.findall("time"):
                    time = Fraction(int(ts.findtext("beats")), int(ts.findtext("beat-type")))
                    bar["time"] = ts.findtext("beats") + "/" + ts.findtext("beat-type")
            elif el.tag == "note" and el.find("chord") is None and el.find("grace") is None:
                t += Fraction(int(el.findtext("duration", "0")), div * 4)
            elif el.tag in ("backup", "forward"):
                t += Fraction(int(el.findtext("duration", "0")), div * 4) * (-1 if el.tag == "backup" else 1)
            longest = max(longest, t)
        bar["length"] = longest if bar["implicit"] or 0 < longest < time else time  # a section break can shorten a bar
        mvts[-1].append(bar)
        last = int(n) if n.isdigit() else last
    return mvts


def block(name: str, bars: list[dict], now: dict) -> str:
    """One movement's \\tag block: its key and time (`now`, carried from the
    movement before when the score doesn't restate them), each change, and
    runs of equal bars as s*N."""
    out = []  # signatures as strings, spacers as [spacer, count]
    for i, b in enumerate(bars):
        for f in ("time", "key"):
            if f in b and (b[f] != now.get(f) or i == 0):
                now[f] = b[f]
            elif i == 0 and f in now:
                b = {**b, f: now[f]}  # the movement opens with the signature in force
            else:
                b = {k: v for k, v in b.items() if k != f}  # restated, unchanged: left out
        if "time" in b:
            out.append(f"\\time {b['time']}")
        if "key" in b:
            fifths, mode = b["key"]
            out.append(f"\\key {(MINOR if mode == 'minor' else MAJOR)[fifths]} \\{'minor' if mode == 'minor' else 'major'}")
        s = spacer(b["length"])
        if i == 0 and b["implicit"]:
            out.append(f"\\partial {s[1:]}")
        if out and isinstance(out[-1], list) and out[-1][0] == s and not b["implicit"] and not out[-1][2]:
            out[-1][1] += 1
        else:
            out.append([s, 1, b["implicit"]])  # a short bar stands alone
    out = [x if isinstance(x, str) else x[0] + (f"*{x[1]}" if x[1] > 1 else "") for x in out]
    return f"%%% MOVEMENT {name}\n\\tag #'mvt{name} {{\n  " + " ".join(out) + "\n}\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("score", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    mvts = measures(a.score)
    text = (f"% Generated by experiments/zeus/g213/structure.py from {a.score.name}: the print's\n"
            "% barring, as OSSQ encoded it. No repeats or tempo marks (the score has none), and\n"
            "% a key without a mode in the score is written as major: the signature is what counts.\n\n"
            + "\n".join(block(ROMAN[i], bars, now) for now in [{}] for i, bars in enumerate(mvts)))
    got = labels.parse_structure(text)
    for i, bars in enumerate(mvts):
        want = sum(1 for b in bars if b["number"].isdigit() and b["number"] != "0")
        g = got[ROMAN[i]]
        print(f"{ROMAN[i]}: {g['total']} bars (score: {want}), pickup {g['pickup']}, key {g.get('key')}, "
              f"time {g.get('time')}, changes {g.get('changes')}")
        if g["total"] != want:
            sys.exit(f"{ROMAN[i]}: the block reads back as {g['total']} bars, not {want}; not written")
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(text)
    print(f"wrote {a.out}")


if __name__ == "__main__":
    main()
