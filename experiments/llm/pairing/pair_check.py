# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic", "numpy", "pillow", "verovio"]
# ///
"""Pairing by asking Claude: shown one staff of a manuscript part and a
window of the score's bars around the pairing's proposal, which bars does
the staff hold? Several setups of the picture and the score, compared on
the staves the pairing leaves out of G. 213's KHM 587, whose bars are known
from the editor's fixed pages (khm587-staves.json: counted on from the last
right kept staff of the part, landing on the next one) and kept staves the
editor's counts confirm, each shown a window of bars around its own,
shifted by -2 to 2 so the answer isn't the window's middle.

    uv run experiments/llm/pairing/pair_check.py --setup text-1x --limit 20 [--model claude-opus-5-5] [--effort medium]
    uv run experiments/llm/pairing/pair_check.py --score     every setup's results so far

The setups:
  text-1x     the staff as the pairing crops it (2,800 px pages); the score's bars as text
  text-2x     the staff from a page rendered twice as large, in two rows; the bars as text
  engraved-2x the staff as text-2x; the bars engraved (verovio), numbered
  boxes-2x    as engraved-2x, the staff's detected bar lines drawn and its bar boxes lettered

Each answer goes to results/<setup>-<model>-<effort>.jsonl with its tokens
and cost (Opus 5.5: $4 / $20 per million in / out); the pictures sent to
~/Data/manuscript-labeler/llm-pairing/<setup>/, to look at.
"""

import argparse
import base64
import copy
import io
import json
import subprocess
import sys
import tempfile
import threading
import os
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parents[1] / "zeus"
sys.path.insert(0, str(ZEUS))
import compare  # noqa: E402

SOURCE = "G213-KHM587"
SCORE = Path.home() / "Data/manuscript-labeler/zeus/g213/sq8454356_cleaned.musicxml"
OUT = Path.home() / "Data/manuscript-labeler/llm-pairing"
PARTS = ("vn1", "vn2", "va", "vc")
NAMES = {"vn1": "violin I", "vn2": "violin II", "va": "viola", "vc": "cello"}
ROMAN = ["I", "II", "III", "IV"]
PRICE = {"claude-opus-5-5": (4.0, 20.0), "claude-sonnet-5-5": (2.0, 10.0), "claude-haiku-5-5": (0.10, 0.50)}
SETUPS = ("text-1x", "text-2x", "engraved-2x", "boxes-2x", "check-text-1x")
DUR = {"whole": "whole", "half": "half", "quarter": "quarter", "eighth": "8th", "16th": "16th", "32nd": "32nd",
       "64th": "64th", "breve": "breve"}


# -- the score ------------------------------------------------------------------------------

def movements(part: str) -> list[list[ET.Element]]:
    """The part's <measure> elements by movement, as mxl.movements splits them (bar = index there)."""
    p = ET.parse(SCORE).getroot().findall("part")[PARTS.index(part)]
    mvts, last = [], None
    for m in p.findall("measure"):
        num = m.get("number") or ""
        n = int(num) if num.isdigit() else None
        if not mvts or (n is not None and last is not None and n <= last):
            mvts.append([])
            last = None
        mvts[-1].append(m)
        last = n if n is not None else last
    return mvts


def attributes_before(ms: list[ET.Element], a: int, earlier: list[ET.Element] = ()) -> ET.Element:
    """One <attributes> with the divisions, key, time and clef in force at bar a, `earlier` the part's
    measures before the movement (the score gives a clef once, at the start of movement I)."""
    keep = {}
    for m in [*earlier, *ms[:a + 1]]:
        for at in m.findall("attributes"):
            for el in at:
                keep[el.tag] = el
    out = ET.Element("attributes")
    for tag in ("divisions", "key", "time", "clef"):
        if tag in keep:
            out.append(copy.deepcopy(keep[tag]))
    return out


def bar_note(m: ET.Element) -> str:
    num = m.get("number") or ""
    return "" if num.isdigit() else " (the rest of the bar before, after a repeat sign)"


def score_text(part: str, mv: str, a: int, b: int) -> str:
    """Bars a..b as text: the clef, key and time in force, then each bar's notes in order."""
    ms = movements(part)[ROMAN.index(mv)]
    at = attributes_before(ms, a, sum(movements(part)[:ROMAN.index(mv)], []))
    fifths = int(at.findtext("key/fifths", "0"))
    key = f"{abs(fifths)} {'sharp' if fifths > 0 else 'flat'}{'s' if abs(fifths) != 1 else ''}" if fifths else "no sharps or flats"
    clef = (at.findtext("clef/sign", "G") + at.findtext("clef/line", "")) if at.find("clef") is not None else "G2"
    time = f"{at.findtext('time/beats')}/{at.findtext('time/beat-type')}" if at.find("time") is not None else "?"
    lines = [f"Clef {clef}, key signature {key}, time {time}. Pitches are written as in the score (letter and octave, "
             "middle C = C4), with an accidental only where the score prints one."]
    for i in range(a, b + 1):
        evs = []
        voices = {n.findtext("voice", "1") for n in ms[i].findall("note") if n.get("print-object") != "no"}
        for n in ms[i].findall("note"):
            if n.get("print-object") == "no":
                continue
            who = f" (voice {n.findtext('voice', '1')})" if len(voices) > 1 else ""  # a bar's voices come one after the other
            kind = DUR.get(n.findtext("type") or "", n.findtext("type") or "whole")
            kind += "." * len(n.findall("dot"))
            trem = n.find("notations/ornaments/tremolo")
            if trem is not None and trem.get("type", "single") == "single":  # repeated notes written as strokes
                kind += f" with {trem.text} tremolo stroke{'s' if trem.text != '1' else ''}"
            if n.find("rest") is not None:
                evs.append(f"rest {kind}{who}")
                continue
            p = n.findtext("pitch/step") + {"sharp": "#", "flat": "b", "natural": "♮"}.get(n.findtext("accidental") or "", "") \
                + n.findtext("pitch/octave")
            if n.find("chord") is not None and evs:
                evs[-1] = evs[-1].replace(" ", f"+{p} ", 1)
            else:
                evs.append(("grace " if n.find("grace") is not None else "") + f"{p} {kind}{who}")
        for c in ms[i].iter("clef"):
            if ms[i].find("attributes") is not None and ms[i] is not ms[a]:
                evs.insert(0, f"[clef {c.findtext('sign')}{c.findtext('line', '')}]")
        lines.append(f"bar {i}{bar_note(ms[i])}: " + ", ".join(evs))
    return "\n".join(lines)


VEROVIO = threading.Lock()  # verovio is not safe in two threads at once: its SVGs come out broken


def score_png(part: str, mv: str, a: int, b: int) -> bytes:
    """Bars a..b engraved by verovio on one line, each bar numbered with its index."""
    cached = OUT / "scores" / f"{part}-{mv}-{a}-{b}.png"  # engraved once: verovio sometimes fails to load its font
    if not cached.exists():
        with VEROVIO:
            png = _score_png(part, mv, a, b)
        cached.parent.mkdir(parents=True, exist_ok=True)
        cached.write_bytes(png)
    return cached.read_bytes()


def _score_png(part: str, mv: str, a: int, b: int) -> bytes:
    import verovio
    tk = verovio.toolkit()
    tk.setOptions({"breaks": "none", "mnumInterval": 1, "header": "none", "footer": "none", "scale": 60,
                   "adjustPageHeight": True, "adjustPageWidth": True, "pageMarginLeft": 20, "pageMarginRight": 20})
    tk.loadData(score_xml(part, mv, a, b))
    with tempfile.TemporaryDirectory() as d:
        svg = Path(d) / "s.svg"
        svg.write_text(tk.renderToSVG(1))
        png = subprocess.run(["rsvg-convert", "-b", "white", "-w", "2400", str(svg)], capture_output=True, check=True).stdout
    return png


def score_xml(part: str, mv: str, a: int, b: int) -> str:
    """Bars a..b of the part as a MusicXML score of their own, each measure numbered with its index."""
    ms = movements(part)[ROMAN.index(mv)]
    root = ET.Element("score-partwise", version="3.1")
    pl = ET.SubElement(root, "part-list")
    sp = ET.SubElement(pl, "score-part", id="P1")
    ET.SubElement(sp, "part-name").text = ""
    p = ET.SubElement(root, "part", id="P1")
    for i in range(a, b + 1):
        m = copy.deepcopy(ms[i])
        m.set("number", str(i))
        for el in m.findall("print"):
            m.remove(el)
        if i == a:
            for el in m.findall("attributes"):
                m.remove(el)
            m.insert(0, attributes_before(ms, a, sum(movements(part)[:ROMAN.index(mv)], [])))
        p.append(m)
    return ET.tostring(root, encoding="unicode")


# -- the staff ------------------------------------------------------------------------------

def page(pdf: Path, n: int, px: int) -> np.ndarray:
    if px == compare.RENDER_PX:
        return compare.page_image(pdf, n)
    out = OUT / "pages" / f"p{n:03d}-{px}.png"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(f".{out.stem}.{os.getpid()}.{threading.get_ident()}")  # renamed when whole: no half-read file
        subprocess.run(["pdftoppm", "-f", str(n), "-l", str(n), "-scale-to", str(px), "-gray", "-png", "-singlefile",
                        str(pdf), str(tmp)], check=True)
        os.replace(f"{tmp}.png", out)
    return np.asarray(Image.open(out).convert("L")).astype(np.float32)


def staff_png(sid: str, scale: int, boxes: bool, source: str = SOURCE, pad: float = 2.5) -> bytes:
    """The staff (compare.staff_crop) from a page rendered `scale` times the pairing's size; at 2x in two
    rows, each half overlapping the other by a little. With boxes, the detected bar lines drawn in red and
    the bar boxes lettered a, b, c ... above the staff."""
    auto = json.loads((ZEUS / "auto" / f"{source}.json").read_text())
    n, k = sid[1:].split("-")
    s = sorted(auto["pages"][n]["systems"], key=lambda s: s["top"])[int(k)]
    g = page(Path(auto["pdf"]), int(n), compare.RENDER_PX * scale)
    im = Image.open(io.BytesIO(compare.staff_crop(g, s, pad))).convert("RGB")
    if boxes:
        W = g.shape[1]
        sp = (s["bottom"] - s["top"]) / 4 * g.shape[0]
        x0 = int(max(0, s["left"] * W - sp))
        d = ImageDraw.Draw(im)
        font = ImageFont.load_default(size=int(1.6 * sp))
        lines = [int((b["x0"] + b["x1"]) / 2 * W) - x0 for b in sorted(s["barlines"], key=lambda b: b["x0"])]
        for x in lines:
            d.line([(x, 0), (x, int(1.2 * sp))], fill=(220, 0, 0), width=max(2, scale * 2))
            d.line([(x, im.height - int(1.2 * sp)), (x, im.height)], fill=(220, 0, 0), width=max(2, scale * 2))
        edges = [int(s.get("start", s["left"]) * W) - x0] + lines + [int(s["right"] * W) - x0]
        for i, (a, b) in enumerate(e for e in zip(edges, edges[1:]) if e[1] - e[0] > 1.5 * sp):
            d.text(((a + b) / 2, 0), "abcdefghijklmnopqrstuvwxyz"[i], fill=(220, 0, 0), font=font, anchor="mt")
    if scale > 1:
        w, h, lap = im.width, im.height, im.width // 40
        top, bot = im.crop((0, 0, w // 2 + lap, h)), im.crop((w // 2 - lap, 0, w, h))
        two = Image.new("RGB", (top.width, 2 * h + 12), "white")
        two.paste(top, (0, 0))
        two.paste(bot, (0, h + 12))
        im = two
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return buf.getvalue()


# -- asking ---------------------------------------------------------------------------------

SCHEMA = {"type": "object", "additionalProperties": False,
          "required": ["evidence", "first_bar", "last_bar"],
          "properties": {"evidence": {"type": "string"}, "first_bar": {"type": "integer"}, "last_bar": {"type": "integer"}}}
CHECK = {"type": "object", "additionalProperties": False, "required": ["evidence", "right"],
         "properties": {"evidence": {"type": "string"}, "right": {"type": "boolean"}}}


def claims(x: dict) -> list[list[int]]:
    """For check-*: the staff's true bars, and the same moved by one bar at one end or both (fixed per staff)."""
    f, l = x["first"], x["last"]
    k = sum(map(ord, x["staff"])) % 6
    wrong = [[f - 1, l], [f + 1, l], [f, l - 1], [f, l + 1], [f - 1, l - 1], [f + 1, l + 1]][k]
    if wrong[0] > wrong[1]:
        wrong = [f - 1, l - 1]
    return [[f, l], wrong]


def prompt(setup: str, x: dict, a: int, b: int, claim: list | None = None) -> list:
    part, mv = x["part"], x["movement"]
    two = setup not in ("text-1x", "check-text-1x")
    staff = ("The first image is one line (staff) of a hand-copied part, " + NAMES[part] +
             f", of Boccherini's string quartet G. 213, movement {mv}" +
             (", shown in two rows: the top row is the left half of the line, the bottom row the right half "
              "(they overlap a little)" if two else "") + ".")
    if setup == "boxes-2x":
        staff += (" Red ticks above and below the staff mark where a program found bar lines; the red letters "
                  "name the spaces between them. The program misses some bar lines and finds some that aren't "
                  "there, so trust the music, not the marks.")
    if setup in ("engraved-2x", "boxes-2x"):
        score = (f"The second image is bars {a} to {b} of the same part from a modern edition, engraved, each bar "
                 "numbered above it. The bar numbers are what to answer with.")
        score_parts = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                                     "data": base64.b64encode(score_png(part, mv, a, b)).decode()}}]
    else:
        score = f"Below are bars {a} to {b} of the same part from a modern edition, as text:\n\n" + score_text(part, mv, a, b)
        score_parts = []
    ask = (f"The line holds a run of consecutive bars from these. Which bar does its music begin in, and which bar "
           "does it end in? A line can begin with the end of a bar the line before started (no bar line before "
           "it), and can end partway through a bar that the next line finishes; answer with those bars too. "
           "Copyists' notation differs from the edition's (beaming, stems, abbreviations, ornaments), so match "
           "pitches and rhythm. In `evidence`, say briefly which notes fixed the first and last bars.")
    if claim:
        ask = (f"A program that matched this line to the edition says the line holds bars {claim[0]} to {claim[1]}: "
               f"its music begins in bar {claim[0]} and ends in bar {claim[1]}. Is that exactly right? A line can "
               "begin with the end of a bar the line before started, or end partway through a bar the next line "
               "finishes; those bars count as the line's. "
               "Copyists' notation differs from the edition's (beaming, stems, abbreviations, ornaments), so match "
               "pitches and rhythm. In `evidence`, say which notes at each end decide it.")
    content = [{"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                            "data": base64.b64encode(staff_png(x["staff"], 2 if two else 1, setup == "boxes-2x")).decode()}}]
    content += score_parts
    content.append({"type": "text", "text": "\n\n".join([staff, score, ask])})
    return content


def ask(client, model: str, effort: str, setup: str, x: dict, claim: list | None = None) -> dict:
    a, b = x["window"]
    a, b = (min(a, claim[0]), max(b, claim[1])) if claim else (a, b)
    content = prompt(setup, x, a, b, claim)
    d = OUT / setup
    d.mkdir(parents=True, exist_ok=True)
    for i, c in enumerate(c for c in content if c["type"] == "image"):
        (d / f"{x['staff']}-{i}.png").write_bytes(base64.b64decode(c["source"]["data"]))
    r = client.messages.create(model=model, max_tokens=16000, messages=[{"role": "user", "content": content}],
                               output_config={"effort": effort, "format": {"type": "json_schema", "schema": CHECK if claim else SCHEMA}})
    text = next((blk.text for blk in r.content if blk.type == "text"), "")
    got = json.loads(text) if r.stop_reason == "end_turn" and text else {}
    pin, pout = PRICE[model]
    cost = (r.usage.input_tokens * pin + r.usage.output_tokens * pout) / 1e6
    return {"staff": x["staff"], "kind": x["kind"], "window": [a, b], "truth": [x["first"], x["last"]],
            "proposal": x["proposal"][1:], "answer": [got.get("first_bar"), got.get("last_bar")],
            **({"claim": claim, "says right": got.get("right")} if claim else {}),
            "evidence": got.get("evidence"), "stop": r.stop_reason, "in": r.usage.input_tokens,
            "out": r.usage.output_tokens, "cost": round(cost, 4)}


def score():
    for f in sorted((HERE / "results").glob("*.jsonl")):
        rows = [json.loads(line) for line in f.read_text().splitlines()]
        if not rows:
            continue
        if "claim" in rows[0]:
            for k in ("left out", "kept"):
                pos = [r for r in rows if r["kind"] == k and r["claim"] == r["truth"]]
                neg = [r for r in rows if r["kind"] == k and r["claim"] != r["truth"]]
                print(f"{f.stem:40} {k:8}: true bars accepted {sum(r['says right'] is True for r in pos)}/{len(pos)}, "
                      f"moved bars rejected {sum(r['says right'] is False for r in neg)}/{len(neg)}")
            print(f"{'':40} ${sum(r['cost'] for r in rows):.2f}, {sum(r['in'] for r in rows) // len(rows)} in / "
                  f"{sum(r['out'] for r in rows) // len(rows)} out a question")
            continue
        right = {k: f"{sum(r['answer'] == r['truth'] for r in rows if r['kind'] == k)}/{sum(r['kind'] == k for r in rows)}"
                 for k in ("left out", "kept")}
        near = sum(r["answer"] != r["truth"] and None not in r["answer"]
                   and max(abs(p - q) for p, q in zip(r["answer"], r["truth"])) == 1 for r in rows)
        print(f"{f.stem:40} right: left out {right['left out']}, kept {right['kept']}; {near} off by one; "
              f"${sum(r['cost'] for r in rows):.2f}, "
              f"{sum(r['in'] for r in rows) // len(rows)} in / {sum(r['out'] for r in rows) // len(rows)} out a staff")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--setup", choices=SETUPS)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.score:
        return score()
    staves = json.loads((HERE / "khm587-staves.json").read_text())
    staves = staves[:a.limit] if a.limit else staves
    import anthropic
    client = anthropic.Anthropic()
    out = HERE / "results" / f"{a.setup}-{a.model}-{a.effort}.jsonl"
    out.parent.mkdir(exist_ok=True)
    key = lambda staff, claim: f"{staff}:{claim}"
    done = {key(r["staff"], r.get("claim")) for r in map(json.loads, out.read_text().splitlines())} if out.exists() else set()
    jobs = [(x, c) for x in staves for c in (claims(x) if a.setup.startswith("check") else [None])]
    todo = [(x, c) for x, c in jobs if key(x["staff"], c) not in done]
    with ThreadPoolExecutor(4) as pool, open(out, "a") as f:
        for row in pool.map(lambda xc: ask(client, a.model, a.effort, a.setup, *xc), todo):
            f.write(json.dumps(row) + "\n")
            f.flush()
            print(row["staff"], "truth", row["truth"], "claim", row.get("claim"), "says", row.get("says right"),
                  "answer", row["answer"], f"${row['cost']}", flush=True)


if __name__ == "__main__":
    main()
