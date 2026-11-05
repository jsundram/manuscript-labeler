# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow", "verovio", "numba"]
# ///
"""The staves Opus accepted added to a source's pairing: the pairing's
left-out staves whose proposed bars Opus said were right
(experiments/llm/pairing/check_leftout.py), as kept staves.

    uv run experiments/zeus/add_opus.py [SOURCE ...]    (default: every source Opus checked)

Opus's "right" lets a line begin partway into its first bar or end partway
through its last, and a label must say which. So a staff is taken only
where its neighbours on the part show it: each end a whole bar (the line
before ends one bar earlier, the line after begins one bar later, or the
staff opens or closes its movement), or a bar the neighbour shares, where
the neighbour is kept and the pairing cut that bar ("halves"): the staff
gets the other half, cut in the same place. Where the neighbour is
accepted too, the bar is cut as the pairing cuts one (autopair.break_cut):
at the onset whose halves are most like the end of the one line's reading
and the start of the other's (D5's or D3S's, the closer), if they fit
within autopair.BREAK_FIT. A neighbour that is neither
kept nor accepted tells nothing, and the staff is left out. So is one
that holds a multi-bar rest, whose bars a kept staff of the part already
holds, or (G. 213, whose staves the set builder labels whole bars only)
that shares a bar with its neighbour. D-Dl_Mus.3403-P-513 is the readers'
held-out test and gets nothing.

Writes results/autopair-<source>-plus-opus.json from the source's newest
pairing (pairing.results_file), which pairing.RESULTS then puts first, each
added staff marked "opus" with Opus's working and insights.
"""

import argparse
import collections
import json
import sys
from pathlib import Path

ZEUS = Path(__file__).resolve().parent
LLM = ZEUS.parents[1] / "experiments" / "llm" / "pairing"
sys.path.insert(0, str(ZEUS.parents[1]))
sys.path.insert(0, str(LLM))
import pairing  # noqa: E402
import check_leftout as cl  # noqa: E402
import notes  # noqa: E402
sys.path.insert(0, str(ZEUS))
import autopair  # noqa: E402
import compare  # noqa: E402

ANSWERS = LLM / "results" / "cli-check-claude-opus-5-5-high.jsonl"
READERS = ("musvit-D5-B6k-d11-op48x3-s1", "musvit-D3S-h96")  # their readings: answers/<source>-auto-<reader>.json


def answers() -> dict[str, dict[str, dict]]:
    """{source: {staff: Opus's last answer}}, the accepted ones."""
    last = {}
    for r in map(json.loads, ANSWERS.read_text().splitlines()):
        last[(r["source"], r["staff"])] = r
    out = collections.defaultdict(dict)
    for (src, sid), r in last.items():
        if r["right"]:
            out[src][sid] = r
    return out


def reading_order(src: str) -> dict[str, list[str]]:
    """{part: its staves, page by page, top to bottom}."""
    auto = json.loads((ZEUS / "auto" / f"{src}.json").read_text())
    out = collections.defaultdict(list)
    for n, page in sorted(auto["pages"].items(), key=lambda kv: int(kv[0])):
        for k, s in enumerate(sorted(page["systems"], key=lambda s: s["top"])):
            out[s.get("part", page.get("part"))].append((f"p{n}-{k}", int(n), s))
    return out


class Readings:
    """A source's staves as each reader read them, by the crop's hash as autopair.py keys them."""

    def __init__(self, src: str):
        auto = json.loads((ZEUS / "auto" / f"{src}.json").read_text())
        self.pdf, self.pages = Path(auto["pdf"]), auto["pages"]
        self.by = {r: json.loads(f.read_text()) for r in READERS
                   if (f := ZEUS / "answers" / f"{src}-auto-{r}.json").exists()}
        self.keys, self.page = {}, None

    def key(self, sid: str, n: int, s: dict) -> str:
        if sid not in self.keys:
            if self.page is None or self.page[0] != n:
                self.page = (n, compare.page_image(self.pdf, n))
            self.keys[sid] = f"{sid}:{autopair.hashlib.sha1(compare.staff_crop(self.page[1], s)).hexdigest()[:10]}"
        return self.keys[sid]

    def measures(self, sid: str, n: int, s: dict) -> dict[str, list[list[dict]]]:
        k = self.key(sid, n, s)
        return {r: compare.parse(d[k])[0] for r, d in self.by.items() if k in d}


def cut_between(rd: Readings, before: tuple, after: tuple, evs: list[dict]) -> tuple | None:
    """(cut, fit, reader) for a bar the end of `before` and the start of `after` share (staves as
    reading_order gives them), or None where no reader's readings fit a cut."""
    a, b = rd.measures(*before), rd.measures(*after)
    best = None
    for r in set(a) & set(b):
        if not a[r] or not b[r]:
            continue
        got = autopair.break_cut(autopair.tokens(a[r][-1], autopair.steps_zeus),
                                 autopair.tokens(b[r][0], autopair.steps_zeus), compare.encoded(evs))
        if got and (best is None or got[1] < best[1]):
            best = (*got, r)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="*")
    a = ap.parse_args()
    accepted = answers()
    lily = cl.lilies()
    for src in a.sources or sorted(accepted):
        if src in cl.HELD_OUT:
            print(f"{src}: held out, nothing added")
            continue
        base_file = next(f for f in (ZEUS / "results" / f"autopair-{src}-{r}.json" for r in pairing.RESULTS
                                     if r != "plus-opus") if f.exists())
        base = json.loads(base_file.read_text())
        kept = {k["staff"]: k for k in base["kept"]}
        notk = {k["staff"]: k for k in base["not kept"]}
        ours = {sid: r for sid, r in accepted.get(src, {}).items() if sid in notk}
        held = {(k["part"], json.dumps(b)) for k in base["kept"] for b in k["bars"]}
        g213 = src in cl.G213
        rd = Readings(src)
        added, why = [], collections.Counter()
        for part, staves in reading_order(src).items():
            for i, (sid, page, system) in enumerate(staves):
                if sid not in ours:
                    continue
                x, r = notk[sid], ours[sid]
                bars = x["bars"]
                *piece, mv, f = bars[0]
                l = bars[-1][-1]
                if [f, l] != r["claim"]:
                    why["not the bars Opus was asked about"] += 1
                    continue
                # the movement's first and last bars, as check_leftout found them
                lo, hi = (0, len(cl.pc.movements(part)[cl.pc.ROMAN.index(mv)]) - 1) if g213 else (
                    lambda ns: (min(ns), max(ns)))([int(n) for n in cl.philhar.encoding(
                        cl.pp.EDITION, lily[src], piece[0], part, mv)["bars"]])
                halves, ends = [], []
                for side, j, bar, edge in (("start", i - 1, f, lo), ("end", i + 1, l, hi)):
                    other = staves[j][0] if 0 <= j < len(staves) else None
                    nb = (kept.get(other) or (notk[other] if other in ours else None) or {}).get("bars") if other else None
                    if other is None or (nb and nb[0][:-1] != bars[0][:-1]):  # no line on that side in this movement
                        ends.append("whole" if bar == edge else "unknown")
                        continue
                    if not nb:
                        ends.append("unknown")
                        continue
                    near = nb[-1][-1] if side == "start" else nb[0][-1]
                    if near == bar + (-1 if side == "start" else 1):
                        ends.append("whole")
                    elif near == bar and other in ours and other not in kept and not g213:
                        enc = cl.philhar.encoding(cl.pp.EDITION, lily[src], piece[0], part, mv)["bars"]
                        pair = (staves[j], staves[i]) if side == "start" else (staves[i], staves[j])
                        got = cut_between(rd, *pair, enc.get(str(bar), []))
                        if got is None:
                            ends.append("shared, no cut fits")
                            continue
                        halves.append({"bar": bars[0][:-1] + [bar], "half": "second" if side == "start" else "first",
                                       "cut": str(got[0]), "fit": got[1], "reader": got[2], "with": other})
                        ends.append("cut")
                    elif near == bar and other in kept:
                        h = next((h for h in kept[other].get("halves", []) if h["bar"][-1] == bar), None)
                        if h is None or g213:
                            ends.append("shared, not cut")
                            continue
                        halves.append({"bar": bars[0][:-1] + [bar], "half": "second" if side == "start" else "first",
                                       "cut": h["cut"], "from": other})
                        ends.append("cut")
                    else:
                        ends.append("shared, not cut" if near == bar else "gap or overlap")
                if any(e not in ("whole", "cut") for e in ends):
                    why["an end the neighbours don't show: " + " / ".join(ends)] += 1
                    continue
                shared = {json.dumps(h["bar"]) for h in halves}
                if any((part, json.dumps(b)) in held and json.dumps(b) not in shared for b in bars):
                    why["bars a kept staff holds"] += 1
                    continue
                if g213:
                    head, evs = notes.g213(part, mv, f, l)
                else:
                    head, evs = notes.philhar(lily[src], piece[0], part, mv, f, l)
                    enc = cl.philhar.encoding(cl.pp.EDITION, lily[src], piece[0], part, mv)["bars"]
                    if any(str(b[-1]) not in enc or any(e["kind"] == "mmrest" for e in enc[str(b[-1])]) for b in bars):
                        why["a multi-bar rest"] += 1
                        continue
                clef = notes.CLEFS.get(tuple(head["clef"]), "treble")
                if clef == "alto" and part == "vc":
                    clef = "tenor"  # Philhar's C clef: the cello's is the tenor
                # a bar a repeat splits: two measures, the set builder cutting it where the upbeat starts
                split = set() if g213 else set(cl.philhar.encoding(cl.pp.EDITION, lily[src], piece[0], part, mv).get("split", []))
                boxes = []
                for b in bars:
                    if b[-1] in split:
                        boxes += [{"bars": [b], "count": 1}, {"bars": [b], "count": 0}]
                    else:
                        boxes.append({"bars": [b], "count": 0 if any(h["bar"] == b and h["half"] == "second" for h in halves) else 1})
                irregular = ["a bar a repeat splits"] if any(b[-1] in split for b in bars) else []
                added.append({"staff": sid, "part": part, "page": page, "system": system, "clef": clef, "bars": bars,
                              "plain": not halves and not irregular, "measures": len(boxes), "bar_boxes": len(boxes),
                              "right": None, **({"halves": halves} if halves else {}),
                              **({"irregular": irregular} if irregular else {}), "steps": {"one": len(bars)}, "boxes": boxes,
                              "why_left_out": x.get("why", []),
                              "opus": {"model": "claude-opus-5-5", "effort": "high", "working": r["working"],
                                       "insights": r["insights"]}})
        gone = {x["staff"] for x in added}
        out = dict(base, kept=base["kept"] + added,
                   **{"not kept": [x for x in base["not kept"] if x["staff"] not in gone]},
                   added_opus={"from": base_file.name, "answers": ANSWERS.name, "accepted": len(ours),
                               "staves": len(added), "left out": dict(why)})
        (ZEUS / "results" / f"autopair-{src}-plus-opus.json").write_text(json.dumps(out, indent=1))
        print(f"{src}: {len(base['kept'])} kept, {len(ours)} accepted by Opus, {len(added)} added "
              f"({sum(why.values())} left out)", flush=True)


if __name__ == "__main__":
    main()
