"""
Send the 5 carrier outreach draft emails via Resend API.
Reads drafts from carrier_outreach_drafts/ and sends each one.
"""
import os, sys, json, uuid
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx
from supabase import create_client

RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
FROM_ADDRESS = os.environ.get("FROM_ADDRESS", "noreply@empire-ai.co.uk")
FROM_NAME = os.environ.get("FROM_NAME", "Empire-AI Operations")

DRAFTS_DIR = Path("/root/empire-v49/carrier_outreach_drafts")

DRAFT_FILES = [
    ("State Farm",   "state_farm.txt",   "partners@statefarm.com"),
    ("Allstate",     "allstate.txt",     "vendorpartners@allstate.com"),
    ("USAA",         "usaa.txt",         "partnerships@usaa.com"),
    ("Liberty Mutual","liberty_mutual.txt","partners@libertymutual.com"),
    ("Farmers",      "farmers.txt",      "partners@farmers.com"),
]


def parse_draft(filepath: Path) -> dict:
    with open(filepath) as f:
        text = f.read()
    lines = text.split("\n")
    subject = ""
    body_start = 0
    for i, line in enumerate(lines):
        if line.startswith("Subject: "):
            subject = line[9:].strip()
        elif line.startswith("=" * 70):
            body_start = i + 1
            break
    body = "\n".join(lines[body_start:]).strip()
    return {"subject": subject, "body": body}


def send_email(to: str, subject: str, body: str) -> dict:
    if not RESEND_API_KEY:
        return {"ok": False, "error": "RESEND_API_KEY not set"}
    html_body = body.replace("\n", "<br>\n")
    html = f"""<!DOCTYPE html>
<html><body style="font-family:-apple-system,system-ui,sans-serif;background:#0a0a0a;color:#e4e4e7;padding:32px;line-height:1.7;font-size:14px;">
<div style="max-width:580px;margin:0 auto;">
{html_body}
</div>
</body></html>"""
    try:
        r = httpx.post(
            "https://api.resend.com/emails",
            headers={"Authorization": f"Bearer {RESEND_API_KEY}", "Content-Type": "application/json"},
            json={"from": f"{FROM_NAME} <{FROM_ADDRESS}>", "to": [to], "subject": subject, "html": html},
            timeout=20,
        )
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        ok = r.status_code < 300
        return {"ok": ok, "id": data.get("id"), "status_code": r.status_code, "raw": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def log_to_activity(results: list):
    try:
        sb = create_client(os.environ.get("SUPABASE_URL", ""), os.environ.get("SUPABASE_SERVICE_KEY", ""))
        success_count = sum(1 for r in results if r.get("ok"))
        sb.table("agent_activity").insert({
            "agent_name": "carrier_outreach_drafts_send",
            "run_id": str(uuid.uuid4()),
            "started_at": datetime.now(timezone.utc).isoformat(),
            "finished_at": datetime.now(timezone.utc).isoformat(),
            "status": "ok",
            "rows_seen": len(results),
            "rows_processed": success_count,
            "rows_errored": len(results) - success_count,
            "summary": f"carrier_outreach_drafts: sent {success_count}/{len(results)} emails via Resend",
            "meta": {"results": [
                {"carrier": r["carrier"], "to": r["to"], "ok": r.get("ok"), "id": r.get("id"), "error": r.get("error")}
                for r in results
            ]},
        }).execute()
    except Exception as e:
        print(f"[WARN] Could not log to activity: {e}")


def main():
    if not RESEND_API_KEY:
        print("ERROR: RESEND_API_KEY not set")
        sys.exit(1)

    print(f"Sender: {FROM_NAME} <{FROM_ADDRESS}>")
    results = []

    for carrier, filename, expected_to in DRAFT_FILES:
        filepath = DRAFTS_DIR / filename
        if not filepath.exists():
            print(f"[SKIP] {carrier}: file not found")
            results.append({"carrier": carrier, "to": expected_to, "ok": False, "error": "file_not_found"})
            continue

        draft = parse_draft(filepath)
        print(f"\n--- {carrier} ---")
        print(f"  To: {expected_to}")
        print(f"  Subj: {draft['subject']}")
        print(f"  Body: {len(draft['body'])} chars")

        result = send_email(expected_to, draft["subject"], draft["body"])
        result["carrier"] = carrier
        result["to"] = expected_to

        if result.get("ok"):
            print(f"  ✅ Sent! Resend ID: {result.get('id')}")
        else:
            print(f"  ❌ Failed: {result.get('error', 'unknown')} (status: {result.get('status_code')})")
        results.append(result)

    success = sum(1 for r in results if r.get("ok"))
    failed = sum(1 for r in results if not r.get("ok"))
    print(f"\n{'='*50}")
    print(f"SUMMARY: {success} sent, {failed} failed out of {len(results)}")

    log_to_activity(results)

    status_path = DRAFTS_DIR / "send_status.json"
    with open(status_path, "w") as f:
        json.dump({
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "total": len(results),
            "success": success,
            "failed": failed,
            "results": [
                {"carrier": r.get("carrier"), "to": r.get("to"), "ok": r.get("ok"), "id": r.get("id"), "error": r.get("error")}
                for r in results
            ],
        }, f, indent=2)
    print(f"Status log: {status_path}")


if __name__ == "__main__":
    main()
