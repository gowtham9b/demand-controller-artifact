#!/bin/bash
# launchd entry point for the Pilot 2b pipeline (launchctl submit keeps it alive, so a
# killed pipeline restarts and resumes). Removes containers orphaned by a killed run.
# Stop with: launchctl remove dc-pilot2b
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin" HOME="/Users/gowtham"
PILOT="$(cd "$(dirname "$0")" && pwd)"
cd "$PILOT" || exit 1
export REQUESTS_CA_BUNDLE="$PILOT/certs/host-ca.pem" SSL_CERT_FILE="$PILOT/certs/host-ca.pem" CURL_CA_BUNDLE="$PILOT/certs/host-ca.pem"
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] supervisor: $*" >> orchestrate2b.log; }

if [ -f pilot2b_done ] || [ "$(cat pilot2b_failures 2>/dev/null || echo 0)" -ge 3 ]; then
  exec sleep 31536000
fi
log "start (pid $$)"
for c in $(docker ps -a --format '{{.Names}}' | grep -E '^(sweb\.eval\..*\.pilot2b|dcpilot2-|dcvalid-)'); do
  log "removing orphaned container $c"; docker rm -f "$c" >/dev/null
done
./orchestrate2b.sh >> orchestrate2b.log 2>&1
rc=$?
if [ $rc -eq 0 ]; then
  touch pilot2b_done; log "pipeline finished"
elif [ $rc -eq 1 ]; then
  echo $(( $(cat pilot2b_failures 2>/dev/null || echo 0) + 1 )) > pilot2b_failures; log "pipeline failed (exit 1)"
else
  log "pipeline exited with $rc (killed?); launchd will restart it"
fi
exit $rc
