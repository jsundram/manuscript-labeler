# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "linearized-musicxml @ git+https://github.com/OMR-Research/lmx.git@87fca1c38bda83bc032596ab00af28412f92941d",
#   "mcr-metric==1.1.0",
# ]
# ///
"""Musical Correction Rate (MCR; Hornbogen and Valentin, "Measure for
Measure", ISMIR 2026) for a staff reader, by the authors' own package
(mcr-metric): each held-out staff's reading against its label, both
turned from LMX into MusicXML by the lmx library.

    uv run experiments/zeus/mcr_score.py SAMPLES --readings answers/<source>-musvit-<run>-mps.json ...

SAMPLES is dataset.py's list of a held-out set's staves (their .lmx is the
truth); each --readings is read.py's cache of a reader's readings, keyed
by staff. Prints each reader's corpus MCR (each staff weighted by its
cost of retyping from blank: its predicted events plus twice its
reference events, as `mcr batch` weights) and its content precision and
recall. 0 is perfect.

MCR inflects each note by the key in force, so a wrong key costs every
note it alters. A staff the copyist began without its clef and key (in
mid-movement) leaves the reader to guess them: --label-signature gives
each reading the label's first key and clef instead of its own, to score
the notes alone.
"""

import argparse
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import mcr
from lmx.tokenization.Decoder import Decoder


def musicxml(lmx: str) -> str:
    """One staff's LMX as a MusicXML score of one part."""
    part = Decoder().process_text(lmx)
    part.set("id", "P1")
    score = ET.Element("score-partwise", version="4.0")
    plist = ET.SubElement(score, "part-list")
    ET.SubElement(ET.SubElement(plist, "score-part", id="P1"), "part-name").text = "staff"
    score.append(part)
    return ET.tostring(score, encoding="unicode")


STEPS = "CDEFGAB"
_PITCH = re.compile(r"^([A-G])(-?\d+)$")


def bottom_line(clef: str) -> int:
    """A clef (`clef:G2`) as the diatonic step of its staff's bottom line (E4 for G2)."""
    sign, line = clef.split(":")[1][0], int(clef.split(":")[1][1:])
    base = {"G": 7 * 4 + 4, "C": 7 * 4, "F": 7 * 3 + 3}[sign]
    return base - 2 * (line - 1)


def with_signature(reading: str, label: str) -> str:
    """The reading as if read with the label's first key and clef: its
    first key token replaced, and, if its first clef differs, the clef
    replaced and its notes moved to where they sit on the staff under the
    label's (LMX pitches are absolute, so a wrong clef moves every note)."""
    theirs = re.search(r"key:fifths:\S+", label)
    if theirs:
        reading = re.sub(r"key:fifths:\S+", lambda m: theirs.group(), reading, count=1)
    ours, theirs = re.search(r"clef:\S+", reading), re.search(r"clef:\S+", label)
    if not (ours and theirs) or ours.group() == theirs.group():
        return reading
    shift = bottom_line(theirs.group()) - bottom_line(ours.group())
    out, clefs = [], 0
    for t in reading.split():
        if t.startswith("clef:"):
            clefs += 1
            t = theirs.group() if clefs == 1 else t
        elif clefs == 1 and (m := _PITCH.match(t)):
            d = 7 * int(m.group(2)) + STEPS.index(m.group(1)) + shift
            t = f"{STEPS[d % 7]}{d // 7}"
        out.append(t)
    return " ".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("samples", type=Path)
    ap.add_argument("--readings", type=Path, nargs="+", required=True)
    ap.add_argument("--label-signature", action="store_true", help="score each reading with the label's first key and clef")
    a = ap.parse_args()
    staves = [a.samples.parent / s for s in a.samples.read_text().split()]
    for f in a.readings:
        cache = json.loads(f.read_text())
        by_staff = {k.split(":")[0]: v for k, v in cache.items()}
        cost = denom = n = unreadable = 0
        prec = rec = 0.0
        for s in staves:
            got = by_staff.get(s.name)
            if got is None:
                continue
            label = s.with_suffix(".lmx").read_text()
            if a.label_signature:
                got = with_signature(got, label)
            try:
                ref = musicxml(label)
            except ValueError:  # a label lmx can't turn back into MusicXML: left out
                continue
            try:
                pred = musicxml(got)
            except ValueError:  # a reading that can't be MusicXML (a voice past its bar): scored as empty
                pred = musicxml("")
                unreadable += 1
            r = mcr.score(pred, ref, pred_format="musicxml", ref_format="musicxml")
            w = len(mcr.parse(pred, format="musicxml").events) + 2 * len(mcr.parse(ref, format="musicxml").events)
            cost += r.mcr * w
            denom += w
            prec += r.content_precision * w
            rec += r.content_recall * w
            n += 1
        print(f"{f.stem}: MCR {cost / denom:.2%} over {n} of {len(staves)} staves ({unreadable} readings not MusicXML); "
              f"content precision {prec / denom:.1%}, recall {rec / denom:.1%}")


if __name__ == "__main__":
    main()
