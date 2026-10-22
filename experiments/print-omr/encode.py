# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""A quartet of BA 2676 as event JSON for pairing with manuscripts: every
measure the OSSQ reader (musvit D3S-h96-ossq) read, each marked with the
readers that agree with it, and "use" where it may label a manuscript bar.

    uv run experiments/print-omr/encode.py 223

"use" is the rule the test bed supports (README, "Verdict"): Audiveris
read the same measure (aligned as score.py aligns two readings, without
any encoding), and the measure is not a lone bar rest (a multi-bar rest's
count isn't read). On the test bed that kept 60% of bars, 99.2% of them
right by the print. "agree" also says whether musvit-D4 agrees (all three:
55% of bars, 99.2% right).

Measures are numbered from 1 in each movement, in reading order, one per
measure read: a bar a repeat sign splits counts twice and a multi-bar rest
once, so the numbers are not the print's bar numbers. Pitches are as
written (the reader's own clefs), events as compare.py compares them.

Writes <G>/BA2676-G<G>.json.
"""

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import readings  # noqa: E402
import score  # noqa: E402

MAIN, OTHERS = "musvit:D3S-h96-ossq", ["mxl:audiveris", "musvit:D3S-h96"]


def main():
    g = int(sys.argv[1])
    q = next(q for q in score.PAGEMAP["quartets"] if q["G"] == g)
    reads = {s: score.load(s) for s in [MAIN] + OTHERS}
    out = {"edition": score.PAGEMAP["edition"], "quartet": f"G. {g}: {q['title']}", "reader": MAIN,
           "checked against": OTHERS, "rule": __doc__.split("\n\n")[1].replace("\n", " "), "parts": {}}
    tally = {"measures": 0, "use": 0, "all three": 0}
    for part in readings.PARTS:
        ms = score.measures_for(reads[MAIN], g, part)
        agree = {i: [] for i in range(len(ms))}
        for o in OTHERS:
            mo = score.measures_for(reads[o], g, part)
            for kind, ia, ib in score.align([m["events"] for m in ms], [m["events"] for m in mo]):
                if kind == "one" and score.same(ms[ia[0]]["events"], mo[ib[0]]["events"]):
                    agree[ia[0]].append(o)
        mvts = q["parts"][part]["movements"]
        first = {name: m["pages"][0] for name, m in mvts.items()}
        out["parts"][part] = {}
        count = {}
        for i, m in enumerate(ms):
            # a movement starts on its first page (BA 2676's G. 223 movements start at a page top)
            mvt = max((n for n, p in first.items() if p <= m["page"]), key=lambda n: first[n])
            count[mvt] = count.get(mvt, 0) + 1
            use = "mxl:audiveris" in agree[i] and not score.bar_rest(m["events"])
            out["parts"][part].setdefault(mvt, []).append({
                "measure": count[mvt], "page": m["page"], "staff": m["staff"], "m": m["m"],
                "events": [{k: (list(v) if isinstance(v, tuple) else str(v) if k == "end" else v) for k, v in e.items()}
                           for e in m["events"]],
                "text": " ".join(map(score.text, m["events"])), "agree": agree[i], "fills": m["fills"], "use": use})
            tally["measures"] += 1
            tally["use"] += use
            tally["all three"] += len(agree[i]) == 2
    out["counts"] = tally
    dest = HERE / f"G{g}" / f"BA2676-G{g}.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, indent=1))
    print(f"G. {g}: {tally['measures']} measures; use {tally['use']} ({tally['use'] / tally['measures']:.0%}); "
          f"all three agree {tally['all three']} -> {dest.relative_to(HERE)}")
    for part in readings.PARTS:
        print(" ", part, {mv: f"{sum(x['use'] for x in v)}/{len(v)}" for mv, v in out["parts"][part].items()})


if __name__ == "__main__":
    main()
