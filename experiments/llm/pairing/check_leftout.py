# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "verovio"]
# ///
"""The Opus check on the staves the pairing leaves out: shown one staff and
the score's bars around the pairing's proposal (pair_check.py's
check-text-1x), is the proposal exactly right? Asked through headless Claude
Code (`claude -p`), on the user's login rather than the API, so it spends the
plan's quota; each answer reports the quota used so far, and the run stops
before starting another question once the 5-hour window passes --stop-at.

    uv run experiments/llm/pairing/check_leftout.py --stop-at 0.10 [--limit 10] [--philhar] [SOURCE ...]
    uv run experiments/llm/pairing/check_leftout.py --test text,engraved,lily,range --stop-at 0.20
    uv run experiments/llm/pairing/check_leftout.py --score

Sources: the G. 213 parts (the score as text from its MusicXML). A staff is
asked about when it was left out with a proposal of bars (one with no bars
proposed, for a measure the score hasn't at all, is not). The answer comes in three fields, in this order:
`working` (the line bar by bar against the score, written before deciding),
`right`, and `insights` (what made it hard). Each question's whole stream-json
transcript goes to transcripts/<results file>/<source>/<staff>-<first>-<last>.jsonl,
its row to results/cli-check-<model>-<effort>.jsonl. --score scores KHM 587's
answers against the editor's fixed pages (khm587-staves.json's left-out staves).
"""

import argparse
import base64
import json
import os
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from itertools import zip_longest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[2]))
import pair_check as pc  # noqa: E402
import pairing  # noqa: E402

G213 = ("G213-KHM587", "G213-Sibley", "G213-DB-Pleyel")
HELD_OUT = {"D-Dl_Mus.3403-P-513"}  # the readers' test: kept out of training
CLI = HERE / "transcripts"  # in Dropbox: paid for, not to be lost
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["working", "right", "insights"],
          "properties": {"working": {"type": "string"}, "right": {"type": "boolean"}, "insights": {"type": "string"}}}
SYSTEM = "You match lines of hand-copied music to a modern edition's bars. Answer only in the format asked."
sys.path.insert(0, str(pc.ZEUS))
import parallel_pair as pp  # noqa: E402
import philhar  # noqa: E402


def lilies() -> dict[str, Path]:
    """{source: the Philhar encodings it was paired with}: parallel_pair's groups M and W."""
    out = {r[0]: pp.QUARTET_LILY for r in pp.rows(pc.ZEUS / "philhar-repair" / "sources.txt")}
    return out | {r[1]: pp.SITE_LILY for r in pp.rows(pc.ZEUS / "wayback-print-pairs" / "sources.txt") if r[0] == "W"}


def staves(sources) -> list[dict]:
    """The left-out staves with a proposal, each with a window of the score's bars around it: for G. 213
    a bar is (movement, index), for Philhar's encodings (quartet, movement, bar)."""
    out, lily = [], lilies()
    for src in sources:
        r = json.loads(pairing.results_file(src).read_text())
        mvts = {p: [len(m) for m in pc.movements(p)] for p in pc.PARTS} if src in G213 else None
        for x in r["not kept"]:
            if not x.get("bars") or x["bars"][0][:-1] != x["bars"][-1][:-1]:
                continue
            *piece, mv, f = x["bars"][0]
            l = x["bars"][-1][-1]
            if mvts:
                lo, hi = 0, mvts[x["part"]][pc.ROMAN.index(mv)] - 1
            else:
                ns = [int(n) for n in philhar.encoding(pp.EDITION, lily[src], piece[0], x["part"], mv)["bars"]]
                lo, hi = min(ns), max(ns)
            out.append({"source": src, "staff": x["staff"], "part": x["part"], "quartet": piece[0] if piece else None,
                        "movement": mv, "claim": [f, l], "why": x.get("why", []),
                        "window": [max(lo, f - 3), min(hi, l + 3)]})
    return out


CLEFS = {"clefs.G": "G2", "clefs.C": "C3", "clefs.F": "F4"}
TREM = {"8": "8th", "16": "16th", "32": "32nd"}
REST = {"label": "r1", "kind": "mmrest", "pos": "0", "grace": "0", "voice": 1, "dur": "", "notes": [], "slur": [], "slur_to": [], "tie": False, "tie_to": None, "beam": [], "dyn": [], "hair": [], "text": [], "art": [], "tup": [], "clef": ""}  # the rest of a multi-bar rest


def philhar_text(lily: Path, quartet: str, part: str, mv: str, a: int, b: int) -> str:
    """Bars a..b of Philhar's encoding as text, as pc.score_text writes the MusicXML's."""
    d = philhar.encoding(pp.EDITION, lily, quartet, part, mv)
    kt = [v for n, v in sorted(d["key_time"].items(), key=lambda kv: int(kv[0])) if int(n) <= a] or [[0, "?"]]
    fifths, time_ = kt[-1]
    key = f"{abs(fifths)} {'sharp' if fifths > 0 else 'flat'}{'s' if abs(fifths) != 1 else ''}" if fifths else "no sharps or flats"
    clef = next((e["clef"] for n in range(a, -1, -1) for e in d["bars"].get(str(n), []) if e["clef"]), "clefs.G")
    lines = [f"Clef {CLEFS.get(clef, clef)}, key signature {key}, time {time_}. Pitches are written as they sound, "
             "letter, sharp (#) or flat (b) and octave, middle C = C4, the key signature's sharps and flats included."]
    for n in range(a, b + 1):
        evs, voices = [], {e["voice"] for e in d["bars"].get(str(n), []) if e["kind"] in ("note", "rest")}
        for e in d["bars"].get(str(n)) or [REST]:  # a bar a multi-bar rest covers isn't in the encoding
            if e["clef"] and e["clef"] != clef:
                clef = e["clef"]
                evs.append(f"[clef {CLEFS.get(clef, clef)}]")
            if e["kind"] == "mmrest":
                evs.append("rest for the whole bar")
                continue
            if e["kind"] not in ("note", "rest"):
                continue
            kind = pc.DUR.get(e["dur"].rstrip("."), e["dur"].rstrip(".")) + "." * e["dur"].count(".")
            if "tremolo" in e:
                kind += f" written with tremolo strokes as repeated {TREM.get(str(e['tremolo']), e['tremolo'])} notes"
            ev = f"rest {kind}" if e["kind"] == "rest" else ("grace " if e["grace"] != "0" else "") + "+".join(p["pitch"] for p in e["notes"]) + f" {kind}"
            if any(t[0] == "stop" for t in e["tup"]):  # the tuplet ended before this event
                if evs:
                    evs[-1] += "]"
                else:
                    lines[-1] += "]"
            for t in e["tup"]:
                if t[0] == "start":
                    ev = f"[{t[2]} in the time of {t[1]}: " + ev
            evs.append((f"(voice {e['voice']}) " if len(voices) > 1 else "") + ev)
        split = " (a repeat sign falls inside this bar)" if n in d["split"] else ""
        lines.append(f"bar {n}{split}: " + ", ".join(evs))
    return "\n".join(lines)


def title(q: str | None) -> str:
    """Op33-1 -> Op. 33 No. 1; boccherini-G87 -> G. 87; None -> G. 213."""
    if q is None:
        return "G. 213"
    if q.startswith("Op"):
        op, _, no = q[2:].partition("-")
        return f"Op. {int(op)}" + (f" No. {no}" if no else "")
    return "G. " + q.rsplit("-G", 1)[-1] if "-G" in q else q


VARIANTS = ("text", "engraved", "lily", "range", "stacked")  # the score's bars as: text; text and engraved; LilyPond;
# text, the proposed bars only; the proposed bars engraved under the manuscript's line, the question asked of each end
TOP = ["music I can read", "no music, or I can't read it (a blank or smudged line, or a crop that cuts the notes)"]
START = ["at the start of the first bar", "partway into the first bar: the top line begins with only its end",
         "earlier: the top line has music before the first bar", "later: the first bar is not on the top line"]
END = ["at the end of the last bar", "partway through the last bar: the top line ends with only its beginning",
       "later: the top line has music after the last bar", "earlier: the last bar is not on the top line"]
STACKED = {"type": "object", "additionalProperties": False,
           "required": ["working", "top", "start", "end", "middle_same", "insights"],
           "properties": {"working": {"type": "string"}, "top": {"type": "string", "enum": TOP}, "start": {"type": "string", "enum": START},
                          "end": {"type": "string", "enum": END}, "middle_same": {"type": "boolean"},
                          "insights": {"type": "string"}}}


def stacked_right(got: dict) -> bool | None:
    """The proposal is right when the top line is music that can be read, begins at or partway into the first
    bar, ends at or partway through the last, and the music between is the same."""
    if not got:
        return None
    return got["top"] == TOP[0] and got["start"] in START[:2] and got["end"] in END[:2] and got["middle_same"]


def stacked_prompt(x: dict) -> list:
    import engrave
    import notes
    f, l = x["claim"]
    head, bars = (notes.g213(x["part"], x["movement"], f, l) if x["quartet"] is None
                  else notes.philhar(lilies()[x["source"]], x["quartet"], x["part"], x["movement"], f, l))
    text = (f"The image has two lines of music. The top line is one line (staff) of a hand-copied part, "
            f"{pc.NAMES.get(x['part'], x['part'])}, of a string quartet by Boccherini, {title(x['quartet'])}, movement "
            f"{x['movement']}. The bottom line is a run of bars of the same part from a modern edition, engraved; "
            "here is the same run as text, its bars numbered from 1:\n\n" + notes.as_text(head, bars, relabel=True) +
            "\n\nA program matched the two lines. Is the top line the same music as the bottom line, from start to "
            "end? A line of a part often begins partway into a bar or ends partway through one (the neighbouring lines, "
            "not shown, have the rest). Copyists' notation differs from the edition's "
            "(beaming, stems, abbreviations such as strokes for repeated notes or a sign repeating a bar, "
            "ornaments), so match pitches and rhythm.\n\nAnswer in six fields, in this order. `working`: go along "
            "the top line from its start to its end, saying which bar of the bottom line each stretch of its music "
            "is and the notes that show it, and anything that doesn't match. `top`: whether the top line has music "
            "you can read; if not, answer the rest as best you can. `start`: where the top line begins, "
            "against the bottom line's first bar. `end`: where the top line ends, against the bottom line's last bar. "
            "`middle_same`: whether everything between is the same music. `insights`: one or two sentences on what "
            "made this hard or easy to decide, and what would have made it easier.")
    png = engrave.stacked_png(x)
    return [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(png).decode()}},
            {"type": "text", "text": text}]


def prompt(x: dict, variant: str = "text") -> list:
    """What Opus is sent: the staff's picture (and, for "engraved", the bars engraved), then the text."""
    import notes
    if variant == "stacked":
        return stacked_prompt(x)
    (f, l) = x["claim"]
    (a, b) = (f, l) if variant == "range" else x["window"]
    staff = (f"The {'first ' if variant == 'engraved' else ''}image is one line (staff) of a hand-copied part, "
             f"{pc.NAMES.get(x['part'], x['part'])}, of a string quartet by Boccherini, {title(x['quartet'])}, movement {x['movement']}.")
    head, bars = (notes.g213(x["part"], x["movement"], a, b) if x["quartet"] is None
                  else notes.philhar(lilies()[x["source"]], x["quartet"], x["part"], x["movement"], a, b))
    if variant == "lily":
        score = (f"Below are bars {a} to {b} of the same part from a modern edition, in LilyPond notation with absolute "
                 "pitches, each bar after a comment with its number:\n\n" + notes.as_lily(head, bars))
    else:
        score = f"Below are bars {a} to {b} of the same part from a modern edition, as text:\n\n" + notes.as_text(head, bars)
    if variant == "engraved":
        score = (f"The second image is the same bars {a} to {b} engraved, each numbered at its start, the bars {f} to {l} "
                 "bracketed in red. " + score)
    ask = (f"A program that matched this line to the edition says the line holds bars {f} to {l}: its music begins "
           f"in bar {f} and ends in bar {l}. Is that exactly right? A line can begin with the end of a bar the line "
           "before started, or end partway through a bar the next line finishes; those bars count as the line's. "
           "Copyists' notation differs from the edition's (beaming, stems, abbreviations, ornaments), so match "
           "pitches and rhythm.\n\nAnswer in three fields, in this order. `working`: go along the line from its "
           "start to its end, saying which bar of the edition each stretch of its music is and the notes that show "
           "it, and anything that doesn't match. `right`: whether the program's bars are exactly right. "
           "`insights`: one or two sentences on what made this line hard or easy to match (the copyist's "
           "notation, the image, the score's text), and what would have made it easier to decide.")
    pngs = [pc.staff_png(x["staff"], 1, False, x["source"], pad=4)]  # taller than the reader's: notes far above or below the staff
    if variant == "engraved":
        import engrave
        pngs.append(engrave.score_png(x, grey=True))
    return [*({"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(p).decode()}}
              for p in pngs),
            {"type": "text", "text": "\n\n".join([staff, score, ask])}]


def ask(x: dict, model: str, effort: str, variant: str = "text", run: str = "") -> dict:
    msg = json.dumps({"type": "user", "message": {"role": "user", "content": prompt(x, variant)}})
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}  # else claude -p bills the API key
    cmd = ["claude", "-p", "--model", model, "--effort", effort, "--tools", "", "--strict-mcp-config",
           "--system-prompt", SYSTEM, "--json-schema", json.dumps(STACKED if variant == "stacked" else SCHEMA),
           "--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
    t0 = time.time()
    p = subprocess.run(cmd, input=msg, capture_output=True, text=True, env=env, timeout=900)
    lines = [json.loads(s) for s in p.stdout.splitlines() if s.startswith("{")]
    path = CLI / run / x["source"] / f"{x['staff']}-{x['claim'][0]}-{x['claim'][1]}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(p.stdout)
    init = next((m for m in lines if m.get("subtype") == "init"), {})
    res = next((m for m in lines if m.get("type") == "result"), {})
    lim = [m["rate_limit_info"].get("unifiedWindows", {}) for m in lines if m.get("type") == "rate_limit_event"]
    got = res.get("structured_output") or {}
    u = res.get("usage", {})
    return {**{k: x[k] for k in ("source", "staff", "part", "quartet", "movement", "claim", "window", "truth") if k in x},
            "variant": variant,
            "right": stacked_right(got) if variant == "stacked" else got.get("right"),
            **({k: got.get(k) for k in ("top", "start", "end", "middle_same")} if variant == "stacked" else {}),
            "working": got.get("working"), "insights": got.get("insights"),
            "error": None if got else (res.get("subtype") or p.stderr[-300:] or "no answer"),
            "text": 3,  # the score's text: 1 the first 10; 2 voices and clefs fixed; 3 notes.py's (slurs, dynamics, multi-bar rests)
            "auth": init.get("apiKeySource"), "seconds": round(time.time() - t0, 1),
            "in": u.get("input_tokens", 0) + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
            "out": u.get("output_tokens", 0), "api_usd": res.get("total_cost_usd"),
            "five_hour": lim[-1].get("five_hour", {}).get("utilization") if lim else None,
            "seven_day": lim[-1].get("seven_day", {}).get("utilization") if lim else None}


def score(model: str, effort: str):
    rows = [json.loads(s) for s in (HERE / "results" / f"cli-check-{model}-{effort}.jsonl").read_text().splitlines()]
    key = {x["staff"]: [x["first"], x["last"]] for x in json.loads((HERE / "khm587-staves.json").read_text())
           if x["kind"] == "left out"}
    print(f"{len(rows)} answers: {sum(r['right'] is True for r in rows)} accepted, {sum(r['right'] is False for r in rows)} "
          f"rejected, {sum(r['right'] is None for r in rows)} without an answer")
    known = [r for r in rows if r["source"] == "G213-KHM587" and r["staff"] in key]
    for name, want in (("proposal right", True), ("proposal wrong", False)):
        rs = [r for r in known if (r["claim"] == key[r["staff"]]) == want]
        print(f"  KHM 587, {name}: {len(rs)}; accepted {sum(r['right'] is True for r in rs)}, rejected {sum(r['right'] is False for r in rs)}")
    n = len(rows) or 1
    print(f"  {sum(r['in'] for r in rows) // n} in / {sum(r['out'] for r in rows) // n} out a question, "
          f"{sum(r['seconds'] for r in rows) / n:.0f} s; 5-hour window now {rows[-1]['five_hour']}, week {rows[-1]['seven_day']}")


REDO = {("Op02-4-G162", "p4-3"), ("Op22-5-G187", "p13-8"), ("Op22-6-Vmbr153-va", "p37-1")}  # shown multi-bar rests as empty bars


def tests() -> list[dict]:
    """KHM 587's left-out staves whose bars the editor's fixed pages give, each asked twice: with its true
    bars and with them moved by one (pair_check.claims), the window three bars either side of the claim."""
    out = []
    for x in json.loads((HERE / "khm587-staves.json").read_text()):
        if x["kind"] != "left out":
            continue
        n = len(pc.movements(x["part"])[pc.ROMAN.index(x["movement"])])
        for c in pc.claims(x):
            out.append({"source": "G213-KHM587", "staff": x["staff"], "part": x["part"], "quartet": None,
                        "movement": x["movement"], "claim": c, "truth": [x["first"], x["last"]],
                        "window": [max(0, c[0] - 3), min(n - 1, c[1] + 3)]})
    return out


def score_tests(model: str, effort: str):
    for v in VARIANTS:
        f = HERE / "results" / f"cli-test-{v}-{model}-{effort}.jsonl"
        if not f.exists():
            continue
        rows = [json.loads(s) for s in f.read_text().splitlines()]
        pos = [r for r in rows if r["claim"] == r["truth"]]
        neg = [r for r in rows if r["claim"] != r["truth"]]
        n = len(rows) or 1
        print(f"{v:9} true bars accepted {sum(r['right'] is True for r in pos)}/{len(pos)}, moved bars rejected "
              f"{sum(r['right'] is False for r in neg)}/{len(neg)}; {sum(r['in'] for r in rows) // n} in / "
              f"{sum(r['out'] for r in rows) // n} out a question, {sum(r['seconds'] for r in rows) / n:.0f} s")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="*", default=G213)
    ap.add_argument("--philhar", action="store_true", help="also every source paired with Philhar's encodings")
    ap.add_argument("--test", help="compare the score's versions (comma-separated, of " + ", ".join(VARIANTS) +
                    ") on KHM 587's staves of known bars, in place of the left-out staves")
    ap.add_argument("--variant", default="text", choices=VARIANTS)
    ap.add_argument("--stop-at", type=float, default=0.10, help="stop once the 5-hour window's use passes this (0-1)")
    ap.add_argument("--until", type=float, default=0, help="start no question after this time (Unix seconds), e.g. the window's reset")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--model", default="claude-opus-5-5")
    ap.add_argument("--effort", default="high")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--score", action="store_true")
    a = ap.parse_args()
    if a.score:
        score(a.model, a.effort)
        return score_tests(a.model, a.effort)
    jobs = []  # (results file, variant, question)
    if a.test:
        per = []
        for v in a.test.split(","):
            out = HERE / "results" / f"cli-test-{v}-{a.model}-{a.effort}.jsonl"
            done = {(r["staff"], tuple(r["claim"])) for r in map(json.loads, out.read_text().splitlines())} if out.exists() else set()
            per.append([(out, v, x) for x in tests() if (x["staff"], tuple(x["claim"])) not in done])
        jobs = [j for js in zip_longest(*per) for j in js if j]  # the versions in turn: a stop leaves them even
    else:
        out = HERE / "results" / f"cli-check-{a.model}-{a.effort}.jsonl"
        rows = [json.loads(s) for s in out.read_text().splitlines()] if out.exists() else []
        done = {(r["source"], r["staff"]) for r in rows if (r["source"], r["staff"]) not in REDO or r.get("text", 0) >= 3}
        sources = list(a.sources) + ([s for s in lilies() if s not in HELD_OUT and pairing.results_file(s)] if a.philhar else [])
        by = [[x for x in staves([s]) if (x["source"], x["staff"]) not in done] for s in dict.fromkeys(sources)]
        jobs = [(out, a.variant, x) for xs in zip_longest(*by) for x in xs if x]  # the sources in turn: many hands
    jobs = jobs[:a.limit] if a.limit else jobs
    print(f"{len(jobs)} questions to ask", flush=True)
    stop, lock = threading.Event(), threading.Lock()

    def one(job):
        out, variant, x = job
        if stop.is_set() or (a.until and time.time() >= a.until):
            return
        try:
            row = ask(x, a.model, a.effort, variant, out.stem)
        except Exception as e:  # one failed question doesn't stop the others
            print(f"{x['source']} {x['staff']} failed: {e!r}", flush=True)
            return
        with lock, open(out, "a") as f:
            f.write(json.dumps(row) + "\n")
        if row["auth"] not in ("none", None):
            print(f"stopping: answered on {row['auth']}, not the plan's quota", flush=True)
            stop.set()
        if row["five_hour"] is not None and row["five_hour"] >= a.stop_at:
            stop.set()
        print(f"{variant} {row['source']} {row['staff']} claim {row['claim']}{' truth ' + str(row['truth']) if 'truth' in row else ''} "
              f"right {row['right']} {row['error'] or ''} {row['out']} out, {row['seconds']} s; 5-hour {row['five_hour']}, "
              f"week {row['seven_day']}", flush=True)

    with ThreadPoolExecutor(a.jobs) as pool:
        list(pool.map(one, jobs))
    if stop.is_set():
        print(f"stopped at the 5-hour window's {a.stop_at:.0%}", flush=True)


if __name__ == "__main__":
    main()
