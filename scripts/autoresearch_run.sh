#!/bin/bash
# Empire-AI Autoresearch nightly runner — runs BOTH targets in series
# 1. contractor_recruit (60 min)
# 2. storm_strike (60 min)
# After each, sends a Telegram digest if there's a new best.
set -e
LOG=/root/empire-v49/logs/autoresearch_cron.log
TSV1=/root/empire-v49/integrations/autoresearch/results.tsv
TSV2=/root/empire-v49/integrations/autoresearch/storm/results.tsv
DIR1=/root/empire-v49/integrations/autoresearch
DIR2=/root/empire-v49/integrations/autoresearch/storm

log() { echo "[$(date -u +%H:%M:%S)] $*" | tee -a "$LOG"; }

run_target() {
  local dir="$1" tsv="$2" label="$3"
  log "=== $label cycle ==="
  cd "$dir" || return 1
  # 1 hour budget for the agent's experimentation
  timeout 3000 python3 train.py 2>&1 | tee -a "$LOG"
  # Send the digest
  python3 <<PY
import os, json
data = open("/root/.env").read()
for m in __import__("re").finditer(r'^([A-Z_][A-Z0-9_]*)="(.*?)"(?=\n[A-Z_]|\n#|\n\n|\$)', data, __import__("re").MULTILINE | __import__("re").DOTALL):
    os.environ[m.group(1)] = m.group(2)

import urllib.request
TSV = "$tsv"
LABEL = "$label"
if not os.path.exists(TSV):
    print("no results.tsv")
    raise SystemExit
with open(TSV) as f:
    lines = [l.strip() for l in f if l.strip() and not l.startswith("timestamp")]
if not lines:
    raise SystemExit

last_kept = None
for line in lines:
    parts = line.split("\t")
    if len(parts) >= 9 and parts[8] == "yes":
        last_kept = {
            "ts": parts[0], "body": parts[1], "length": parts[2],
            "spam": parts[3], "tcpa": parts[4], "length_pen": parts[5],
            "reply": parts[6], "weighted": parts[7],
            "note": parts[9] if len(parts) > 9 else "",
        }
if not last_kept:
    raise SystemExit

prev = None
seen_first = False
for line in lines:
    parts = line.split("\t")
    if len(parts) >= 9 and parts[8] == "yes":
        if last_kept["ts"] == parts[0]:
            if seen_first:
                prev = {"body": parts[1], "weighted": parts[7], "note": parts[9] if len(parts) > 9 else ""}
                break
            seen_first = True

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_HOME_CHANNEL", "808657420")
if not TG_TOKEN:
    raise SystemExit

improvement = ""
if prev:
    improvement = f"\nPrevious: {prev['weighted']} ({prev.get('note','')[:40]})"

msg = (
    f"🤖 *Autoresearch · {LABEL}*\n"
    f"weighted: *{last_kept['weighted']}* ({last_kept['note'][:60]}){improvement}\n\n"
    f"*Body:*\n"
    f"```\n{last_kept['body']}\n```\n"
    f"\nlen: {last_kept['length']} | spam: {last_kept['spam']} | tcpa: {last_kept['tcpa']} | reply: {last_kept['reply']}%\n\n"
    f"Reply *deploy* to ship, *skip* to keep old."
)
payload = json.dumps({"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown",
                     "disable_web_page_preview": True}).encode()
req = urllib.request.Request(
    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
    data=payload, method="POST",
    headers={"Content-Type": "application/json"},
)
try:
    urllib.request.urlopen(req, timeout=10).read()
    print("telegram sent")
except Exception as e:
    print(f"telegram error: {e}")
PY
}

log "autoresearch nightly start"
run_target "$DIR1" "$TSV1" "contractor_recruit"
run_target "$DIR2" "$TSV2" "storm_strike"
log "done"
