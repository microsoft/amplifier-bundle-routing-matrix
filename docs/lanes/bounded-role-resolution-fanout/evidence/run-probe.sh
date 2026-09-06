#!/usr/bin/env bash
# usage: run-probe.sh <label> <concurrent_rounds_of_5> <sequential_count>
LABEL=${1:?label}; ROUNDS=${2:-2}; SEQ=${3:-6}
cd /root/work || exit 1
OUT=/root/work/out-$LABEL
rm -rf "$OUT"; mkdir -p "$OUT"
echo "== $LABEL: ${ROUNDS} rounds x 5 concurrent, then ${SEQ} sequential =="
for R in $(seq 1 "$ROUNDS"); do
  for i in 1 2 3 4 5; do
    (
      PYTHONFAULTHANDLER=1 amplifier tool invoke recipes operation=execute \
        recipe_path=/root/work/probe-min.yaml \
        context="{\"marker\": \"${LABEL}r${R}c$i\"}" \
        -b recipes -o json > "$OUT/c-r${R}c$i.out" 2> "$OUT/c-r${R}c$i.err"
      echo $? > "$OUT/c-r${R}c$i.rc"
    ) &
  done
  wait
  echo "  concurrent round $R done"
done
for i in $(seq 1 "$SEQ"); do
  PYTHONFAULTHANDLER=1 amplifier tool invoke recipes operation=execute \
    recipe_path=/root/work/probe-min.yaml \
    context="{\"marker\": \"${LABEL}s$i\"}" \
    -b recipes -o json > "$OUT/s-$i.out" 2> "$OUT/s-$i.rc.err"
  echo $? > "$OUT/s-$i.rc"
  echo "  sequential $i done (rc $(cat "$OUT/s-$i.rc"))"
done
echo "== $LABEL finished =="
