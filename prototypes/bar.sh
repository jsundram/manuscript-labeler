#!/bin/bash
# bar.sh PAGE CENTER X0 X1 OUT : labelled zoom over pitch overlay, plus head list
cd "$(dirname "$0")/hi"
uv run --quiet ../heads.py $1.png $2 $3 $4 _h.png | awk -v c=$2 '{gsub("x=","");gsub("y=","")} $2>c-75 && $2<c+75 {printf "%s:%s ", $1,$3}'; echo
uv run --quiet ../zoom.py $1.png $2 $3 $4 _z.png 2.0 >/dev/null
magick _z.png \( _h.png -resize "$(magick identify -format %w _z.png)x" \) -append $5
