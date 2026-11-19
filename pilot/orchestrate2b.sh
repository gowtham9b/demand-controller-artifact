#!/bin/bash
# Pilot 2b pipeline: Pilot 2 replicated with a second model (see PREREGISTRATION.md,
# "Pilot 2b"). Same tasks, conditions, prompts, limits, scoring and analysis as Pilot 2;
# gold and baseline results are reused from run id pilot2. Resumable.
set -uo pipefail
PILOT="$(cd "$(dirname "$0")" && pwd)"
APY="$PILOT/../.venv-agent/bin/python"
HPY="$PILOT/../harness/.venv/bin/python"
MODEL="gpt-5.6-sol-medium"
export DC_RUN_NAME=pilot2b DC_RUNS_DIR=runs_cursor2b DC_PRED_PREFIX=predictions2b DC_RESULTS=results2b HF_HUB_OFFLINE=1
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
cd "$PILOT" || exit 1

docker start dc-keepalive >/dev/null 2>&1 || docker run -d --name dc-keepalive --memory 16m --cpuset-cpus 0 \
  --entrypoint sleep redis:7-alpine infinity >/dev/null
( while true; do
    for c in gitlab tdm-dev-process-webserver-1; do
      if [ -n "$(docker ps -q -f "name=^${c}\$")" ]; then log "watchdog: $c was running again; docker stop"; docker stop "$c" >/dev/null; fi
    done
    docker start dc-keepalive >/dev/null 2>&1
    sleep 60
  done ) &
WATCHDOG=$!
trap 'kill $WATCHDOG 2>/dev/null' EXIT

LOGS="$PILOT/../harness/logs/run_evaluation"
mkdir -p "$LOGS/pilot2b" results2b
for d in gold baseline; do
  [ -e "$LOGS/pilot2b/$d" ] || ln -s "$LOGS/pilot2/$d" "$LOGS/pilot2b/$d"
done
[ -f results2b/required_tests.json ] || cp results2/required_tests.json results2b/required_tests.json
log "final set (from Pilot 2): $(wc -l < tasks2_final.txt) tasks; model $MODEL"

if [ ! -f results2b/profiler_validation.json ] || ! "$APY" -c "import json,sys; sys.exit(0 if all(r['ok'] for r in json.load(open('results2b/profiler_validation.json'))) else 1)"; then
  log "profiler validation in every task container"
  "$APY" validate_profiler.py --workers 3 2>&1 | grep --line-buffered -v -E "mini-swe-agent|migration|Loading global|Support/mini"
  [ "${PIPESTATUS[0]}" -eq 0 ] || { log "profiler validation failed; stopping before any agent run"; exit 1; }
fi

for pass in 1 2; do
  log "agent runs, pass $pass (infra failures are retried)"
  "$APY" cursor_runner.py --model "$MODEL" --tasks tasks2_final.txt --workers 3 2>&1 \
    | grep --line-buffered -v -E "mini-swe-agent|migration|Loading global|Support/mini"
done

log "scoring (3 workers; infra failures, incl. crash-lost required tests, rescored with 1 worker, 6 GB, 2 then 1 pytest processes)"
"$HPY" score2.py 2>&1 | grep --line-buffered -v -E "httpx|datasets|WARNING"

log "analysis"
"$APY" analyze2.py > results2b.log 2>&1; tail -60 results2b.log
log "done"
