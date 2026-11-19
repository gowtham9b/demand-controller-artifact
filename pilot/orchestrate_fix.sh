#!/bin/bash
# Correction run (see PREREGISTRATION.md, amendment 2026-11-12). Skips finished work.
set -uo pipefail
PILOT="$(cd "$(dirname "$0")" && pwd)"
HARNESS="$PILOT/../harness"
GOLD="$HARNESS/logs/run_evaluation/pilot/gold"
MODEL="claude-sonnet-5-5-medium"
WORKERS=3
export SWEF_FORCE_X86=1 SWEF_MEM_LIMIT=2500m SWEF_MEM_RESERVATION=1g SWEF_EXTRA_CA="$PILOT/certs/host-ca.pem"
log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "clearing every gold task whose timing failed (bug 1), so it is rescored"
for d in "$GOLD"/*/; do
  [ -f "$d/perf_summary.txt" ] || { log "clear $(basename "$d")"; rm -rf "$d"; }
done

log "rescoring the sampled tasks first ($WORKERS workers)"
regex="^($(paste -sd'|' "$PILOT/tasks_initial.txt"))$"
(cd "$HARNESS" && .venv/bin/swefficiency eval --run_id pilot --num_workers $WORKERS --instances_regex "$regex" 2>&1 | grep -v httpx | tail -3)

log "applying the replacement rule (fixed)"
(cd "$PILOT" && ../.venv-agent/bin/python finalize_tasks.py 2>&1 | grep -v httpx | tail -40)

log "agent runs for tasks not yet run"
(cd "$PILOT" && ../.venv-agent/bin/python cursor_runner.py --model "$MODEL" --tasks tasks_final.txt --workers $WORKERS 2>&1 | grep -v -E "mini-swe-agent|migration|Loading global|Support/mini")

log "union of all tasks with complete runs, for the secondary analysis"
(cd "$PILOT" && cat tasks_final.txt tasks_buggy_set.txt | sort -u > tasks_all_run.txt)
for c in C0 C1 C2; do
  (cd "$PILOT" && ../.venv-agent/bin/python cursor_runner.py --model "$MODEL" --tasks tasks_all_run.txt --conditions $c --workers 1 >/dev/null 2>&1)
  log "scoring $c"
  (cd "$HARNESS" && .venv/bin/swefficiency eval --run_id pilot --num_workers $WORKERS \
     --prediction_path "$PILOT/predictions_$c.jsonl" 2>&1 | grep -v httpx | tail -3)
  (cd "$HARNESS" && .venv/bin/swefficiency report --gold_run logs/run_evaluation/pilot/gold \
     --pred_run "logs/run_evaluation/pilot/pilot_$c" 2>&1 | tail -2)
done

log "analysis: primary (corrected pre-registered set) and secondary (all complete tasks)"
(cd "$PILOT" && DC_TASKS=tasks_final.txt DC_RESULTS=results ../.venv-agent/bin/python analyze.py > results_primary.log 2>&1; tail -30 results_primary.log)
(cd "$PILOT" && DC_TASKS=tasks_all_run.txt DC_RESULTS=results_all ../.venv-agent/bin/python analyze.py > results_all.log 2>&1; tail -5 results_all.log)
log "done"
