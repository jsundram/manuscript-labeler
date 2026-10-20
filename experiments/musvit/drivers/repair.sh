#!/bin/zsh
# Re-pair every source with a MuSViT reader: read its detected staves on Modal, then autopair.
# Prints one line per source (staves, kept) and a total; failures as FAILED <source>.
set -u
S=/private/tmp/claude-501/-Users-jsundram-Dropbox-Code-manuscript-labeler/cc978c64-0de2-421a-becf-f422917c9c34/scratchpad
RUN=C4-bocch-tf8-L; FILE=best.pt; NAME=musvit-$RUN-best
LAB=/Users/jsundram/Dropbox/Code/manuscript-labeler
E=~/Dropbox/Code/boccherini-opus-48; L=~/Dropbox/Code/boccherini-quartet-data/lilypond
SOURCES=(D-B_KHM-602 F-Pn_RES-507-2 F-Pn_Vma-ms-1067-1 F-Po_RES-507-14 Op02-2-G160 Op02-3-G161 Op02-4-CZ-Pu-va Op02-4-CZ-Pu-vc Op02-4-CZ-Pu-vn1 Op02-4-CZ-Pu-vn2 Op02-4-G162 Op02-5-G163 Op02-6-G164 Op22-1-G183 Op22-2-G184 Op22-3-G185 Op22-4-G186 Op22-5-G187 Op22-6-G188 Op22-6-Vmbr153-va Op22-6-Vmbr153-vc Op22-6-Vmbr153-vn1 Op22-6-Vmbr153-vn2 Op22-Paris-va Op22-Paris-vc Op22-Paris-vn1 Op22-Paris-vn2 Op32-G201-206 Op33-1-G207 Op33-2-G208 Op33-3-G209 Op33-4-G210 Op33-5-G211 Op33-6-G212)

quartets() {  # the Philhar quartets a source holds, in order; empty for a labelled Op. 48 source
  case $1 in
    D-B_KHM-602|F-Pn_Vma-ms-1067-1|F-Po_RES-507-14) echo "";;
    F-Pn_RES-507-2) echo "Op33-1,Op33-2,Op33-3,Op33-4,Op33-5,Op33-6";;
    Op02-4-CZ-Pu-*) echo "Op02-4";;
    Op02-?-G*) echo "${1[1,6]}";;
    Op22-6-Vmbr153-*) echo "Op22-6";;
    Op22-Paris-*) echo "Op22-4,Op22-2,Op22-6,Op22-3";;
    Op22-?-G*) echo "${1[1,6]}";;
    Op32-G201-206) echo "Op32-1,Op32-2,Op32-3,Op32-4,Op32-5,Op32-6";;
    Op33-?-G*) echo "${1[1,6]}";;
  esac
}

cd $LAB
# one reader process (Modal refuses several apps created at once); sources already read are skipped
out=$(uv run experiments/musvit/read_auto.py --run $RUN --file $FILE $SOURCES 2>&1)
if echo "$out" | grep -q Traceback; then echo "FAILED reading"; echo "$out" | grep -A3 Traceback | tail -4; touch $S/repair.failed; exit 1; fi
for s in $SOURCES; do q=$(quartets $s); echo "$s ${q:--}"; done | xargs -P 6 -L 1 zsh $S/pair1.sh > $S/repair-pair.txt
grep FAILED $S/repair-pair.txt && touch $S/repair.failed
python3 - > $S/repair-summary.txt <<EOF
import json
from pathlib import Path
R = Path("$LAB/experiments/zeus/results")
tot = {"new": [0, 0, 0], "old": [0, 0, 0]}
for s in "${SOURCES[*]} Op02-1-G159".split():
    row = []
    for tag, f in (("new", f"autopair-{s}-any-count-$NAME.json"), ("old", f"autopair-{s}-any-count-F-lr1e5-e8.json")):
        p = R / f
        if not p.exists():
            row.append(f"{tag} -"); continue
        t = json.loads(p.read_text())["tally"]
        k = t.get("staves kept", 0); wrong = t.get("kept, wrong", 0); st = t.get("staves", 0)
        tot[tag][0] += st; tot[tag][1] += k; tot[tag][2] += wrong
        row.append(f"{tag} {k}/{st}" + (f" ({wrong} wrong)" if "kept, wrong" in t else ""))
    print(s, " | ".join(row))
print("TOTAL new kept", tot["new"][1], "of", tot["new"][0], "wrong", tot["new"][2], "| old kept", tot["old"][1], "of", tot["old"][0], "wrong", tot["old"][2])
EOF
cat $S/repair-summary.txt
[ -f $S/repair.failed ] || touch $S/repair.done
