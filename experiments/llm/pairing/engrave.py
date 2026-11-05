"""The score's bars engraved, for a person to read beside what Opus read as
text (spotcheck.py): G. 213's from its MusicXML (pair_check.score_xml),
Philhar's encodings' converted from their events (philhar.encoding) to a
MusicXML of their own: notes and rests, chords, voices, grace notes,
tuplets, beams, ties, tremolo strokes, clef, key and time. Not slurs,
dynamics or articulations: the bars are to be matched by pitch and rhythm.
"""

import re
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from fractions import Fraction
from pathlib import Path

import check_leftout as cl

DIV = 96  # divisions of a quarter: a triplet 32nd is 8
BASE = {"breve": Fraction(8), "whole": Fraction(4), "half": Fraction(2), "quarter": Fraction(1), "8th": Fraction(1, 2),
        "16th": Fraction(1, 4), "32nd": Fraction(1, 8), "64th": Fraction(1, 16)}
BEAMS = {"8th": 1, "16th": 2, "32nd": 3, "64th": 4}
CLEF = {"clefs.G": ("G", "2"), "clefs.C": ("C", "3"), "clefs.F": ("F", "4")}
SHARPS, FLATS = "FCGDAEB", "BEADGCF"


def engrave(xml: str, bars: tuple[int, int] | None = None) -> bytes:
    """A MusicXML score as a PNG, every bar numbered, broken into lines; with `bars`, the bars outside
    that range greyed."""
    import verovio
    with cl.pc.VEROVIO:  # verovio in two threads at once fails to load its fonts
        tk = verovio.toolkit()
        tk.setOptions({"breaks": "auto", "pageWidth": 2400, "mnumInterval": 1, "header": "none", "footer": "none",
                       "scale": 45, "adjustPageHeight": True, "pageMarginLeft": 30, "pageMarginRight": 30,
                       "pageMarginTop": 30, "pageMarginBottom": 30, "svgAdditionalAttribute": ["measure@n"]})
        if not tk.loadData(xml) or not tk.getPageCount():
            raise RuntimeError("verovio couldn't engrave the bars")
        svgs = [tk.renderToSVG(n) for n in range(1, tk.getPageCount() + 1)]
    with tempfile.TemporaryDirectory() as d:
        pngs = []
        for n, s in enumerate(svgs, 1):
            svg = Path(d) / f"s{n}.svg"
            svg.write_text(_grey(s, bars) if bars else s)
            pngs.append(subprocess.run(["rsvg-convert", "-b", "white", "-w", "1600", str(svg)], capture_output=True,
                                       check=True).stdout)
    return pngs[0] if len(pngs) == 1 else _stack(pngs)


def _grey(svg: str, bars: tuple[int, int]) -> str:
    """The measures outside bars (verovio's data-n) drawn faint."""
    def faint(m):
        n = m.group(1)
        return m.group(0) if n.isdigit() and bars[0] <= int(n) <= bars[1] else m.group(0).replace("<g ", '<g opacity="0.3" ', 1)
    return re.sub(r'<g [^>]*class="measure"[^>]*data-n="([^"]*)"[^>]*>', faint, svg)


def _stack(pngs: list[bytes]) -> bytes:
    import io
    from PIL import Image
    ims = [Image.open(io.BytesIO(p)).convert("RGB") for p in pngs]
    out = Image.new("RGB", (max(i.width for i in ims), sum(i.height for i in ims)), "white")
    y = 0
    for im in ims:
        out.paste(im, (0, y))
        y += im.height
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def _key_alter(fifths: int) -> dict[str, int]:
    return {s: 1 for s in SHARPS[:fifths]} if fifths > 0 else {s: -1 for s in FLATS[:-fifths]}


def _pitch(name: str) -> tuple[str, int, int]:
    """'Eb3' -> ('E', -1, 3)."""
    m = re.fullmatch(r"([A-G])(#{0,2}|b{0,2})(-?\d+)", name)
    return m[1], m[2].count("#") - m[2].count("b"), int(m[3])


def philhar_xml(lily: Path, quartet: str, part: str, mv: str, a: int, b: int) -> str:
    """Bars a..b of Philhar's encoding of a part's movement as a MusicXML score, each measure numbered."""
    d = cl.philhar.encoding(cl.pp.EDITION, lily, quartet, part, mv)
    kts = sorted(((int(n), v) for n, v in d["key_time"].items()), key=lambda kv: kv[0])
    root = ET.Element("score-partwise", version="3.1")
    sp = ET.SubElement(ET.SubElement(root, "part-list"), "score-part", id="P1")
    ET.SubElement(sp, "part-name").text = ""
    p = ET.SubElement(root, "part", id="P1")
    clef = next((e["clef"] for n in range(a, -1, -1) for e in d["bars"].get(str(n), []) if e["clef"]), "clefs.G")
    in_force = None
    for n in range(a, b + 1):
        m = ET.SubElement(p, "measure", number=str(n))
        kt = [v for k, v in kts if k <= n][-1] if any(k <= n for k, _ in kts) else [0, "4/4"]
        fifths, time_ = kt
        beats, beat_type = time_.split("/")
        bar_len = Fraction(int(beats) * 4, int(beat_type))
        if kt != in_force or n == a:
            at = ET.SubElement(m, "attributes")
            if n == a:
                ET.SubElement(at, "divisions").text = str(DIV)
            k = ET.SubElement(at, "key")
            ET.SubElement(k, "fifths").text = str(fifths)
            t = ET.SubElement(at, "time")
            ET.SubElement(t, "beats").text, ET.SubElement(t, "beat-type").text = beats, beat_type
            if n == a:
                c = ET.SubElement(at, "clef")
                ET.SubElement(c, "sign").text, ET.SubElement(c, "line").text = CLEF.get(clef, ("G", "2"))
            in_force = kt
        evs = d["bars"].get(str(n)) or [cl.REST]  # a bar a multi-bar rest covers isn't in the encoding
        voices = sorted({e["voice"] for e in evs if e["kind"] in ("note", "rest", "mmrest")})
        for vi, v in enumerate(voices):
            if vi:
                bk = ET.SubElement(m, "backup")
                ET.SubElement(bk, "duration").text = str(int(bar_len * DIV))
            _voice(m, [e for e in evs if e["voice"] == v], vi + 1, fifths, bar_len, clef)
            clef = next((e["clef"] for e in reversed(evs) if e["clef"]), clef)
    return ET.tostring(root, encoding="unicode")


def _voice(m: ET.Element, evs: list[dict], voice: int, fifths: int, bar_len: Fraction, clef: str):
    """One voice's events into measure m; a voice that doesn't fill the bar is padded with a forward."""
    key, acc = _key_alter(fifths), {}
    used, tup, beam_open = Fraction(0), None, False
    for i, e in enumerate(evs):
        if e["clef"] and e["clef"] != clef and e["kind"] != "mmrest":
            clef = e["clef"]
            at = ET.SubElement(m, "attributes")
            c = ET.SubElement(at, "clef")
            ET.SubElement(c, "sign").text, ET.SubElement(c, "line").text = CLEF.get(clef, ("G", "2"))
        if any(t[0] == "stop" for t in e["tup"]):
            tup = None
        starts = [t for t in e["tup"] if t[0] == "start"]
        if starts:
            tup = (starts[0][2], starts[0][1])  # (actual, normal): 3 in the time of 2
        if e["kind"] == "mmrest":
            n = ET.SubElement(m, "note")
            ET.SubElement(n, "rest", measure="yes")
            ET.SubElement(n, "duration").text = str(int(bar_len * DIV))
            ET.SubElement(n, "voice").text = str(voice)
            used += bar_len
            continue
        if e["kind"] not in ("note", "rest"):
            continue
        base = e["dur"].rstrip(".")
        dots = e["dur"].count(".")
        dur = BASE.get(base, Fraction(1)) * (2 - Fraction(1, 2 ** dots))
        if tup:
            dur = dur * tup[1] / tup[0]
        grace = e["grace"] != "0"
        last_in_tup = tup and (i + 1 == len(evs) or any(t[0] == "stop" for t in evs[i + 1]["tup"]))
        pitches = e["notes"] if e["kind"] == "note" else [None]
        for j, pn in enumerate(pitches):
            n = ET.SubElement(m, "note")
            if grace:
                ET.SubElement(n, "grace", slash="yes")
            if j:
                ET.SubElement(n, "chord")
            if pn is None:
                ET.SubElement(n, "rest")
            else:
                step, alter, octave = _pitch(pn["pitch"])
                pt = ET.SubElement(n, "pitch")
                ET.SubElement(pt, "step").text = step
                if alter:
                    ET.SubElement(pt, "alter").text = str(alter)
                ET.SubElement(pt, "octave").text = str(octave)
            if not grace:
                ET.SubElement(n, "duration").text = str(int(dur * DIV))
            if pn is not None and e["tie"]:
                ET.SubElement(n, "tie", type="start")
            ET.SubElement(n, "voice").text = str(voice)
            ET.SubElement(n, "type").text = {"8th": "eighth"}.get(base, base)
            for _ in range(dots):
                ET.SubElement(n, "dot")
            if pn is not None:
                written = acc.get((step, octave), key.get(step, 0))
                if alter != written:
                    ET.SubElement(n, "accidental").text = {2: "double-sharp", 1: "sharp", 0: "natural", -1: "flat",
                                                           -2: "flat-flat"}[alter]
                    acc[(step, octave)] = alter
            if tup and not grace:
                tm = ET.SubElement(n, "time-modification")
                ET.SubElement(tm, "actual-notes").text, ET.SubElement(tm, "normal-notes").text = str(tup[0]), str(tup[1])
            if j == 0 and base in BEAMS and not grace:
                state = "begin" if "start" in e["beam"] else "end" if "stop" in e["beam"] else "continue" if beam_open else None
                beam_open = state in ("begin", "continue")
                for k in range(1, BEAMS[base] + 1) if state else ():
                    ET.SubElement(n, "beam", number=str(k)).text = state
            notations = []
            if j == 0 and tup and not grace and (starts or last_in_tup):
                notations.append(("tuplet", {"type": "start" if starts else "stop"}, None))
            if pn is not None and e["tie"]:
                notations.append(("tied", {"type": "start"}, None))
            if "tremolo" in e and pn is not None and j == 0:
                strokes = max(1, {"8": 1, "16": 2, "32": 3}.get(str(e["tremolo"]), 1) - BEAMS.get(base, 0))
                notations.append(("tremolo", {"type": "single"}, str(strokes)))
            if notations:
                nt = ET.SubElement(n, "notations")
                for tag, attrs, text in notations:
                    if tag == "tremolo":
                        ET.SubElement(ET.SubElement(nt, "ornaments"), tag, **attrs).text = text
                    else:
                        ET.SubElement(nt, tag, **attrs)
        if not grace:
            used += dur
    if used < bar_len:
        fw = ET.SubElement(m, "forward")
        ET.SubElement(fw, "duration").text = str(int((bar_len - used) * DIV))


def score_png(r: dict, grey: bool = False) -> bytes:
    """The window of bars Opus was shown for answer r, engraved by LilyPond from the LilyPond Opus may be given
    (notes.as_lily); with grey, the proposed bars bracketed. (verovio's engraving of a MusicXML, above, drew
    a two-note tremolo as two long notes.)"""
    import notes
    a, b = r["window"]
    head, bars = (notes.g213(r["part"], r["movement"], a, b) if r["quartet"] is None
                  else notes.philhar(cl.lilies()[r["source"]], r["quartet"], r["part"], r["movement"], a, b))
    return notes.engrave(notes.as_lily(head, bars, score=True, mark=tuple(r["claim"]) if grey else None))


def stacked_png(r: dict) -> bytes:
    """The manuscript's line on top, the proposed bars engraved on one line beneath it (no numbers),
    scaled to the same width: the two to be compared bar by bar."""
    import io
    import notes
    from PIL import Image
    f, l = r["claim"]
    head, bars = (notes.g213(r["part"], r["movement"], f, l) if r["quartet"] is None
                  else notes.philhar(cl.lilies()[r["source"]], r["quartet"], r["part"], r["movement"], f, l))
    top = Image.open(io.BytesIO(cl.pc.staff_png(r["staff"], 1, False, r["source"], pad=4))).convert("RGB")
    # the same staff size as the manuscript's (its crop is 4 staff spaces of staff and 4 above and below;
    # LilyPond's staff at 130 dpi is 7 mm, 36 px), but hardly smaller than LilyPond's, where the crop is bad;
    # and the line as wide as the manuscript's
    k = max(0.9, top.height / 3 / 36)
    width_mm = top.width / k / (130 / 25.4)
    bot = Image.open(io.BytesIO(notes.engrave(notes.as_lily(head, bars, score=True, plain=True, width_mm=width_mm)))).convert("RGB")
    k = min(k, top.width / bot.width)
    bot = bot.resize((max(1, round(bot.width * k)), max(1, round(bot.height * k))), Image.LANCZOS)
    gap = 24
    out = Image.new("RGB", (top.width, top.height + gap + bot.height), "white")
    out.paste(top, (0, 0))
    for x in range(0, top.width, 12):  # a dashed rule between the two
        out.paste((170, 170, 170), (x, top.height + gap // 2, min(x + 6, top.width), top.height + gap // 2 + 2))
    out.paste(bot, (0, top.height + gap))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()
