#!/bin/bash
# Pilot 2 pipeline (see PREREGISTRATION.md, "Pilot 2"). Resumable: each step skips finished work.
set -uo pipefail
PILOT="$(cd "$(dirname "$0")" && pwd)"
APY="$PILOT/../.venv-agent/bin/python"
HPY="$PILOT/../harness/.venv/bin/python"
MODEL="claude-sonnet-5-5-medium"
export DC_RUN_NAME=pilot2 DC_RUNS_DIR=runs_cursor2 DC_PRED_PREFIX=predictions2 DC_RESULTS=results2 HF_HUB_OFFLINE=1
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*"; }
cd "$PILOT" || exit 1

# Docker Desktop's Resource Saver stops the VM when no container runs; on restart the
# user's restart=always containers come back. Keep one idle container running, and
# re-stop those containers (user-approved for the pilot) if a VM restart revives them.
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

if [ ! -f tasks2_final.txt ]; then
  log "gold scoring under run id pilot2, baseline (empty patch) runs, amended replacement rule (baseline-passing required tests + >= 1.05x)"
  "$HPY" finalize2_tasks.py 2>&1 | grep --line-buffered -v -E "httpx|datasets|WARNING" || exit 1
  [ -f tasks2_final.txt ] || { log "replacement rule did not finish"; exit 1; }
fi
log "final set: $(wc -l < tasks2_final.txt) tasks"

if [ ! -f results2/profiler_validation.json ] || ! "$APY" -c "import json,sys; sys.exit(0 if all(r['ok'] for r in json.load(open('results2/profiler_validation.json'))) else 1)"; then
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
"$APY" analyze2.py > results2.log 2>&1; tail -60 results2.log
log "done"
