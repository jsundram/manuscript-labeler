# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""How much would LilyPond's bar check catch of Zeus's errors? For each
bar Zeus read (compare.py's cached readings and results), whether its
durations fill the bar exactly, against whether compare.py found the bar
right.

    uv run experiments/zeus/barcheck.py <edition-repo> [--source D-B_KHM-602] [--movements II] [--model NAME]

A bar's length as Zeus wrote it: the latest time any of its voices
reaches (tuplets, a `backup` and an invisible `forward` included); a bar
rest, or a whole rest, fills the bar. Compared with the time Structure.ily
gives the bar. Only whole bars: not a pickup, half of a split bar, a multi-bar rest or
a movement's last bar (which may be short). No API calls, no edition changes.
"""

import argparse
import json
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent.parent)]
import compare  # noqa: E402
import structure  # noqa: E402


def length(events: list[dict], end: Fraction, bar: Fraction) -> Fraction:
    """The measure's length as Zeus wrote it (`end`, from compare.parse); a
    bar rest, or a whole rest (compare.py scores it as one), fills the bar."""
    if any(e["kind"] == "rest" and (e["bar_rest"] or e["dur_raw"] == "whole") for e in events):
        return bar
    return end


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("edition", type=Path)
    ap.add_argument("--source", default="D-B_KHM-602")
    ap.add_argument("--movements", nargs="+", default=["II"])
    ap.add_argument("--model", nargs="+", default=["ayce-2026-08-03.model", "heldout-602-II.model"])
    a = ap.parse_args()
    pdf = next(a.edition.glob(f"sources/*/{a.source}.pdf"))
    export = json.loads(pdf.with_name(pdf.stem + ".bars.json").read_text())
    quartet = f"Op48-{export['source']['gerard'] - 225}"
    expected = structure.expected((a.edition / quartet / "Structure.ily").read_text())
    staves: dict[str, list] = {}
    for b in export["bars"]:
        if b["part"] in ("vn1", "vn2", "va", "vc") and b["movement"] in a.movements:
            staves.setdefault(b["system"], []).append(b)
    boxes = Counter((b["part"], b["movement"], b["bar"]) for bs in staves.values() for b in bs)
    last = {}  # each movement's last bar, which may be short
    for b in export["bars"]:
        last[b["movement"]] = max(last.get(b["movement"], 0), b["bar"])
    common = None
    tables = {}
    for model in a.model:
        res = json.loads((HERE / "results" / f"{a.source}-{'-'.join(a.movements)}-{model}.json").read_text())
        verdict = {(r["part"], r["movement"], r["bar"]): r for r in res["bars"]}
        cache = json.loads((HERE / "answers" / f"{a.source}-{model}.json").read_text())
        lmx = {k.split(":")[0]: v for k, v in cache.items()}
        flagged = {}
        for sid, bs in staves.items():
            ends = []
            measures, _ = compare.parse(lmx[sid], ends)
            if len(measures) != len(bs):
                continue
            for b, ms, end in zip(bs, measures, ends):
                key = (b["part"], b["movement"], b["bar"])
                if b["count"] != 1 or boxes[key] != 1 or b["bar"] in (0, last[b["movement"]]) or key not in verdict:
                    continue
                bar = Fraction(*structure.meter(compare.in_force(expected[b["movement"]], "time", b)))
                flagged[key] = length(ms, end, bar) != bar
        tables[model] = (flagged, verdict)
        common = set(flagged) if common is None else common & set(flagged)
    for model, (flagged, verdict) in tables.items():
        t = Counter()
        for k in common:
            right = verdict[k]["exact"]
            t[("right" if right else "wrong", "flagged" if flagged[k] else "passed")] += 1
            if not verdict[k]["rhythm"]:
                t[("rhythm wrong", "flagged" if flagged[k] else "passed")] += 1
        wrong = t[("wrong", "flagged")] + t[("wrong", "passed")]
        rw = t[("rhythm wrong", "flagged")] + t[("rhythm wrong", "passed")]
        print(f"{model}, {len(common)} whole bars:")
        print(f"  bars wrong {wrong}: the bar check flags {t[('wrong', 'flagged')]}")
        print(f"  bars wrong in rhythm {rw}: flags {t[('rhythm wrong', 'flagged')]}")
        print(f"  bars right {t[('right', 'flagged')] + t[('right', 'passed')]}: flags {t[('right', 'flagged')]}")



if __name__ == "__main__":
    main()
