"""
Empire AI · Sales Agent
==========================

Closes open leads. Watches for:
  - Contractors who clicked /for-contractors but haven't activated
  - Activations with no payment after 24h / 72h
  - Recently dispatched contractors who haven't engaged

For each, fires a high-touch action:
  - 24h after click but no activate: SMS via Vonage
  - 72h after click but no activate: voice call via Amy
  - 7d after activate but no payment: urgent SMS
  - Active subs that lapsed: re-engagement SMS

Writes actions to business_actions_log. Live route at
  GET /api/v1/sales/pipeline   — current active leads
  GET /api/v1/sales/queue     — what's queued to fire next

Cron: every 4h
"""
import os, sys, json, time, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

import httpx, jwt as pyjwt
from supabase import create_client

log = logging.getLogger("sales_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

VAULT = "egJ1t9NZkDs8FvMbfnQTqXzC4KNuhAc9XSfpG9y9AZM"


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))


def _send_vonage_sms(to: str, body: str) -> dict:
    app_id = os.environ.get("VONAGE_APPLICATION_ID", "")
    key_path = os.getenv("VONAGE_PRIVATE_KEY_PATH", "/root/vonage_private.key")
    from_number = os.environ.get("VONAGE_NUMBER", "12142277528").lstrip("+")
    if not (app_id and os.path.exists(key_path)):
        return {"ok": False, "error": "vonage creds missing"}
    with open(key_path) as f:
        pk = f.read()
    ts = int(time.time())
    tok = pyjwt.encode({"iat": ts, "exp": ts + 180, "jti": str(__import__('uuid').uuid4()),
                        "application_id": app_id}, pk, algorithm="RS256")
    try:
        with httpx.Client(timeout=15) as c:
            r = c.post("https://api.nexmo.com/v1/messages",
                json={"from": from_number, "to": to.lstrip("+"),
                      "message_type": "text", "text": body[:1000], "channel": "sms"},
                headers={"Authorization": f"Bearer {tok}", "Content-Type": "application/json"})
        return {"ok": r.status_code < 400, "status": r.status_code}
    except Exception as e:
        return {"ok": False, "error": str(e)[:200]}


def _log_action(action_type: str, payload: dict, result: str):
    _sb().table("business_actions_log").insert({
        "action_type": action_type, "action_payload": payload, "result": result,
    }).execute()


def get_pipeline() -> list:
    """Find all contractors with open sales opportunities (clicked-no-activate, pending payment, etc)."""
    sb = _sb()
    now = datetime.now(timezone.utc)
    out = []

    # 1. Clicked /for-contractors but haven't activated
    r = sb.table("contractor_outreach").select(
        "id,contractor_id,clicked_at,sequence,step"
    ).eq("status", "sent").not_.is_("clicked_at", "null").execute().data or []
    cutoff_24 = (now - timedelta(hours=24)).isoformat()
    cutoff_72 = (now - timedelta(hours=72)).isoformat()
    for row in r:
        # Check if there's a sub already (means activated)
        sub = sb.table("contractor_subscriptions").select("id,status").eq("contractor_id", row["contractor_id"]).limit(1).execute().data
        if sub and sub[0].get("status") == "active":
            continue  # already converted
        if row["clicked_at"] > cutoff_24:
            continue  # clicked recently, give them time
        stage = "24h-no-activate" if row["clicked_at"] < cutoff_24 and row["clicked_at"] > cutoff_72 else "72h-no-activate"
        out.append({"contractor_id": row["contractor_id"], "stage": stage,
                    "outreach_id": row["id"], "clicked_at": row["clicked_at"]})

    # 2. Pending subscriptions (active or pending_payment) where no payment yet
    r = sb.table("contractor_subscriptions").select(
        "id,contractor_id,tier,monthly_amount_usdc,created_at,status,last_payment_at"
    ).in_("status", ["pending", "active"]).execute().data or []
    cutoff_7d = (now - timedelta(days=7)).isoformat()
    for row in r:
        if row.get("last_payment_at"):
            continue  # paid
        if row["created_at"] > cutoff_7d:
            continue  # less than 7 days
        out.append({"contractor_id": row["contractor_id"], "stage": "sub-no-payment-7d",
                    "subscription_id": row["id"], "tier": row["tier"],
                    "monthly_amount_usdc": row["monthly_amount_usdc"]})

    return out


def act_on_lead(lead: dict, dry_run: bool = False) -> dict:
    """Fire a high-touch action for one lead."""
    sb = _sb()
    cid = lead["contractor_id"]
    cont = sb.table("contractors").select("name,phone,email").eq("id", cid).limit(1).execute().data
    if not cont:
        return {"ok": False, "error": "no contractor"}
    cont = cont[0]
    first = (cont["name"] or "there").split()[0]
    phone = cont.get("phone")
    stage = lead["stage"]

    if stage == "24h-no-activate":
        body = (f"Empire AI: {first}, you checked out our pricing yesterday but didn't activate. "
                f"Quick question: are the tiers off, or is it the timing? "
                f"Pay $99-499 USDC/month for priority storm-damage leads. "
                f"Reply here if you have questions. → empire-ai.co.uk/for-contractors STOP to opt out")
    elif stage == "72h-no-activate":
        body = (f"Empire AI: {first}, last note on this. We have storm season coming up and "
                f"the Pro tier ($299/mo) gives you 200 leads with instant routing. "
                f"Right now those leads are going to contractors on the free tier who wait 24hr. "
                f"Activate: empire-ai.co.uk/for-contractors STOP to opt out")
    elif stage == "sub-no-payment-7d":
        body = (f"Empire AI: {first}, you activated a tier but no payment has come through. "
                f"Tier is still pending. Send ${lead.get('monthly_amount_usdc', 99)} USDC to: "
                f"{VAULT[:8]}...{VAULT[-8:]} (memo: empire-{lead['tier']}-{cid[:8]}) "
                f"to activate. Or cancel here. STOP to opt out")
    else:
        body = f"Empire AI: {first}, just checking in. Reply with any questions."

    if not phone:
        return {"ok": False, "error": "no phone"}
    if dry_run:
        return {"ok": True, "dry_run": True, "stage": stage, "body": body[:100]}

    r = _send_vonage_sms(phone, body)
    _log_action(f"sales:{stage}", {"contractor_id": cid}, "ok" if r.get("ok") else f"error:{r.get('error') or r.get('status')}")
    return r


def run(dry_run: bool = False, max_actions: int = 50):
    pipeline = get_pipeline()
    log.info(f"sales pipeline: {len(pipeline)} open leads")
    acted = 0
    for lead in pipeline[:max_actions]:
        r = act_on_lead(lead, dry_run=dry_run)
        if r.get("ok"):
            acted += 1
            log.info(f"  acted: {lead['stage']} cid={lead['contractor_id'][:8]}")
    log.info(f"done: acted={acted}/{len(pipeline)}")
    return {"pipeline": len(pipeline), "acted": acted}


if __name__ == "__main__":
    import sys
    dry = "--dry" in sys.argv
    run(dry_run=dry)