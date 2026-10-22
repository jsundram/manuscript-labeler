#!/bin/zsh
# Staff detection (autodetect.py) for every source in sources.txt, one after another.
#   zsh experiments/zeus/wayback-print-pairs/detect.sh [SOURCE ...]
set -u
LAB=/Users/jsundram/Dropbox/Code/manuscript-labeler; W=$LAB/experiments/zeus/wayback-print-pairs
E=~/Dropbox/Code/boccherini-opus-48
typeset -A EXTRA
# the KHM 600 cello part opens pp. 20, 22, 23 with the first violin's cue staff above the cello's
EXTRA[G223-KHM600]="--leave-out 20:0,22:0,23:0"
# Sibley (levelled): an oblong page holds at most 10 staves; more are fragments
EXTRA[US-R_M351.B664M]="--max-staves 12"
# Montecassino: a trio score, systems of three staves
EXTRA[I-MC_1-C-7]="--score-parts vn1,vn2,vc --score-layout 9:0-2,3-5,6-8;10:0-2,3-5,6-8|1-3,4-6,7-9;12:0-2,3-5,6-8,9-11"
grep -v '^#' $W/sources.txt | while read g s pages q pdf; do
  [ $# -gt 0 ] && [[ ${@[(Ie)$s]} -eq 0 ]] && continue
  extra=(${=EXTRA[$s]:-})
  uv run --with markdown-it-py $LAB/experiments/zeus/autodetect.py $E --pdf ${~pdf} --name $s --pages $pages $extra < /dev/null \
    > $W/logs/autodetect-$s.log 2>&1 && echo "$s: $(grep -c ' staves' $W/logs/autodetect-$s.log) pages" \
    || { echo "FAILED $s"; tail -3 $W/logs/autodetect-$s.log; }
done
