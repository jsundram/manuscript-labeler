#!/bin/zsh
# Pair the Madrid Op. 22 copies with Zeus J and with the MuSViT reader; keep the staves both pair with the same bars.
set -u
LAB=/Users/jsundram/Dropbox/Code/manuscript-labeler; E=~/Dropbox/Code/boccherini-opus-48; L=~/Dropbox/Code/boccherini-quartet-data/lilypond
J=~/.cache/manuscript-labeler/models/zeus/sweep/J-lr1e5-e8.model; M=musvit-C4-bocch-tf8-L-best
typeset -A Q; Q=(Op22-1-EMc Op22-1 Op22-2-EMc Op22-2 Op22-3-EMc Op22-3 Op22-4-EMc Op22-4 Op22-6-EMc Op22-6)
cd $LAB
uv run experiments/musvit/read_auto.py --run C4-bocch-tf8-L --file best.pt ${(k)Q} 2>&1 | grep -E "Traceback|Error" && { echo "FAILED reading"; exit 1; }
cd $LAB/experiments/zeus
for s q in ${(kv)Q}; do
  for model in $J /nonexistent/$M; do
    uv run autopair.py $E --source $s --philhar $L --quartets $q --any-count --model $model > /dev/null 2>&1 || echo "FAILED $s $(basename $model)"
  done
done
python3 - <<EOF
import json
from pathlib import Path
R = Path("$LAB/experiments/zeus/results")
for s in "${(k)Q}".split():
    j = json.loads((R / f"autopair-{s}-any-count-J-lr1e5-e8.json").read_text())
    m = json.loads((R / f"autopair-{s}-any-count-$M.json").read_text())
    mk = {k["staff"]: k for k in m["kept"]}
    both = [k for k in j["kept"] if k["staff"] in mk and mk[k["staff"]]["bars"] == k["bars"]]
    out = dict(j, kept=both, note="kept by both Zeus J and $M, with the same bars")
    (R / f"autopair-{s}-any-count-both.json").write_text(json.dumps(out, indent=1))
    print(s, "staves", j["tally"]["staves"], "| Zeus J kept", len(j["kept"]), "| MuSViT kept", len(m["kept"]), "| both", len(both),
          "| plain (usable)", sum(k["plain"] for k in both))
EOF
