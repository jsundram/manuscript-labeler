# /// script
# requires-python = ">=3.11"
# dependencies = [
#   "verovio==6.3.0", "resvg-py==0.5.0", "opencv-python-headless==4.10.0.84", "numpy", "lxml", "pillow",
#   "linearized-musicxml==1.0.0",
# ]
# ///
"""Staves with where each note, rest and bar line of their LMX is, for teaching the reader to point (musvit/pointer.py).

Each staff is OUT/<name>.jpg, OUT/<name>.lmx and OUT/<name>.pos.json: {"ss", "w", "h", "targets": [[token index,
kind, x, y], ...], ...}, x and y in the image's pixels. The token is the one that writes the symbol: a note's pitch
(a chord's every note), "rest", and "measure" for the bar line before that bar (a staff's first "measure" has none).
A bar line's y is the staff's middle (only its x is scored), as is a real rest's ("rest_x": the map places rests
sideways only).

rendered: drawn by sam_synth.render (the copyist's hand, or --plain fonts), each symbol's mask tied back to its
engraved element, the elements to the LMX's tokens bar by bar: notes by onset (a chord's notes by height), rests and
bar lines in order. A bar whose notes don't all land on their own line or space (within 0.35 of a space) gives no
note targets. The json also keeps the opening's end and the bar lines (as the labels give them) for the classical
map (pos_score.py).

    uv run experiments/synth/pos_data.py rendered LMX_LIST --glyphs GLYPHS/berlin --out DIR --n 500 [--plain] [--seed 0]

real: dataL2's staves with the classical map's notes and rests in the bars it got all but perfect (sam_data.good_bars),
and the labels' bar lines (all of them: the editor placed them).

    uv run experiments/synth/pos_data.py real KEY_LIST --maps DIR --out DIR

dolores: Dolores's staves (MusiCorpus v1.0; Zeus's copies of the staff images and MusicXML), each symbol's place from
the stylus polygon its annotator drew round it (the polygon's centroid; a note's from its head's own polygon), tied to
the MusicXML by MusiCorpus's links (noteN.notehead, restN, <measure id>.right_barline) and to the LMX's tokens as the
linearizer writes them. ANN is the annotations fetched from the MusiCorpus zip: <page>/Staves/<n>/coco-object-detection
.json (compacted: [id, category, bbox, cx, cy, polygon]) and <page>/Systems/<n>/coco-to-semantic.json.

    uv run experiments/synth/pos_data.py dolores SAMPLES.txt --ann ANN --out DIR [--n 1000] [--data ZEUS/data/dolores]
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

import cv2
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import align  # noqa: E402

PITCH = re.compile(r"[A-G]\d$")


def walk(lmx: str) -> list[dict]:
    """The LMX's bars, as align.parse reads them, with each event's token index: {"tok" (the "measure"), "events":
    [{"tok", "type", "step", "clef", "voice", "chord", "grace"}]}."""
    bars, clef, voice, pending = [], "G2", "1", []
    for i, t in enumerate(lmx.split()):
        if t == "measure":
            bars.append({"tok": i, "events": []})
            voice = "1"
        elif not bars:
            continue
        elif t.startswith("clef:"):
            clef = t[5:]
        elif t.startswith("voice:"):
            voice = t[6:]
            if bars[-1]["events"]:
                bars[-1]["events"][-1]["voice"] = voice
        elif t in ("chord", "grace", "grace:slash"):
            pending.append(t)
        elif PITCH.match(t) or t == "rest":
            bars[-1]["events"].append({"tok": i, "type": "rest" if t == "rest" else "note", "voice": voice, "clef": clef,
                                       "step": align.STEPS.index(t[0]) + 7 * int(t[1]) if t != "rest" else None,
                                       "chord": "chord" in pending, "grace": any(p.startswith("grace") for p in pending)})
            pending = []
    return bars


def onsets(events: list[dict]) -> list[list[dict]]:
    """Notes grouped into onsets: a note and the chord notes after it."""
    out = []
    for e in events:
        if e["type"] != "note":
            continue
        if e["chord"] and out:
            out[-1].append(e)
        else:
            out.append([e])
    return out


# -- rendered staves ------------------------------------------------------------------

def rendered_targets(lmx: str, det: dict, ss: float) -> tuple[list, dict]:
    import sam_synth
    from copyist import SVG, _cls
    tagged, idm = det["tagged"], det["idm"]
    centre = {}
    for i, (kind, el) in enumerate(tagged, 1):
        ys, xs = np.nonzero(idm == i)
        if len(xs):
            centre[id(el)] = (float(xs.mean()), float(ys.mean()), float(xs.min()), float(xs.max()))
    # the engraving's bars in order, each with its noteheads by onset (a note, or a chord), rests and bar line
    svg_bars = []
    root = tagged[0][1].getroottree().getroot() if tagged else None
    for m in (root.iter(f"{{{SVG}}}g") if root is not None else []):
        if not _cls(m, "measure"):
            continue
        groups, rests, bar = [], [], None
        for kind, el in tagged:
            if m not in el.iterancestors():
                continue
            if kind == "head":
                owner = next((a for a in el.iterancestors() if _cls(a, "chord")), None)
                if owner is None:
                    owner = next(a for a in el.iterancestors() if _cls(a, "note"))
                if groups and groups[-1][0] is owner:
                    groups[-1][1].append(el)
                else:
                    groups.append((owner, [el]))
            elif kind.startswith("rest"):
                rests.append(el)
            elif kind == "barline":
                bar = el
        svg_bars.append({"onsets": [g for _, g in groups], "rests": rests, "barline": bar})
    bars = walk(lmx)
    targets, stats = [], {"bars": len(bars), "note_bars_dropped": 0, "notes": 0}
    mid = 2.5 * ss + 2 * ss  # the middle line: the crop starts 2.5 spaces above the top line
    if len(svg_bars) != len(bars):
        stats["mismatch"] = [len(svg_bars), len(bars)]
        return [], stats
    for k, (b, sb) in enumerate(zip(bars, svg_bars)):
        lo = onsets(b["events"])
        # notes: onset by onset; within one, highest first on both sides
        ok = len(lo) == len(sb["onsets"]) and all(len(a) == len(e) for a, e in zip(lo, sb["onsets"]))
        mine = []
        if ok:
            for evs, els in zip(lo, sb["onsets"]):
                evs = sorted(evs, key=lambda e: -e["step"])
                cs = sorted((centre[id(el)] for el in els if id(el) in centre), key=lambda c: c[1])
                if len(cs) != len(evs):
                    ok = False
                    break
                for e, c in zip(evs, cs):
                    if abs(c[1] - align.height(e["step"], e["clef"], ss)) > 0.35 * ss:
                        ok = False
                    mine.append([e["tok"], "grace" if e["grace"] else "note", round(c[0], 1), round(c[1], 1)])
        if ok:
            targets += mine
            stats["notes"] += len(mine)
        elif lo:
            stats["note_bars_dropped"] += 1
        lr = [e for e in b["events"] if e["type"] == "rest"]
        if len(lr) == len(sb["rests"]):
            for e, el in zip(lr, sb["rests"]):
                if id(el) in centre:
                    c = centre[id(el)]
                    targets.append([e["tok"], "rest", round(c[0], 1), round(c[1], 1)])
        # the bar line closing bar k is "measure" of bar k+1
        if k + 1 < len(bars) and sb["barline"] is not None and id(sb["barline"]) in centre:
            targets.append([bars[k + 1]["tok"], "barline", round(centre[id(sb["barline"])][0], 1), round(mid, 1)])
    return targets, stats


def opening_end(det: dict) -> float | None:
    """Where the staff's opening (clef, key, time) ends: the first note, rest or bar line's left edge, less a space's
    worth of room, as the labels' "start" is placed (the classical map's input)."""
    xs = [np.nonzero(det["idm"] == i)[1].min() for i, (k, _) in enumerate(det["tagged"], 1)
          if (k == "head" or k.startswith("rest") or k in ("accidental", "barline")) and (det["idm"] == i).any()]
    return float(min(xs)) if xs else None


def rendered(a):
    import sam_synth
    sam_synth.KINDS.setdefault("mRest", "rest")  # whole-bar rests too (here only: sam_synth's windows leave them out)
    files = [Path(l) for l in a.src.read_text().split() if l]
    random.Random(a.seed).shuffle(files)
    fonts = tuple(a.fonts.split(","))
    rests = {} if a.plain else sam_synth.rest_library(a.glyphs)
    a.out.mkdir(parents=True, exist_ok=True)
    done, tally = 0, {"staves_failed": 0, "bars": 0, "note_bars_dropped": 0, "notes": 0, "mismatch": 0}
    for i, f in enumerate(files):
        if done >= a.n:
            break
        lmx = f.read_text()
        try:
            img, masks, ss, det = sam_synth.render(lmx, a.hand, a.seed + i, rests, fonts=fonts, plain=a.plain, detail=True)
        except Exception:
            tally["staves_failed"] += 1
            continue
        targets, st = rendered_targets(lmx, det, ss)
        if "mismatch" in st:
            tally["mismatch"] += 1
            continue
        for k in ("bars", "note_bars_dropped", "notes"):
            tally[k] += st[k]
        name = f"{f.parent.name}-{f.stem}-{a.seed + i}"
        h, w = img.shape
        bl = sorted(t[2] for t in targets if t[1] == "barline")
        cv2.imwrite(str(a.out / f"{name}.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        (a.out / f"{name}.lmx").write_text(lmx)
        (a.out / f"{name}.pos.json").write_text(json.dumps({"ss": ss, "w": w, "h": h, "source": str(f),
                                                             "start": opening_end(det), "barlines": bl,
                                                             "targets": targets}))
        done += 1
    print(f"{done} staves", json.dumps(tally), flush=True)


# -- real staves ----------------------------------------------------------------------

def real(a):
    import segment
    import sam_data
    a.out.mkdir(parents=True, exist_ok=True)
    tally = {"staves": 0, "bars": 0, "good": 0, "notes": 0, "rests": 0, "barlines": 0, "unmatched_bars": 0}
    for key in a.src.read_text().split():
        sk = key.replace("/", "_")
        m = json.loads((a.maps / f"{sk}.json").read_text())
        g = cv2.imread(str(a.data / f"{key}.jpg"), cv2.IMREAD_GRAYSCALE)
        lmx = (a.data / f"{key}.lmx").read_text()
        h, w = g.shape
        ss = m["ss"]
        good = {(int(x0), int(x1)) for x0, x1 in sam_data.good_bars(m, g, segment.segment(key, m, g))}
        bars = walk(lmx)
        targets = []
        mid = float(m["lines"][2])
        for k, (b, mb) in enumerate(zip(bars, m["bars"])):
            tally["bars"] += 1
            if k > 0:  # the labels' bar line opening this bar
                targets.append([b["tok"], "barline", round(float(mb["x0"]), 1), mid])
                tally["barlines"] += 1
            if (int(mb["x0"]), int(mb["x1"])) not in good:
                continue
            tally["good"] += 1
            # the map lists each voice in turn (voices with notes), in the label's order
            voices = sorted({e["voice"] for e in b["events"] if e["type"] == "note"})
            evs = [e for v in voices for e in b["events"] if e["voice"] == v]
            syms = mb["symbols"]
            if len(evs) != len(syms) or any((e["type"] == "rest") != bool(s.get("rest")) or
                                            (e["type"] == "note" and e["step"] != s["step"]) for e, s in zip(evs, syms)):
                tally["unmatched_bars"] += 1
                continue
            for e, s in zip(evs, syms):
                if s.get("rest"):
                    if s.get("found"):
                        targets.append([e["tok"], "rest_x", float(s["x"]), mid])  # x only: the map has no y for rests
                        tally["rests"] += 1
                elif not s.get("outside"):
                    targets.append([e["tok"], "grace" if e["grace"] else "note", float(s["x"]), float(s["y"])])
                    tally["notes"] += 1
        tally["staves"] += 1
        cv2.imwrite(str(a.out / f"{sk}.jpg"), g, [cv2.IMWRITE_JPEG_QUALITY, 95])
        (a.out / f"{sk}.lmx").write_text(lmx)
        (a.out / f"{sk}.pos.json").write_text(json.dumps({"ss": ss, "w": w, "h": h, "source": key, "targets": targets}))
    print(json.dumps(tally), flush=True)


def linearize(musicxml: Path) -> tuple[list[str], dict[str, int], dict[str, int]]:
    """The LMX tokens of a staff's MusicXML, with the token writing each <note> (its pitch or "rest", by the note's id)
    and each <measure>'s "measure" token (by the measure's id)."""
    import xml.etree.ElementTree as ET
    from lmx.linearization.Linearizer import Linearizer

    notes, measures = {}, {}

    class Tracing(Linearizer):
        def process_measure(self, measure):
            measures[measure.attrib.get("id")] = len(self.output_tokens)
            super().process_measure(measure)

        def process_note(self, note, measure):
            n0 = len(self.output_tokens)
            super().process_note(note, measure)
            i = next((i for i in range(n0, len(self.output_tokens))
                      if self.output_tokens[i] == "rest" or PITCH.match(self.output_tokens[i])), None)
            if i is not None and note.attrib.get("id"):
                notes[note.attrib["id"]] = i

    lin = Tracing(fail_on_unknown_tokens=False)
    lin.process_part(ET.parse(musicxml).getroot().find("part"))
    return lin.output_tokens, notes, measures


def dolores(a):
    from PIL import Image
    a.out.mkdir(parents=True, exist_ok=True)
    lines = [l for l in a.src.read_text().split() if l]
    random.Random(a.seed).shuffle(lines)
    tally = {"staves": 0, "no_ann": 0, "notes": 0, "rests": 0, "barlines": 0, "lmx_same_as_zeus": 0, "size_mismatch": 0}
    sems = {}
    for line in lines:
        if tally["staves"] >= a.n:
            break
        page, staff = line.split("/")[-2], line.split("/")[-1]  # samples/<page>/Staves_<n>
        ann = a.ann / page / "Staves" / staff.split("_")[1] / "coco-object-detection.json"
        if not ann.exists():
            tally["no_ann"] += 1
            continue
        if page not in sems:
            sems[page] = {}
            for f in (a.ann / page / "Systems").glob("*/coco-to-semantic.json"):
                sems[page] |= {int(k): v for k, v in json.loads(f.read_text()).items()}
        sem = sems[page]
        base = (a.src.parent / line) if (a.src.parent / line).with_suffix(".jpg").exists() else a.data / line
        jpg, mx = base.with_suffix(".jpg"), base.with_suffix(".musicxml")
        d = json.loads(ann.read_text())
        w, h = Image.open(jpg).size
        sx, sy = w / d["w"], h / d["h"]
        if abs(sx - 1) > 0.01 or abs(sy - 1) > 0.01:
            tally["size_mismatch"] += 1
        try:
            toks, notes, measures = linearize(mx)
        except Exception:
            continue
        # Zeus's LMX (what the reader learnt from) has a few tokens more (its linearizer's newer version writes
        # print-object:no on hidden key signatures): the tokens are Zeus's, the indices carried over where they agree
        zeus = base.with_suffix(".lmx").read_text().split()
        tally["lmx_same_as_zeus"] += toks == zeus
        if toks != zeus:
            import difflib
            carry = {}
            for i0, j0, n in difflib.SequenceMatcher(a=toks, b=zeus, autojunk=False).get_matching_blocks():
                carry |= {i0 + k: j0 + k for k in range(n)}
            notes = {k: carry[v] for k, v in notes.items() if v in carry}
            measures = {k: carry[v] for k, v in measures.items() if v in carry}
            toks = zeus
        order = sorted(measures, key=measures.get)
        nxt = {m: measures[order[i + 1]] for i, m in enumerate(order[:-1])}  # a measure's right bar line opens the next
        targets = []
        bars = {}
        for aid, cat, bbox, cx, cy, poly in d["anns"]:
            s = sem.get(aid, "")
            x, y = cx * sx, cy * sy
            if s.endswith(".notehead") and s.split(".")[0] in notes:
                targets.append([notes[s.split(".")[0]], "note", round(x, 1), round(y, 1)])
            elif re.fullmatch(r"rest\d+", s) and s in notes:
                targets.append([notes[s], "rest", round(x, 1), round(y, 1)])
            elif ".right_barline." in s and s.split(".")[0] in nxt:
                bars.setdefault(nxt[s.split(".")[0]], []).append(x)
        for tok, xs in bars.items():
            targets.append([tok, "barline", round(float(np.mean(xs)), 1), round(h / 2, 1)])
        if not targets:
            continue
        # grace notes, as the LMX marks them
        for t in targets:
            i = t[0] - 1
            while i >= 0 and toks[i] in ("print-object:no", "grace", "grace:slash", "chord"):
                if toks[i] == "grace":
                    t[1] = "grace" if t[1] == "note" else t[1]
                i -= 1
        targets.sort()
        # the staff space, from the staff's own lines (a head's polygon is too coarse to say)
        g = np.asarray(Image.open(jpg).convert("L"), dtype=np.float32)
        try:
            rows = align.fit_lines(np.clip((1 - g / 255 - 0.15) / 0.6, 0, 1), h / 9)
            ss = float((rows[-1] - rows[0]) / 4)
        except Exception:
            continue
        name = f"{page}-{staff}"
        (a.out / f"{name}.jpg").write_bytes(jpg.read_bytes())
        (a.out / f"{name}.lmx").write_text(" ".join(toks))
        (a.out / f"{name}.pos.json").write_text(json.dumps({"ss": ss, "w": w, "h": h, "source": line, "lines": rows,
                                                             "targets": targets}))
        tally["staves"] += 1
        for t in targets:
            tally[t[1] + "s"] = tally.get(t[1] + "s", 0) + 1
    print(json.dumps(tally), flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("what", choices=("rendered", "real", "dolores"))
    ap.add_argument("src", type=Path, help="rendered: a list of .lmx files; real: a list of keys")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--glyphs", type=Path, help="rendered, the hand's: GLYPHS/<hand> with curated.json")
    ap.add_argument("--hand", default="berlin")
    ap.add_argument("--fonts", default="Petaluma,Petaluma,Leland,Gootville,Leipzig,Bravura")
    ap.add_argument("--plain", action="store_true")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--maps", type=Path)
    ap.add_argument("--data", type=Path, default=align.ZEUS / "dataL2")
    ap.add_argument("--ann", type=Path, help="dolores: the fetched annotations")
    a = ap.parse_args()
    {"rendered": rendered, "real": real, "dolores": dolores}[a.what](a)


if __name__ == "__main__":
    main()
