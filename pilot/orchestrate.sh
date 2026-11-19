#!/bin/bash
# End-to-end pilot pipeline. Safe to re-run: every step skips finished work.
set -uo pipefail
PILOT="$(cd "$(dirname "$0")" && pwd)"
HARNESS="$PILOT/../harness"
GOLD="$HARNESS/logs/run_evaluation/pilot/gold"
MODEL="claude-sonnet-5-5-medium"
WORKERS=3
export SWEF_FORCE_X86=1 SWEF_MEM_LIMIT=2500m SWEF_MEM_RESERVATION=1g SWEF_EXTRA_CA="$PILOT/certs/host-ca.pem"
log() { echo "[$(date '+%H:%M:%S')] $*"; }

log "clearing gold tasks whose timing failed, so they are rescored with the CA fix"
for d in "$GOLD"/*/; do
  [ -d "$d" ] || continue
  if [ ! -f "$d/perf_summary.txt" ]; then log "rescoring $(basename "$d")"; rm -rf "$d"; fi
done

log "gold scoring of the sampled tasks ($WORKERS workers; finished tasks are skipped)"
regex="^($(paste -sd'|' "$PILOT/tasks_initial.txt"))$"
(cd "$HARNESS" && .venv/bin/swefficiency eval --run_id pilot --num_workers $WORKERS --instances_regex "$regex" 2>&1 | grep -v httpx | tail -5)

log "applying the replacement rule"
(cd "$PILOT" && ../.venv-agent/bin/python finalize_tasks.py)

log "agent runs"
(cd "$PILOT" && ../.venv-agent/bin/python cursor_runner.py --model "$MODEL" --tasks tasks_final.txt --workers $WORKERS 2>&1 | grep -v -E "mini-swe-agent|migration|Loading global|Support/mini")

for c in C0 C1 C2; do
  log "scoring $c"
  (cd "$HARNESS" && .venv/bin/swefficiency eval --run_id pilot --num_workers $WORKERS \
     --prediction_path "$PILOT/predictions_$c.jsonl" 2>&1 | grep -v httpx | tail -3)
  (cd "$HARNESS" && .venv/bin/swefficiency report --gold_run logs/run_evaluation/pilot/gold \
     --pred_run "logs/run_evaluation/pilot/pilot_$c" 2>&1 | tail -3)
done

log "analysis"
(cd "$PILOT" && ../.venv-agent/bin/python analyze.py)
log "done"
