#!/bin/bash
# Empire-AI Autoresearch nightly runner — runs 4 targets in series
# 1. contractor_recruit (60 min)
# 2. storm_strike (60 min)
# 3. buyer (60 min)
# 4. email_subject (60 min)
# After each, sends a Telegram digest via autoresearch_digest.py
# (separate process to avoid bash heredoc + f-string conflicts).
set -e
LOG=/root/empire-v49/logs/autoresearch_cron.log
DIGEST=/root/empire-v49/scripts/autoresearch_digest.py
DIR1=/root/empire-v49/integrations/autoresearch
DIR2=/root/empire-v49/integrations/autoresearch/storm
DIR3=/root/empire-v49/integrations/autoresearch/buyer
DIR4=/root/empire-v49/integrations/autoresearch/email_subject

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

run_target() {
  local dir="$1" tsv="$2" label="$3"
  log "=== $label cycle ==="
  cd "$dir" || return 1
  # 1 hour budget for the agent's experimentation
  timeout 3000 python3 train.py 2>&1 | tee -a "$LOG"
  # Send the digest (separate process; no bash heredoc)
  python3 "$DIGEST" "$tsv" "$label" 2>&1 | tee -a "$LOG" || true
}

log "autoresearch nightly start"
run_target "$DIR1" "$DIR1/results.tsv" "contractor_recruit"
run_target "$DIR2" "$DIR2/results.tsv" "storm_strike"
run_target "$DIR3" "$DIR3/results.tsv" "buyer"
run_target "$DIR4" "$DIR4/results.tsv" "email_subject"
log "done"
