# /// script
# requires-python = ">=3.11"
# dependencies = ["anthropic", "numpy", "pillow"]
# ///
"""Can Claude read a bar's notes as the edition encodes them, taught by
examples rather than fine-tuned? Scored as Zeus is (experiments/zeus/compare.py),
on the same held-out bars.

    uv run experiments/llm/bars.py <edition-repo> [--limit N] [--workers 4] [--effort low] [--same-as ANSWERS]

Each bar of KHM 602 movement II (Op48-1) is cut from its straightened
staff, a little past its bar lines, scaled to about 40 px a staff space,
and sent with its clef (the labels'), key and time (Structure.ily). Before
it, 40 example bars with their answers from the encoding: 8 per part from
movement I, and 8 from RES 507 (14) movement II, the material Zeus's
fine-tune trained on. The examples are one cached prefix, paid for in full
once.

Claude answers each event in order (a note or chord, a rest, a bar rest;
duration, dots, grace, accidentals shown), as structured output. Compared
with scripts/events.py by compare.py's rules: letter and octave per note,
durations, rests, graces. Answers are cached in answers/, so a rerun pays
only for new bars.
"""

import argparse
import base64
import hashlib
import io
import json
import random
import subprocess
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
sys.path[:0] = [str(ROOT), str(ROOT / "experiments" / "zeus")]
import compare  # noqa: E402
import labels  # noqa: E402
import reader  # noqa: E402
import structure  # noqa: E402

MODEL, EFFORT = reader.MODEL, reader.EFFORT
PRICE = {"input": 4.0, "cache_write": 5.0, "cache_read": 0.4, "output": 20.0}  # $ per million tokens
SPACE_PX = 40  # a staff space in the image sent
PARTS = ("vn1", "vn2", "va", "vc")
DURATIONS = ["whole", "half", "quarter", "8th", "16th", "32nd", "64th"]

PROMPT = """You read one bar of a late-18th-century manuscript part (a string quartet: violin I, violin II, viola or cello) into its notes, as the edition encodes them.

The image shows one bar on its staff, straightened, with a little of the neighbouring bars at each side: read only between the bar line at the left (or, for a line's first bar, the start of the music after the clef and key signature) and the bar line at the right. The clef, key signature and time signature in force are given with each bar; a clef or key change written inside the bar is in the image.

Answer each event of the bar in the order it sounds:
- kind: "note" (one note, or a chord / double stop: several heads on one stem, one event), "rest", or "bar_rest" (a whole-bar rest).
- pitches: each head's pitch as letter, accidental in force and octave, scientific (middle C is C4): "Bb3", "F#5", "E4". Lowest first. Empty for a rest.
- duration: the written value: whole, half, quarter, 8th, 16th, 32nd or 64th (inside a triplet, still the written value). For a bar rest, "whole".
- dots: augmentation dots.
- grace: true for a small grace note before a note.
- accidentals: the accidental signs written before this event's heads ("sharp", "flat", "natural"), empty if none.

Read what the copyist wrote, not what the music ought to be. The examples first, each with the edition's answer."""

SCHEMA = {
    "type": "object",
    "properties": {"events": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "kind": {"type": "string", "enum": ["note", "rest", "bar_rest"]},
            "pitches": {"type": "array", "items": {"type": "string"}},
            "duration": {"type": "string", "enum": DURATIONS},
            "dots": {"type": "integer"},
            "grace": {"type": "boolean"},
            "accidentals": {"type": "array", "items": {"type": "string", "enum": ["sharp", "flat", "natural"]}},
        },
        "required": ["kind", "pitches", "duration", "dots", "grace", "accidentals"],
        "additionalProperties": False}}},
    "required": ["events"],
    "additionalProperties": False,
}

KEYS = {0: "no sharps or flats"} | {k: f"{abs(k)} {'sharp' if k > 0 else 'flat'}{'s' if abs(k) > 1 else ''}"
                                    for k in range(-7, 8) if k}


# -- the bars ----------------------------------------------------------------------------

class Source:
    def __init__(self, edition: Path, name: str):
        self.pdf = next(edition.glob(f"sources/*/{name}.pdf"))
        self.export = json.loads(self.pdf.with_name(self.pdf.stem + ".bars.json").read_text())
        self.quartet = f"Op48-{self.export['source']['gerard'] - 225}"
        self.expected = structure.expected((edition / self.quartet / "Structure.ily").read_text())
        self.edition, self.events, self.pages = edition, {}, {}
        self.lock = threading.Lock()  # the workers share the page images and the encoding
        self.boxes = Counter((b["part"], b["movement"], b["bar"]) for b in self.export["bars"])

    def encoded(self, part, mvt) -> dict:
        with self.lock:
            return self._encoded(part, mvt)

    def _encoded(self, part, mvt) -> dict:
        if (part, mvt) not in self.events:
            r = subprocess.run(["uv", "run", "--offline", str(self.edition / "scripts" / "events.py"),
                                self.quartet, part, mvt, "--json"], capture_output=True, text=True, check=True)
            self.events[(part, mvt)] = json.loads(r.stdout)
        return self.events[(part, mvt)]

    def bars(self, mvt) -> list[dict]:
        """The movement's bar boxes that are whole bars (not half a split bar)."""
        return [b for b in self.export["bars"] if b["movement"] == mvt and b["part"] in PARTS
                and self.boxes[(b["part"], mvt, b["bar"])] == 1]

    def image(self, b: dict) -> bytes:
        s = self.export["systems"][b["system"]]
        with self.lock:
            if s["page"] not in self.pages:
                self.pages[s["page"]] = compare.page_image(self.pdf, s["page"])
            g = self.pages[s["page"]]
        H, W = g.shape
        staff = Image.open(io.BytesIO(compare.staff_crop(g, s)))
        sp = (s["bottom"] - s["top"]) / 4 * H
        x0 = max(0, s["left"] * W - sp)  # the crop's left edge, on the page
        xs = [q[0] * W for q in b["quad"]]
        left, right = int(max(0, min(xs) - x0 - 1.5 * sp)), int(min(staff.width, max(xs) - x0 + 1.5 * sp))
        bar = staff.crop((left, 0, right, staff.height))
        f = SPACE_PX / sp
        bar = bar.resize((max(1, int(bar.width * f)), max(1, int(bar.height * f))), Image.LANCZOS)
        return reader.jpeg(bar, quality=90)

    def context(self, b: dict) -> str:
        exp = self.expected[b["movement"]]
        key = compare.in_force(exp, "key", b)
        time = compare.in_force(exp, "time", b)
        return f"{dict(vn1='Violin I', vn2='Violin II', va='Viola', vc='Cello')[b['part']]}, bar {b['bar']}. " \
               f"Clef: {b['clefs'][0]}. Key signature: {KEYS[key]}. Time: {time}."

    def answer(self, b: dict) -> dict:
        """The encoding's events for the bar, as Claude is asked to answer."""
        out = []
        for e in self.encoded(b["part"], b["movement"]).get(str(b["bar"]), []):
            dur = (e["dur"] or "").rstrip(".")
            if e["kind"] == "mmrest":
                out.append({"kind": "bar_rest", "pitches": [], "duration": "whole", "dots": 0, "grace": False,
                            "accidentals": []})
                continue
            out.append({"kind": "rest" if e["kind"] == "rest" else "note",
                        "pitches": sorted((n["pitch"] for n in e["notes"]), key=compare.num),
                        "duration": dur, "dots": (e["dur"] or "").count("."), "grace": e["grace"] != "0",
                        "accidentals": [n["acc"] for n in e["notes"] if n["acc"]]})
        return {"events": out}


def examples(edition: Path) -> list[tuple]:
    """40 example bars: (source, box), 8 per part of KHM 602 I and 8 of RES 507 (14) II,
    chosen for variety (chords, graces, triplets, 32nds, rests), seeded; one voice
    only (the encoding writes a two-stem unison as two voices)."""
    rng = random.Random(48)
    out = []
    for name, mvt, per_part in (("D-B_KHM-602", "I", 8), ("F-Po_RES-507-14", "II", 2)):
        src = Source(edition, name)
        for part in PARTS:
            one_voice = lambda b: len({e["voice"] for e in src.encoded(part, mvt).get(str(b["bar"]), [])
                                       if e["grace"] == "0"}) <= 1
            pool = [b for b in src.bars(mvt) if b["part"] == part and b["count"] == 1 and one_voice(b)]
            def traits(b):
                evs = src.encoded(part, mvt).get(str(b["bar"]), [])
                return {"chord": any(len(e["notes"]) > 1 for e in evs), "grace": any(e["grace"] != "0" for e in evs),
                        "tuplet": any(e["tup"] for e in evs), "32nd": any("32" in (e["dur"] or "") for e in evs),
                        "rest": any(e["kind"] == "rest" for e in evs)}
            chosen = []
            for t in ("chord", "grace", "tuplet", "32nd", "rest"):
                c = [b for b in pool if traits(b)[t] and b not in chosen]
                if c and len(chosen) < per_part:
                    chosen.append(rng.choice(c))
            rest = [b for b in pool if b not in chosen]
            chosen += rng.sample(rest, max(0, per_part - len(chosen)))
            out += [(src, b) for b in chosen[:per_part]]
    return out


# -- asking ---------------------------------------------------------------------------------

def image_block(jpeg: bytes) -> dict:
    return {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                        "data": base64.standard_b64encode(jpeg).decode()}}


def prefix(ex: list[tuple]) -> list[dict]:
    blocks = []
    for k, (src, b) in enumerate(ex, 1):
        blocks += [{"type": "text", "text": f"Example {k}. {src.context(b)}"}, image_block(src.image(b)),
                   {"type": "text", "text": json.dumps(src.answer(b))}]
    blocks[-1]["cache_control"] = {"type": "ephemeral"}
    return blocks


def ask(client, pre: list[dict], context: str, jpeg: bytes) -> dict:
    r = client.beta.messages.create(
        model=MODEL, max_tokens=8000, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        output_config={"effort": EFFORT, "format": {"type": "json_schema", "schema": SCHEMA}},
        system=PROMPT,
        messages=[{"role": "user", "content": pre + [
            {"type": "text", "text": f"Now this bar. {context}"}, image_block(jpeg)]}])
    paid = {"model": r.model, "usage": r.usage.to_dict()}
    text = next((x.text for x in r.content if x.type == "text"), "")
    try:
        return {**json.loads(text), **paid}
    except ValueError:
        return {"error": f"unusable answer (stopped: {r.stop_reason})", **paid}


def dollars(answers) -> float:
    t = Counter()
    for a in answers:
        u = a.get("usage", {})
        t["input"] += u.get("input_tokens") or 0
        t["cache_write"] += u.get("cache_creation_input_tokens") or 0
        t["cache_read"] += u.get("cache_read_input_tokens") or 0
        t["output"] += u.get("output_tokens") or 0
    return sum(t[k] * PRICE[k] for k in PRICE) / 1e6


def to_event(e: dict) -> dict:
    """An answer's event, as compare.py compares events."""
    if e["kind"] == "bar_rest":
        return {"kind": "rest", "pitches": (), "dur": "bar", "dots": 0, "grace": e["grace"], "acc": ()}
    if e["kind"] == "rest":
        return {"kind": "rest", "pitches": (), "dur": e["duration"], "dots": e["dots"], "grace": e["grace"], "acc": ()}
    pitches = tuple(sorted(f"{p[0]}{p[-1]}" if p[-1].isdigit() else p for p in e["pitches"]))
    return {"kind": "note", "pitches": pitches, "dur": e["duration"], "dots": e["dots"], "grace": e["grace"],
            "acc": tuple(sorted(e["accidentals"]))}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--effort", default=reader.EFFORT, choices=["low", "medium", "high"])
    ap.add_argument("--same-as", help="ask only the bars answered in this answers file (a pilot's)")
    a = ap.parse_args()
    import anthropic
    global EFFORT
    EFFORT = a.effort

    ex = examples(a.edition)
    pre = prefix(ex)
    tag = hashlib.sha1(f"{MODEL}:{EFFORT}:{PROMPT}:{json.dumps(SCHEMA)}:{json.dumps(pre)}".encode()).hexdigest()[:10]
    out = HERE / "answers" / f"bars-{tag}.json"
    done = json.loads(out.read_text()) if out.exists() else {}
    test = Source(a.edition, "D-B_KHM-602")
    bars = test.bars("II")
    key = lambda b: f"{b['part']}:{b['movement']}:{b['bar']}"
    if a.same_as:
        pilot = set(json.loads(Path(a.same_as).read_text()))
        bars = [b for b in bars if key(b) in pilot]
    todo = [b for b in bars if key(b) not in done][: a.limit]
    client = anthropic.Anthropic(api_key=reader.api_key(), max_retries=3, timeout=120.0)
    lock = threading.Lock()
    failed = []

    def one(b):
        r = ask(client, pre, test.context(b), test.image(b))
        with lock:
            if "error" in r:  # not kept: a rerun asks again
                failed.append((key(b), r["error"]))
            else:
                done[key(b)] = r
                reader.save_json(out, done)
        return r

    if todo:
        print(f"asking {len(todo)} bars ({len(done)} cached) ...", flush=True)
        one(todo[0])  # writes the cache the others read
        with ThreadPoolExecutor(a.workers) as pool:
            list(pool.map(one, todo[1:]))

    tally, rows = Counter(), []
    for b in bars:
        r = done.get(key(b))
        if r is None:
            continue
        if "error" in r:
            tally["refused or unusable"] += 1
            continue
        enc = compare.encoded(test.encoded(b["part"], "II").get(str(b["bar"]), []))
        got = [to_event(e) for e in r["events"]]
        rhythm = lambda es: [(e["kind"], e["dur"], e["dots"], e["grace"]) for e in es]
        pitch = lambda es: [e["pitches"] for e in es if e["kind"] == "note"]
        exact = len(enc) == len(got) and all(map(compare.same, enc, got))
        tally["bars"] += 1
        tally["bars exact"] += exact
        tally["bars right in rhythm"] += rhythm(enc) == rhythm(got)
        tally["bars right in pitch"] += pitch(enc) == pitch(got)
        tally["events"] += len(enc)
        errors = []
        for i, j in compare.align(enc, got):
            k = ["extra"] if i is None else ["missed"] if j is None else \
                ["right"] if compare.same(enc[i], got[j]) else compare.what_differs(enc[i], got[j])
            for x in k:
                tally["event: " + x] += 1
            errors += [x for x in k if x != "right"]
        rows.append({"part": b["part"], "movement": "II", "bar": b["bar"], "exact": exact,
                     "rhythm": rhythm(enc) == rhythm(got), "pitch": pitch(enc) == pitch(got), "errors": errors,
                     "encoded": " ".join(map(compare.text, enc)), "claude": " ".join(map(compare.text, got))})
    res = HERE / "results" / f"bars-{tag}.json"
    res.parent.mkdir(exist_ok=True)
    res.write_text(json.dumps({"tally": tally, "bars": rows}, indent=1))
    n = max(tally["bars"], 1)
    print(f"{tally['bars']} bars of {len(bars)} answered, {dollars(done.values()):.2f} $ so far "
          f"({dollars(done.values()) / max(len(done), 1) * 100:.1f} ¢ a bar)")
    print(f"  exact {tally['bars exact'] / n:.0%}, rhythm {tally['bars right in rhythm'] / n:.0%}, "
          f"pitch {tally['bars right in pitch'] / n:.0%}; events right {tally['event: right']}/{tally['events']}; "
          + ", ".join(f"{k[7:]} {v}" for k, v in sorted(tally.items()) if k.startswith("event: ") and k != "event: right"))
    if failed:
        print(f"{len(failed)} refused or unusable, not kept: {failed[:3]}")
    print(f"wrote {res.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
