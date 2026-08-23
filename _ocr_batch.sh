#!/bin/bash
set -e
cd /Users/luapple/Documents/AncientBooks
PY=/Users/luapple/.workbuddy/binaries/python/envs/default/bin/python3
export PYTHONPATH=.:_ocr_one.py
export ANCIENTBOOK_ROOT=/Users/luapple/Documents/AncientBooks
BOOK="《标注传习录》卷一"
QUALITY=high
DPI=200

# 20 leaves: pi*2+1 = R, pi*2+2 = L for pi=0..9
for pi in 0 1 2 3 4 5 6 7 8 9; do
  leaf_r=$(( pi*2+1 ))
  leaf_l=$(( pi*2+2 ))
  for leaf in $leaf_r $leaf_l; do
    side=R
    [ "$leaf" = "$leaf_l" ] && side=L
    $PY _ocr_one.py "$BOOK" "$leaf" "$side" "$QUALITY" "$DPI" 2>&1 | grep -v "^\[INFO\]" | grep -E "^(OK|SKIP|NO_REC|FAIL)" || echo "FAIL $leaf $side"
  done
done
echo "---DONE---"
date
