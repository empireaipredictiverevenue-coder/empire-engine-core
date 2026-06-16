"""
Empire AI · Gmail IMAP scanner (v2 — robust)
Connects per message to avoid IMAP state issues with large folders.
"""
import os, re, sys, json, imaplib, email
from email import policy
from email.utils import parseaddr
from datetime import datetime, timezone, timedelta
from pathlib import Path
import argparse
import socket
import time

# Load .env
data = open("/root/.env").read()
for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)="(.*?)"(?=\n[A-Z_]|\n#|\n\n|$)', data, re.MULTILINE | re.DOTALL):
    os.environ[m.group(1)] = m.group(2)
for m in re.finditer(r'^([A-Z_][A-Z0-9_]*)=([^\n#"]+)$', data, re.MULTILINE):
    k = m.group(1)
    if k not in os.environ:
        os.environ[k] = m.group(2).strip()

GMAIL    = os.environ.get("GMAIL_ADDRESS", "")
APP_PW   = os.environ.get("GMAIL_APP_PASSWORD", "")
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
TG_CHAT  = os.environ.get("TELEGRAM_HOME_CHANNEL", "808657420")
SUPABASE_URL  = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY  = os.environ.get("SUPABASE_SERVICE_KEY", "")

if not GMAIL or not APP_PW:
    print("FATAL: GMAIL_ADDRESS and GMAIL_APP_PASSWORD must be in /root/.env")
    sys.exit(1)

p = argparse.ArgumentParser()
p.add_argument("--days", type=int, default=7)
p.add_argument("--dry-run", action="store_true")
args = p.parse_args()

from supabase import create_client
import urllib.request
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


def classify_reply(text):
    if not text: return "empty"
    t = text.lower().strip()
    if any(k in t for k in ["unsubscribe", "remove me", "stop contacting"]):
        return "opt_out"
    if any(k in t for k in ["wrong person", "not the right", "no longer with"]):
        return "wrong_person"
    if any(k in t for k in ["not now", "later", "not interested right now"]):
        return "not_now"
    if any(k in t for k in ["undeliverable", "mailbox full", "550", "551", "553"]):
        return "bounce"
    if any(k in t for k in ["interested", "let's talk", "schedule a call", "set up a call",
                            "sounds good", "tell me more", "demo", "happy to chat",
                            "love to learn", "would like to learn more", "i would like to learn"]):
        return "interested"
    if "?" in t or any(k in t for k in ["how do", "what is", "where can", "can you", "do you"]):
        return "question"
    return "unknown"


def tg_send(msg):
    if not TG_TOKEN: return
    try:
        payload = json.dumps({"chat_id": TG_CHAT, "text": msg, "parse_mode": "Markdown",
                              "disable_web_page_preview": True}).encode()
        req = urllib.request.Request(f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
                                     data=payload, method="POST",
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=10).read()
    except Exception:
        pass


def connect():
    """Open a fresh IMAP connection. Returns the M object or None."""
    try:
        M = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        M.login(GMAIL, APP_PW)
        return M
    except Exception as e:
        print(f"  connect failed: {e}")
        return None


def scan_folder(folder, since_date, max_msgs=50):
    """Returns list of dicts for messages that mention empire-ai."""
    print(f"  scanning {folder}...")
    M = connect()
    if not M:
        return []
    out = []
    try:
        M.select(folder, readonly=True)
    except Exception as e:
        print(f"  select {folder} failed: {e}")
        try: M.logout()
        except: pass
        return []
    try:
        typ, data = M.search(None, f'(SINCE {since_date})')
    except Exception as e:
        print(f"  search {folder} failed: {e}")
        try: M.logout()
        except: pass
        return []
    if typ != "OK" or not data or not data[0]:
        try: M.logout()
        except: pass
        return []
    ids = data[0].split()
    print(f"    {len(ids)} msgs (capping at {max_msgs})")
    for mid in ids[-max_msgs:]:
        try:
            typ, msg_data = M.fetch(mid, "(RFC822)")
            if typ != "OK" or not msg_data or not msg_data[0]:
                continue
            raw = msg_data[0][1]
            if not raw:
                continue
            msg = email.message_from_bytes(raw, policy=policy.default)
            from_h   = msg.get("From", "")
            to_h     = msg.get("To", "")
            subject  = msg.get("Subject", "")
            date_h   = msg.get("Date", "")
            msg_id   = msg.get("Message-ID", "")
            body = ""
            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body = part.get_content()
                        break
                    if part.get_content_type() == "text/html" and not body:
                        body = re.sub(r"<[^>]+>", "", part.get_content())
            else:
                body = msg.get_content()
            combined = f"{from_h} {to_h} {subject} {body[:2000]}".lower()
            if "empire-ai" not in combined and "empire ai" not in combined:
                continue
            _, from_addr = parseaddr(from_h)
            _, to_addr   = parseaddr(to_h)
            if "delivered" in (subject or "").lower() or "undelivered" in (subject or "").lower():
                continue  # skip bounce notifications
            intent = classify_reply(body)
            out.append({
                "folder": folder, "from": from_addr, "to": to_addr,
                "subject": subject, "body": body[:4000], "date": date_h,
                "msg_id": msg_id, "intent": intent,
            })
        except (imaplib.IMAP4.abort, OSError, ConnectionError, socket.error) as e:
            # Connection died mid-fetch. Reconnect and continue.
            print(f"    {mid} connection lost: {e}, reconnecting...")
            try: M.logout()
            except: pass
            M = connect()
            if not M: break
            try: M.select(folder, readonly=True)
            except: break
    try: M.logout()
    except: pass
    return out


# === MAIN ===
since_date = (datetime.now(timezone.utc) - timedelta(days=args.days)).strftime("%d-%b-%Y")
print(f"=== Gmail scan: {GMAIL}, last {args.days} days (since {since_date}) ===\n")

FOLDERS = ["INBOX", "[Gmail]/Spam", "[Gmail]/Trash", "[Gmail]/Promotions"]
all_matches = []
for folder in FOLDERS:
    found = scan_folder(folder, since_date, max_msgs=50)
    all_matches.extend(found)
    print()

# Dedup by msg_id
seen = set()
unique = []
for m in all_matches:
    key = m.get("msg_id") or (m.get("from", "") + m.get("subject", "") + m.get("date", ""))
    if key in seen: continue
    seen.add(key)
    unique.append(m)

print(f"\n=== summary: {len(unique)} unique empire-ai messages across folders ===")
by_intent = {}
for m in unique:
    by_intent.setdefault(m["intent"], []).append(m)
for intent, msgs in sorted(by_intent.items()):
    print(f"  {intent}: {len(msgs)}")

# Backfill
inserted = 0
skipped = 0
for m in unique:
    if args.dry_run:
        print(f"  [DRY] {m['folder']:25} {m['from']:30} -> {m['intent']:10} {m['subject'][:60]}")
        continue
    try:
        existing = sb.table("inbox_messages").select("id").eq("meta->>gmail_msg_id", m["msg_id"]).limit(1).execute()
        if existing.data:
            skipped += 1
            continue
    except Exception:
        pass
    try:
        sb.table("inbox_messages").insert({
            "channel": "email",
            "from_address": m["from"],
            "to_address": m["to"],
            "subject": m["subject"],
            "body": m["body"],
            "received_at": datetime.now(timezone.utc).isoformat(),
            "classified_intent": m["intent"],
            "in_reply_to": None,
            "meta": {
                "gmail_folder": m["folder"],
                "gmail_date": m["date"],
                "gmail_msg_id": m["msg_id"],
                "backfilled_via": "gmail_imap_scan",
            },
        }).execute()
        inserted += 1
        print(f"  [INSERT] {m['folder']:25} {m['from']:30} -> {m['intent']:10} {m['subject'][:60]}")
        if m["intent"] in ("interested", "question", "opt_out", "not_now"):
            tg_send(
                f"📬 *Gmail scan: {m['folder']}*\n"
                f"  from: {m['from']}\n"
                f"  intent: *{m['intent']}*\n"
                f"  subject: {m['subject'][:60]}\n"
            )
    except Exception as e:
        print(f"  [ERR] {m['from']}: {e}")

if not args.dry_run:
    print(f"\n=== final ===")
    print(f"  matched:  {len(unique)}")
    print(f"  inserted: {inserted}")
    print(f"  skipped:  {skipped}")
    if inserted > 0:
        tg_send(f"📬 Gmail scan done: {inserted} new captures from {len(set(m['folder'] for m in unique))} folders")
