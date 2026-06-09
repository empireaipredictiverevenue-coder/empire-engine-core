"""
EMPIRE V49 - BUYER OUTREACH
===========================
Generates personalized "Pay-Per-Call" email drafts for top-scored prospects
identified by prospector.py. Uses the refined PPC outreach template.

Safety: All drafts are saved to /root/empire-v49/outreach_drafts/
for manual review — nothing is sent automatically.
"""
import os, logging
from datetime import datetime

from dotenv import load_dotenv
load_dotenv("/root/.env")
from supabase import create_client

log = logging.getLogger("empire.buyer_outreach")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

DRAFTS_DIR = "/root/empire-v49/outreach_drafts"

PPC_TEMPLATE = """Subject: High-Intent Roofing Leads for {business_name} — Wichita Area

Hi {contact_name},

I've been monitoring storm activity in Wichita and noticed {business_name} is well-positioned for upcoming repairs. I operate a predictive revenue engine that captures high-intent homeowners at the exact moment they need storm damage assistance.

I'm looking to partner with one reliable roofer in the area to handle these calls on a Pay-Per-Call basis.

We don't sell 'leads'—we route verified homeowners directly to your phone. Are you interested in taking 5 test calls this week to see the quality firsthand?

Best,
Phil | Empire AI
"""


def fetch_top_prospects(metro="Wichita", limit=10):
    """Fetch the highest-scored prospects for a given metro."""
    try:
        res = (sb.table("prospects")
               .select("id,business_name,phone,website,buy_signal_score,contact_name,contact_title,rating,review_count")
               .eq("metro", metro)
               .order("buy_signal_score", desc=True)
               .limit(limit)
               .execute())
        return res.data or []
    except Exception as e:
        log.error(f"[BUYER_OUTREACH] Supabase fetch error: {e}")
        return []


def render_draft(prospect):
    """Render a personalized PPC email draft for one prospect."""
    biz = (prospect.get("business_name") or "").strip()
    contact = prospect.get("contact_name") or "Roofing Team"
    return PPC_TEMPLATE.format(
        business_name=biz or "Your Company",
        contact_name=contact,
    )


def save_draft(prospect, draft):
    """Write a single draft to the outreach_drafts directory."""
    safe_name = prospect.get("business_name", "unknown").replace("/", "_").replace(" ", "_")[:60]
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{ts}__{safe_name}.txt"
    path = os.path.join(DRAFTS_DIR, filename)

    lines = [
        f"=== OUTREACH DRAFT ===",
        f"Business:  {prospect.get('business_name', '?')}",
        f"Phone:     {prospect.get('phone', '?')}",
        f"Website:   {prospect.get('website', '?')}",
        f"Score:     {prospect.get('buy_signal_score', '?')}",
        f"Contact:   {prospect.get('contact_name', '—')} ({prospect.get('contact_title', '—')})",
        f"Rating:    {prospect.get('rating', '?')} · {prospect.get('review_count', '?')} reviews",
        f"Generated: {datetime.now().isoformat()}",
        f"Status:    DRAFT — REVIEW BEFORE SENDING",
        f"",
        f"{'=' * 60}",
        f"",
        draft,
        f"",
        f"{'=' * 60}",
        f"⚠  This is a manually-reviewed draft.  No automated sending has occurred.",
    ]

    with open(path, "w") as f:
        f.write("\n".join(lines))
    return path


def generate_drafts(metro="Wichita", limit=10):
    """Main workflow: fetch top prospects → render drafts → save → report."""
    prospects = fetch_top_prospects(metro, limit)
    if not prospects:
        print(f"[BUYER_OUTREACH] No prospects found for {metro}.")
        return []

    os.makedirs(DRAFTS_DIR, exist_ok=True)

    saved = []
    for i, p in enumerate(prospects, 1):
        draft = render_draft(p)
        path = save_draft(p, draft)
        saved.append(path)
        print(f"  {i}. {p['business_name']} (score {p['buy_signal_score']}) → {os.path.basename(path)}")

    print(f"\n[BUYER_OUTREACH] {len(saved)} drafts saved to {DRAFTS_DIR}/")
    print(f"[BUYER_OUTREACH] All drafts require manual review before any sending.")
    return saved


if __name__ == "__main__":
    import sys
    metro = sys.argv[1] if len(sys.argv) > 1 else "Wichita"
    limit = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    generate_drafts(metro, limit)
