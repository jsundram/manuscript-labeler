#!/bin/bash
# ov.sh PAGE CENTER PREFIX : pitch overlays of one system in 3 segments
cd "$(dirname "$0")/hi"
p=$1; c=$2; o=$3; k=1
for x in 330 1560 2790; do
  uv run --quiet ../heads.py $p.png $c $x $((x+1340)) $o-$k.png > $o-$k.txt; k=$((k+1)); done
