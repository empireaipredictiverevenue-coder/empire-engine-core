"""
EMPIRE V49 · B2B QUALIFICATION AGENT
=====================================
Scores and classifies B2B leads for outreach priority.
Multi-signal scoring: lead_score, website enrichment, email validity,
niche match, metro coverage, and site_content data.

Stores results in b2b_leads.meta.qualification and updates urgency/status.

Usage:
    python3 bots/b2b_qualifier.py --limit 50
    python3 bots/b2b_qualifier.py --lead-id <uuid>
    python3 bots/b2b_qualifier.py --all
"""

import os
import sys
import json
import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Dict, Optional, List

sys.path.insert(0, "/root/empire-v49")
try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("b2b.qualifier")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

_sb = None

def _get_sb():
    global _sb
    if _sb is None:
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


# ── QUALIFICATION TIERS ──────────────────────────────────────────────

TIER_HOT = "hot"           # score >= 80: ready for immediate outreach
TIER_WARM = "warm"         # score >= 50: good candidate, enrich first
TIER_COLD = "cold"         # score >= 20: low priority
TIER_UNQUALIFIED = "cold"  # score < 20: skip


def _email_quality(email: str) -> int:
    """Score email quality: 0-15 points."""
    if not email:
        return 0
    lower = email.lower()
    # Business domain (not gmail/yahoo/hotmail)
    if not any(free in lower for free in ["@gmail.", "@yahoo.", "@hotmail.", "@outlook.", "@aol.", "@icloud."]):
        # Business email — verify format
        if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
            return 15
        return 10
    # Free email — still has value if format is valid
    if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        return 8
    return 5


def _website_quality(website: str) -> int:
    """Score website presence: 0-15 points."""
    if not website:
        return 0
    lower = website.lower()
    # Social media = low signal
    if any(s in lower for s in ["facebook.com", "linkedin.com/company", "instagram.com", "youtube.com"]):
        return 5
    # Free subdomain = medium
    if any(s in lower for s in [".wordpress.com", ".blogspot.", ".wixsite.", ".weebly."]):
        return 8
    # Custom domain = high signal
    return 15


def _contact_completeness(lead: Dict) -> int:
    """Score contact data completeness: 0-20 points."""
    score = 0
    if lead.get("email"):
        score += 8
    if lead.get("phone"):
        score += 8
    if lead.get("address"):
        score += 4
    return min(score, 20)


def _niche_signal(niche: str) -> int:
    """Score niche relevance for Empire AI: 0-25 points."""
    if not niche:
        return 3
    niche_lower = niche.lower()
    # Tier 1: direct match (storm, insurance, roofing, restoration)
    t1 = ["roofing", "commercial roofing", "restoration", "insurance", "storm"]
    for n in t1:
        if n in niche_lower:
            return 25
    # Tier 2: adjacent (construction, hvac, solar, legal, financial)
    t2 = ["construction", "hvac", "solar", "legal", "financial", "healthcare", "real estate"]
    for n in t2:
        if n in niche_lower:
            return 18
    # Tier 3: general business
    t3 = ["marketing", "technology", "consulting", "software", "manufacturing"]
    for n in t3:
        if n in niche_lower:
            return 10
    return 6


def _enrichment_signal(enrichment: Dict) -> int:
    """Score from site_content enrichment: 0-20 points."""
    if not enrichment.get("has_site"):
        return 0
    score = 5  # has scraped content
    if enrichment.get("has_contact_form"):
        score += 5
    if enrichment.get("has_pricing"):
        score += 5
    if enrichment.get("service_pages", 0) > 1:
        score += 5
    return min(score, 20)


def _freshness_score(created_at: str) -> int:
    """Score lead freshness: 0-15 points with wider spread."""
    if not created_at:
        return 3
    try:
        created = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        age_days = (datetime.now(timezone.utc) - created).days
        if age_days <= 1:
            return 15
        elif age_days <= 7:
            return 12
        elif age_days <= 30:
            return 8
        elif age_days <= 90:
            return 4
        elif age_days <= 180:
            return 2
        else:
            return 0
    except Exception:
        return 3


def _existing_lead_score(lead: Dict) -> int:
    """Normalize existing lead_score (0-100) to our 0-25 component with more spread."""
    raw = lead.get("lead_score", 0) or 0
    try:
        return min(int(float(raw) * 0.25), 25)
    except (ValueError, TypeError):
        return 10


async def _get_enrichments_batch(lead_ids: List[str]) -> Dict[str, Dict]:
    """Batch-query site_content for all lead_ids at once."""
    if not lead_ids:
        return {}
    try:
        sb = _get_sb()
        # Supabase `in_` has a practical limit of ~300 items, so chunk
        results = {}
        for i in range(0, len(lead_ids), 300):
            chunk = lead_ids[i:i+300]
            r = sb.table("site_content").select("b2b_lead_id,page_type,pricing_mentions,cta_buttons,contact_info").in_("b2b_lead_id", chunk).execute()
            for row in (r.data or []):
                lid = row.get("b2b_lead_id")
                if lid not in results:
                    results[lid] = {"pages": []}
                results[lid]["pages"].append(row)
        # Convert to enrichment dicts
        enriched = {}
        for lid, data in results.items():
            pages = data["pages"]
            enriched[lid] = {
                "has_site": True,
                "pages_scraped": len(pages),
                "has_pricing": any(bool(p.get("pricing_mentions")) for p in pages),
                "has_contact_form": any(bool(p.get("contact_info")) for p in pages),
                "service_pages": sum(1 for p in pages if p.get("page_type") == "services"),
            }
        return enriched
    except Exception as e:
        log.warning(f"[b2b_qualifier] batch enrichment failed: {e}")
        return {}


def qualify_lead(lead: Dict, enrichment: Dict = None) -> Dict:
    """Score and classify a single B2B lead. Returns qualification dict."""
    enrichment = enrichment or {}
    components = {
        "email_quality": _email_quality(lead.get("email", "")),
        "website_quality": _website_quality(lead.get("website", "")),
        "contact_completeness": _contact_completeness(lead),
        "niche_signal": _niche_signal(lead.get("niche", "")),
        "enrichment_signal": _enrichment_signal(enrichment),
        "freshness": _freshness_score(lead.get("created_at", "")),
        "existing_score": _existing_lead_score(lead),
    }

    total = sum(components.values())  # max = 135 (15+15+20+25+20+15+25)
    normalized = min(round(total / 135 * 100), 100)

    if normalized >= 80:
        tier = TIER_HOT
    elif normalized >= 50:
        tier = TIER_WARM
    else:
        tier = TIER_COLD

    return {
        "score": normalized,
        "tier": tier,
        "components": components,
        "recommended_action": (
            "draft_outreach" if tier == "hot" else
            "enrich_then_draft" if tier == "warm" else
            "skip"
        ),
        "qualified_at": datetime.now(timezone.utc).isoformat(),
    }


async def qualify_lead_by_id(lead_id: str, dry_run: bool = False, fast: bool = False) -> Dict:
    """Qualify a single lead and persist the result."""
    try:
        sb = _get_sb()
        r = sb.table("b2b_leads").select("*").eq("id", lead_id).limit(1).execute()
        if not r.data:
            return {"ok": False, "error": "lead not found", "lead_id": lead_id}

        lead = r.data[0]
        enrichment = {} if fast else await _get_enrichments_batch([lead_id]).get(lead_id, {"has_site": False})
        qualification = qualify_lead(lead, enrichment)

        if dry_run:
            return {"ok": True, "lead_id": lead_id, "qualification": qualification, "dry_run": True}

        # Persist to meta
        existing_meta = lead.get("meta") or {}
        if isinstance(existing_meta, str):
            try:
                existing_meta = json.loads(existing_meta)
            except Exception:
                existing_meta = {}
        existing_meta["qualification"] = qualification

        sb.table("b2b_leads").update({
            "meta": existing_meta,
            "urgency": qualification["score"],
            "lead_score": qualification["score"],
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", lead_id).execute()

        log.info(f"[b2b_qualifier] {lead.get('company_name', '?')[:30]} — score={qualification['score']} tier={qualification['tier']}")
        return {"ok": True, "lead_id": lead_id, "qualification": qualification}
    except Exception as e:
        return {"ok": False, "error": str(e), "lead_id": lead_id}


async def qualify_batch(limit: int = 50, niche: str = "", metro: str = "", dry_run: bool = False, fast: bool = False) -> Dict:
    """Qualify a batch of B2B leads."""
    try:
        sb = _get_sb()
        query = sb.table("b2b_leads").select("id,company_name,email,phone,website,niche,metro,lead_score,created_at").order("lead_score", desc=True).limit(limit)

        if niche:
            query = query.eq("niche", niche)
        if metro:
            query = query.eq("metro", metro)

        r = query.execute()
        leads = r.data or []

        # Batch enrichment: 3 queries for 775 leads instead of 775
        enrichment_map: Dict[str, Dict] = {}
        if not fast and leads:
            lead_ids = [l["id"] for l in leads]
            enrichment_map = await _get_enrichments_batch(lead_ids)
            log.info(f"[b2b_qualifier] batched enrichment: {len(enrichment_map)}/{len(leads)} leads have site_content")

        results = {"total": len(leads), "qualified": 0, "hot": 0, "warm": 0, "cold": 0, "errors": 0, "dry_run": dry_run, "fast": fast}

        # Build updates in batches of 50 for faster writes
        updates = []
        for lead in leads:
            try:
                enrichment = enrichment_map.get(lead["id"], {"has_site": False})
                qualification = qualify_lead(lead, enrichment)

                if not dry_run:
                    existing_meta = lead.get("meta") or {}
                    if isinstance(existing_meta, str):
                        try:
                            existing_meta = json.loads(existing_meta)
                        except Exception:
                            existing_meta = {}
                    existing_meta["qualification"] = qualification
                    updates.append({
                        "id": lead["id"],
                        "meta": existing_meta,
                        "urgency": qualification["score"],
                        "lead_score": qualification["score"],
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    })

                results["qualified"] += 1
                results[qualification["tier"]] += 1
            except Exception:
                results["errors"] += 1

        # Batch-write updates in chunks of 50
        if updates and not dry_run:
            for i in range(0, len(updates), 50):
                chunk = updates[i:i+50]
                for u in chunk:
                    try:
                        sb.table("b2b_leads").update({
                            "meta": u["meta"],
                            "urgency": u["urgency"],
                            "lead_score": u["lead_score"],
                            "updated_at": u["updated_at"],
                        }).eq("id", u["id"]).execute()
                    except Exception:
                        pass

        log.info(f"[b2b_qualifier] batch: {results}")
        return results
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="B2B Lead Qualification Agent")
    ap.add_argument("--limit", type=int, default=50)
    ap.add_argument("--niche", type=str, default="")
    ap.add_argument("--metro", type=str, default="")
    ap.add_argument("--lead-id", type=str, default="")
    ap.add_argument("--all", action="store_true", help="Qualify all 775 leads")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--fast", action="store_true", help="Skip site_content enrichment queries (fast mode)")
    args = ap.parse_args()

    if args.lead_id:
        result = asyncio.run(qualify_lead_by_id(args.lead_id, dry_run=args.dry_run, fast=args.fast))
        print(json.dumps(result, indent=2))
    else:
        limit = 1000 if args.all else args.limit
        result = asyncio.run(qualify_batch(
            limit=limit,
            niche=args.niche,
            metro=args.metro,
            dry_run=args.dry_run,
            fast=args.fast,
        ))
        print(json.dumps(result, indent=2))
