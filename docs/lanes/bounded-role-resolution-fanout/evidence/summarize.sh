#!/usr/bin/env bash
LABEL=${1:?label}
OUT=/root/work/out-$LABEL
cn=0; ca=0; sn=0; sa=0
for f in "$OUT"/c-*.rc; do [ -e "$f" ] || continue; cn=$((cn+1)); rc=$(cat "$f"); case "$rc" in 134|139) ca=$((ca+1));; esac; done
for f in "$OUT"/s-*.rc; do [ -e "$f" ] || continue; sn=$((sn+1)); rc=$(cat "$f"); case "$rc" in 134|139) sa=$((sa+1));; esac; done
echo "LABEL=$LABEL concurrent_aborts=$ca/$cn sequential_aborts=$sa/$sn total_aborts=$((ca+sa))/$((cn+sn))"
echo "-- exit codes --"; for f in "$OUT"/*.rc; do echo "$(basename "$f" .rc)=$(cat "$f")"; done | tr '\n' ' '; echo
echo "-- fatal signatures --"
grep -l "Fatal Python error" "$OUT"/*.err 2>/dev/null | while read -r e; do
  echo "$(basename "$e"): _configure_context=$(grep -c 'truststore/_openssl.py\", line 38' "$e") wrap_bio=$(grep -c 'in wrap_bio' "$e") wrap_socket=$(grep -c 'in wrap_socket' "$e")"
done
grep -h "double free\|corruption\|Segmentation" "$OUT"/*.err 2>/dev/null | sort | uniq -c
