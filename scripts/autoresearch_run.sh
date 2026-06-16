#!/bin/bash
# Empire-AI Autoresearch nightly runner
# Runs train.py (the autoresearch agent's editable body builder),
# then sends a Telegram digest if there's a new best.
set -e
HANDLER_DIR=/root/empire-v49/integrations/autoresearch
LOG=/root/empire-v49/logs/autoresearch.log
TSV="$HANDLER_DIR/results.tsv"

cd "$HANDLER_DIR"

# Run the autoresearch training script (1 hour budget)
echo "[$(date -u +%H:%M:%S)] starting autoresearch cycle..."
timeout 3000 python3 train.py 2>&1 | tee -a "$LOG"

# Read the last kept=yes row (the current best)
python3 <<'PY'
import os, json
data = open("/root/.env").read()
for m in __import__("re").finditer(r'^([A-Z_][A-Z0-9_]*)="(.*?)"(?=\n[A-Z_]|\n#|\n\n|$)', data, __import__("re").MULTILINE | __import__("re").DOTALL):
    os.environ[m.group(1)] = m.group(2)

import urllib.request
TSV = "/root/empire-v49/integrations/autoresearch/results.tsv"
if not os.path.exists(TSV):
    print("no results.tsv")
    raise SystemExit

with open(TSV) as f:
    lines = [l.strip() for l in f if l.strip() and not l.startswith("timestamp")]
if not lines:
    print("empty results")
    raise SystemExit

# Find the most recent kept=yes
last_kept = None
for line in lines:
    parts = line.split("\t")
    if len(parts) >= 9 and parts[8] == "yes":
        last_kept = {
            "timestamp": parts[0],
            "body":      parts[1],
            "length":    parts[2],
            "spam":      parts[3],
            "tcpa":      parts[4],
            "length_pen": parts[5],
            "reply":     parts[6],
            "weighted":  parts[7],
            "note":      parts[9] if len(parts) > 9 else "",
        }
if not last_kept:
    print("no kept=yes rows")
    raise SystemExit

# Find the previous kept=yes (the one before this)
prev_kept = None
seen_first = False
for line in lines:
    parts = line.split("\t")
    if len(parts) >= 9 and parts[8] == "yes":
        if last_kept["timestamp"] == parts[0]:
            if seen_first:
                prev_kept = {
                    "body":      parts[1],
                    "weighted":  parts[7],
                    "note":      parts[9] if len(parts) > 9 else "",
                }
                break
            seen_first = True

# Send Telegram digest
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_HOME_CHANNEL", "808657420")
if not TG_TOKEN:
    print("no TG token")
    raise SystemExit

improvement = ""
if prev_kept:
    improvement = f"\nPrevious best: {prev_kept['weighted']} ({prev_kept.get('note','')[:40]})"

msg = (
    f"🤖 *Autoresearch nightly cycle*\n"
    f"\n"
    f"weighted: *{last_kept['weighted']}* ({last_kept['note'][:60]}){improvement}\n"
    f"\n"
    f"*Body:*\n"
    f"```\n{last_kept['body']}\n```\n"
    f"\n"
    f"length: {last_kept['length']} | spam: {last_kept['spam']} | tcpa: {last_kept['tcpa']} | length_pen: {last_kept['length_pen']} | reply: {last_kept['reply']}%\n"
    f"\n"
    f"Reply *deploy* to ship this body, *skip* to keep the old one."
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

echo "[$(date -u +%H:%M:%S)] done"
