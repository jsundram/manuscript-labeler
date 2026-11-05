# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "verovio"]
# ///
"""A page for the editor to check new training labels: staves Opus's check
added to the pairing (experiments/zeus/add_opus.py), and multi-bar rests
the set builder now labels (`multirest:N`). Each card is the staff as the
reader sees it, over its label engraved, and asks: the same music, start
to end? Verdicts stay in the browser and are copied out as JSON.

    uv run experiments/llm/pairing/labelcheck.py DATA [--opus 15] [--rests 5] [--seed 0]

DATA is a dataset.py --out folder built from the plus-opus pairings
(DATA/<source>/<staff>.jpg and .lmx). Each label goes LMX -> MusicXML
(experiments/synth/lmx2xml.py) -> LilyPond (musicxml2ly), on one line as
wide as the staff. Writes experiments/llm/pairing/labelcheck.html.
"""

import argparse
from fractions import Fraction
import base64
import html
import io
import json
import random
import re
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote

import check_leftout as cl
import spotcheck

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parents[2] / "experiments" / "zeus"
LMX2XML = HERE.parents[2] / "experiments" / "synth" / "lmx2xml.py"
RESULTS = HERE / "results"


def engraved(lmx: str, width_mm: float) -> bytes:
    """The label on one line, `width_mm` wide: a multi-bar rest's count written over its bar."""
    counts = {}  # measure index -> multi-bar rest count
    k = -1
    for t in lmx.split():
        k += t == "measure"
        if t.startswith("multirest:"):
            counts[k] = t.split(":")[1]
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "in.lmx").write_text(re.sub(r" multirest:\d+", "", lmx))
        subprocess.run(["uv", "run", "-q", str(LMX2XML), str(d / "in.lmx"), str(d / "in.musicxml")], check=True,
                       capture_output=True)
        xml = fill_bar_rests((d / "in.musicxml").read_text(), counts)
        (d / "in.musicxml").write_text(xml)
        subprocess.run(["musicxml2ly", "--no-beaming", "-o", str(d / "in.ly"), str(d / "in.musicxml")], check=True,
                       capture_output=True)
        ly = (d / "in.ly").read_text()
        ly = re.sub(r"\\header\s*\{.*?\n\s*\}", "", ly, flags=re.S)
        ly = re.sub(r"(\\set Staff\.)?(short)?[iI]nstrumentName\s*=\s*\"[^\"]*\"", "", ly)
        if " time " not in f" {lmx} ":  # the label has no time signature: don't draw LilyPond's default
            ly = ly.replace("\\clef", "\\omit Staff.TimeSignature \\clef", 1)
        ly += ("\n\\header { tagline = ##f }\n\\paper { indent = 0 paper-width = %.1f\\mm left-margin = 5\\mm line-width = %.1f\\mm ragged-right = ##f "
               "system-count = 1 }\n\\layout { \\context { \\Score \\remove Bar_number_engraver } "
               "\\context { \\Staff \\remove Instrument_name_engraver } }\n" % (width_mm + 10, width_mm))
        (d / "in.ly").write_text(ly)
        subprocess.run(["lilypond", "-dcrop", "--png", "-dresolution=130", "-o", str(d / "in"), str(d / "in.ly")],
                       check=True, capture_output=True)
        png = next(iter(sorted(d.glob("in*.cropped.png")) or sorted(d.glob("in*.png"))))
        return png.read_bytes()


def fill_bar_rests(xml: str, counts: dict) -> str:
    """lmx2xml's MusicXML made fit for musicxml2ly: each measure numbered; a bar rest given the bar's
    length (the label's longest measure, the time not always written) and a whole-rest type; and a
    multi-bar rest's count ({measure index: N}) written over it."""
    import xml.etree.ElementTree as ET
    root = ET.fromstring(xml)
    for part in root.iter("part"):
        ms = part.findall("measure")
        lengths = []
        for m in ms:
            lengths.append(sum(int(n.findtext("duration") or 0) for n in m.findall("note")
                               if n.find("chord") is None and n.find("grace") is None and n.findtext("voice", "1") == "1"))
        div = int(root.findtext(".//divisions") or 1)
        bar = max(lengths) if any(lengths) else div * 4
        if ms and part.find(".//time") is None:  # else musicxml2ly takes 4/4 and pads each bar (not drawn: stacked)
            at = ms[0].find("attributes")
            if at is None:
                at = ET.Element("attributes")
                ms[0].insert(0, at)
            q = Fraction(bar, div)  # quarters
            beats, beat_type = (q, 4) if q.denominator == 1 else (q * 2, 8)
            t = ET.Element("time")
            ET.SubElement(t, "beats").text = str(int(beats))
            ET.SubElement(t, "beat-type").text = str(beat_type)
            kids = [c.tag for c in at]
            at.insert(next((kids.index(x) for x in ("staves", "clef") if x in kids), len(kids)), t)
        for i, m in enumerate(ms):
            m.set("number", str(i + 1))
            for n in m.findall("note"):
                r = n.find("rest")
                if r is not None and r.get("measure") == "yes" and n.find("duration") is None:
                    dur = ET.Element("duration")
                    dur.text = str(bar)
                    n.insert(list(n).index(r) + 1, dur)
                    if n.find("type") is None:
                        ET.SubElement(n, "type").text = "whole"
            if i in counts:
                dr = ET.Element("direction", placement="above")
                ET.SubElement(ET.SubElement(dr, "direction-type"), "words", {"font-weight": "bold"}).text = f"{counts[i]} bars"
                m.insert(0, dr)
    return ET.tostring(root, encoding="unicode")


def stacked(jpg: Path, lmx: str) -> bytes:
    """The staff as the reader sees it, over its label engraved to the same width."""
    from PIL import Image
    top = Image.open(jpg).convert("RGB")
    k = max(0.9, top.height / 3 / 36)  # as engrave.stacked_png: about the manuscript's staff size
    bot = Image.open(io.BytesIO(engraved(lmx, top.width / k / (130 / 25.4)))).convert("RGB")
    k = min(k, top.width / bot.width)
    bot = bot.resize((max(1, round(bot.width * k)), max(1, round(bot.height * k))), Image.LANCZOS)
    gap = 24
    out = Image.new("RGB", (top.width, top.height + gap + bot.height), "white")
    out.paste(top, (0, 0))
    for x in range(0, top.width, 12):
        out.paste((170, 170, 170), (x, top.height + gap // 2, min(x + 6, top.width), top.height + gap // 2 + 2))
    out.paste(bot, (0, top.height + gap))
    buf = io.BytesIO()
    out.save(buf, "PNG")
    return buf.getvalue()


def bar_text(k: dict) -> str:
    """The staff's bars in words, its cut ends said."""
    *piece, mv, f = k["bars"][0]
    l = k["bars"][-1][-1]
    name = " ".join([cl.title(piece[0]) if piece else "G. 213", "movement", mv])
    s = f"{name}, bars {f}–{l}" if f != l else f"{name}, bar {f}"
    for h in k.get("halves", []):
        how = "from the readings" if "reader" in h else "where the pairing cut it for the neighbouring line"
        where = "begins with the second part" if h["half"] == "second" else "ends with the first part"
        s += f"; {where} of bar {h['bar'][-1]}, cut {h['cut']} of a whole note in, {how}"
    return s


def kind(k: dict, lmx: str) -> str:
    if "multirest:" in lmx and "opus" not in k:
        return "rests"
    if any("reader" in h for h in k.get("halves", [])):
        return "cut from readings"
    if k.get("halves"):
        return "cut from a neighbour"
    return "whole bars"


def card(i: int, src: str, k: dict, lmx: str, jpg: Path, ids: dict) -> str:
    img = base64.b64encode(stacked(jpg, lmx)).decode()
    pdf = next((p for p, names in cl.pairing.sources().items() if src in names), None)
    link = (f"{spotcheck.LABELER}/#pdf={quote(ids[pdf.name], safe=':/')}&page={k['page']}"
            if pdf is not None and pdf.name in ids else None)
    what = kind(k, lmx)
    note = {"rests": "Pairing kept; the label now writes its multi-bar rest as one bar rest with its count.",
            "cut from readings": "Added from Opus's check; a bar it shares with an Opus-checked neighbour, cut where "
                                 "the two lines' readings fit.",
            "cut from a neighbour": "Added from Opus's check; a bar it shares with a kept neighbour, cut as the "
                                    "pairing cut it there.",
            "whole bars": "Added from Opus's check; its neighbours show it begins and ends on bar lines."}[what]
    key = f"{src}/{k['staff']}"
    group = ('<div class="buttons" data-q="label"><span class="q">label:</span>' +
             "".join(f'<button data-v="{v}">{v}</button>' for v in ("right", "wrong", "can't tell")) + "</div>")
    opus = (f'<details><summary>Opus\'s working</summary><p>{html.escape(k["opus"]["working"] or "")}</p></details>'
            if "opus" in k else "")
    return f"""
<section class="card" data-key="{html.escape(key)}">
  <h2>{i}. {html.escape(bar_text(k))}, {cl.pc.NAMES.get(k['part'], k['part'])}
    <span class="src">{html.escape(src)} · page {k['page']}, staff {int(k['staff'].split('-')[1]) + 1} from the top · {what}</span></h2>
  <img src="data:image/png;base64,{img}" alt="the staff over its label">
  <p class="ask"><b>Is the bottom line (the label) the same music as the top, from start to end?</b> {html.escape(note)}</p>
  {group}
  <div class="buttons"><input class="note" placeholder="what's wrong, or what made it hard"></div>
  {opus}
  {f'<p class="more"><a href="{link}" target="_blank">The page in the labeler</a></p>' if link else ''}
</section>"""


PAGE = (spotcheck.PAGE
        .replace("<title>Opus check spot-check</title>", "<title>New label check</title>")
        .replace("<h1>Opus check: spot-check</h1>", "<h1>New labels: check</h1>")
        .replace("const KEY = 'opus-spotcheck-v5';", "const KEY = 'label-check-v1';")
        .replace("const done = !!(v.top && (v.top !== TOP0 || (v.start && v.end && v.middle)));", "const done = !!v.label;"))
PAGE = re.sub(r"<p>Each staff:.*?</p>", "<p>Each staff: the picture the reader trains on, over its new label "
              "engraved. A label is right when every note, rest and rhythm matches, from the first note to the last "
              "(slurs, beams and stems aside). Your verdicts are kept in this browser; when you're done, press "
              "<b>Copy verdicts</b> and paste them back to Claude.</p>", PAGE, flags=re.S)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("data", type=Path)
    ap.add_argument("--opus", type=int, default=15)
    ap.add_argument("--rests", type=int, default=5)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    pool = {"rests": [], "cut from readings": [], "cut from a neighbour": [], "whole bars": []}
    for folder in sorted(p for p in a.data.iterdir() if p.is_dir()):
        src = folder.name
        res = json.loads((ZEUS / "results" / f"autopair-{src}-plus-opus.json").read_text())
        for k in res["kept"]:
            f = folder / f"{k['staff']}.lmx"
            if f.exists():
                lmx = f.read_text()
                if "opus" in k or "multirest:" in lmx:
                    pool[kind(k, lmx)].append((src, k, lmx, f.with_suffix(".jpg")))
    rng = random.Random(a.seed)
    share = {"cut from readings": 6, "cut from a neighbour": 4, "whole bars": a.opus - 10, "rests": a.rests}
    sample = [x for w, n in share.items() for x in rng.sample(pool[w], min(n, len(pool[w])))]
    rng.shuffle(sample)
    ids = spotcheck.labeler_ids()
    cards = []
    for i, (src, k, lmx, jpg) in enumerate(sample):
        try:
            cards.append(card(len(cards) + 1, src, k, lmx, jpg, ids))
        except subprocess.CalledProcessError as e:
            print(f"{src} {k['staff']}: not engraved ({(e.stderr or b'')[-200:]!r})")
    out = HERE / "labelcheck.html"
    out.write_text(PAGE.replace("%TOP0%", "null").replace("%CARDS%", "".join(cards)))
    print(f"{len(cards)} staves ({ {w: len(p) for w, p in pool.items()} } in the pool) -> {out}")


if __name__ == "__main__":
    main()
