# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@main",
#   "tensorflow-macos==2.12.0; sys_platform == 'darwin' and platform_machine == 'arm64'",
#   "numpy", "pillow",
# ]
# [tool.uv]
# override-dependencies = ["tensorflow; sys_platform != 'darwin' or platform_machine != 'arm64'"]
# ///
"""Training pairs without labelling: which bars each automatically detected
staff holds, found by lining Zeus's reading up with the encoding, and
checked against the editor's labels.

    UV_PYTHON_INSTALL_DIR=~/.cache/manuscript-labeler/zeus/py \
      uv run --python-preference only-managed experiments/zeus/autopair.py <edition-repo> --source F-Po_RES-507-14

Input: auto/<source>.json (autodetect.py: detection's staves on each music
page, and the page's part). Each staff is cut and read by Zeus (zero-shot)
as compare.py does. Then, part by part, the measures Zeus read on all its
staves, in reading order, are aligned with the encoding's bars (all
movements, in order; the edition's scripts/events.py) by dynamic
programming. A Zeus measure is paired with:
- one bar (cost: how unlike they are, below);
- with the next Zeus measure, one bar: a bar split across two staves, or
  anywhere at a repeat with an upbeat (Structure.ily says which bars), if
  neither half is as long as the bar;
- a run of rest bars, if it is a bar rest (a multi-bar rest), and the
  reverse: several bar rests for one multi-bar rest of the encoding;
- two bars (a bar line Zeus missed);
- nothing (an extra measure), and a bar with nothing (a missed one).
How unlike two measures are: edit distance over their events' rhythm
(rest or note, duration, dots, grace) and the step from the note before,
which needs no clef (Zeus's clefs are unreliable on these hands).

A staff is **kept** for training if all its measures paired one-to-one
(or as a split bar or a multi-bar rest), no bar was skipped at its ends,
no measure is nothing like its bar (unlike > UNLIKE: the pairing has
slipped), and detection's bar boxes on it are as many as Zeus's
measures (with --any-count, or else its first and last measures each
paired with one bar, not a run of rests). Keeping a staff depends on counts, and only loosely on whether
Zeus read its notes right, so the kept staves aren't just the ones Zeus
already reads well. A bar rest is never half of a split bar.

Each kept staff's clef is chosen as the one under which Zeus's notes
(placed by its own staff positions) name the encoding's pitches most often.

Scored against the labels (the edition's bar export): a kept staff is
right if it holds exactly the bars the editor's staff at its place holds.

With --philhar, the encoding is Philhar's (philhar.py) for the quartets
the source holds, in order, and nothing is scored: the source has no
labels. Its staves' parts come from autodetect.py (a page's, or a score
system's).

    UV_PYTHON_INSTALL_DIR=~/.cache/manuscript-labeler/zeus/py \\
      uv run --python-preference only-managed experiments/zeus/autopair.py <edition-repo> \\
        --source F-Pn_RES-507-2 --philhar <boccherini-quartet-data>/lilypond --quartets Op33-1,...,Op33-6
"""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent)]
import compare  # noqa: E402
import philhar  # noqa: E402
import structure  # noqa: E402

PARTS = ("vn1", "vn2", "va", "vc")
CLEFS = ("treble", "alto", "tenor", "bass")
BAND = 60          # Zeus measures from the bar index the alignment may stray
MAX_REST_RUN = 40  # bars a multi-bar rest may stand for
UNLIKE = 0.75      # a measure further than this from its bar puts its staff out
COST = {"split": 0.2, "rests": 0.1, "two": 0.6, "extra": 1.0, "missed": 1.0}


# -- measures as compared ---------------------------------------------------------

def steps_zeus(e: dict):
    return min(e["pos"]) if e["kind"] == "note" and e["pos"] else None


def steps_enc(e: dict):
    return min(compare.num(p) for p in e["pitches"]) if e["kind"] == "note" and e["pitches"] else None


def tokens(events: list[dict], step) -> list[tuple]:
    """(kind, duration, dots, grace, step from the note before) per event. A
    rest that fills the bar is one kind, however written: Zeus's bar rest,
    whole rest or breve (how it reads a multi-bar rest), the encoding's R."""
    out, prev = [], None
    for e in events:
        s = step(e)
        dur, dots = e["dur"], e["dots"]
        if e["kind"] == "rest" and (e.get("bar_rest") or dur in ("whole", "breve", "bar")):
            dur, dots = "bar", 0
        out.append((e["kind"], dur, dots, e["grace"], None if s is None or prev is None else s - prev))
        prev = s if s is not None else prev
    return out


def unlike(a: list[tuple], b: list[tuple]) -> float:
    """0 (alike) to 1: edit distance, a substitution half-priced when the
    rhythm or the step agrees."""
    if not a and not b:
        return 0.0
    n, m = len(a), len(b)
    prev = list(range(m + 1))
    for i in range(1, n + 1):
        cur = [i] + [0] * m
        for j in range(1, m + 1):
            x, y = a[i - 1], b[j - 1]
            sub = 0 if x == y else 0.5 if (x[:4] == y[:4] or x[4] == y[4]) else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + sub)
        prev = cur
    return prev[m] / max(n, m)


def rest_bar(tok: list[tuple]) -> bool:
    return bool(tok) and all(t[0] == "rest" for t in tok) and any(t[1] == "bar" for t in tok)


LENGTHS = {"breve": Fraction(2), "whole": Fraction(1), "half": Fraction(1, 2), "quarter": Fraction(1, 4),
           "8th": Fraction(1, 8), "16th": Fraction(1, 16), "32nd": Fraction(1, 32), "64th": Fraction(1, 64)}


def length(tok: list[tuple]) -> Fraction:
    """How long a measure's events last, one after another (voices and
    tuplets aside: a rough figure), grace notes not counted."""
    total = Fraction(0)
    for kind, dur, dots, grace, _ in tok:
        if grace or dur not in LENGTHS:
            continue
        total += LENGTHS[dur] * (2 - Fraction(1, 2 ** dots))
    return total


# -- the alignment -------------------------------------------------------------------

def align(Z: list[list[tuple]], E: list[list[tuple]], breaks: set[int], spans: list[int],
          halves: set[int], band: int = BAND) -> list[tuple]:
    """[(op, zeus indices, bar indices)] in order, by least cost. `breaks`:
    the Zeus measures that end a staff, the only place a bar may split.
    `spans`: the bars each entry of E stands for (a multi-bar rest, more than one).
    `halves`: the entries of E split by a repeat (Structure.ily), which
    may split anywhere. Neither half of a split may fill the bar alone."""
    n, m = len(Z), len(E)
    INF = float("inf")
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back: list[list] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    lo = lambda i: max(0, int(i * m / max(n, 1)) - band)
    hi = lambda i: min(m, int(i * m / max(n, 1)) + band)
    zlen, elen = [length(z) for z in Z], [length(e) for e in E]
    rests_from = [0] * (m + 1)  # rest bars in a run starting at j
    for j in range(m - 1, -1, -1):
        rests_from[j] = rests_from[j + 1] + 1 if rest_bar(E[j]) else 0
    for i in range(n + 1):
        for j in range(lo(i), hi(i) + 1):
            c = cost[i][j]
            if c == INF:
                continue

            def go(i2, j2, add, step):
                if i2 <= n and j2 <= m and c + add < cost[i2][j2]:
                    cost[i2][j2] = c + add
                    back[i2][j2] = (i, j, step)
            if i < n and j < m:
                go(i + 1, j + 1, unlike(Z[i], E[j]), "one")
                go(i + 1, j + 2, unlike(Z[i], E[j] + E[j + 1]) + COST["two"], "two") if j + 1 < m else None
                if rest_bar(E[j]) and spans[j] > 1:
                    for k in range(2, spans[j] + 1):
                        if i + k <= n and all(rest_bar(Z[x]) for x in range(i, i + k)):
                            go(i + k, j + 1, COST["rests"], "rests")
                if rest_bar(Z[i]):
                    for k in range(2, min(rests_from[j], MAX_REST_RUN) + 1):
                        go(i + 1, j + k, COST["rests"], "rests")
            if (i + 1 < n and j < m and (i in breaks or j in halves) and not (rest_bar(Z[i]) or rest_bar(Z[i + 1]))
                    and zlen[i] < elen[j] and zlen[i + 1] < elen[j]):
                go(i + 2, j + 1, unlike(Z[i] + Z[i + 1], E[j]) + COST["split"], "split")
            if i < n:
                go(i + 1, j, COST["extra"], "extra")
            if j < m:
                go(i, j + 1, COST["missed"], "missed")
    out, i, j = [], n, m
    while (i, j) != (0, 0):
        pi, pj, step = back[i][j]
        out.append((step, list(range(pi, i)), list(range(pj, j))))
        i, j = pi, pj
    return out[::-1]


# -- the staves ------------------------------------------------------------------------

def boxes(s: dict, aspect: float) -> int:
    """Detection's bar boxes on a staff: one per bar line, and one more when
    music runs on past the last (more than 1.5 staff spaces of staff)."""
    gap = (s["bottom"] - s["top"]) / 4 * aspect  # a staff space, in page widths
    xs = sorted((b["x0"] + b["x1"]) / 2 for b in s["barlines"] if (b["x0"] + b["x1"]) / 2 > s["start"] + gap)
    return len(xs) + (not xs or s["right"] - xs[-1] > 1.5 * gap)


def truth_staves(export: dict) -> dict:
    """{system id: (page, middle, set of (movement, bar), its clefs)} from the bar export."""
    out = {}
    for b in export["bars"]:
        if b["part"] not in PARTS:
            continue
        s = export["systems"][b["system"]]
        _, _, held, clefs = out.setdefault(b["system"], (s["page"], (s["top"] + s["bottom"]) / 2, set(), set()))
        for k in range(max(1, b["count"])):
            held.add((b["movement"], b["bar"] + k))
        clefs.update(b["clefs"])
    return out


def edition_encoding(edition: Path, quartet: str, movements: list[str], part: str):
    """The edition's bars for a part, all movements in order: ([bars each
    entry stands for, as (movement, bar)], [its events]), and the bars a
    repeat splits (Structure.ily)."""
    split_bars = set()
    for mvt, e in structure.expected((edition / quartet / "Structure.ily").read_text()).items():
        end = 0
        for seg in e["segments"]:
            end += seg["bars"]
            if seg["split"]:
                split_bars.add((mvt, end))
    blocks = []
    for mvt in movements:
        r = subprocess.run(["uv", "run", "--offline", str(edition / "scripts" / "events.py"), quartet, part, mvt,
                            "--json"], capture_output=True, text=True, check=True)
        blocks.append(((mvt,), json.loads(r.stdout)))
    return blocks, split_bars


def philhar_encoding(edition: Path, lily: Path, quartets: list[str], part: str):
    """The same from Philhar's encodings (philhar.py), bars as (quartet, movement, bar)."""
    blocks, split_bars = [], set()
    for q in quartets:
        for mvt in philhar.movements(lily / q):
            r = subprocess.run(["uv", "run", str(HERE / "philhar.py"), str(edition), str(lily), q, part, mvt, "--json"],
                               capture_output=True, text=True, check=True,
                               env={k: v for k, v in os.environ.items() if k != "UV_PYTHON_INSTALL_DIR"})
            d = json.loads(r.stdout)
            blocks.append(((q, mvt), d["bars"]))
            split_bars.update((q, mvt, b) for b in d["split"])
    return blocks, split_bars


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source", required=True, help="auto/<source>.json; a labelled source is scored")
    ap.add_argument("--philhar", type=Path, help="Philhar's lilypond/ folder: pair with these encodings")
    ap.add_argument("--quartets", help="with --philhar: the quartets in the source, in order (Op33-1,...)")
    ap.add_argument("--model", type=Path, default=compare.MODEL)
    ap.add_argument("--band", type=int, default=BAND, help="bars from the straight line the alignment may stray")
    ap.add_argument("--debug", nargs="*", default=[], help="staves (p7-6 ...) whose pairing to print")
    ap.add_argument("--any-count", action="store_true",
                    help="keep a staff whatever number of bar boxes detection found on it (results/autopair-<source>-any-count.json)")
    a = ap.parse_args()
    auto = json.loads((HERE / "auto" / f"{a.source}.json").read_text())
    if a.philhar:
        pdf, export = Path(auto["pdf"]), None
        encoding = lambda part: philhar_encoding(a.edition, a.philhar, a.quartets.split(","), part)
    else:
        pdf = next(a.edition.glob(f"sources/*/{a.source}.pdf"))
        export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
        quartet = f"Op48-{export['source']['gerard'] - 225}"
        movements = sorted({b["movement"] for b in export["bars"]}, key=lambda r: ("I", "II", "III", "IV").index(r))
        encoding = lambda part: edition_encoding(a.edition, quartet, movements, part)

    # Zeus reads each detected staff
    staves = []  # (id, part, page, system)
    for n, p in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
        for k, s in enumerate(sorted(p["systems"], key=lambda s: s["top"])):
            staves.append((f"p{n}-{k}", s.get("part", p["part"]), int(n), s))
    cache_file = HERE / "answers" / f"{a.source}-auto-{a.model.name}.json"
    cache = json.loads(cache_file.read_text()) if cache_file.exists() else {}
    keys, crops, aspect, page = {}, {}, {}, None
    for sid, _, n, s in staves:
        if page != n:
            g, page = compare.page_image(pdf, n), n
            aspect[n] = g.shape[0] / g.shape[1]
        crops[sid] = compare.staff_crop(g, s)
        keys[sid] = f"{sid}:{hashlib.sha1(crops[sid]).hexdigest()[:10]}"
    todo = [sid for sid, *_ in staves if keys[sid] not in cache]
    if todo:
        from zeus import InferenceOptions, Zeus
        model = Zeus.load(a.model)
        print(f"Zeus reads {len(todo)} staves ...", flush=True)
        for sid, lmx in zip(todo, model.predict([crops[sid] for sid in todo], InferenceOptions(batch_size=8))):
            cache[keys[sid]] = lmx
        cache_file.parent.mkdir(exist_ok=True)
        cache_file.write_text(json.dumps(cache, indent=1, sort_keys=True))

    truth = truth_staves(export) if export else {}
    tally, wrong, clef_tally, kept = Counter(), [], Counter(), []
    for part in PARTS:
        mine = [(sid, n, s) for sid, pt, n, s in staves if pt == part]
        if not mine:
            continue
        # the encoding's bars, all movements in order; a bar a repeat splits
        # (an upbeat follows) is where each such section ends
        blocks, split_bars = encoding(part)
        bars, E, E_raw = [], [], []
        for where, by_bar in blocks:
            got = sorted(by_bar.items(), key=lambda kv: int(kv[0]))
            for k, (bar, evs) in enumerate(got):
                # a multi-bar rest is one entry, up to the next bar there is
                upto = int(got[k + 1][0]) if k + 1 < len(got) else int(bar) + 1
                enc = compare.encoded(evs)
                bars.append([(*where, b) for b in range(int(bar), max(int(bar) + 1, upto))])
                E.append(tokens(enc, steps_enc))
                E_raw.append(enc)
        # Zeus's measures, staff after staff
        Z, Z_raw, owner = [], [], []
        for sid, n, s in mine:
            measures, _ = compare.parse(cache[keys[sid]])
            for ms in measures:
                Z.append(tokens(ms, steps_zeus))
                Z_raw.append(ms)
                owner.append(sid)
        breaks = {k for k in range(len(owner) - 1) if owner[k] != owner[k + 1]}
        halves = {j for j, bs in enumerate(bars) if bs[0] in split_bars}
        path = align(Z, E, breaks, [len(b) for b in bars], halves, a.band)
        for step, zs, js in path:
            if any(owner[z] in a.debug for z in zs):
                print(owner[zs[0]], step, [" ".join(map(str, Z[z])) for z in zs], [bars[j] for j in js],
                      [round(unlike(Z[z], E[j]), 2) for z in zs for j in js])

        # each staff's bars, and whether it holds up
        held = defaultdict(set)
        bad = set()
        pairs = defaultdict(list)  # staff -> [(zeus measure, bar index)] paired one to one
        plain = defaultdict(lambda: True)  # every measure one bar, none split by a repeat
        last_owner = None
        for step, zs, js in path:
            staves_here = {owner[z] for z in zs}
            if step != "one" or any(len(bars[j]) > 1 or j in halves for j in js):
                for st in staves_here:
                    plain[st] = False
            for z in zs:
                held[owner[z]].update(b for j in js for b in bars[j])
            if step in ("extra", "two"):
                bad.update(staves_here)
            if step in ("one", "split") and unlike(sum((Z[z] for z in zs), []), E[js[0]]) > UNLIKE:
                bad.update(staves_here)  # nothing like its bar: the pairing has slipped
            if step == "missed":
                # a bar no staff holds: the staves either side are suspect
                bad.add(last_owner)
                nxt = next((owner[z] for st, zz, _ in path[path.index((step, zs, js)) + 1:] for z in zz), None)
                bad.add(nxt)
            if step == "one":
                pairs[owner[zs[0]]].append((zs[0], js[0]))
            if zs:
                last_owner = owner[zs[-1]]
        # a staff's first and last measures each one bar, not a run of rests:
        # its ends are anchored even where detection's bar boxes don't say so
        ends = {}
        for step, zs, js in path:
            for z in zs:
                one = step == "one" and len(bars[js[0]]) == 1
                ends.setdefault(owner[z], [one, one])[1] = one
        for sid, n, s in mine:
            count = sum(1 for o in owner if o == sid)
            found = boxes(s, aspect[n])
            cy = (s["top"] + s["bottom"]) / 2
            match = [t for t in truth.values() if t[0] == n and abs(t[1] - cy) < 0.015]
            t = match[0] if match else None
            keep = count > 0 and sid not in bad and (count == found or (a.any_count and all(ends.get(sid, [False]))))
            got = held[sid]
            right = t is not None and got == t[2]
            tally["staves"] += 1
            tally["staves kept"] += keep
            tally["bars on kept staves"] += len(got) if keep else 0
            tally["kept, bar boxes as many"] += keep and count == found
            if export:
                tally["kept and right"] += keep and right
                tally["kept, wrong"] += keep and not right
                tally["not kept, would have been right"] += (not keep) and right
                tally["bars on kept staves, right"] += len(got) if keep and right else 0
                tally["no labelled staff here"] += t is None
            if export and keep and not right:
                wrong.append(f"{part} {sid}: paired {sorted(got)[:1]}..{sorted(got)[-1:]} ({len(got)}), labels "
                             + (f"{sorted(t[2])[:1]}..{sorted(t[2])[-1:]} ({len(t[2])})" if t else "no staff"))
            if not keep:
                continue
            # the clef under which Zeus's notes name the encoding's pitches most often
            score = {}
            for clef in CLEFS:
                hits = 0
                for z, j in pairs[sid]:
                    zev = [compare.zeus_event(e, clef) for e in Z_raw[z]]
                    hits += sum(1 for x, y in compare.align(E_raw[j], zev)
                                if x is not None and y is not None and E_raw[j][x]["pitches"]
                                and E_raw[j][x]["pitches"] == zev[y]["pitches"])
                score[clef] = hits
            best = max(score, key=score.get)
            kept.append({"staff": sid, "part": part, "page": n, "system": s, "clef": best, "bars": sorted(got),
                         "plain": plain[sid], "measures": count, "bar_boxes": found, "right": right if export else None})
            if t is not None and len(t[3]) == 1:
                clef_tally["clef chosen = labels'" if best == next(iter(t[3])) else "clef chosen wrong"] += 1
        if export:
            tally["labelled staves"] += len({b["system"] for b in export["bars"] if b["part"] == part})

    out = {"source": a.source, "tally": tally, "clefs": clef_tally, "kept but wrong": wrong, "kept": kept}
    (HERE / "results").mkdir(exist_ok=True)
    by = "" if a.model == compare.MODEL else f"-{a.model.stem}"  # paired with another model's reading
    (HERE / "results" / f"autopair-{a.source}{'-any-count' if a.any_count else ''}{by}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"tally": tally, "clefs": clef_tally}, indent=1))
    print("\n".join(wrong))


if __name__ == "__main__":
    main()
