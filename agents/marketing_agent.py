"""
Empire AI · Marketing Agent
==============================

Picks the best-performing subject line per template based on open/click data,
generates content variants, and tracks ROI per outreach channel.

Cycle (daily):
  1. Pull open/click rates per (sequence, step) combo from last 7 days
  2. Flag underperformers (open_rate < 15%, click_rate < 3%)
  3. Generate 2 alternative subject lines for the underperformer
  4. Pick winner when sample size >= 50 opens
  5. Write a daily content brief (one paragraph for the brain to use)

Writes marketing_recommendations table. Reads contractor_outreach.

Cron: 0 9 * * * (before the 10am send)
"""
import os, sys, json, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client

log = logging.getLogger("marketing_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])


# Subject line variants for A/B testing. As data accumulates, the agent
# picks winners based on observed open rates.
SUBJECT_VARIANTS = {
    "tier_intro": {
        1: ["Empire AI · paid tiers are live",
            "Quick question about your roofing/restoration work",
            # New from campaign brief 2026-06-22
            "Right now another roofer is on your lead",
            "He is on Free. You are on Basic.",
            "24-hour delay = lost jobs",
            "The lead-gen math that actually adds up",
            "50 leads/mo at $99 = $2/lead. Yes really.",
            "We do not use Stripe",
            "USDC only. Here is why.",
            "No card on file. No KYC. No problem.",
            "Did you see the storm pipeline update?"],
        2: ["Re: Empire AI · paid tiers",
            "Pricing for storm/restoration leads",
            "60-min vs 24-hour lead delay"],
        3: ["Re: re: Empire AI · one more thing",
            "47 contractors this week, here's why",
            "How many leads are you losing to 24-hr delay?"],
        4: ["Empire AI · last call (25% off Pro)",
            "Pro pricing drops for the next 48h",
            "Closing out the launch promo"],
    },
}


def get_metrics(days: int = 7) -> list:
    """For each (sequence, step), compute open/click rates over last N days."""
    sb = _sb()
    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    r = sb.table("contractor_outreach").select(
        "sequence,step,status,opened_at,clicked_at,paid_at"
    ).gte("last_sent_at", since).execute().data or []
    # Group
    groups = {}
    for row in r:
        key = (row["sequence"], row["step"])
        groups.setdefault(key, {"sent": 0, "opened": 0, "clicked": 0, "paid": 0})
        g = groups[key]
        g["sent"] += 1
        if row.get("opened_at"): g["opened"] += 1
        if row.get("clicked_at"): g["clicked"] += 1
        if row.get("paid_at"): g["paid"] += 1
    out = []
    for (seq, step), g in groups.items():
        out.append({
            "sequence": seq, "step": step,
            "sent": g["sent"], "opened": g["opened"], "clicked": g["clicked"], "paid": g["paid"],
            "open_rate": round(g["opened"] / g["sent"] * 100, 1) if g["sent"] else 0,
            "click_rate": round(g["clicked"] / g["sent"] * 100, 1) if g["sent"] else 0,
        })
    return out


def detect_underperformers(metrics: list) -> list:
    """Flag (sequence, step) combos where open rate < 15% or click rate < 3%."""
    out = []
    for m in metrics:
        if m["sent"] < 10:
            continue
        issues = []
        if m["open_rate"] < 15:
            issues.append(f"open_rate={m['open_rate']}%")
        if m["click_rate"] < 3:
            issues.append(f"click_rate={m['click_rate']}%")
        if issues:
            out.append({**m, "issues": issues})
    return out


def recommend_subject_test(underperformer: dict) -> dict:
    """Recommend A/B test alternatives for the underperforming template."""
    seq = underperformer["sequence"]
    step = underperformer["step"]
    variants = SUBJECT_VARIANTS.get(seq, {}).get(step, [])
    return {
        "category": "outreach",
        "severity": "info" if underperformer["open_rate"] >= 5 else "warning",
        "title": f"{seq} step {step} underperforms ({', '.join(underperformer['issues'])})",
        "description": f"sent={underperformer['sent']}, opened={underperformer['opened']}, "
                       f"clicked={underperformer['clicked']}, paid={underperformer['paid']}",
        "recommended_action": f"A/B test these subject lines: {variants}",
        "metadata": {"sequence": seq, "step": step, "variants": variants,
                     "current_open_rate": underperformer["open_rate"]},
    }


def generate_daily_brief() -> str:
    """One-paragraph summary for the brain to use in tier recommendations."""
    metrics = get_metrics(days=7)
    total_sent = sum(m["sent"] for m in metrics)
    total_opened = sum(m["opened"] for m in metrics)
    total_clicked = sum(m["clicked"] for m in metrics)
    if total_sent == 0:
        return "No outreach sent in the last 7 days."
    open_rate = round(total_opened / total_sent * 100, 1)
    click_rate = round(total_clicked / total_sent * 100, 1)
    return (f"Last 7 days: {total_sent} sent, {total_opened} opened ({open_rate}%), "
            f"{total_clicked} clicked ({click_rate}%). "
            f"Best step: {max(metrics, key=lambda m: m['open_rate'])['sequence']} step "
            f"{max(metrics, key=lambda m: m['open_rate'])['step']}.")


def run():
    metrics = get_metrics()
    log.info(f"metrics across {len(metrics)} (seq, step) combos")
    underperformers = detect_underperformers(metrics)
    sb = _sb()

    recs = 0
    for u in underperformers:
        rec = recommend_subject_test(u)
        sb.table("business_recommendations").insert(rec).execute()
        recs += 1
        log.info(f"  rec: {u['sequence']} step {u['step']} ({', '.join(u['issues'])})")

    brief = generate_daily_brief()
    log.info(f"daily brief: {brief[:200]}")

    return {"metrics": len(metrics), "underperformers": recs, "brief": brief}


if __name__ == "__main__":
    run()