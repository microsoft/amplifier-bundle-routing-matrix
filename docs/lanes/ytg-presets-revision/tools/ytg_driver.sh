#!/usr/bin/env bash
# S1+S3 per-ARM run driver for the ytg-presets-revision lane.
#
# Derived from 161's preset_driver.sh (S3, proven) + 20260901-threeknob's
# cell_driver_oai.sh (S1, proven). Changes, all deliberate:
#   1. Handles BOTH scenarios -- the S1 half is the clause 161 could not buy.
#   2. Re-asserts and re-verifies the arm before EVERY run (V2), so a container
#      that silently reverted cannot contaminate a later run.
#   3. Pushes THIS TREE's new matrix into the container's routing dir and
#      records the md5 of openai.yaml / anthropic.yaml as the container sees
#      them, so "the shipped matrix" in a control arm is a checked fact.
#
# Usage: ytg_driver.sh <dtu> <arm> <matrix|SHIPPED:name> <rprov> <rmodel> <reffort|NONE> <s1_n> <s3_n>
set -u
DTU="$1"; ARM="$2"; MATRIX="$3"; RPROV="$4"; RMODEL="$5"; REFFORT="$6"; S1_N="$7"; S3_N="$8"

CAP="/home/bkrabach/dev/openai-evals-team-ci/.amplifier/evaluation/treatment-validation/20260902-ytg-presets-revision"
WS="/home/bkrabach/dev/openai-evals-team-ci"
S1_CAP="${S1_CAP:-2400}"; S3_CAP="${S3_CAP:-2400}"
# Run-number offsets, so a later batch appends instead of overwriting run 01.
S1_START="${S1_START:-1}"; S3_START="${S3_START:-1}"

CDIR="$CAP/runs/$ARM"; mkdir -p "$CDIR"
RUNLOG="$CDIR/RUNLOG.jsonl"; LOG="$CDIR/driver.log"
log(){ echo "$(date -Is) $*" >>"$LOG"; }

adt(){ amplifier-digital-twin "$@"; }
jout(){ python3 -c "import sys,json;d=json.load(sys.stdin);sys.stdout.write(d.get('stdout',''))" 2>/dev/null; }
exec_c(){ adt exec "$DTU" -- bash -lc "$1" 2>/dev/null | jout; }

reset_container(){
  exec_c 'pkill -f "[a]mplifier run" 2>/dev/null; sleep 2; rm -rf /root/s3-work /root/s1.out /root/s1.done /root/.amplifier/projects/*/sessions/* 2>/dev/null; echo RESET_OK' >/dev/null
}
verify_reset(){
  local n; n="$(exec_c 'find /root/.amplifier/projects -maxdepth 3 -type d -path "*/sessions/*" 2>/dev/null | wc -l' | tr -d ' \n')"
  [ "$n" = "0" ]
}

measure_run(){   # <scenario> <nn> <outdir> <prefer_sid>  -> prints mfile path
  local scn="$1" nn="$2" OUT="$3" prefer="$4"
  mkdir -p "$OUT/all-sessions"
  # Retry the pull: 161 lost a whole run (2,404 s of real spend) to one silent
  # pull failure. Verify events actually landed before moving on.
  for attempt in 1 2 3; do
    adt file-pull "$DTU" /root/.amplifier/projects "$OUT/all-sessions" -r >/dev/null 2>&1
    n_ev=$(find "$OUT/all-sessions" -name events.jsonl 2>/dev/null | wc -l)
    [ "$n_ev" -gt 0 ] && break
    log "$scn $nn WARN pull attempt $attempt landed 0 events; retrying"
    sleep 10
  done
  log "$scn $nn pulled events.jsonl files: $(find "$OUT/all-sessions" -name events.jsonl 2>/dev/null | wc -l)"
  local root_sid mfile rev
  root_sid="$(python3 "$CAP/find_root.py" "$OUT/all-sessions" "$prefer" 2>/dev/null)"
  mfile="$CAP/measure/measure-${ARM}-${scn}-${nn}.json"
  python3 "$WS/probes/dw_measure.py" "$OUT/all-sessions" "$root_sid" > "$mfile" 2>/dev/null
  rev="$(find "$OUT/all-sessions" -path "*/sessions/$root_sid/events.jsonl" ! -path "*/context-intelligence/*" 2>/dev/null | head -1)"
  if [ -n "$rev" ]; then
    python3 "$CAP/wire_openai.py" "$rev" "$RMODEL" "$REFFORT" > "$OUT/wire.json" 2>/dev/null || echo '{}' > "$OUT/wire.json"
  else echo '{}' > "$OUT/wire.json"; fi
  python3 "$CAP/stalls.py" "$OUT/all-sessions" "$root_sid" > "$OUT/stalls.json" 2>/dev/null || echo '{"stalled_legs":-1}' > "$OUT/stalls.json"
  python3 "$CAP/routing_realised.py" "$OUT/all-sessions" "$RMODEL" > "$OUT/routing.json" 2>/dev/null || echo '{}' > "$OUT/routing.json"
  echo "$mfile"
}

emit(){          # <scenario> <nn> <outdir> <mfile> <completion> <score>
  python3 - "$ARM" "$1" "$2" "$4" "$3" "$5" "$6" "$MATRIX" "$RMODEL" "$REFFORT" >>"$RUNLOG" <<'PY'
import json,sys
arm,scn,nn,mfile,out,completion,score,matrix,rmodel,reffort=sys.argv[1:11]
def load(p):
    try: return json.load(open(p))
    except Exception: return {}
m=load(mfile); w=load(out+"/wire.json"); s=load(out+"/stalls.json"); r=load(out+"/routing.json")
try: hw=int(open(out+"/host_wall.txt").read().strip())
except Exception: hw=None
try: anchors=open(out+"/s1_judge.txt").read().strip()
except Exception: anchors=None
rec={"arm":arm,"scenario":scn,"run":nn,"matrix":matrix,"root_model":rmodel,"root_effort":reffort,
     "completion":completion,"score":score,"s1_anchors":anchors,
     "wall_s":m.get("wall_s"),"host_wall_s":hw,"cost_usd":m.get("cost_usd"),
     "llm_calls":m.get("llm_calls"),"tree_sessions":m.get("tree_sessions"),
     "root_delegate_calls":m.get("root_delegate_calls"),
     "cache_read_share_pct":m.get("cache_read_share_pct"),
     "models":m.get("models"),"routing_realised":r,
     "model_id_ok":w.get("model_id_ok") if isinstance(w,dict) else None,
     "effort_applied_ok":w.get("effort_applied_ok") if isinstance(w,dict) else None,
     "off_model":w.get("off_model_requests") if isinstance(w,dict) else None,
     "provider_errors":w.get("provider_errors") if isinstance(w,dict) else None,
     "stalled_legs":s.get("stalled_legs"),"root_sid":m.get("root_sid")}
print(json.dumps(rec))
PY
}

arm_ok(){
  bash "$CAP/configure_arm.sh" "$DTU" "$MATRIX" "$RPROV" "$RMODEL" "$REFFORT" 2>&1 | grep -E '^ARM_(OK|FAIL)' | head -1
}

adt file-push "$DTU" "$WS/.amplifier/evaluation/scenarios/s3" /root/ -r >/dev/null 2>&1   # -> /root/s3 (the in-container grader)

log "ARM start dtu=$DTU arm=$ARM matrix=$MATRIX root=$RPROV/$RMODEL@$REFFORT s1=$S1_N s3=$S3_N"

# ---- this tree's new matrix into the container; record what is really there --
RDIR="$(exec_c 'ls -d /root/.amplifier/cache/amplifier-bundle-routing-matrix-*/routing 2>/dev/null | head -1' | tr -d '\n')"
if [ -n "$RDIR" ]; then
  adt file-push "$DTU" "$CAP/tree-routing/openai-cheap-fast.yaml" "$RDIR/openai-cheap-fast.yaml" >/dev/null 2>&1
  exec_c "md5sum $RDIR/openai.yaml $RDIR/anthropic.yaml $RDIR/openai-cheap-fast.yaml 2>/dev/null" > "$CDIR/container-routing-md5.txt"
  exec_c "grep -c '^preset:' $RDIR/openai.yaml 2>/dev/null" > "$CDIR/container-openai-has-preset.txt"
  log "routing dir=$RDIR md5s=$(tr '\n' ' ' < "$CDIR/container-routing-md5.txt") openai_preset_lines=$(tr -d ' \n' < "$CDIR/container-openai-has-preset.txt")"
else
  log "WARN no routing dir found in container"
fi

# ---------------- S1 runs ----------------
i=0
while [ "$i" -lt "$S1_N" ]; do
  NN=$(printf "%02d" $((S1_START + i))); i=$((i+1))
  OUT="$CAP/runs/${ARM}-s1-${NN}"; mkdir -p "$OUT"
  t0=$(date +%s)
  reset_container; verify_reset || { log "s1 $NN WARN reset not clean; retry"; reset_container; }
  AL="$(arm_ok)"; echo "$AL" > "$OUT/arm_verify.txt"; log "s1 $NN $AL"
  case "$AL" in ARM_OK*) : ;; *) log "s1 $NN ABORT arm not configured"; continue ;; esac

  adt file-push "$DTU" "$CAP/s1-prompt.md" /root/s1-prompt.md >/dev/null 2>&1
  exec_c 'cd /root && rm -f s1.out s1.done && nohup bash -lc "amplifier run < /root/s1-prompt.md > /root/s1.out 2>&1; echo EXIT:\$? > /root/s1.done" >/dev/null 2>&1 & echo launched' >/dev/null
  waited=0; done=0
  while [ "$waited" -lt "$S1_CAP" ]; do
    st="$(exec_c 'if [ -f /root/s1.done ]; then echo DONE; else echo RUNNING; fi' | tr -d ' \n')"
    [ "$st" = "DONE" ] && { done=1; break; }
    sleep 20; waited=$((waited+20))
  done
  echo $(( $(date +%s) - t0 )) > "$OUT/host_wall.txt"
  completion="complete"; [ "$done" = "1" ] || { completion="bounded_cap"; log "s1 $NN CAP HIT ${S1_CAP}s"; }
  exec_c 'cat /root/s1.out 2>/dev/null' > "$OUT/final-answer.txt" 2>/dev/null
  python3 "$CAP/s1_judge.py" "$OUT/final-answer.txt" > "$OUT/s1_judge.txt" 2>/dev/null || echo "judge-failed" > "$OUT/s1_judge.txt"
  mfile="$(measure_run s1 "$NN" "$OUT" "")"
  emit s1 "$NN" "$OUT" "$mfile" "$completion" "-"
  log "s1 $NN $completion after $(cat "$OUT/host_wall.txt")s anchors=$(cat "$OUT/s1_judge.txt")"
done

# ---------------- S3 runs ----------------
i=0
while [ "$i" -lt "$S3_N" ]; do
  NN=$(printf "%02d" $((S3_START + i))); i=$((i+1))
  OUT="$CAP/runs/${ARM}-s3-${NN}"; mkdir -p "$OUT"
  t0=$(date +%s)
  reset_container; verify_reset || { log "s3 $NN WARN reset not clean; retry"; reset_container; }
  AL="$(arm_ok)"; echo "$AL" > "$OUT/arm_verify.txt"; log "s3 $NN $AL"
  case "$AL" in ARM_OK*) : ;; *) log "s3 $NN ABORT arm not configured"; continue ;; esac

  bash "$CAP/seed_and_run_s3.sh" "$DTU" "$OUT" >>"$LOG" 2>&1
  waited=0; done=0
  while [ "$waited" -lt "$S3_CAP" ]; do
    [ -f "$OUT/driver_record.json" ] && { done=1; break; }
    sleep 20; waited=$((waited+20))
  done
  echo $(( $(date +%s) - t0 )) > "$OUT/host_wall.txt"
  completion="complete"; [ "$done" = "1" ] || completion="bounded_cap"
  prefer=""
  [ -f "$OUT/driver_record.json" ] && prefer="$(python3 -c 'import json,sys;print(json.load(open(sys.argv[1])).get("root_session_id") or "")' "$OUT/driver_record.json" 2>/dev/null)"

  adt file-push "$DTU" "$OUT/transcript.txt" /root/s3-transcript.txt >/dev/null 2>&1
  exec_c 'cd /root && python3 /root/s3/grader.py --deliverables /root/s3-work --transcript /root/s3-transcript.txt --scenario-dir /root/s3 --out /root/s3-scorecard.json >/root/s3-grade.log 2>&1; echo GRADED' >/dev/null
  exec_c 'cat /root/s3-scorecard.json 2>/dev/null' > "$OUT/scorecard.json"
  score="$(python3 -c 'import json,sys
try:
  d=json.load(open(sys.argv[1])); print(d.get("total") if isinstance(d.get("total"),(int,float)) else d.get("score") or "?")
except Exception: print("?")' "$OUT/scorecard.json" 2>/dev/null)"
  mfile="$(measure_run s3 "$NN" "$OUT" "$prefer")"
  emit s3 "$NN" "$OUT" "$mfile" "$completion" "$score"
  log "s3 $NN $completion score=$score after $(cat "$OUT/host_wall.txt")s"
done

log "ARM done $ARM"
echo "ARM_DONE $ARM"
