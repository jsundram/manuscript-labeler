# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""The staves two readers' pairings both keep, with the same bars and clef.

    uv run experiments/zeus/philhar-repair/both.py SOURCE... [--suffix S] [--readers musvit-D3S-h96 musvit-C4-bocch-tf8-L-best]

For a source the first reader was trained on (dataM's and dataT's sources,
in musvit-D4's training), its reading of a staff can repeat the old label,
right or wrong; the second reader (C4, trained on Op. 48 alone) never saw
these sources. Writes results/autopair-<source>-both.json: the first
reader's records for the staves both keep with the same bars and clef,
and a "not kept" list with why (each reader's reasons, or the bars they
differ on).
"""

import argparse
import json
from pathlib import Path

ZEUS = Path(__file__).resolve().parent.parent


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--suffix", default="-any-count-neighbours-paired-short-ends-long-ends")
    ap.add_argument("--readers", nargs=2, default=["musvit-D3S-h96", "musvit-C4-bocch-tf8-L-best"])
    a = ap.parse_args()
    r1, r2 = a.readers
    for src in a.sources:
        A = json.loads((ZEUS / "results" / f"autopair-{src}{a.suffix}-{r1}.json").read_text())
        B = json.loads((ZEUS / "results" / f"autopair-{src}{a.suffix}-{r2}.json").read_text())
        bk = {k["staff"]: k for k in B["kept"]}
        bn = {k["staff"]: k for k in B["not kept"]}
        kept, not_kept = [], [dict(k, why=[f"{r1}: {w}" for w in k["why"]]) for k in A["not kept"]]
        for k in A["kept"]:
            o = bk.get(k["staff"])
            if o is not None and o["bars"] == k["bars"] and o["clef"] == k["clef"]:
                kept.append(dict(k, second_reader=r2))
                continue
            why = ([f"{r2}: {w}" for w in bn[k["staff"]]["why"]] if k["staff"] in bn else
                   [f"{r2} pairs other bars: {o['bars'][0]}..{o['bars'][-1]} ({len(o['bars'])})"] if o["bars"] != k["bars"] else
                   [f"{r2} chose clef {o['clef']}"])
            not_kept.append({"staff": k["staff"], "part": k["part"], "page": k["page"], "bars": k["bars"], "why": why})
        out = {"source": src, "readers": [r1, r2], "kept": kept, "not kept": not_kept}
        (ZEUS / "results" / f"autopair-{src}-both.json").write_text(json.dumps(out, indent=1))
        print(f"{src}: {r1} kept {len(A['kept'])}, {r2} kept {len(B['kept'])}, both (same bars, clef) {len(kept)}")


if __name__ == "__main__":
    main()
