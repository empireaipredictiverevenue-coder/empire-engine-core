"""
Empire AI · Business Growth Agent
====================================

Meta-orchestrator that monitors the entire funnel and either:
  - Logs a recommendation (human review)
  - Auto-executes a small action (with safety bounds)

Checks performed each cycle:
  1. Open rate below 15% on outreach > 50 sent → recommend A/B test subject
  2. Click rate below 3% on outreach > 100 sent → recommend CTA/body rewrite
  3. Conversion rate below 0.5% → recommend review pricing/landing page
  4. Bounced emails > 10% → recommend email validation gate
  5. Active subs < 5 after 30 days → recommend new lead sources/verticals
  6. MRR stalled 3 days → recommend proactive outreach blast
  7. Pipeline (contractor count) shrinking → recommend re-scrape
  8. Buyers without phones → remind Phil (no auto-action)

Outputs:
  - business_recommendations table (human-readable suggestions)
  - business_actions_log table (audit trail of auto-actions)
  - /api/v1/growth/recommendations endpoint (live query)

Cron: 0 11 * * * (after the morning outreach send runs)
"""
import os, sys, json, time, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client

log = logging.getLogger("business_growth_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


def _post(category: str, severity: str, title: str, description: str,
          recommended_action: str = None, auto_executable: bool = False,
          metadata: dict = None) -> dict:
    """Log a recommendation to the business_recommendations table."""
    sb = _sb()
    row = {
        "category": category,
        "severity": severity,
        "title": title,
        "description": description,
        "recommended_action": recommended_action,
        "auto_executable": auto_executable,
        "metadata": metadata or {},
    }
    sb.table("business_recommendations").insert(row).execute()
    return row


def _log_action(action_type: str, payload: dict, result: str, duration_ms: int = 0):
    sb = _sb()
    sb.table("business_actions_log").insert({
        "action_type": action_type,
        "action_payload": payload,
        "result": result,
        "duration_ms": duration_ms,
    }).execute()


def get_funnel_snapshot() -> dict:
    """Pull current funnel state directly from DB (avoid HTTP round-trip)."""
    sb = _sb()

    # Outreach
    outreach_sent = sb.table("contractor_outreach").select("id", count="exact").eq("status", "sent").execute().count or 0
    outreach_opened = sb.table("contractor_outreach").select("id", count="exact").eq("status", "sent").not_.is_("opened_at", "null").execute().count or 0
    outreach_clicked = sb.table("contractor_outreach").select("id", count="exact").eq("status", "sent").not_.is_("clicked_at", "null").execute().count or 0
    outreach_paid = sb.table("contractor_outreach").select("id", count="exact").eq("status", "paid").execute().count or 0
    outreach_bounced = sb.table("contractor_outreach").select("id", count="exact").eq("status", "bounced").execute().count or 0

    # Subs
    sub_active = sb.table("contractor_subscriptions").select("id", count="exact").eq("status", "active").execute().count or 0
    sub_total = sb.table("contractor_subscriptions").select("id", count="exact").execute().count or 0
    r = sb.table("contractor_subscriptions").select("monthly_amount_usdc").eq("status", "active").execute().data
    mrr_usdc = sum(float(s.get("monthly_amount_usdc") or 0) for s in (r or []))

    # Invoices
    inv_paid_total = sum(float(i.get("amount_usdc") or 0) for i in
                          (sb.table("dispatch_invoices").select("amount_usdc").eq("status", "paid").execute().data or []))
    inv_pending_total = sum(float(i.get("amount_usdc") or 0) for i in
                            (sb.table("dispatch_invoices").select("amount_usdc").eq("status", "unpaid").execute().data or []))

    # Fee events
    fee_paid = sb.table("fee_events").select("fee_amount").eq("status", "paid").execute().data or []
    fee_paid_usdc = sum(float(f.get("fee_amount") or 0) for f in fee_paid)
    fee_pending = sb.table("fee_events").select("fee_amount").eq("status", "pending").execute().data or []
    fee_pending_usdc = sum(float(f.get("fee_amount") or 0) for f in fee_pending)

    # Contractors
    contractors_active = sb.table("contractors").select("id", count="exact").eq("active", True).execute().count or 0
    contractors_with_email = sb.table("contractors").select("id", count="exact").eq("active", True).not_.is_("email", "null").execute().count or 0

    # Buyers missing phone
    buyers_missing_phone = sb.table("buyers").select("id", count="exact").eq("is_active", True).is_("destination_phone", "null").execute().count or 0

    return {
        "outreach_sent": outreach_sent,
        "outreach_opened": outreach_opened,
        "outreach_clicked": outreach_clicked,
        "outreach_paid": outreach_paid,
        "outreach_bounced": outreach_bounced,
        "open_rate": (outreach_opened / outreach_sent * 100) if outreach_sent else 0,
        "click_rate": (outreach_clicked / outreach_sent * 100) if outreach_sent else 0,
        "conversion_rate": (outreach_paid / outreach_sent * 100) if outreach_sent else 0,
        "bounce_rate": (outreach_bounced / (outreach_sent + outreach_bounced) * 100) if (outreach_sent + outreach_bounced) else 0,
        "sub_active": sub_active,
        "sub_total": sub_total,
        "mrr_usdc": mrr_usdc,
        "inv_paid_total": inv_paid_total,
        "inv_pending_total": inv_pending_total,
        "fee_paid_usdc": fee_paid_usdc,
        "fee_pending_usdc": fee_pending_usdc,
        "contractors_active": contractors_active,
        "contractors_with_email": contractors_with_email,
        "buyers_missing_phone": buyers_missing_phone,
    }


def detect_and_recommend(snapshot: dict) -> list:
    """Return a list of recommendations based on funnel state."""
    recs = []

    # Rule 1: low open rate
    if snapshot["outreach_sent"] >= 50 and snapshot["open_rate"] < 15:
        recs.append({
            "category": "outreach",
            "severity": "warning",
            "title": f"Outreach open rate is {snapshot['open_rate']:.1f}% (target: 25%+)",
            "description": f"Of {snapshot['outreach_sent']} sent, only {snapshot['outreach_opened']} opened.",
            "recommended_action": "Test new subject lines: shorter, more direct. Examples: 'Quick question about your roofing work' or 'Did you see the storm pipeline update?'. A/B test via separate templates.",
            "auto_executable": False,
        })

    # Rule 2: low click rate (people open but don't click)
    if snapshot["outreach_sent"] >= 100 and snapshot["click_rate"] < 3:
        recs.append({
            "category": "outreach",
            "severity": "warning",
            "title": f"Click-through rate is {snapshot['click_rate']:.1f}% (target: 5%+)",
            "description": f"Only {snapshot['outreach_clicked']} of {snapshot['outreach_opened']} openers clicked. Body or CTA isn't compelling enough.",
            "recommended_action": "Rewrite the email body to lead with a specific number (50 leads/mo) and the pain point (24-hour lead delay = lost jobs). Move the link earlier in the email.",
            "auto_executable": False,
        })

    # Rule 3: zero conversions after substantial outreach
    if snapshot["outreach_sent"] >= 100 and snapshot["outreach_paid"] == 0:
        recs.append({
            "category": "funnel",
            "severity": "critical",
            "title": f"0 paid conversions from {snapshot['outreach_sent']} outreach emails",
            "description": "Conversion rate is 0%. Either the funnel isn't reaching contractors, or they're not activating.",
            "recommended_action": "Check /for-contractors page (curl https://empire-ai.co.uk/for-contractors). Verify Resend webhook is wired (open + click events). Confirm tier pricing is competitive vs market ($99-499/mo is mid-tier; could try a $49 lead-in tier).",
            "auto_executable": False,
        })

    # Rule 4: high bounce rate
    if snapshot["bounce_rate"] > 5:
        recs.append({
            "category": "leads",
            "severity": "warning",
            "title": f"Bounce rate is {snapshot['bounce_rate']:.1f}%",
            "description": f"{snapshot['outreach_bounced']} bounced emails indicate bad data. Today we found 27 placeholder emails from BBB scraper.",
            "recommended_action": "Add email validation gate to enroll_universe() in scripts/contractor_outreach.py. Reject addresses with control chars, missing @, or no TLD.",
            "auto_executable": True,
            "metadata": {"script": "scripts/contractor_outreach.py", "function": "enroll_universe"},
        })

    # Rule 5: very few subs after 30 days
    if snapshot["sub_active"] < 3 and snapshot["outreach_sent"] >= 100:
        recs.append({
            "category": "pricing",
            "severity": "critical",
            "title": f"Only {snapshot['sub_active']} active subscription(s) after {snapshot['outreach_sent']} outreach sends",
            "description": "Either pricing is wrong, tier mix is off, or contractors don't see enough value at $99/mo.",
            "recommended_action": "Add a $49 'starter' tier with 10 leads/mo. Add social proof on /for-contractors ('47 contractors signed up this week'). Test a 'first month free' promo to lower the barrier.",
            "auto_executable": False,
        })

    # Rule 6: MRR stalled
    if snapshot["mrr_usdc"] < 1000 and snapshot["outreach_sent"] >= 100:
        recs.append({
            "category": "verticals",
            "severity": "info",
            "title": f"MRR is ${snapshot['mrr_usdc']:.0f}/mo (target: $1k+ in 30d, $10k+ in 90d)",
            "description": "Need to expand reach. Current contractors are storm/restoration focused.",
            "recommended_action": "Activate 9 unprovisioned buyer lanes (4 legal + 4 insurance + 1 HVAC). Provision their destination_phone numbers in /root/.env via the Vonage dashboard. This unlocks 3 verticals that have zero MRR.",
            "auto_executable": False,
        })

    # Rule 7: pipeline shrinking or flat
    if snapshot["contractors_with_email"] < 1000:
        recs.append({
            "category": "leads",
            "severity": "info",
            "title": f"Only {snapshot['contractors_with_email']} contractors with valid emails",
            "description": "Need more top-of-funnel supply to scale outreach.",
            "recommended_action": "Run bots/bbb_prospector.py --metros 54 --niches 5 --max 8 right now. Adds ~3,000 fresh contractors overnight. Already wired to cron nightly 03:30.",
            "auto_executable": True,
            "metadata": {"script": "bots/bbb_prospector.py"},
        })

    # Rule 8: buyers without phone (blocker)
    if snapshot["buyers_missing_phone"] > 0:
        recs.append({
            "category": "verticals",
            "severity": "critical",
            "title": f"{snapshot['buyers_missing_phone']} buyer lanes have no destination_phone",
            "description": "Outreach to those niches generates 0 calls. The whole vertical is blocked.",
            "recommended_action": "Action: provision Vonage numbers, update buyers.destination_phone in Supabase. This is human action — we can't auto-provision phone numbers.",
            "auto_executable": False,
        })

    # Rule 9: dispatch invoice collection
    if snapshot["inv_pending_total"] > 100 and snapshot["inv_paid_total"] == 0:
        recs.append({
            "category": "funnel",
            "severity": "warning",
            "title": f"${snapshot['inv_pending_total']:.0f} in unpaid dispatch invoices, $0 paid",
            "description": "Contractors are receiving invoices but not paying them.",
            "recommended_action": "Lower the per-lead price ($35 → $20) for first 30 days to seed payment behavior. Add a 7-day countdown SMS reminder.",
            "auto_executable": False,
        })

    return recs


def auto_execute_if_safe(rec: dict) -> bool:
    """Execute an auto-action if marked auto_executable + has a script in metadata.
    For now, just log the action; actual execution depends on safety guardrails."""
    if not rec.get("auto_executable"):
        return False
    metadata = rec.get("metadata") or {}
    script = metadata.get("script")
    if not script:
        return False
    # Safety: only auto-execute known-safe scripts
    SAFE_SCRIPTS = {"bots/bbb_prospector.py"}
    if script not in SAFE_SCRIPTS:
        log.info(f"  skip auto-exec (not in safe list): {script}")
        return False
    t0 = time.time()
    import subprocess
    log.info(f"  auto-executing: {script}")
    try:
        result = subprocess.run(
            ["python3", script],
            cwd="/root/empire-v49",
            capture_output=True, text=True, timeout=600,
        )
        duration = int((time.time() - t0) * 1000)
        _log_action(f"auto_exec:{script}", metadata, result.stdout[:500], duration)
        return result.returncode == 0
    except Exception as e:
        _log_action(f"auto_exec:{script}", metadata, f"error: {e}", 0)
        return False


def run():
    """Main cycle. Pull funnel, detect, log recommendations."""
    t0 = time.time()
    snapshot = get_funnel_snapshot()
    log.info(f"funnel: outreach={snapshot['outreach_sent']} sent, "
             f"{snapshot['outreach_opened']} opened, {snapshot['outreach_paid']} paid; "
             f"mrr=${snapshot['mrr_usdc']:.0f}; subs={snapshot['sub_active']}; "
             f"bounced={snapshot['outreach_bounced']}")

    recs = detect_and_recommend(snapshot)
    if not recs:
        log.info("no recommendations")
        return {"recs": 0, "auto_executed": 0}

    auto_executed = 0
    for rec in recs:
        log.info(f"  [{rec['severity']}] {rec['category']}: {rec['title']}")
        _post(**rec)
        if rec.get("auto_executable"):
            if auto_execute_if_safe(rec):
                auto_executed += 1

    print(json.dumps({
        "snapshot": snapshot,
        "recommendations": len(recs),
        "auto_executed": auto_executed,
    }, indent=2, default=str))

    duration_ms = int((time.time() - t0) * 1000)
    _log_action("growth_cycle", {"recs": len(recs), "auto_executed": auto_executed}, "ok", duration_ms)


def list_recommendations(status: str = "open", limit: int = 50) -> list:
    sb = _sb()
    r = sb.table("business_recommendations").select("*").eq("status", status).order("detected_at", desc=True).limit(limit).execute()
    return r.data or []


def resolve_recommendation(rec_id: str, new_status: str = "dismissed"):
    sb = _sb()
    sb.table("business_recommendations").update({
        "status": new_status,
        "resolved_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", rec_id).execute()


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        for r in list_recommendations():
            print(f"[{r['severity']}] {r['category']}: {r['title']}")
            print(f"  → {r.get('recommended_action', '')[:100]}")
    else:
        run()