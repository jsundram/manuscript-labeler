# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The counts table for README.md: per source (sources.txt), staves
detected, kept by the pairing, and in the staff set (dataW or dataP) with
their bars (counted in each staff's label, so a staff cut to its first
bars counts those only); then the reasons staves weren't kept, from
autopair.py's "not kept" (first reason) and dataset.py's log.

    uv run experiments/zeus/wayback-print-pairs/counts.py > experiments/zeus/wayback-print-pairs/counts.md
"""

import ast
import json
import re
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
ZEUS = HERE.parent
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
SUFFIX = "-any-count-neighbours-paired-short-ends-long-ends-head-box-musvit-D3S-h96"


def reason(why: str) -> str:
    """autopair.py's reason, grouped."""
    for key, name in [("two at", "a measure paired with two bars"), ("extra at", "an extra measure"),
                      ("unlike", "a measure nothing like its bar"), ("beside a missed", "beside a bar no staff holds"),
                      ("next staff begins", "the staff beside it begins or ends with two bars, an extra measure or rests"),
                      ("staff before ends", "the staff beside it begins or ends with two bars, an extra measure or rests"),
                      ("shorter than its bar", "an end measure shorter than its bar"),
                      ("longer than its bar", "an end measure longer than its bar"),
                      ("first narrow", "more bar boxes than measures, the first narrow"),
                      ("bar boxes", "measures and bar boxes differ, and an end isn't one bar"),
                      ("nothing read", "nothing read")]:
        if key in why:
            return name
    return why


def main():
    rows, tot, pair_why, data_why = [], Counter(), {"W": Counter(), "P": Counter()}, {"W": Counter(), "P": Counter()}
    for line in (HERE / "sources.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        g, src, *_ = line.split()
        auto = ZEUS / "auto" / f"{src}.json"
        res = ZEUS / "results" / f"autopair-{src}{SUFFIX}.json"
        if not (auto.exists() and res.exists()):
            rows.append(f"| {g} | {src} | not paired | | | |")
            continue
        detected = sum(len(p["systems"]) for p in json.loads(auto.read_text())["pages"].values())
        r = json.loads(res.read_text())
        for nk in r["not kept"]:
            pair_why[g][reason(nk["why"][0]) if nk["why"] else "?"] += 1
        out = CACHE / ("dataW" if g == "W" else "dataP")
        lst = out / f"samples.{src}.txt"
        staves = [l.split("/")[1] for l in lst.read_text().split()] if lst.exists() else []
        bars = sum((out / src / f"{s}.lmx").read_text().split().count("measure") for s in staves)
        log = HERE / "logs" / f"dataset-{src}.log"
        if log.exists():
            m = re.search(r"left out: (\{.*\})", log.read_text())
            if m:
                for k, v in ast.literal_eval(m.group(1)).items():
                    data_why[g][k] += v
        row = Counter(detected=detected, paired=len(r["kept"]), staves=len(staves), bars=bars)
        tot.update({f"{g} {k}": v for k, v in row.items()})
        rows.append(f"| {g} | {src} | {detected} | {len(r['kept'])} | {len(staves)} | {bars} |")
    print("| group | source | detected | paired | in the set | bars |")
    print("|---|---|--:|--:|--:|--:|")
    print("\n".join(rows))
    for g, name in (("W", "dataW"), ("P", "dataP")):
        print(f"| **{g}** | **{name}** | {tot[g + ' detected']} | {tot[g + ' paired']} | **{tot[g + ' staves']}** | {tot[g + ' bars']} |")
    for g in ("W", "P"):
        print(f"\nNot kept by the pairing ({g}), by first reason:\n")
        print("| reason | staves |\n|---|--:|")
        for k, v in pair_why[g].most_common():
            print(f"| {k} | {v} |")
        print(f"\nLeft out by dataset.py ({g}):\n")
        print("| reason | staves |\n|---|--:|")
        for k, v in data_why[g].most_common():
            print(f"| {k} | {v} |")


if __name__ == "__main__":
    main()
