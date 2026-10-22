# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Score each candidate's reading of BA 2676 bar by bar against the known
encodings of the test-bed quartets, and the agreement of each pair.

    uv run experiments/print-omr/score.py musvit:D3S-h96 musvit:D3S-h96-ossq mxl:audiveris ...

A candidate is musvit:<run> (experiments/zeus/answers) or mxl:<name>
(~/Data/manuscript-labeler/experiments/print-omr/<name>/<part>/p<NN>.*).

**Pairing a reading with the encoding.** For each quartet and part, the
reading's measures on the quartet's pages, in order, are aligned with the
encoding's bars, all movements in order, by dynamic programming. A step
pairs one measure with one bar (cost: how unlike they are, 0 to 1, by an
edit distance over events where an event right in rhythm but not pitch
costs half), two measures with one bar (a bar a repeat sign splits; +0.1),
one measure with two bars (a missed bar line; +0.1), one bar rest with a
run of 2 or more bar rests (a multi-bar rest; 0.1), or leaves a measure or a
bar out (0.45 each). The encoding is never read to decide anything but the
pairing.

**Scores**, in compare.py's terms, over every encoded bar of the test bed:
- bar exact: the same events, in order (notes, rests, durations, dots,
  graces; each note's letter and octave), at the pitches the reader wrote;
  a unison written as two voices (<< d8 \\ d >>) is one note;
- right in rhythm: kinds, durations, dots and graces right;
- right in pitch: each note's letter and octave right, in order.
A bar left out, or paired with part of a measure, is wrong. Bars inside a
multi-bar rest are not scored (counted apart). Accidentals are scored
apart, as compare.py does.

**Agreement.** Two readings are aligned with each other the same way,
without the encoding. A bar is agreed when a measure of one is paired
one-to-one with a measure of the other and their events are the same. It
is right when that measure of the first is paired with an encoded bar (or,
as half of a bar a repeat sign splits, with the other half) and is exact,
its tremolos either way (canon(): the print writes out repeated notes
that Philhar and OSSQ often abbreviate as tremolos, and the reverse).
A second filter adds that the agreed measure fills its bar: its events
(the reader's durations) last as long as most measures on its staff.

Writes results/score.json (per candidate, quartet, part, movement) and
results/bars.json (each bar's verdict, for the error examples).
"""

import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import readings  # noqa: E402

DATA = Path.home() / "Data/manuscript-labeler/experiments/print-omr"
PAGEMAP = json.loads((HERE / "pagemap.json").read_text())
TEST = [159, 189, 213, 228]
GAP, JOIN, RESTS, BAND = 0.45, 0.1, 0.1, 60


def key(e):
    return (e["kind"], tuple(sorted(set(e["pitches"]))), e["dur"], e["dots"], bool(e["grace"]))


def rkey(e):
    return (e["kind"], e["dur"], e["dots"], bool(e["grace"]))


from fractions import Fraction as F
LEN = {"breve": F(2), "whole": F(1), "half": F(1, 2), "quarter": F(1, 4), "8th": F(1, 8), "16th": F(1, 16),
       "32nd": F(1, 32), "64th": F(1, 64)}
VALUE = {LEN[k] * (2 - F(1, 2 ** d)): (k, d) for k in ("whole", "half", "quarter") for d in (0, 1)}


def canon(evs: list) -> list:
    """A bar with its tremolos written one way: a run of two or more equal
    notes (same pitches, same short duration, no grace) lasting one plain
    or dotted note value becomes that one note. Applied to both sides, a
    tremolo abbreviation (Philhar's e2.:8, OSSQ's) equals the notes the
    print writes out; genuinely repeated notes stay equal to themselves."""
    out, i = [], 0
    while i < len(evs):
        e = evs[i]
        j = i + 1
        if e["kind"] == "note" and not e["grace"] and e["dur"] in LEN:
            while (j < len(evs) and evs[j]["kind"] == "note" and not evs[j]["grace"] and evs[j]["dur"] == e["dur"]
                   and evs[j]["dots"] == e["dots"] and sorted(set(evs[j]["pitches"])) == sorted(set(e["pitches"]))):
                j += 1
        total = (j - i) * LEN.get(e["dur"], F(0)) * (2 - F(1, 2 ** e["dots"])) if j - i > 1 else None
        if total in VALUE:
            k, d = VALUE[total]
            out.append({**e, "dur": k, "dots": d})
            i = j
        else:
            out.append(e)
            i += 1
    return out


def unlike(a: list, b: list) -> float:
    a, b = canon(a), canon(b)
    n, m = len(a), len(b)
    if not n and not m:
        return 0.0
    if not n or not m:
        return 1.0
    ka, kb = [key(e) for e in a], [key(e) for e in b]
    ra, rb = [rkey(e) for e in a], [rkey(e) for e in b]
    prev = [j * 1.0 for j in range(m + 1)]
    for i in range(1, n + 1):
        cur = [i * 1.0] + [0.0] * m
        for j in range(1, m + 1):
            sub = 0.0 if ka[i - 1] == kb[j - 1] else 0.5 if ra[i - 1] == rb[j - 1] else 1.0
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + sub)
        prev = cur
    return min(1.0, prev[m] / max(n, m))


def bar_rest(evs):
    return len(evs) == 1 and evs[0]["kind"] == "rest" and evs[0]["dur"] in ("bar", "whole")


def align(A: list[list], B: list[list], rests: bool = True) -> list[tuple]:
    """Steps (kind, [A indices], [B indices]) aligning two sequences of bars."""
    n, m = len(A), len(B)
    INF = float("inf")
    cost = {(0, 0): 0.0}
    back = {}
    memo = {}

    def d(i0, i1, j0, j1):
        k = (i0, i1, j0, j1)
        if k not in memo:
            memo[k] = unlike([e for x in A[i0:i1] for e in x], [e for y in B[j0:j1] for e in y])
        return memo[k]

    ratio = m / n if n else 1
    for i in range(n + 1):
        lo, hi = max(0, int(i * ratio) - BAND), min(m, int(i * ratio) + BAND)
        for j in range(lo, hi + 1):
            c = cost.get((i, j), INF)
            if c == INF:
                continue

            def go(di, dj, k, kind):
                t = (i + di, j + dj)
                if c + k < cost.get(t, INF):
                    cost[t] = c + k
                    back[t] = (kind, i, j)
            if i < n:
                go(1, 0, GAP, "skipA")
            if j < m:
                go(0, 1, GAP, "skipB")
            if i < n and j < m:
                go(1, 1, d(i, i + 1, j, j + 1), "one")
            if i + 1 < n and j < m:
                go(2, 1, d(i, i + 2, j, j + 1) + JOIN, "joinA")
            if i < n and j + 1 < m:
                go(1, 2, d(i, i + 1, j, j + 2) + JOIN, "joinB")
            if rests and i < n and bar_rest(A[i]) and j < m and bar_rest(B[j]):
                k = 1
                while j + k < m and bar_rest(B[j + k]):
                    k += 1
                    go(1, k, RESTS, f"rests{k}")
    t = (n, m)
    if t not in cost:  # the band cut the end off: take the best end reached
        t = min((k for k in cost), key=lambda k: cost[k] + GAP * ((n - k[0]) + (m - k[1])))
    steps = []
    i, j = t
    tail = [("skipA", [x], []) for x in range(i, n)] + [("skipB", [], [y]) for y in range(j, m)]
    while (i, j) != (0, 0):
        kind, pi, pj = back[(i, j)]
        steps.append((kind, list(range(pi, i)), list(range(pj, j))))
        i, j = pi, pj
    return steps[::-1] + tail


def same(a, b):
    return len(a) == len(b) and all(key(x) == key(y) for x, y in zip(a, b))


def verdict(enc, read):
    return {"exact": same(enc, read), "exact, tremolos either way": same(canon(enc), canon(read)),
            "rhythm": [rkey(e) for e in enc] == [rkey(e) for e in read],
            "pitch": [tuple(sorted(set(e["pitches"]))) for e in enc if e["kind"] == "note"]
                     == [tuple(sorted(set(e["pitches"]))) for e in read if e["kind"] == "note"]}


def text(e):
    if e["kind"] == "rest":
        return "R" if e["dur"] == "bar" else "r" + (e["dur"] or "?") + "." * e["dots"]
    p = e["pitches"][0] if len(e["pitches"]) == 1 else "<" + " ".join(e["pitches"]) + ">"
    return ("g" if e["grace"] else "") + p + ":" + (e["dur"] or "?") + "." * e["dots"]


def quartet_pages(g: int, part: str) -> range:
    q = next(q for q in PAGEMAP["quartets"] if q["G"] == g)
    a, b = q["parts"][part]["pages"]
    return range(a, b + 1)


def load(spec: str) -> dict:
    kind, _, name = spec.partition(":")
    if kind == "musvit":
        return readings.musvit(name)
    if kind == "mxl":
        return readings.musicxml_dir(DATA / name)
    raise SystemExit(f"unknown candidate {spec}")


def length(evs: list):
    ends = [e["end"] for e in evs if e.get("end") is not None]
    return max(ends) if ends else None


def measures_for(reading: dict, g: int, part: str) -> list[dict]:
    """The reading's measures on the quartet's pages, in order. Each says
    whether it fills its bar: as long as most of its staff's measures (the
    reader's own durations; a bar rest fills any bar)."""
    pages = quartet_pages(g, part)
    out = []
    for s in reading[part]:
        if s["page"] in pages:
            lens = [length(ms) for ms in s["measures"]]
            common = Counter(x for x in lens if x is not None).most_common(1)
            for k, ms in enumerate(s["measures"]):
                fills = bar_rest(ms) or (bool(common) and lens[k] == common[0][0])
                out.append({"page": s["page"], "staff": s["staff"], "m": k, "events": ms, "fills": fills})
    return out


def main():
    specs = sys.argv[1:]
    truth = {g: json.loads((HERE / "truth" / f"G{g}.json").read_text()) for g in TEST}
    reads = {s: load(s) for s in specs}
    score = {}
    bars_out = []
    tobar = {}  # (spec, g, part, measure index) -> (truth index, exact)
    for s in specs:
        tally = defaultdict(Counter)
        for g in TEST:
            for part in readings.PARTS:
                enc = [(mvt, b["bar"], b["events"]) for mvt, bars in truth[g][part].items() for b in bars]
                ms = measures_for(reads[s], g, part)
                steps = align([m["events"] for m in ms], [e[2] for e in enc])
                for kind, ia, ib in steps:
                    if kind == "skipA":
                        continue
                    for jb in ib:
                        mvt, bar, evs = enc[jb]
                        row = {"cand": s, "G": g, "part": part, "mvt": mvt, "bar": bar,
                               "encoded": " ".join(map(text, evs)), "step": kind}
                        if kind.startswith("rests"):
                            row["multirest"] = True
                        elif kind in ("one", "joinA"):
                            read = [e for i in ia for e in ms[i]["events"]]
                            row.update(verdict(evs, read))
                            row["read"] = " ".join(map(text, read))
                            row["where"] = [(ms[i]["page"], ms[i]["staff"], ms[i]["m"]) for i in ia]
                            for i in ia:  # a half bar (a repeat's split) is right if the joined bar is
                                tobar[(s, g, part, i)] = (jb, row["exact, tremolos either way"])
                        else:
                            row.update(exact=False, rhythm=False, pitch=False, read="" if kind == "skipB" else
                                       " ".join(text(e) for i in ia for e in ms[i]["events"]))
                            if ia:
                                row["where"] = [(ms[i]["page"], ms[i]["staff"], ms[i]["m"]) for i in ia]
                        bars_out.append(row)
                        for grp in ("all", f"G{g}", f"G{g} {part}", f"G{g} {mvt}", part):
                            t = tally[grp]
                            if row.get("multirest"):
                                t["in multi-bar rests"] += 1
                                continue
                            t["bars"] += 1
                            t["exact"] += row["exact"]
                            t["exact, tremolos either way"] += row.get("exact, tremolos either way", False)
                            t["rhythm"] += row["rhythm"]
                            t["pitch"] += row["pitch"]
                            t["unread"] += kind == "skipB"
        score[s] = {k: dict(v) for k, v in tally.items()}
        a = tally["all"]
        print(f"{s}: {a['bars']} bars; exact {a['exact']} ({a['exact'] / a['bars']:.1%}; tremolos either way "
              f"{a['exact, tremolos either way'] / a['bars']:.1%}), rhythm {a['rhythm'] / a['bars']:.1%}, "
              f"pitch {a['pitch'] / a['bars']:.1%}; unread {a['unread']}; in multi-bar rests {a['in multi-bar rests']}")
        for g in TEST:
            t = tally[f"G{g}"]
            print(f"   G. {g}: exact {t['exact']}/{t['bars']} ({t['exact'] / t['bars']:.1%}), "
                  f"rhythm {t['rhythm'] / t['bars']:.1%}, pitch {t['pitch'] / t['bars']:.1%}")

    # agreement of each pair, aligned without the encoding
    agree = {}
    agreed_rows = []
    P = {}  # (A, B) -> {(g, part): {A's measure index}} agreed
    fills = {}  # (A, g, part, i) -> fills its bar
    for x in range(len(specs)):
        for y in range(x + 1, len(specs)):
            A, B = specs[x], specs[y]
            t = Counter()
            for g in TEST:
                for part in readings.PARTS:
                    nbars = sum(len(b) for b in truth[g][part].values())
                    t["encoded bars"] += nbars
                    ma, mb = measures_for(reads[A], g, part), measures_for(reads[B], g, part)
                    for kind, ia, ib in align([m["events"] for m in ma], [m["events"] for m in mb]):
                        if kind != "one" or not same(ma[ia[0]]["events"], mb[ib[0]]["events"]):
                            continue
                        t["agreed"] += 1
                        P.setdefault((A, B), {}).setdefault((g, part), set()).add(ia[0])
                        fills[(A, g, part, ia[0])] = ma[ia[0]]["fills"]
                        hit = tobar.get((A, g, part, ia[0]))
                        right = bool(hit and hit[1])
                        t["agreed and right"] += right
                        if ma[ia[0]]["fills"]:
                            t["agreed, filling the bar"] += 1
                            t["agreed, filling the bar, and right"] += right
                        t["agreed, not paired with a bar"] += hit is None
                        if not right:
                            m = ma[ia[0]]
                            mvt_bar = None
                            if hit:
                                mvts = [(mv, b["bar"]) for mv, bars in truth[g][part].items() for b in bars]
                                mvt_bar = mvts[hit[0]]
                            agreed_rows.append({"pair": [A, B], "G": g, "part": part, "page": m["page"],
                                                "staff": m["staff"], "m": m["m"], "bar": mvt_bar,
                                                "read": " ".join(map(text, m["events"]))})
            agree[f"{A} + {B}"] = dict(t)
            print(f"{A} + {B}: agreed {t['agreed']} of {t['encoded bars']} encoded bars ({t['agreed'] / t['encoded bars']:.1%}); "
                  f"right {t['agreed and right']} ({t['agreed and right'] / max(1, t['agreed']):.1%}); "
                  f"not paired with a bar {t['agreed, not paired with a bar']}; filling the bar: "
                  f"{t['agreed, filling the bar']} ({t['agreed, filling the bar'] / t['encoded bars']:.1%}), right "
                  f"{t['agreed, filling the bar, and right'] / max(1, t['agreed, filling the bar']):.1%}")
    # three readings agreeing: a measure of the first agreed with both others
    for x in range(len(specs)):
        for y in range(x + 1, len(specs)):
            for z in range(y + 1, len(specs)):
                A, B, C = specs[x], specs[y], specs[z]
                t = Counter()
                for g in TEST:
                    for part in readings.PARTS:
                        t["encoded bars"] += sum(len(b) for b in truth[g][part].values())
                        both = P.get((A, B), {}).get((g, part), set()) & P.get((A, C), {}).get((g, part), set())
                        for i in both:
                            hit = tobar.get((A, g, part, i))
                            right = bool(hit and hit[1])
                            t["agreed"] += 1
                            t["agreed and right"] += right
                            if not right:
                                m = measures_for(reads[A], g, part)[i]
                                agreed_rows.append({"pair": [A, B, C], "G": g, "part": part, "page": m["page"],
                                                    "staff": m["staff"], "m": m["m"], "fills": m["fills"],
                                                    "read": " ".join(map(text, m["events"]))})
                            if fills[(A, g, part, i)]:
                                t["agreed, filling the bar"] += 1
                                t["agreed, filling the bar, and right"] += right
                agree[f"{A} + {B} + {C}"] = dict(t)
                print(f"{A} + {B} + {C}: agreed {t['agreed']} ({t['agreed'] / t['encoded bars']:.1%}); right "
                      f"{t['agreed and right'] / max(1, t['agreed']):.1%}; filling the bar {t['agreed, filling the bar']} "
                      f"({t['agreed, filling the bar'] / t['encoded bars']:.1%}), right "
                      f"{t['agreed, filling the bar, and right'] / max(1, t['agreed, filling the bar']):.1%}")
    (HERE / "results").mkdir(exist_ok=True)
    (HERE / "results" / "score.json").write_text(json.dumps({"score": score, "agreement": agree}, indent=1))
    (HERE / "results" / "bars.json").write_text(json.dumps({"bars": bars_out, "agreed_wrong": agreed_rows}))


if __name__ == "__main__":
    main()
