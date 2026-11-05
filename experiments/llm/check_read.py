# /// script
# requires-python = ">=3.11"
# dependencies = ["certifi", "pillow"]
# ///
"""An open model checking musvit-D5's reading bar by bar, the loop keeping
the procedure: for each bar it is shown the manuscript (pitch grid) and
D5's line engraved beneath it, says what it sees note by note, and
corrects the line; a changed bar is engraved again and shown, and the
model keeps, reverts or revises it (at most `--rounds` times).

    VLLM_API_KEY=<key> uv run experiments/llm/check_read.py <edition-copy> --parts vn2 \\
        --url https://<app>.modal.run/v1 --model google/gemma-4-31B-it [--bars 0-20]

<edition-copy> is prepared as for agent_read.py, then given D5's draft by
d5_draft.py. The pictures are the edition's own: zoom.py (the bar, its
staff lines and spaces named) and compare.py (the bar over its engraving,
measured heads circled, red where the head check disagrees), with
headcheck.py's text. Each step is logged to
<edition-copy>/build/check-<model>/<part>.jsonl; score with
score_agent_read.py --reader check-<model>.

Run inside Claude Code's sandbox, as agent_read.py.
"""

import argparse
import base64
import io
import json
import os
import re
import ssl
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction
from pathlib import Path

import certifi
from PIL import Image

from agent_read import SAMPLING, chat

FILES = {"vn1": "01-Vn1", "vn2": "02-Vn2", "va": "03-Va", "vc": "04-Vc"}
NAMES = {"vn1": "violin I", "vn2": "violin II", "va": "viola", "vc": "cello"}
CLEFS = {"vn1": "treble", "vn2": "treble", "va": "alto (the cello's tenor or treble where the part changes clef)",
         "vc": "bass (tenor in high passages)"}

SYSTEM = """You check one bar of a string part in an 18th-century manuscript of Boccherini's quartet Op. 48 no. 4, \
movement I (2/4 time; key signature three flats: B-flat, E-flat, A-flat). A reading machine has transcribed the \
bar. Find where its transcription differs from the manuscript, and correct it. It reads about 80% of bars right: \
change only what you can point to on the page.

You are shown:
1. The manuscript bar, its staff straightened; each line and space is named with its pitch in the left margin.
2. The same bar with the transcription engraved beneath it at the same width. Circles mark the note heads a \
detector measured: green where it agrees with the transcription, red where it doesn't (the detector is often \
wrong about beams, accidentals and touching heads; a red circle is a question, not an answer).
3. The transcription as typed (LilyPond) and as LilyPond reads it.

What counts: each note's pitch (letter and octave) read from the centre of its head, not its edge; accidentals \
drawn; note values and dots (count beams and flags on each stem); rests and their values; double stops (two heads \
on one stem, written as a chord); small grace notes before a note. Not counted: slurs, ties, how beams group, \
dynamics, articulations.

How to check: go through the manuscript left to right, head by head, and say for each what you see (its pitch \
against the named lines and spaces, its value from its beams or flag, a dot, an accidental, a grace note). Then \
compare with the engraving, note for note.

Write the bar in LilyPond with English note names and absolute octaves: c' is middle C (C4), c'' is C5, g is G3, \
c is C3, g, is G2. Flats and sharps are part of the name: bf' (B-flat 4), ef'' (E-flat 5), af' (A-flat 4), \
fs' (F-sharp 4); a note the key flattens must be written flat (ef', not e') unless the manuscript draws a natural \
(then e' and, if the natural is redundant, e'!). Every note carries its value: 4 8 16 32, dotted 8. 16.; rests r8 \
r4, a whole-bar rest R2. A chord: <g d'>8. A grace note: \\grace f'8 e'8. A triplet: \\tuplet 3/2 { c''16 g' ef'' }. \
Several voices: << { ... } \\\\ { ... } >>. A clef change: \\clef tenor. The bar must last exactly as long as \
given, and end with |.

Answer in JSON only."""

SCHEMA = {"type": "object", "properties": {
    "seen": {"type": "string", "description": "the manuscript bar, head by head, left to right"},
    "differs": {"type": "array", "items": {"type": "string"},
                "description": "each difference between the manuscript and the engraving; empty if none"},
    "line": {"type": "string", "description": "the bar in LilyPond, corrected, or the transcription unchanged"}},
    "required": ["seen", "differs", "line"], "additionalProperties": False}


def picture(path: Path) -> dict:
    im = Image.open(path).convert("RGB")
    buf = io.BytesIO()
    im.save(buf, "PNG")
    return {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()}}


class Copy:
    """The edition copy: its note files and the edition's tools on them."""

    def __init__(self, root: Path, quartet: str, mvt: str, run: str, source: str):
        self.root, self.q, self.mvt = root, quartet, mvt
        self.env = {**os.environ, "ENCODE_RUN": run, "OP48_SOURCE": source}
        self.locks = {p: threading.Lock() for p in FILES}

    def tool(self, *args) -> str:
        r = subprocess.run(["uv", "run", "--offline", *args], cwd=self.root, env=self.env, capture_output=True,
                           text=True, timeout=600)
        return "\n".join(l for l in (r.stdout + r.stderr).splitlines() if not l.startswith(("Installed ", "Resolved ")))

    def path(self, part: str) -> Path:
        return self.root / self.q / f"{FILES[part]}-{ {'I': 1, 'II': 2, 'III': 3}[self.mvt]}.ily"

    def line(self, part: str, bar: int) -> tuple[int, str]:
        lines = self.path(part).read_text().split("\n")
        i = next(i for i, l in enumerate(lines) if re.search(rf"% bar {bar}:", l))
        return i, lines[i].split("   % bar")[0].strip()

    def set(self, part: str, bar: int, text: str, note: str):
        p = self.path(part)
        lines = p.read_text().split("\n")
        i, _ = self.line(part, bar)
        lines[i] = f"{text}   % bar {bar}: {note}"
        p.write_text("\n".join(lines))

    def reads(self, part: str, lo: int, hi: int) -> dict:
        """LilyPond's reading of bars lo-hi: {bar: text}, and any error."""
        out = self.tool("scripts/bars.py", "show", self.q, part, self.mvt, f"{lo}-{hi}")
        got, bar = {}, None
        for l in out.splitlines():
            m = re.match(r"\s*(\d+) typed:", l)
            if m:
                bar = int(m.group(1))
            m = re.match(r"\s*reads: (.*)", l)
            if m and bar is not None:
                got[bar] = m.group(1).strip()
        return got, ("" if got else out[-1500:])

    def events(self, part: str, lo: int, hi: int) -> dict:
        """LilyPond's events in bars lo-hi, by its own timing: a line too long or short moves the next bar's."""
        got = {}
        for l in self.tool("scripts/events.py", self.q, part, self.mvt, f"{lo}-{hi}").splitlines():
            m = re.match(r"\s*(\d+)\s+(\S.*)", l)
            if m:
                got.setdefault(int(m.group(1)), []).append(m.group(2).strip())
        return got

    def pictures(self, part: str, bar: int) -> tuple[list[Path], str]:
        z = self.tool("scripts/zoom.py", self.q, part, self.mvt, str(bar))
        c = self.tool("scripts/compare.py", self.q, part, self.mvt, f"{bar}-{bar}")
        h = self.tool("scripts/headcheck.py", self.q, part, self.mvt, str(bar))
        paths = [self.root / m.group(1) for m in re.finditer(r"(build/\S+\.png)", z + "\n" + c)]
        return paths, h.strip()


# Worked examples: bars of Op48-4 II (the same hand; not the movement checked) that D5 read wrong, and one it read
# right, each with the Opus reader's own account of the bar (its record's "changes") and the edition's final line.
EXAMPLES = [("va", 9), ("vn1", 11), ("va", 24), ("vn2", 5), ("vn1", 10), ("vn1", 12)]
DURS = {"whole": "1", "half": "2", "quarter": "4", "8th": "8", "16th": "16", "32nd": "32"}
FLATS = {"B", "E", "A"}  # Op48-4's key


def compact_line(text: str) -> str:
    """D5's reading as compare.py prints it ('gG4:8th <D4 D4>:quarter rquarter') in LilyPond."""
    def pitch(n):
        letter, octave = n[0], int(n[1:])
        marks = octave - 3
        return letter.lower() + ("f" if letter in FLATS else "") + ("'" * marks if marks > 0 else "," * -marks)
    words = []
    for w in re.findall(r"g?<[^>]*>:\S+|\S+", text):
        if w == "R":
            words.append("R2.")
            continue
        grace = w.startswith("g") and not w.startswith("g:")
        w = w[1:] if grace else w
        if w.startswith("r"):
            v = w[1:]
            words.append("r" + DURS[v.rstrip(".")] + "." * v.count("."))
            continue
        notes, v = w.rsplit(":", 1)
        heads = [pitch(n) for n in notes.strip("<>").split()]
        words.append(("\\grace " if grace else "") + (heads[0] if len(heads) == 1 else "<" + " ".join(heads) + ">")
                     + DURS[v.rstrip(".")] + "." * v.count("."))
    return " ".join(words) + " |"


def examples(copy: "Copy", edition: Path) -> list[dict]:
    """The worked examples as conversation turns: the bar and D5's line; the answer, in Opus's words."""
    run = next(edition.glob("build/encode/Op48-4-II-*"))
    scored = {(b["part"], b["bar"]): b for b in json.loads((run / "d5/reading-vs-final.json").read_text())["against"]["bars"]}
    turns = []
    for part, bar in EXAMPLES:
        b = scored[(part, bar)]
        record = next(json.loads(l) for l in (run / f"read-{part}.jsonl").read_text().splitlines()
                      if json.loads(l)["bar"] == bar)
        final = subprocess.run(["uv", "run", "--offline", "scripts/bars.py", "show", "Op48-4", part, "II", str(bar)],
                               cwd=edition, capture_output=True, text=True).stdout
        final = re.search(r"reads: (.*)", final).group(1).strip() + " |"
        z = copy.tool("scripts/zoom.py", "Op48-4", part, "II", str(bar))
        pic = copy.root / re.search(r"(build/\S+\.png)", z).group(1)
        d5 = compact_line(b["read"])
        differs = [] if b["exact"] else [f"the transcription reads {b['read']}; the manuscript has {b['ours']}"]
        turns += [{"role": "user", "content": [{"type": "text", "text":
                      f"An example (movement II, 3/4). {NAMES[part][0].upper() + NAMES[part][1:]}, bar {bar}.\nThe transcription as "
                      f"typed: {d5}\nThe picture: the manuscript bar with its pitch grid."}, picture(pic)]},
                  {"role": "assistant", "content": json.dumps({"seen": record["changes"], "differs": differs,
                                                               "line": final if differs else d5})}]
    return turns


def ask(a, extra, key, ctx, messages, seed) -> tuple[dict | None, dict]:
    body = {"model": a.model, "messages": messages, "max_tokens": 12000, **extra, "seed": seed,
            "response_format": {"type": "json_schema", "json_schema": {"name": "check", "schema": SCHEMA, "strict": True}}}
    r = chat(a.url, key, body, ctx)
    m = r["choices"][0]["message"]
    try:
        answer = json.loads(m.get("content") or "")
    except ValueError:
        answer = None
    return answer, {"thinking": m.get("reasoning_content"), "content": m.get("content"), "usage": r["usage"],
                    "finish": r["choices"][0]["finish_reason"]}


def check_bar(a, extra, key, ctx, copy: Copy, part: str, bar: int, length: str, log) -> dict:
    with copy.locks[part]:
        _, d5 = copy.line(part, bar)
        before, _ = copy.reads(part, bar, bar + 1)
        timing = copy.events(part, bar, bar + 1)
        pics, heads = copy.pictures(part, bar)
    lasts = "the pickup, " if bar == 0 else ""
    intro = (f"{NAMES[part][0].upper() + NAMES[part][1:]}, bar {bar} ({lasts}it lasts {Fraction(length)} of a whole note; clef "
             f"{CLEFS[part]}).\nThe transcription as typed: {d5}\nAs LilyPond reads it: {before.get(bar, '?')}\n"
             f"The head detector: {heads or 'no disagreements'}\nThe pictures: the manuscript bar with its pitch grid; "
             f"then the bar over the transcription's engraving.")
    messages = [{"role": "system", "content": SYSTEM}] + a.shown + [
                {"role": "user", "content": [{"type": "text", "text": ("Now the bar to check. " if a.shown else "") + intro}]
                 + [picture(p) for p in pics]}]
    current, rounds, entry = d5, [], {"part": part, "bar": bar, "d5": d5, "headcheck": heads}
    for k in range(a.rounds + 1):
        answer, meta = ask(a, extra, key, ctx, messages, a.seed * 100_000 + bar * 10 + k)
        rounds.append({"answer": answer, **meta})
        if not answer:
            break
        line = answer["line"].strip()
        line = line if line.endswith("|") else line + " |"
        if re.sub(r"\s+", " ", line) == re.sub(r"\s+", " ", current):
            break  # kept
        with copy.locks[part]:
            copy.set(part, bar, line, "checked")
            after, err = copy.reads(part, bar, bar + 1)
            spilled = bar + 1 in timing and copy.events(part, bar, bar + 1).get(bar + 1) != timing[bar + 1]
            if err or spilled or bar not in after:
                copy.set(part, bar, current, "checked" if current != d5 else "D5's reading")
                problem = (f"LilyPond couldn't read it: {err}" if err or bar not in after else
                           f"it doesn't last {Fraction(length)} of a whole note (it moved the next bar's notes)")
                rounds[-1]["refused"] = problem
                messages += [{"role": "assistant", "content": meta["content"]},
                             {"role": "user", "content": f"Your line was not taken: {problem}. Correct it."}]
                continue
            pics, heads = copy.pictures(part, bar)
        current = line
        messages += [{"role": "assistant", "content": meta["content"]},
                     {"role": "user", "content": [{"type": "text", "text":
                         f"Your line, engraved under the manuscript. LilyPond reads it: {after[bar]}\nThe head "
                         f"detector: {heads or 'no disagreements'}\nDoes it match the manuscript note for note now? "
                         f"Answer as before: return the same line if it matches, a corrected one if not, or the "
                         f"original transcription ({d5}) if your change was wrong."}] + [picture(pics[-1])]}]
    entry.update({"final": current, "changed": current != d5, "rounds": rounds})
    with log.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    return entry


def bar_range(text: str) -> list[int]:
    lo, _, hi = text.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("repo", type=Path, help="the edition copy, with D5's draft (d5_draft.py)")
    ap.add_argument("--parts", nargs="+", default=list(FILES))
    ap.add_argument("--bars", help="first-last; default every bar")
    ap.add_argument("--url", required=True)
    ap.add_argument("--model", required=True)
    ap.add_argument("--rounds", type=int, default=2, help="looks again at a changed bar")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--thinking-budget", type=int, default=4096)
    ap.add_argument("--image-tokens", type=int, default=1120)
    ap.add_argument("--examples", type=Path, metavar="EDITION",
                    help="show worked examples first, from this edition's Op48-4 II run (read only)")
    a = ap.parse_args()
    repo = a.repo.resolve()
    if Path.home() / "Dropbox" in repo.parents:
        raise SystemExit("check_read: give it a copy of the edition, not the edition")
    family = next(k for k in SAMPLING if k in a.model.lower())
    extra = {**SAMPLING[family], "chat_template_kwargs": {"enable_thinking": True},
             "thinking_token_budget": a.thinking_budget, "mm_processor_kwargs": {"max_soft_tokens": a.image_tokens}}
    state = json.loads(next((repo / "build/encode").glob("*/state.json")).read_text())
    copy = Copy(repo, state["quartet"], state["mvt"], state["run"], state["source"]["name"])
    draft = json.loads((repo / "build/d5-draft.json").read_text())
    a.shown = examples(copy, a.examples) if a.examples else []
    key = os.environ["VLLM_API_KEY"]
    ctx = ssl.create_default_context(cafile=certifi.where())
    out = repo / "build" / f"check-{a.model.split('/')[-1].lower()}{'-examples' if a.examples else ''}"
    out.mkdir(parents=True, exist_ok=True)
    done = {(e["part"], e["bar"]) for p in a.parts if (out / f"{p}.jsonl").exists()
            for e in map(json.loads, (out / f"{p}.jsonl").read_text().splitlines()) if "bar" in e}
    jobs = [(p, b) for p in a.parts for b in (bar_range(a.bars) if a.bars else sorted(map(int, draft[p])))
            if str(b) in draft[p] and (p, b) not in done]
    print(f"checking {len(jobs)} bars ({len(done)} done before)", flush=True)
    t0, n = time.time(), 0
    with ThreadPoolExecutor(a.workers) as pool:
        for e in pool.map(lambda j: check_bar(a, extra, key, ctx, copy, j[0], j[1], draft[j[0]][str(j[1])]["length"],
                                              out / f"{j[0]}.jsonl"), jobs):
            n += 1
            print(f"{e['part']} {e['bar']}: {'changed to ' + e['final'] if e['changed'] else 'kept'} "
                  f"({len(e['rounds'])} looks; {n}/{len(jobs)}, {(time.time() - t0) / 60:.1f} min)", flush=True)


if __name__ == "__main__":
    main()
