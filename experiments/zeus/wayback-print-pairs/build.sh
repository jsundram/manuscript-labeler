#!/bin/zsh
# Pair and build: autopair.py (musvit-D4's reading) and dataset.py for every source in sources.txt.
# Group W (Philhar's other works) -> dataW, group P (the print's agreed bars, G. 223) -> dataP.
#   zsh experiments/zeus/wayback-print-pairs/build.sh pair|data [SOURCE ...]   (default: every source)
set -u
LAB=/Users/jsundram/Dropbox/Code/manuscript-labeler; Z=$LAB/experiments/zeus; W=$Z/wayback-print-pairs
E=~/Dropbox/Code/boccherini-opus-48; L=~/Data/manuscript-labeler/philhar-site/lily
PRINT=$LAB/experiments/print-omr/G223/BA2676-G223.json
FLAGS=(--any-count --neighbours --neighbours-paired --short-ends --long-ends --head-box)
SUFFIX=-any-count-neighbours-paired-short-ends-long-ends-head-box-musvit-D3S-h96
# F-Po RES-507 (10), Boccherini's autograph parts, draws clef and key only on a movement's or section's first staff
# so does the Giardini duet's copyist
typeset -A EXTRA; EXTRA[G223-RES507-10]="--heads-only"; EXTRA[unknown_IMSLP-PMLP122408]="--heads-only"
step=$1; shift
cd $Z
grep -v '^#' $W/sources.txt | while read g s pages q pdf; do
  [ $# -gt 0 ] && [[ ${@[(Ie)$s]} -eq 0 ]] && continue
  [ -f answers/$s-auto-musvit-D3S-h96.json ] || { echo "$s: not read"; continue; }
  py=(env UV_PYTHON_INSTALL_DIR=$HOME/.cache/manuscript-labeler/zeus/py uv run --python-preference only-managed)
  if [ $step = pair ]; then
    if [ $g = W ]; then enc=(--philhar $L --quartets $q); else enc=(--print-bars $PRINT); fi
    $py autopair.py $E --source $s $enc --model /nonexistent/musvit-D3S-h96 $FLAGS < /dev/null > $W/logs/autopair-$s.log 2>&1 \
      && echo "$s: $(grep -A3 '"tally"' $W/logs/autopair-$s.log | tr -d '\n ' )" || { echo "FAILED $s"; tail -3 $W/logs/autopair-$s.log; }
  else
    drop=(); [ -f $W/drop/$s.txt ] && drop=(--drop $W/drop/$s.txt)
    if [ $g = W ]; then
      args=(--philhar $L --quartets $q --clef-checks --max-unlike 0.5 --min-pitch 0.5 ${=EXTRA[$s]:-}); out=~/.cache/manuscript-labeler/zeus/dataW
    else
      args=(--print-bars $PRINT --max-unlike 0.5 --min-pitch 0.5 --min-bar-pitch 0.5 --cut-agreed 3 ${=EXTRA[$s]:-})
      out=~/.cache/manuscript-labeler/zeus/dataP
    fi
    $py dataset.py $E --pairs $s --results results/autopair-$s$SUFFIX.json $args $drop --out $out < /dev/null > $W/logs/dataset-$s.log 2>&1 \
      && grep "staves kept" $W/logs/dataset-$s.log || { echo "FAILED $s"; tail -3 $W/logs/dataset-$s.log; }
  fi
done
