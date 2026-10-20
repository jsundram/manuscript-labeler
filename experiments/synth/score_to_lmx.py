# /// script
# requires-python = ">=3.10"
# dependencies = [
#   # the LMX writer Zeus uses, at Zeus's pin (dataset.py's labels are written with it)
#   "linearized-musicxml @ git+https://github.com/OMR-Research/lmx.git@87fca1c38bda83bc032596ab00af28412f92941d",
# ]
# ///
"""Quartet scores (MusicXML/MXL) cut into staff-length pieces of one part,
each written as our training labels are (dataset.py's conventions, Zeus's
LMX encoder at Zeus's pin): the key and clef on every staff, the time where
the piece starts or changes it, no stems, of the marks only staccato, trill
and fermata (what the edition's labels record). Staves whose LMX has a
token the reader doesn't know, or a hidden object (print-object:no: hidden
rests and clefs, which our labels never have), are left out, and counted.

How many bars a staff holds: a real staff is drawn from ours, and the staff
ends when it reaches that staff's number of notes and rests or its number of
bars, whichever comes first (so density and length match; runs of whole-bar
rests don't pile up).

    uv run experiments/synth/score_to_lmx.py OUT_DIR SCORE.mxl [...] [--real DIR ...] [--seed 0]

Writes OUT_DIR/<score stem>/<part>-<n>.lmx.
"""
import argparse
import copy
import json
import random
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

from lmx.tokenization.Encoder import Encoder

VOCAB = set(json.loads((Path.home() / ".cache/manuscript-labeler/models/musvit/musvit-D3@2026-10-18/vocab.json").read_text()))
KEEP_ARTIC = {"staccato"}
KEEP_ORN = {"trill-mark"}
EVENT = re.compile(r"^([A-G]\d|rest)$")


def load(path: Path) -> ET.Element:
    if path.suffix == ".mxl":
        z = zipfile.ZipFile(path)
        name = next(n for n in z.namelist() if not n.startswith("META-INF") and n.endswith((".xml", ".musicxml")))
        return ET.fromstring(z.read(name))
    return ET.parse(path).getroot()


def clean_note(n: ET.Element):
    for tag in ("stem", "notehead", "lyric", "play", "listen", "instrument"):
        for e in n.findall(tag):
            n.remove(e)
    nots = n.find("notations")
    if nots is None:
        return
    for e in list(nots):
        if e.tag == "articulations":
            for a in list(e):
                if a.tag not in KEEP_ARTIC:
                    e.remove(a)
            if not len(e):
                nots.remove(e)
        elif e.tag == "ornaments":
            for a in list(e):
                if a.tag not in KEEP_ORN:
                    e.remove(a)
            if not len(e):
                nots.remove(e)
        elif e.tag not in ("tied", "slur", "tuplet", "fermata"):
            nots.remove(e)
    if not len(nots):
        n.remove(nots)


def staves_of(part: ET.Element) -> int:
    for m in part.findall("measure"):
        s = m.find("attributes/staves")
        if s is not None:
            return int(s.text)
    return 1


def pieces(part: ET.Element, targets, rng):
    """[(list of measures, attributes in force at the first, time shown?)] cut to the target densities."""
    state = {}  # divisions, key, time, clef: the latest of each
    out, cur, count, (target, bars), start_state, show_time = [], [], 0, next(targets), None, True
    for m in part.findall("measure"):
        m = copy.deepcopy(m)
        at = m.find("attributes")
        time_changed = False
        if at is not None:
            for tag in ("divisions", "key", "time", "clef"):
                e = at.find(tag)
                if e is not None:
                    if tag == "time" and state.get("time") is not None:
                        time_changed = True
                    state[tag] = copy.deepcopy(e)
        if not cur:
            start_state = {k: copy.deepcopy(v) for k, v in state.items()}
            show_time = show_time or time_changed
        cur.append(m)
        count += sum(1 for n in m.findall("note") if n.find("chord") is None)
        last = any(b.findtext("bar-style") in ("light-heavy", "heavy-heavy") for b in m.findall("barline"))
        if count >= target or len(cur) >= bars or last:  # a staff ends where a movement does
            out.append((cur, start_state, show_time))
            cur, count, (target, bars), show_time = [], 0, next(targets), last  # a new movement shows its time
    return out


def build(measures, state, show_time) -> ET.Element:
    part = ET.Element("part", id="P1")
    for i, m in enumerate(measures):
        for tag in ("print", "direction", "harmony", "figured-bass", "sound", "listening", "barline"):
            for e in m.findall(tag):
                m.remove(e)
        for n in m.findall("note"):
            clean_note(n)
        at = m.find("attributes")
        if i == 0:
            new = ET.Element("attributes")
            for tag in ("divisions", "key", "time", "clef"):
                e = state.get(tag)
                if tag == "time" and not show_time:
                    continue
                if e is not None:
                    new.append(copy.deepcopy(e))
            if at is not None:
                m.remove(at)
            m.insert(0, new)
        elif at is not None:  # keep changes (key, time, clef) the measure itself makes
            for e in list(at):
                if e.tag not in ("divisions", "key", "time", "clef"):
                    at.remove(e)
        part.append(m)
    return part


def encode(part: ET.Element) -> str:
    enc = Encoder(errout=None)
    enc.process_part(part)
    return " ".join(enc.output_tokens)


def real_densities(dirs):
    """(notes and rests, bars) of each real staff."""
    n = []
    for d in dirs:
        for f in Path(d).glob("*/*.lmx"):
            toks = f.read_text().split()
            n.append((sum(1 for t in toks if EVENT.match(t)) - toks.count("chord"), toks.count("measure")))
    return [x for x in n if x[0] > 4]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out", type=Path)
    ap.add_argument("scores", nargs="+", type=Path)
    ap.add_argument("--real", nargs="+", default=[str(Path.home() / ".cache/manuscript-labeler/zeus/dataL2")])
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    dens = real_densities(a.real)

    def targets():
        while True:
            yield rng.choice(dens)

    tg = targets()
    why = Counter()
    for sc in a.scores:
        try:
            root = load(sc)
        except Exception as e:
            why[f"unreadable: {type(e).__name__}"] += 1
            continue
        stem = re.sub(r"[^\w-]+", "_", sc.stem)[:80]
        for pi, part in enumerate(root.findall("part")):
            if staves_of(part) != 1:
                why["part on two staves"] += 1
                continue
            for k, (ms, state, show_time) in enumerate(pieces(part, tg, rng)):
                if "clef" not in state or "key" not in state:
                    why["no clef or key"] += 1
                    continue
                try:
                    lmx = encode(build(ms, state, show_time))
                except Exception as e:
                    why[f"encoder: {type(e).__name__}"] += 1
                    continue
                if not any(EVENT.match(t) and t != "rest" for t in lmx.split()):
                    why["only rests"] += 1  # whole-bar rests alone carry no durations the LMX reader can place
                    continue
                if "print-object:no" in lmx.split():  # hidden rests and clefs: our labels have none
                    why["a hidden object"] += 1
                    continue
                unknown = set(lmx.split()) - VOCAB
                if unknown:
                    why["unknown token " + sorted(unknown)[0]] += 1
                    continue
                d = a.out / stem
                d.mkdir(parents=True, exist_ok=True)
                (d / f"p{pi}-{k:03d}.lmx").write_text(lmx + "\n")
                why["written"] += 1
        print(sc.name, dict(why), file=sys.stderr, flush=True)
    print(json.dumps(dict(why.most_common()), indent=1))


if __name__ == "__main__":
    main()
