#!/bin/zsh
# Build dataM2 from the re-pairings: one staff list per source (sources.txt), every check on. A source already
# in dataM or dataT takes both.py's results (D4's and C4's pairings agree); a new one, D4's.
#   zsh experiments/zeus/philhar-repair/build.sh [SOURCE ...]    (default: every source in sources.txt)
set -u
LAB=/Users/jsundram/Dropbox/Code/manuscript-labeler; Z=$LAB/experiments/zeus
E=~/Dropbox/Code/boccherini-opus-48; L=~/Dropbox/Code/boccherini-quartet-data/lilypond
OUT=~/.cache/manuscript-labeler/zeus/dataM2; SUFFIX=-any-count-neighbours-paired-short-ends-long-ends-musvit-D3S-h96
cd $Z
grep -v '^#' $Z/philhar-repair/sources.txt | while read s q before; do
  # a source in musvit-D4's training (dataM's, dataT's): the staves D4's and C4's pairings agree on (both.py);
  # the full scores detected afresh (-score) had 43 staves in dataM, and are taken as new
  res=results/autopair-$s$SUFFIX.json; [[ "$before" != "-" && $s != *-score ]] && res=results/autopair-$s-both.json
  [ $# -gt 0 ] && [[ ${@[(Ie)$s]} -eq 0 ]] && continue
  drop=(); [ -f $Z/philhar-repair/drop/$s.txt ] && drop=(--drop $Z/philhar-repair/drop/$s.txt)
  UV_PYTHON_INSTALL_DIR=~/.cache/manuscript-labeler/zeus/py uv run --python-preference only-managed dataset.py $E \
    --pairs $s --philhar $L --quartets $q --results $res \
    --clef-checks --max-unlike 0.5 --min-pitch 0.5 $drop --out $OUT > $Z/philhar-repair/logs/dataset-$s.log 2>&1 \
    && grep "staves kept" $Z/philhar-repair/logs/dataset-$s.log || { echo "FAILED $s"; tail -3 $Z/philhar-repair/logs/dataset-$s.log; }
done
