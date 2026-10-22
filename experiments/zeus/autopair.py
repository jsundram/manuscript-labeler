# /// script
# requires-python = "==3.10.*"
# dependencies = [
#   "zeus @ git+https://github.com/OmniOMR/zeus.git@c8569eb1c8b5bb24511de6a5e53ef2450de6206c",
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

With --neighbours, a staff is also put out when the staff beside it
begins or ends with a measure paired with two bars or with a run of rest
bars: the reading may have dropped this staff's last (or first) bar,
typically a bar rest at the line's end, and the neighbour taken it, which
leaves this staff paired one-to-one but a bar short (found on G. 213's
Sibley copy, viola p10-5, with --any-count). Or with an extra measure:
half a bar the line breaks, whose other half this staff paired as the
whole bar (G. 213, Berlin print, violin 1 p16-11/12, bar IV 129: the
reading of the second half doubled it to a whole bar's length).

With --neighbours-paired, a neighbour that paired none of its measures
with a bar (an empty staff with a heading such as "Minuetto" or "Violino
Primo", a title, a scrap of detection: read as one extra measure) puts no
staff out: it holds no part of a bar the alignment placed. Found
re-pairing Philhar's sources, where most of the staves --neighbours put
out stood beside such a staff.

With --short-ends, a staff is also put out when its first or last
measure, paired with a whole bar, reads under 3/4 of the bar's length:
half of a bar split across a line break, taken for the whole. With
--long-ends, when it reads over 5/4 of it: the piece of a bar the line
breaks read into the staff's first or last measure (found re-pairing
Philhar's sources: Op. 2/2, D-Eu copy, p8-6 opens with the last four
eighths of III 8, read as part of III 9).

With --head-box, a staff is also put out when detection found more bar
boxes on it than the reading has measures and its first box (from where
the music starts to the first bar line) is under 0.6 of its median box,
unless that first bar is a movement's pickup: part of a bar the line
breaks, at the staff's head, that the reading dropped, leaving the staff
paired one-to-one but its label short of the music shown (found pairing
Schober's KHM 620, cello p2-2: it opens with the second half of I 14,
whose first half the reading of p2-1 had stretched to a whole bar).

A mis-measured staff is never kept, nor is any staff of its part below it
on the page: one measured under half its page's median staff width
(detection's staff_extent stopping early, as on grey paper) with music past
its measured ends (between the lines, from 8 staff spaces past them out to
the page's median ends, at least 0.25 of the page's written staves' median
ink). Its line
holds more bars than its crop shows, and the alignment may hand them to the
staves below (found on Op. 32's cello, p138: a fully written staff traced as
a clef, whose bars went to the next two staves). A short staff with nothing
past its ends (a movement ending mid-line) is left alone.

The alignment may stray BAND (120) bars from the straight line through
the part; at 60, Op. 32's long parts were held off their bars (vn1 pp.
21-36) and movement ends out of reach.

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

With --musicxml, the encoding is a MusicXML score of one quartet (OSSQ's,
read by ossq/mxl.py: parts in score order vn1, vn2, va, vc, as the page map
names them), and nothing is scored. Movements start where its bar numbers
start again; a bar is (movement, its index there: 0, 1, ...), every
<measure> one (a bar a repeat splits is two measures there, so none is
split here).

With --print-bars, the encoding is a printed edition's reading
(experiments/print-omr/encode.py: BA 2676's G. 223, every measure the OSSQ
reader read, by part and movement, pitches as written), and nothing is
scored. A bar is (movement, measure number there), one per measure the
print's reader read (a bar a repeat splits is two, a multi-bar rest one).
Every measure is paired, agreed by the print's two readers or not, so the
alignment has all of them to hold on to; dataset.py --print-bars keeps only
staves whose bars the readers agree on.
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
sys.path.insert(0, str(HERE / "ossq"))
import mxl  # noqa: E402
import structure  # noqa: E402

PARTS = ("vn1", "vn2", "va", "vc", "va2")  # va2: a quintet's second viola (MH 411)
CLEFS = ("treble", "alto", "tenor", "bass")
BAND = 120         # Zeus measures from the bar index the alignment may stray
MAX_REST_RUN = 40  # bars a multi-bar rest may stand for
SHORT = 0.5        # a staff measured under this share of its page's median width is short
MIS_MARGIN = 8     # staff spaces past a short staff's measured end before looking for music there
MIS_INK = 0.25     # music past the end: at least this share of the page's written staves' median ink
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
          halves: set[int], band: int = BAND, joins: set[int] = frozenset()) -> list[tuple]:
    """[(op, zeus indices, bar indices)] in order, by least cost. `breaks`:
    the Zeus measures that end a staff, the only place a bar may split.
    `spans`: the bars each entry of E stands for (a multi-bar rest, more than one).
    `halves`: the entries of E split by a repeat (Structure.ily), which
    may split anywhere. Neither half of a split may fill the bar alone.
    `joins`: the entries of E that, with the next, are one bar a repeat
    splits in two (a MusicXML score's two measures): one measure may stand
    for both ("join", priced as a split)."""
    n, m = len(Z), len(E)
    INF = float("inf")
    cost = [[INF] * (m + 1) for _ in range(n + 1)]
    back: list[list] = [[None] * (m + 1) for _ in range(n + 1)]
    cost[0][0] = 0.0
    # each row's band must reach the next's: at least the bars per measure (all of them if Zeus read none)
    band = max(band, -(-m // max(n, 1)))
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
                if j + 1 < m:
                    go(i + 1, j + 2, unlike(Z[i], E[j] + E[j + 1]) + COST["split" if j in joins else "two"],
                       "join" if j in joins else "two")
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


def box_bars(path: list[tuple], bars: list[list[tuple]], breaks: set[int], uncounted: set[tuple]) -> dict[int, dict]:
    """What each Zeus measure (a bar box) holds, for numbering a staff's bar
    lines: {measure: {"bars", "count", "join", "continues", "ends_movement"}}.
    `count`: the bars the box's closing bar line counts, each bar counted
    once: a pickup, or the second half of a bar a repeat splits (a MusicXML
    score's X1 ...: `uncounted`), counts 0; a bar split in two counts at its
    first half, except where that half ends a staff ("continues": the bar
    runs on to the next staff, no bar line there). `ends_movement`: the box
    holding the end of its movement's last bar. `join`: one measure for a
    bar a repeat splits, its two halves (a repeat bar line between them)."""
    out, last = {}, {}
    for j, bs in enumerate(bars):
        for b in bs:
            last[b[:-1]] = b  # the movement's last bar, in order
    ends = set(last.values())
    for step, zs, js in path:
        held = [b for j in js for b in bars[j]]
        each = step == "rests" and len(zs) > 1 and len(held) == len(zs)  # a bar rest for each bar of a multi-bar rest
        per = [[b] for b in held] if each else [held] * len(zs)
        payer = 1 if step == "split" and zs[0] in breaks else 0
        for k, (z, bs) in enumerate(zip(zs, per)):
            c = sum(b not in uncounted for b in bs) if each or k == payer else 0
            out[z] = {"bars": [list(b) for b in bs], "count": c, "join": step == "join",
                      "continues": step == "split" and k == 0 and z in breaks,
                      "ends_movement": bool(set(bs) & ends) and k == len(zs) - 1}
    return out


# -- the staves ------------------------------------------------------------------------

def boxes(s: dict, aspect: float) -> int:
    """Detection's bar boxes on a staff: one per bar line, and one more when
    music runs on past the last (more than 1.5 staff spaces of staff)."""
    gap = (s["bottom"] - s["top"]) / 4 * aspect  # a staff space, in page widths
    xs = sorted((b["x0"] + b["x1"]) / 2 for b in s["barlines"] if (b["x0"] + b["x1"]) / 2 > s["start"] + gap)
    return len(xs) + (not xs or s["right"] - xs[-1] > 1.5 * gap)


def head_box(s: dict, aspect: float) -> float:
    """A staff's first bar box (where the music starts to the first bar
    line, as boxes() finds them) as a share of its median box."""
    import statistics
    gap = (s["bottom"] - s["top"]) / 4 * aspect
    xs = sorted((b["x0"] + b["x1"]) / 2 for b in s["barlines"] if (b["x0"] + b["x1"]) / 2 > s["start"] + gap)
    edges = [s["start"]] + xs + ([s["right"]] if not xs or s["right"] - xs[-1] > 1.5 * gap else [])
    w = [b - a for a, b in zip(edges, edges[1:])]
    return w[0] / statistics.median(w[1:]) if len(w) > 1 else 1.0


def space_ink(g, s: dict, x0: float, x1: float) -> float:
    """Share of dark pixels (< 120) at the middle of each of a staff's spaces, along its bend, from x0 to x1
    (page fractions): detect.inner_ink, on the page."""
    import labels
    H, W = g.shape[:2]
    gap = (s["bottom"] - s["top"]) / 4
    hits = n = 0
    for x in range(max(0, int(x0 * W)), min(W, int(x1 * W)), 2):
        y0 = s["top"] + labels.bend_at(s, x / W)
        for i in range(4):
            y = int(round((y0 + (i + 0.5) * gap) * H))
            if 0 <= y < H:
                hits += g[y, x] < 120
                n += 1
    return hits / n if n else 0.0


def mis_measured(g, on_page: list) -> set:
    """The page's staves (id, system) measured short (under SHORT of the page's median width) though music
    runs on past a measured end: between the lines from MIS_MARGIN staff spaces past its right end to the
    page's median right (or from the median left to as far before its left end), at least MIS_INK of the
    page's written staves' median ink (written: at least detect.WRITTEN_INK). The margin clears a movement's
    closing bar line, repeat dots or "fine"; on 8 staves viewed, 0.25 parted the 5 mis-measured from the
    movement ends (0.43 and up against 0.07-0.12), all but one whose slanting blank staff the flat bend
    past its end drifts onto the lines of (Op. 2/1, G159 p23-7)."""
    import statistics
    import detect
    if not on_page:
        return set()
    lo = statistics.median(s["left"] for _, s in on_page)
    hi = statistics.median(s["right"] for _, s in on_page)
    med = statistics.median(s["right"] - s["left"] for _, s in on_page)
    written = [v for v in (space_ink(g, s, s["left"], s["right"]) for _, s in on_page) if v >= detect.WRITTEN_INK]
    ink = statistics.median(written) if written else 0.0
    out = set()
    H, W = g.shape[:2]
    for sid, s in on_page:
        past = MIS_MARGIN * (s["bottom"] - s["top"]) / 4 * H / W  # clear of a closing bar line, repeat dots, "fine"
        if s["right"] - s["left"] < SHORT * med and ink and max(
                space_ink(g, s, s["right"] + past, hi), space_ink(g, s, lo, s["left"] - past)) >= MIS_INK * ink:
            out.add(sid)
    return out


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


def musicxml_encoding(path: Path, part: str):
    """The same from a MusicXML score (mxl.py), bars as (movement, index);
    each bar's events are already as compared. In place of the bars a repeat
    splits: the measures followed by the other half of their bar (an
    implicit measure numbered X1, X2 ...), which the reading may join."""
    mvts = mxl.movements(path)[part]
    roman = ["I", "II", "III", "IV", "V", "VI"]
    joins = {(roman[k], i - 1) for k, bars in enumerate(mvts) for i, b in enumerate(bars)
             if i and not (b["number"] or "").isdigit()}
    return [((roman[k],), {str(i): b["events"] for i, b in enumerate(bars)}) for k, bars in enumerate(mvts)], joins


def musicxml_uncounted(path: Path, part: str) -> set[tuple]:
    """The bars of musicxml_encoding that count none: a pickup (numbered 0)
    and the second half of a bar a repeat splits (X1, X2 ...)."""
    roman = ["I", "II", "III", "IV", "V", "VI"]
    return {(roman[k], i) for k, bars in enumerate(mxl.movements(path)[part]) for i, b in enumerate(bars)
            if not (b["number"] or "").isdigit() or b["number"] == "0"}


def print_encoding(path: Path, part: str):
    """The same from a print's reading (print-omr/encode.py), bars as
    (movement, measure number); each measure's events already as compared."""
    doc = json.loads(path.read_text())
    ev = lambda e: {**e, "pitches": tuple(sorted(e["pitches"])), "acc": tuple(sorted(e["acc"]))}
    return [((mvt,), {str(m["measure"]): [ev(e) for e in m["events"]] for m in ms})
            for mvt, ms in doc["parts"].get(part, {}).items()], set()


def judge(part: str, mine: list[tuple], lmx: dict, blocks: list, split_bars: set, a, aspect: dict,
          mismeasured: set, truth: dict, export: dict | None) -> dict:
    """One part's staves paired with its encoding and judged: `mine`, its
    staves [(id, page, system)] in reading order; `lmx`, their readings by
    id; `blocks` and `split_bars`, its encoding (the *_encoding functions);
    `a`, the options (main's); `aspect`, each page's height over width;
    `mismeasured`, the staves mis_measured found. {"kept", "not kept",
    "kept but wrong", "tally", "clefs"}, as main writes them."""
    tally, wrong, clef_tally, kept, not_kept = Counter(), [], Counter(), [], []
    # the encoding's bars, all movements in order; a bar a repeat splits
    # (an upbeat follows) is where each such section ends
    bars, E, E_raw = [], [], []
    for where, by_bar in blocks:
        got = sorted(by_bar.items(), key=lambda kv: int(kv[0]))
        for k, (bar, evs) in enumerate(got):
            # a multi-bar rest is one entry, up to the next bar there is
            upto = int(got[k + 1][0]) if k + 1 < len(got) else int(bar) + 1
            enc = evs if a.musicxml or a.print_bars else compare.encoded(evs)
            bars.append([(*where, b) for b in range(int(bar), max(int(bar) + 1, upto))])
            E.append(tokens(enc, steps_enc))
            E_raw.append(enc)
    # Zeus's measures, staff after staff
    Z, Z_raw, owner = [], [], []
    for sid, n, s in mine:
        measures, _ = compare.parse(lmx[sid])
        for ms in measures:
            Z.append(tokens(ms, steps_zeus))
            Z_raw.append(ms)
            owner.append(sid)
    breaks = {k for k in range(len(owner) - 1) if owner[k] != owner[k + 1]}
    halves = {j for j, bs in enumerate(bars) if bs[0] in split_bars}
    joins = set()
    if a.musicxml:  # a bar a repeat splits is two measures there: the reading may take them as one
        halves, joins = set(), halves
    path = align(Z, E, breaks, [len(b) for b in bars], halves, a.band, joins)
    # a pickup counts no bar: bar 0 (in MusicXML, by its number: its bars are by index)
    uncounted = (musicxml_uncounted(a.musicxml, part) if a.musicxml
                 else {b for bs in bars for b in bs if b[-1] == 0})
    box = box_bars(path, bars, breaks, uncounted)
    for step, zs, js in path:
        if any(owner[z] in a.debug for z in zs):
            print(owner[zs[0]], step, [" ".join(map(str, Z[z])) for z in zs], [bars[j] for j in js],
                  [round(unlike(Z[z], E[j]), 2) for z in zs for j in js])

    # each staff's bars, and whether it holds up
    held = defaultdict(set)
    bad = set()
    why = defaultdict(list)  # staff -> why it's put out (results' "not kept")

    def out_(staves, reason):
        for st in staves:
            if st is not None:
                bad.add(st)
                why[st].append(reason)
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
            out_(staves_here, f"{step} at {[list(bars[j][0]) for j in js] or 'none'}")
        if step in ("one", "split", "join") and unlike(sum((Z[z] for z in zs), []), sum((E[j] for j in js), [])) > UNLIKE:
            out_(staves_here, f"unlike {[list(bars[j][0]) for j in js]}")  # nothing like its bar: the pairing has slipped
        if step == "missed":
            # a bar no staff holds: the staves either side are suspect
            nxt = next((owner[z] for st, zz, _ in path[path.index((step, zs, js)) + 1:] for z in zz), None)
            out_([last_owner, nxt], f"beside a missed bar {list(bars[js[0]][0])}")
        if step == "one":
            pairs[owner[zs[0]]].append((zs[0], js[0]))
        if zs:
            last_owner = owner[zs[-1]]
    # a staff's first and last measures each one bar, not a run of rests:
    # its ends are anchored even where detection's bar boxes don't say so
    ends = {}
    for step, zs, js in path:
        for z in zs:
            one = step in ("one", "join") and all(len(bars[j]) == 1 for j in js)
            ends.setdefault(owner[z], [one, one])[1] = one
    if a.neighbours:
        # a staff's end measure that stands for more than one bar (two bars, or a bar rest for
        # a run of rest bars) may have taken a bar the staff beside it holds but its reading
        # dropped (a bar rest at a line's end); an extra measure there may be half a bar the
        # line breaks, whose other half the staff beside it paired as the whole bar: that
        # staff is suspect too
        step_of = {z: (step, js) for step, zs, js in path for z in zs}
        # with --neighbours-paired, a neighbour none of whose measures paired with a bar (an empty
        # staff under a heading, a title, a scrap of detection) puts no staff out by its extra measure
        paired_any = {o for z, o in enumerate(owner) if step_of[z][0] != "extra"}
        blank = lambda st: a.neighbours_paired and st not in paired_any
        for k in sorted(breaks):
            if step_of[k + 1][0] in ("two", "rests", "extra") and not blank(owner[k + 1]):
                out_([owner[k]], f"next staff begins with {step_of[k + 1][0]}")
            if step_of[k][0] in ("two", "rests", "extra") and not blank(owner[k]):
                out_([owner[k + 1]], f"staff before ends with {step_of[k][0]}")
    if a.short_ends:
        # a staff's first or last measure paired with a whole bar but read much shorter than it:
        # half of a bar the line breaks (the other half on the staff beside it, taken as extra)
        ends_at = {}
        for z, o in enumerate(owner):
            ends_at.setdefault(o, [z, z])[1] = z
        step_of = {z: (step, js) for step, zs, js in path for z in zs}
        for o, (z0, z1) in ends_at.items():
            for z in {z0, z1}:
                step, js = step_of[z]
                if step == "one" and len(bars[js[0]]) == 1 and length(Z[z]) < 0.75 * length(E[js[0]]):
                    out_([o], f"an end measure shorter than its bar {list(bars[js[0]][0])}")
    if a.long_ends:
        # a staff's first or last measure paired with a whole bar but read much longer than it: the
        # piece of a bar the line breaks (its other part on the staff beside it) read into it
        ends_at = {}
        for z, o in enumerate(owner):
            ends_at.setdefault(o, [z, z])[1] = z
        step_of = {z: (step, js) for step, zs, js in path for z in zs}
        for o, (z0, z1) in ends_at.items():
            for z in {z0, z1}:
                step, js = step_of[z]
                if step == "one" and len(bars[js[0]]) == 1 and length(Z[z]) > 1.25 * length(E[js[0]]):
                    out_([o], f"an end measure longer than its bar {list(bars[js[0]][0])}")
    first_bar = {}
    for step, zs, js in path:
        for z in zs:
            if js:
                first_bar.setdefault(owner[z], bars[js[0]][0])
    # a mis-measured staff (mis_measured: measured short, music past its ends; staff_extent stopping
    # early, as on grey paper) holds less than its line, and the alignment may hand the rest of its bars
    # to the staves below it in the part (Op32 vc p138): it, and every staff of the part below it on the
    # page, is put out
    for pg in sorted({n for _, n, _ in mine}):
        tops = [s["top"] for sid, n, s in mine if n == pg and sid in mismeasured]
        for sid, n, s in mine:
            if n == pg and tops and s["top"] >= min(tops):
                out_([sid], "mis-measured: measured under half its page's median width, music past its ends"
                     if sid in mismeasured else "below a mis-measured staff on its page")
    for sid, n, s in mine:
        count = sum(1 for o in owner if o == sid)
        found = boxes(s, aspect[n])
        if a.head_box and found > count and head_box(s, aspect[n]) < 0.6 and first_bar.get(sid, (0,))[-1] != 0:
            out_([sid], "more bar boxes than measures, the first narrow: part of a bar at its head dropped")
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
            reasons = list(dict.fromkeys(why[sid]))
            if count == 0:
                reasons.append("nothing read")
            if count != found and not (a.any_count and all(ends.get(sid, [False]))):
                reasons.append(f"{count} measures, {found} bar boxes" + (", an end not one bar" if a.any_count else ""))
            not_kept.append({"staff": sid, "part": part, "page": n, "why": reasons, "bars": sorted(got),
                             "steps": dict(Counter(st for st, zs, _ in path if any(owner[z] == sid for z in zs))),
                             "boxes": [box[z] for z, o in enumerate(owner) if o == sid and z in box]})
            continue
        # the clef under which Zeus's notes name the encoding's pitches most often
        # (and bar by bar, for a clef the encoding doesn't have: "bar_clefs", each one-to-one
        # pair's hits under each clef; "read_clefs": the clefs the reading wrote; "worst": the
        # most unlike of those pairs)
        by_bar = [{clef: sum(1 for x, y in compare.align(E_raw[j], zev)
                             if x is not None and y is not None and E_raw[j][x]["pitches"]
                             and E_raw[j][x]["pitches"] == zev[y]["pitches"])
                   for clef in CLEFS for zev in [[compare.zeus_event(e, clef) for e in Z_raw[z]]]}
                  for z, j in pairs[sid]]
        score = {clef: sum(h[clef] for h in by_bar) for clef in CLEFS}
        best = max(score, key=score.get)
        kept.append({"staff": sid, "part": part, "page": n, "system": s, "clef": best, "bars": sorted(got),
                     "plain": plain[sid], "measures": count, "bar_boxes": found, "right": right if export else None,
                     "steps": dict(Counter(st for st, zs, _ in path if any(owner[z] == sid for z in zs))),
                     "boxes": [box[z] for z, o in enumerate(owner) if o == sid and z in box],
                     "bar_clefs": by_bar, "read_clefs": compare.parse(lmx[sid])[1],
                     "worst": round(max((unlike(Z[z], E[j]) for z, j in pairs[sid]), default=0.0), 3)})
        if t is not None and len(t[3]) == 1:
            clef_tally["clef chosen = labels'" if best == next(iter(t[3])) else "clef chosen wrong"] += 1
    if export:
        tally["labelled staves"] += len({b["system"] for b in export["bars"] if b["part"] == part})

    return {"kept": kept, "not kept": not_kept, "kept but wrong": wrong, "tally": tally, "clefs": clef_tally}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source", required=True, help="auto/<source>.json; a labelled source is scored")
    ap.add_argument("--philhar", type=Path, help="Philhar's lilypond/ folder: pair with these encodings")
    ap.add_argument("--quartets", help="with --philhar: the quartets in the source, in order (Op33-1,...)")
    ap.add_argument("--musicxml", type=Path, help="pair with this MusicXML score (OSSQ's) of the source's one quartet")
    ap.add_argument("--print-bars", type=Path,
                    help="pair with a print's reading (experiments/print-omr/encode.py's JSON) of the source's one quartet")
    ap.add_argument("--model", type=Path, default=compare.MODEL)
    ap.add_argument("--band", type=int, default=BAND, help="bars from the straight line the alignment may stray")
    ap.add_argument("--debug", nargs="*", default=[], help="staves (p7-6 ...) whose pairing to print")
    ap.add_argument("--neighbours", action="store_true",
                    help="a staff is also put out when the staff beside it begins or ends with a measure paired "
                         "with two bars or a run of rests (results/autopair-<source>[-any-count]-neighbours...json)")
    ap.add_argument("--neighbours-paired", action="store_true",
                    help="with --neighbours: only a neighbour that paired some measure with a bar puts a staff out "
                         "(not an empty staff under a heading, read as an extra measure; results ...-neighbours-paired...)")
    ap.add_argument("--short-ends", action="store_true",
                    help="a staff is also put out when its first or last measure, paired with a whole bar, reads "
                         "under 3/4 of it (results/autopair-<source>[-any-count][-neighbours]-short-ends...json)")
    ap.add_argument("--long-ends", action="store_true",
                    help="a staff is also put out when its first or last measure, paired with a whole bar, reads "
                         "over 5/4 of it (results ...-long-ends...)")
    ap.add_argument("--head-box", action="store_true",
                    help="a staff is also put out when its bar boxes outnumber its measures and its first box is "
                         "narrow (part of a bar the reading dropped; results ...-head-box...)")
    ap.add_argument("--any-count", action="store_true",
                    help="keep a staff whatever number of bar boxes detection found on it (results/autopair-<source>-any-count.json)")
    a = ap.parse_args()
    auto = json.loads((HERE / "auto" / f"{a.source}.json").read_text())
    if a.print_bars:
        pdf, export = Path(auto["pdf"]), None
        encoding = lambda part: print_encoding(a.print_bars, part)
    elif a.musicxml:
        pdf, export = Path(auto["pdf"]), None
        encoding = lambda part: musicxml_encoding(a.musicxml, part)
    elif a.philhar:
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
    keys, crops, aspect, mismeasured = {}, {}, {}, set()
    by_page = defaultdict(list)
    for sid, _, n, s in staves:
        by_page[n].append((sid, s))
    for n, on_page in by_page.items():
        g = compare.page_image(pdf, n)
        aspect[n] = g.shape[0] / g.shape[1]
        for sid, s in on_page:
            crops[sid] = compare.staff_crop(g, s)
            keys[sid] = f"{sid}:{hashlib.sha1(crops[sid]).hexdigest()[:10]}"
        mismeasured |= mis_measured(g, on_page)
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
    tally, wrong, clef_tally, kept, not_kept = Counter(), [], Counter(), [], []
    for part in PARTS:
        mine = [(sid, n, s) for sid, pt, n, s in staves if pt == part]
        if not mine:
            continue
        got = judge(part, mine, {sid: cache[keys[sid]] for sid, _, _ in mine}, *encoding(part), a, aspect,
                    mismeasured, truth, export)
        kept += got["kept"]
        not_kept += got["not kept"]
        wrong += got["kept but wrong"]
        tally.update(got["tally"])
        clef_tally.update(got["clefs"])

    out = {"source": a.source, "tally": tally, "clefs": clef_tally, "kept but wrong": wrong, "kept": kept,
           "not kept": not_kept}
    (HERE / "results").mkdir(exist_ok=True)
    by = "" if a.model == compare.MODEL else f"-{a.model.stem}"  # paired with another model's reading
    (HERE / "results" / f"autopair-{a.source}{'-any-count' if a.any_count else ''}{'-neighbours' if a.neighbours else ''}"
                        f"{'-paired' if a.neighbours and a.neighbours_paired else ''}{'-short-ends' if a.short_ends else ''}{'-long-ends' if a.long_ends else ''}"
                        f"{'-head-box' if a.head_box else ''}"
                        f"{by}.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({"tally": tally, "clefs": clef_tally}, indent=1))
    print("\n".join(wrong))


if __name__ == "__main__":
    main()
