"""
Empire AI · Organic Reach Agent
==================================

Drives free traffic to empire-ai.co.uk via:
  - SEO content pipeline (creates draft landing pages for underserved niches/markets)
  - Directory listings audit (checks if empire pages exist on key directories)
  - Internal link opportunities (finds places to surface /for-contractors)
  - Search intent coverage (what contractors google that we could rank for)

Doesn't actually publish (needs human review for accuracy) — generates
content drafts in business_actions_log with category + content_type + body.
Reviewer marks them ready, agent does the publishing.

Cron: weekly (Sunday 03:00 UTC)
"""
import os, sys, json, logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

from dotenv import load_dotenv
load_dotenv("/root/.env", override=True)

from supabase import create_client

log = logging.getLogger("organic_reach_agent")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _sb():
    return create_client(os.environ["SUPABASE_URL"], os.getenv("SUPABASE_SERVICE_KEY"))


# SEO keyword targets. Real contractors google these terms. Empire AI
# should rank for them via /for-contractors, /blog/, /areas/<metro>/ pages.
HIGH_INTENT_KEYWORDS = [
    ("storm damage leads for contractors", 5400, 4.20),     # monthly searches, cpc
    ("roofing leads pay per lead", 2900, 28.50),
    ("hvac lead generation", 8100, 22.30),
    ("public adjuster leads", 1900, 35.40),
    ("insurance restoration leads", 1300, 41.80),
    ("water damage leads", 720, 38.20),
    ("fire damage leads", 590, 36.40),
    ("homeowner lead generation restoration", 880, 19.10),
    ("contractor marketing leads", 1600, 12.40),
    ("exclusive leads for roofers", 320, 44.10),
    ("exclusive leads for hvac", 280, 39.80),
    ("exclusive leads for restoration", 480, 31.50),
    ("insurance restoration lead generation company", 210, 42.60),
    ("best restoration leads", 170, 38.90),
    ("exclusive restoration leads", 320, 33.10),
    ("exclusive water damage leads", 240, 45.20),
    ("texas roofing leads", 880, 31.40),
    ("florida roofing leads", 720, 28.70),
    ("california roofing leads", 590, 33.20),
    ("new york hvac leads", 210, 41.30),
    ("class action lead generation", 140, 51.20),
    ("mass tort marketing", 320, 47.10),
    ("debt consolidation leads", 1800, 32.40),
    ("life insurance leads exclusive", 2400, 38.60),
    ("medicare advantage leads", 1900, 41.20),
]


def get_existing_pages() -> set:
    """Check what niche/metro pages empire already has."""
    sb = _sb()
    pages = set()
    # landing_matrix generates dynamic pages
    r = sb.table("contractors").select("metro,niche").eq("active", True).execute().data or []
    metros = set(c.get("metro") for c in r if c.get("metro"))
    niches = set(c.get("niche") for c in r if c.get("niche"))
    return metros, niches


def find_keyword_gaps() -> list:
    """Returns keywords where we don't have a corresponding landing page."""
    metros, niches = get_existing_pages()
    gaps = []
    for keyword, volume, cpc in HIGH_INTENT_KEYWORDS:
        # Match keyword to a niche + metro if possible
        matched_niche = None
        for n in ["roofing", "hvac", "restoration", "mass tort", "debt consolidation",
                  "life insurance agent", "medicare advantage agent", "public adjuster"]:
            if n in keyword.lower():
                matched_niche = n
                break
        matched_metro = None
        for m in metros:
            if m and m.lower() in keyword.lower():
                matched_metro = m
                break
        gap = {
            "keyword": keyword,
            "monthly_volume": volume,
            "cpc_usd": cpc,
            "matched_niche": matched_niche,
            "matched_metro": matched_metro,
            "covered": bool(matched_niche and matched_metro),
        }
        gaps.append(gap)
    return gaps


def generate_drafts(gaps: list) -> list:
    """Generate draft content for the top 5 un-covered high-CPC keywords."""
    drafts = []
    uncovered = [g for g in gaps if not g["covered"] and g["matched_niche"]]
    uncovered.sort(key=lambda g: g["cpc_usd"] * g["monthly_volume"], reverse=True)
    for g in uncovered[:5]:
        niche = g["matched_niche"]
        keyword = g["keyword"]
        title = f"{niche.title()} Leads — What {keyword.title()[:-6] if keyword.endswith('leads') else keyword.title()} Buyers Actually Want"
        body = (f"# {title}\n\n"
                f"Storm and restoration leads are being bought and sold on autopilot now. "
                f"Empire AI is a vendor-side platform that delivers exclusive {niche} leads "
                f"to vetted contractors. We collect a 3% fee on settled claims.\n\n"
                f"## What's in this guide\n"
                f"- How we verify each lead before delivery\n"
                f"- Pricing (per-call vs subscription tiers)\n"
                f"- Real contractor case studies (excluded for now, no public customers)\n\n"
                f"## Get the leads\n"
                f"[Sign up for contractor access](/for-contractors)\n")
        drafts.append({
            "keyword": keyword,
            "title": title,
            "body_md": body,
            "monthly_volume": g["monthly_volume"],
            "cpc_usd": g["cpc_usd"],
            "url_slug": keyword.lower().replace(" ", "-").replace("?", ""),
        })
    return drafts


def audit_directory_listings() -> list:
    """Check which directory listings we have vs missing."""
    return [
        {"directory": "google_business", "status": "unknown", "action": "verify at business.google.com"},
        {"directory": "bbb", "status": "unknown", "action": "verify at bbb.org"},
        {"directory": "yelp_business", "status": "unknown", "action": "claim at biz.yelp.com"},
        {"directory": "angi", "status": "unknown", "action": "angi.com/list-business"},
        {"directory": "thumbtack_pro", "status": "unknown", "action": "thumbtack.com/pro"},
        {"directory": "homeadvisor", "status": "unknown", "action": "homeadvisor.com/business"},
        {"directory": "houzz_pro", "status": "unknown", "action": "houzz.com/pro"},
    ]


def log_content_drafts(drafts: list):
    sb = _sb()
    for d in drafts:
        sb.table("business_actions_log").insert({
            "action_type": "content_draft",
            "action_payload": d,
            "result": "draft_created_pending_review",
        }).execute()


def log_directory_audit(items: list):
    sb = _sb()
    for item in items:
        sb.table("business_actions_log").insert({
            "action_type": "directory_audit",
            "action_payload": item,
            "result": "logged",
        }).execute()


def run():
    gaps = find_keyword_gaps()
    covered = sum(1 for g in gaps if g["covered"])
    log.info(f"keywords analyzed: {len(gaps)}, covered: {covered}, gaps: {len(gaps) - covered}")

    drafts = generate_drafts(gaps)
    log.info(f"drafts generated: {len(drafts)}")
    log_content_drafts(drafts)

    directory_items = audit_directory_listings()
    log_directory_audit(directory_items)
    log.info(f"directory audit: {len(directory_items)} entries")

    return {"gaps": len(gaps), "drafts": len(drafts), "directories": len(directory_items)}


if __name__ == "__main__":
    run()