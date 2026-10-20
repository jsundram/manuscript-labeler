# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pillow"]
# ///
"""Bar by bar, how each staff autopair.py --musicxml kept reads against the
bars it was paired with: the reader's measure and the encoding's bar, how
unlike (autopair.unlike, 0 to 1), and their event counts. Flags the bars to
look at: unlike above --flag, and bars where the encoding writes out
repeated notes the print may abbreviate (a run of 4 or more of one pitch
and duration) while the reader read far fewer events.

    uv run experiments/zeus/g213/check.py RESULTS.json SCORE.musicxml ANSWERS.json [--flag 0.5] [--out check.json]
"""

import argparse
import hashlib
import json
import sys
from pathlib import Path

ZEUS = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ZEUS), str(ZEUS / "ossq")]
import autopair  # noqa: E402
import compare  # noqa: E402
import mxl  # noqa: E402

ROMAN = ["I", "II", "III", "IV", "V", "VI"]


def repeated_run(evs: list[dict]) -> int:
    best = run = 0
    prev = None
    for e in evs:
        key = (e["kind"], e["pitches"], e["dur"], e["dots"]) if e["kind"] == "note" and not e["grace"] else None
        run = run + 1 if key is not None and key == prev else (1 if key else 0)
        prev = key
        best = max(best, run)
    return best


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", type=Path)
    ap.add_argument("score", type=Path)
    ap.add_argument("answers", type=Path)
    ap.add_argument("--flag", type=float, default=0.5)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    res = json.loads(a.results.read_text())
    cache = json.loads(a.answers.read_text())
    by_staff = {k.split(":")[0]: v for k, v in cache.items()}  # one crop per staff in a run
    mv = mxl.movements(a.score)
    out, flagged = {}, 0
    for k in res["kept"]:
        measures, _ = compare.parse(by_staff[k["staff"]])
        rows = []
        if k["plain"] and len(measures) == len(k["bars"]):
            for ms, (m, i) in zip(measures, k["bars"]):
                bar = mv[k["part"]][ROMAN.index(m)][i]
                z = autopair.tokens(ms, autopair.steps_zeus)
                e = autopair.tokens(bar["events"], autopair.steps_enc)
                u = autopair.unlike(z, e)
                run = repeated_run(bar["events"])
                why = []
                if u > a.flag:
                    why.append(f"unlike {u:.2f}")
                if run >= 4 and len(ms) < 0.7 * len(bar["events"]):
                    why.append(f"encoding repeats a note {run}x, read {len(ms)} of {len(bar['events'])} events")
                rows.append({"bar": f"{m} {bar['number']}", "unlike": round(u, 2), "read": len(ms),
                             "encoded": len(bar["events"]), "why": why})
        out[k["staff"]] = {"part": k["part"], "plain": k["plain"], "bars": rows,
                           "flags": [r for r in rows if r["why"]]}
        if out[k["staff"]]["flags"]:
            flagged += 1
            print(k["staff"], k["part"], "; ".join(f"{r['bar']}: {', '.join(r['why'])}" for r in out[k["staff"]]["flags"]))
    print(f"{flagged} of {len(res['kept'])} kept staves have a flagged bar")
    if a.out:
        a.out.write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
