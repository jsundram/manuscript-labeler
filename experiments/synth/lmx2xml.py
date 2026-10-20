# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless", "numpy", "lxml", "pillow",
#   # the LMX reader (Delinearizer); score_to_lmx.py writes LMX with Zeus's pinned encoder
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""LMX (Zeus's and our staves') -> single-part MusicXML, via the lmx package's
Delinearizer. Adds <stem> directions (our LMX has none): per beamed group or
chord, by the note farthest from the middle line; voice 2 down. Secondary
beams that end or continue without a begin become hooks or begins.

    uv run lmx2xml.py IN.lmx OUT.musicxml
"""
import sys
import xml.etree.ElementTree as ET

from lmx.linearization.Delinearizer import Delinearizer
from lmx.symbolic.part_to_score import part_to_score

STEPS = "CDEFGAB"
MIDDLE = {("G", "2"): 6 + 28, ("C", "3"): 28, ("C", "4"): 5 + 21, ("F", "4"): 1 + 21, ("C", "1"): 2 + 28}
NO_STEM = {"whole", "breve"}


def _pos(note):
    p = note.find("pitch")
    if p is None:
        return None
    return STEPS.index(p.findtext("step")) + 7 * int(p.findtext("octave"))


def add_stems(part: ET.Element):
    middle = MIDDLE[("G", "2")]
    for measure in part.findall("measure"):
        clef = measure.find("attributes/clef")
        if clef is not None:
            middle = MIDDLE.get((clef.findtext("sign"), clef.findtext("line")), middle)
        # group notes: chords (chord tag joins previous) and beams
        groups, cur, open_beam = [], [], False
        chords = []
        for n in measure.findall("note"):
            if n.find("rest") is not None or n.findtext("type") in NO_STEM:
                continue
            if n.find("chord") is not None and chords:
                chords[-1].append(n)
            else:
                chords.append([n])
        for ch in chords:
            beams = [b.text for b in ch[0].findall("beam")]
            cur.append(ch)
            if beams and beams[0] in ("begin", "continue"):
                open_beam = True
                continue
            if beams and beams[0] == "end":
                open_beam = False
            if not open_beam:
                groups.append(cur)
                cur = []
        if cur:
            groups.append(cur)
        for g in groups:
            notes = [n for ch in g for n in ch]
            voice = notes[0].findtext("voice") or "1"
            ps = [p for p in map(_pos, notes) if p is not None]
            if not ps:
                continue
            far = max(ps, key=lambda p: abs(p - middle))
            d = "down" if far >= middle else "up"
            if voice == "2":
                d = "down"
            elif any(m.findtext("voice") == "2" for m in measure.findall("note")):
                d = "up"
            for n in notes:
                for old in n.findall("stem"):
                    n.remove(old)
                s = ET.Element("stem")
                s.text = d
                # MusicXML order: stem goes after type/dot/accidental/time-modification
                kids = list(n)
                idx = len(kids)
                for i, k in enumerate(kids):
                    if k.tag in ("notehead", "staff", "beam", "notations", "lyric"):
                        idx = i
                        break
                n.insert(idx, s)


def fix_beams(part: ET.Element):
    """Secondary beams that end/continue without a begin (a beam over a rest:
    8th, 32nd rest, 32nd) become hooks / begins, so a renderer accepts them."""
    for measure in part.findall("measure"):
        open_ = set()
        for n in measure.findall("note"):
            if n.find("chord") is not None:
                continue
            for b in n.findall("beam"):
                k = int(b.get("number", "1"))
                if b.text == "begin":
                    open_.add(k)
                elif b.text == "continue" and k not in open_:
                    b.text = "begin"
                    open_.add(k)
                elif b.text == "end":
                    if k in open_:
                        open_.discard(k)
                    else:
                        b.text = "backward hook"


FLAGS = {"16th": 2, "32nd": 3, "64th": 4}


def autobeam(part: ET.Element):
    """Beam runs of unbeamed 16ths/32nds within a quarter beat. For labels made
    before edition 518fdc0 (dataL), which left out LilyPond's automatic beams;
    never for dataL2 or later, whose unbeamed notes are flagged as written."""
    div = 1
    for measure in part.findall("measure"):
        d = measure.find("attributes/divisions")
        if d is not None:
            div = int(d.text)
        if measure.find("backup") is not None:
            continue
        t = 0
        runs, cur, cur_beat = [], [], None
        chord_of = {}
        last = None
        for n in measure.findall("note"):
            if n.find("chord") is not None:
                chord_of.setdefault(id(last), []).append(n)
                continue
            last = n
            if n.find("grace") is not None:
                continue
            dur = int(n.findtext("duration") or 0)
            beat = t // div
            ok = (n.find("rest") is None and n.find("beam") is None and n.findtext("type") in FLAGS)
            if ok and (cur and beat == cur_beat):
                cur.append(n)
            else:
                if len(cur) > 1:
                    runs.append(cur)
                cur, cur_beat = ([n], beat) if ok else ([], None)
            t += dur
        if len(cur) > 1:
            runs.append(cur)
        for run in runs:
            levels = [FLAGS[n.findtext("type")] for n in run]
            for i, n in enumerate(run):
                vals = []
                for k in range(1, levels[i] + 1):
                    prev = i > 0 and levels[i - 1] >= k
                    nxt = i < len(run) - 1 and levels[i + 1] >= k
                    vals.append("continue" if prev and nxt else "begin" if nxt else "end" if prev
                                else ("backward hook" if i else "forward hook"))
                for m in [n] + chord_of.get(id(n), []):
                    kids = list(m)
                    idx = next((j for j, c in enumerate(kids) if c.tag in ("notations", "lyric")), len(kids))
                    for k, v in reversed(list(enumerate(vals, 1))):
                        b = ET.Element("beam", number=str(k))
                        b.text = v
                        m.insert(idx, b)


def lmx_to_musicxml(text: str, name: str = "Violin", beam=False) -> str:
    d = Delinearizer(errout=sys.stderr)
    d.process_text(text)
    fix_beams(d.part_element)
    if beam:
        autobeam(d.part_element)
    add_stems(d.part_element)
    tree = part_to_score(d.part_element, part_id="P1", part_name=name)
    return ET.tostring(tree.getroot(), encoding="unicode", xml_declaration=True)


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    open(dst, "w").write(lmx_to_musicxml(open(src).read()))
