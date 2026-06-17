#!/bin/bash
# Empire-AI Autoresearch nightly runner — runs 4 targets in series
# 1. contractor_recruit (60 min)
# 2. storm_strike (60 min)
# 3. buyer (60 min)
# 4. email_subject (60 min)
# After each, sends a Telegram digest if there's a new best.
set -e
LOG=/root/empire-v49/logs/autoresearch_cron.log
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
    raise SystemExit
with open(TSV) as f:
    lines = [l.strip() for l in f if l.strip() and not l.startswith("timestamp")]
if not lines:
    raise SystemExit

last_kept = None
for line in lines:
    parts = line.split("\t")
    # accept any "yes" in the kept position
    for i, p in enumerate(parts):
        if p == "yes":
            last_kept = parts
            break
    if last_kept:
        break
if not last_kept:
    raise SystemExit

# Format: depends on target type
if LABEL == "contractor_recruit":
    body, weighted, prev_w, note = last_kept[1], float(last_kept[8]), "n/a", last_kept[10] if len(last_kept) > 10 else ""
    msg = (
        f"🤖 *Autoresearch · {LABEL}*\nweighted: *{weighted}*\n\n"
        f"*Body:*\n```\n{body[:280]}\n```\n\n"
        f"Reply *deploy* to ship, *skip* to keep old."
    )
elif LABEL == "storm_strike":
    body, weighted = last_kept[1], float(last_kept[8])
    msg = (
        f"🤖 *Autoresearch · {LABEL}*\nweighted: *{weighted}*\n\n"
        f"*Storm touch-0 body:*\n```\n{body[:280]}\n```\n\n"
        f"Reply *deploy* to ship, *skip* to keep old."
    )
elif LABEL == "buyer":
    subject, body, weighted = last_kept[1], last_kept[2], float(last_kept[10])
    msg = (
        f"🤖 *Autoresearch · {LABEL}*\nweighted: *{weighted}*\n\n"
        f"*Subject:* {subject}\n\n"
        f"*Body (preview):*\n```\n{body[:280]}\n```\n\n"
        f"Reply *deploy* to ship, *skip* to keep old."
    )
elif LABEL == "email_subject":
    subject, weighted = last_kept[1], float(last_kept[10])
    msg = (
        f"🤖 *Autoresearch · {LABEL}*\nweighted: *{weighted}*\n\n"
        f"*Subject:* {subject}\n\n"
        f"Reply *deploy* to ship, *skip* to keep old."
    )
else:
    msg = f"🤖 *Autoresearch · {LABEL}*\nweighted: {last_kept[1]}"

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_HOME_CHANNEL", "808657420")
if not TG_TOKEN:
    raise SystemExit

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
run_target "$DIR1" "$DIR1/results.tsv" "contractor_recruit"
run_target "$DIR2" "$DIR2/results.tsv" "storm_strike"
run_target "$DIR3" "$DIR3/results.tsv" "buyer"
run_target "$DIR4" "$DIR4/results.tsv" "email_subject"
log "done"
