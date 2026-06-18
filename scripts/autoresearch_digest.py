#!/usr/bin/env python3
"""
EMPIRE V49 · AUTORESEARCH DIGEST
=================================
Parses the latest 'kept=yes' row from an autoresearch results.tsv
and sends a Telegram digest to the home channel. Designed to be
called from autoresearch_run.sh as a separate process (avoids
bash heredoc / f-string / brace-expansion conflicts).

Usage:
    autoresearch_digest.py <results.tsv> <label>

label ∈ {contractor_recruit, storm_strike, buyer, email_subject}
"""

import os
import re
import sys
import json
import urllib.request

TSV = sys.argv[1] if len(sys.argv) > 1 else ""
LABEL = sys.argv[2] if len(sys.argv) > 2 else ""

if not TSV or not LABEL:
    print("usage: autoresearch_digest.py <results.tsv> <label>", file=sys.stderr)
    sys.exit(2)

# load /root/.env manually (cron env doesn't always have it)
env_path = "/root/.env"
if os.path.exists(env_path):
    with open(env_path) as f:
        for m in re.finditer(
            r'^([A-Z_][A-Z0-9_]*)\s*=\s*"?([^"\n]*)"?',
            f.read(),
            re.MULTILINE,
        ):
            os.environ.setdefault(m.group(1), m.group(2))

if not os.path.exists(TSV):
    print(f"tsv not found: {TSV}", file=sys.stderr)
    sys.exit(0)

# parse kept=yes rows (newest first by timestamp)
# Backwards-compatible: old schema has 10 columns, new schema has 11+.
# weighted lives at index 7 (old) or 8 (new). kept at 8 (old) or 9 (new).
kept = []
with open(TSV) as f:
    for line in f:
        line = line.rstrip("\n")
        if not line or line.startswith("timestamp"):
            continue
        parts = line.split("\t")
        if len(parts) < 9:
            continue
        # detect schema
        if len(parts) == 10:
            kept_idx = 8
        elif len(parts) >= 11:
            kept_idx = 9
        else:
            continue
        if "yes" in parts[kept_idx]:
            kept.append(parts)

if not kept:
    print(f"no kept=yes rows in {TSV}", file=sys.stderr)
    sys.exit(0)

# use the LAST kept=yes (most recent accepted improvement)
last = kept[-1]

# detect schema for weighted index
if len(last) == 10:
    weighted_idx = 7
else:
    weighted_idx = 8

# format: depends on label
try:
    if LABEL == "contractor_recruit":
        body = last[1]
        weighted = float(last[weighted_idx])
        note = last[weighted_idx + 2] if len(last) > weighted_idx + 2 else ""
        msg = (
            f"🤖 *Autoresearch · {LABEL}*\n"
            f"weighted: *{weighted:.2f}* · note: {note}\n\n"
            f"*Body:*\n```\n{body[:280]}\n```\n\n"
            f"Reply *deploy* to ship, *skip* to keep old."
        )
    elif LABEL == "storm_strike":
        body = last[1]
        weighted = float(last[weighted_idx])
        msg = (
            f"🤖 *Autoresearch · {LABEL}*\n"
            f"weighted: *{weighted:.2f}*\n\n"
            f"*Storm touch-0 body:*\n```\n{body[:280]}\n```\n\n"
            f"Reply *deploy* to ship, *skip* to keep old."
        )
    elif LABEL == "buyer":
        subject = last[1]
        body = last[2]
        weighted = float(last[weighted_idx])
        msg = (
            f"🤖 *Autoresearch · {LABEL}*\n"
            f"weighted: *{weighted:.2f}*\n\n"
            f"*Subject:* {subject}\n\n"
            f"*Body (preview):*\n```\n{body[:280]}\n```\n\n"
            f"Reply *deploy* to ship, *skip* to keep old."
        )
    elif LABEL == "email_subject":
        subject = last[1]
        weighted = float(last[weighted_idx])
        msg = (
            f"🤖 *Autoresearch · {LABEL}*\n"
            f"weighted: *{weighted:.2f}*\n\n"
            f"*Subject:* {subject}\n\n"
            f"Reply *deploy* to ship, *skip* to keep old."
        )
    else:
        msg = f"🤖 *Autoresearch · {LABEL}*\nweighted: {last[1]}"
except (IndexError, ValueError) as e:
    print(f"parse error on {LABEL}: {e} · row={last}", file=sys.stderr)
    sys.exit(0)

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT = os.environ.get("TELEGRAM_HOME_CHANNEL", "808657420")
if not TG_TOKEN:
    print("no TELEGRAM_BOT_TOKEN", file=sys.stderr)
    sys.exit(0)

payload = json.dumps({
    "chat_id": TG_CHAT,
    "text": msg,
    "parse_mode": "Markdown",
    "disable_web_page_preview": True,
}).encode()

req = urllib.request.Request(
    f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
    data=payload,
    method="POST",
    headers={"Content-Type": "application/json"},
)
try:
    resp = urllib.request.urlopen(req, timeout=10).read()
    print(f"telegram sent ({LABEL})")
except Exception as e:
    print(f"telegram error: {e}", file=sys.stderr)
