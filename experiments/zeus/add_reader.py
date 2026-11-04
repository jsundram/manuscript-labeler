# /// script
# requires-python = ">=3.11"
# ///
"""A second reader's staves added to a source's pairing: every staff the
pairing already keeps (pairing.results_file: G. 213's merge, the two
readers' merge, or one reader's), and those the reader's own pairing keeps
that it wasn't trained on and whose bars no kept staff of the part holds.

    uv run experiments/zeus/add_reader.py --reader musvit-D5-B6k-d11-op48x3-s1 --tag D5 SOURCE...

The reader's pairing is results/autopair-<source>-any-count*-<reader>.json
(parallel_pair.py --reader). A staff in the reader's training (the staff
sets' samples lists, pairing.SETS) is left out: its reading can repeat its
label, right or wrong (philhar-repair/both.py). D-Dl_Mus.3403-P-513 is the
readers' held-out test, labelled by D4's pairing alone, and gets nothing.
Writes results/autopair-<source>-plus-<tag>.json, which pairing.RESULTS
puts first, with each added staff marked "reader".
"""

import argparse
import json
import sys
from pathlib import Path

ZEUS = Path(__file__).resolve().parent
sys.path.insert(0, str(ZEUS.parents[1]))
import pairing  # noqa: E402

CACHE = Path.home() / ".cache/manuscript-labeler/zeus"
HELD_OUT = {"D-Dl_Mus.3403-P-513"}


def trained() -> set[str]:
    """'<source>/p<page>-<k>' for every staff in the newest staff sets."""
    return {line.strip() for s in pairing.SETS for f in (CACHE / s).glob("samples.*.txt")
            for line in f.read_text().split() if line.strip()}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("sources", nargs="+")
    ap.add_argument("--reader", required=True)
    ap.add_argument("--tag", required=True, help="the results file's name: autopair-<source>-plus-<tag>.json")
    a = ap.parse_args()
    seen = trained()
    for src in a.sources:
        if src in HELD_OUT:
            print(f"{src}: held out, nothing added")
            continue
        own = sorted((ZEUS / "results").glob(f"autopair-{src}-any-count*-{a.reader}.json"))
        if len(own) != 1:
            sys.exit(f"{src}: {len(own)} pairings by {a.reader}, want 1")
        base_file = next(f for f in (ZEUS / "results" / f"autopair-{src}-{r}.json" for r in pairing.RESULTS
                                     if not r.startswith("plus-")) if f.exists())
        base, new = json.loads(base_file.read_text()), json.loads(own[0].read_text())
        have = {x["staff"] for x in base["kept"]}
        held = {(x["part"], json.dumps(b)) for x in base["kept"] for b in x["bars"]}
        added, why = [], {"trained on": 0, "bars held": 0}
        for x in new["kept"]:
            if x["staff"] in have:
                continue
            if f"{src}/{x['staff']}" in seen:
                why["trained on"] += 1
            elif any((x["part"], json.dumps(b)) in held for b in x["bars"]):
                why["bars held"] += 1
            else:
                added.append(dict(x, reader=a.reader))
        gone = {x["staff"] for x in added}
        out = dict(base, kept=base["kept"] + added, **{"not kept": [x for x in base.get("not kept", []) if x["staff"] not in gone]},
                   added={"reader": a.reader, "from": base_file.name, "staves": len(added), "left out": why})
        (ZEUS / "results" / f"autopair-{src}-plus-{a.tag}.json").write_text(json.dumps(out, indent=1))
        print(f"{src}: {len(base['kept'])} kept, {len(added)} added by {a.tag} "
              f"({why['trained on']} trained on, {why['bars held']} with bars already held left out)")


if __name__ == "__main__":
    main()
