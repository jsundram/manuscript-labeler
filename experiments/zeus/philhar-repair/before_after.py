# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""dataM's and dataT's staves against the re-pairing: for each source, the
staves in the old staff set (samples.<source>.txt) and the bars the old
pairing gave them, against the new pairing's.

    uv run experiments/zeus/philhar-repair/before_after.py NEW_SUFFIX [--old-set dataM] SOURCE...

NEW_SUFFIX names the new results (results/autopair-<source><NEW_SUFFIX>.json).
The old pairing is the one each set was built from: dataM's
-any-count-musvit-C4-bocch-tf8-L-best, dataT's -any-count-both. Prints, per
source, the old set's staves, how many the new pairing keeps with the same
bars, keeps with other bars, or doesn't keep (and why); and writes the
differing staves to philhar-repair/before-after.json.
"""

import json
import sys
from collections import Counter
from pathlib import Path

ZEUS = Path(__file__).resolve().parent.parent
CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
OLD = {"dataM": "-any-count-musvit-C4-bocch-tf8-L-best", "dataT": "-any-count-both"}


def main():
    new_suffix, sources = sys.argv[1], sys.argv[2:]
    out, tot = {}, Counter()
    for src in sources:
        old_set = "dataT" if src.endswith("-EMc") else "dataM"
        listed = CACHE / old_set / f"samples.{src}.txt"
        in_set = [l.split("/")[1] for l in listed.read_text().split()] if listed.exists() else []
        old = json.loads((ZEUS / "results" / f"autopair-{src}{OLD[old_set]}.json").read_text())
        new = json.loads((ZEUS / "results" / f"autopair-{src}{new_suffix}.json").read_text())
        ob = {k["staff"]: k["bars"] for k in old["kept"]}
        nb = {k["staff"]: k for k in new["kept"]}
        nk = {k["staff"]: k for k in new["not kept"]}
        c, diff = Counter(), []
        for s in in_set:
            if s in nb and nb[s]["bars"] == ob[s]:
                c["same bars"] += 1
            elif s in nb:
                c["other bars"] += 1
                diff.append({"staff": s, "old": [ob[s][0], ob[s][-1], len(ob[s])],
                             "new": [nb[s]["bars"][0], nb[s]["bars"][-1], len(nb[s]["bars"])]})
            else:
                c["not kept"] += 1
                w = nk.get(s, {}).get("why", ["?"])
                c["  " + w[0].split(" [")[0].split(" at ")[0]] += 1
                same = nk.get(s, {}).get("bars") == ob[s]
                c["  (its bars as before)" if same else "  (other bars)"] += 1
                diff.append({"staff": s, "not kept": w, "same bars": same, "old": [ob[s][0], ob[s][-1], len(ob[s])]})
        out[src] = diff
        tot.update({k: v for k, v in c.items() if not k.startswith("  ")})
        tot["in old set"] += len(in_set)
        print(f"{src}: old set {len(in_set)}; " + "; ".join(f"{k.strip()} {v}" for k, v in sorted(c.items())))
    print("TOTAL", dict(tot))
    (Path(__file__).parent / "before-after.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
