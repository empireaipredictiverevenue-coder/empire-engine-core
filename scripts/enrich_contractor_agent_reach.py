"""
EMPIRE V49 · CONTRACTOR AGENT-REACH INTEL ENRICHER
===================================================
Runs Agent-Reach multi-source intelligence on contractors that have
real emails (from Clay or phone-matching) but no intel yet.

Modes:
  1. Per-contractor adaptive SI genome (DEFAULT): each contractor gets
     a genome matched to their specialties. A roofing contractor gets
     AGGRESSIVE_STRIKE (wide-net, emergency), a software firm gets
     FINANCIAL_STRIKE (tech-heavy channels). See NICHE_GENOME_MAP and
     genome_for_contractor().

  2. Global SI genome override: pass --genome-archetype or --genome to
     apply the same genome to ALL contractors. Useful for batch testing.

  3. Legacy pick_channels() fallback: pass --legacy to use the old
     1-2 channel approach (semantic_search ± github_search for tech).

SI genome traits (each 0.0-1.0):
    aggressiveness       — channel quantity (low=essential only, high=full suite)
    narrow_focus         — broad vs targeted (low=wide net, high=ultra-targeted)
    risk_tolerance        — experimental channels (cloudscraper, apify, crawl4ai)
    outreach_intensity    — volume multiplier for max_results
    price_premium         — paid/API-key channels (Google, Apify, Claude)

Results are written to contractors.meta.agent_reach_intel.

Rate-limited: 3.5s sleep between contractors to stay under 20/min
semantic search cap. ~1,000 contractors takes ~1 hour.

Usage:
    python3 scripts/enrich_contractor_agent_reach.py                     # per-contractor SI genome (dry-run)
    python3 scripts/enrich_contractor_agent_reach.py --deep-research --apply  # + LLM deep analysis
    python3 scripts/enrich_contractor_agent_reach.py --genome-archetype RECALL_SNIPER  # global override
    python3 scripts/enrich_contractor_agent_reach.py --genome '{"aggressiveness":0.7}'  # custom global
    python3 scripts/enrich_contractor_agent_reach.py --legacy            # old 1-2 channel mode
    python3 scripts/enrich_contractor_agent_reach.py --genome-tier SCRAPER_ENTERPRISE  # Enterprise channel pool
    python3 scripts/enrich_contractor_agent_reach.py --apply             # write to DB (adaptive mode)
    python3 scripts/enrich_contractor_agent_reach.py --deep-research --apply  # + LLM deep analysis
    python3 scripts/enrich_contractor_agent_reach.py --genome-archetype AGGRESSIVE_STRIKE --apply
    python3 scripts/enrich_contractor_agent_reach.py --genome-tier SCRAPER_ENTERPRISE --genome-archetype FINANCIAL_STRIKE --apply
    python3 scripts/enrich_contractor_agent_reach.py --limit 10          # first 10 only

Integrates with Clay workflow:
    1. Clay enriches contractor emails → updates contractors.email
    2. Run this script → adds multi-source intel to meta.agent_reach_intel
    3. Also chainable via: python3 scripts/enrich_contractor_emails.py --agent-reach
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass

from supabase import create_client

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from products.agent_reach_enrichment import AgentReachEnricher, TIER_CHANNELS
from empire_si_core import beta_posterior
from bots.predictive_deep_research_agent import PredictiveDeepResearchAgent

logging.basicConfig(level=logging.INFO, format="%(asctime)s:%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("enrich.agent_reach")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)

# ── Rate limits ─────────────────────────────────────────────────────
# Lowest limit is semantic_search at 20/min = 1 per 3.0s.
# We use 3.5s to provide a safety margin.
RATE_LIMIT_SLEEP = 3.5

# Channels run per contractor (always semantic, optional others)
DEFAULT_CHANNELS = ["semantic_search"]

# Specialties that suggest the contractor might have a GitHub/tech presence
TECH_SPECIALTIES = {
    "software", "it_services", "technology", "web_development",
    "app_development", "data_science", "ai", "machine_learning",
    "cybersecurity", "cloud", "devops", "saas",
}

# SI Genome archetypes for --genome-archetype CLI arg
GENOME_ARCHETYPES = {
    "AGGRESSIVE_STRIKE": {
        "description": "Wide-net aggressive — maximum channel coverage, high volume, paid channels enabled",
        "genome": {"aggressiveness": 0.9, "narrow_focus": 0.3, "risk_tolerance": 0.7, "price_premium": 0.8, "outreach_intensity": 0.9},
    },
    "RECALL_SNIPER": {
        "description": "Precision-targeted — ultra-focused on high-intent signals, social + paid channels",
        "genome": {"aggressiveness": 0.7, "narrow_focus": 0.8, "risk_tolerance": 0.5, "price_premium": 0.5, "outreach_intensity": 0.8},
    },
    "UGLY_BANNER": {
        "description": "Conservative — no paid channels, no experimental, moderate volume",
        "genome": {"aggressiveness": 0.4, "narrow_focus": 0.5, "risk_tolerance": 0.3, "price_premium": 0.2, "outreach_intensity": 0.6},
    },
    "FINANCIAL_STRIKE": {
        "description": "Balanced-aggressive — wide coverage with paid channels and high volume",
        "genome": {"aggressiveness": 0.8, "narrow_focus": 0.4, "risk_tolerance": 0.6, "price_premium": 0.7, "outreach_intensity": 0.7},
    },
    "STANDARD": {
        "description": "Balanced — moderate coverage with paid channels at baseline volume",
        "genome": {"aggressiveness": 0.5, "narrow_focus": 0.5, "risk_tolerance": 0.5, "price_premium": 0.5, "outreach_intensity": 0.5},
    },
}

# ── Per-Contractor Niche-to-Genome Mapping ─────────────────────────
# Maps contractor specialties to the best SI genome archetype.
# The order matters: first match wins.
NICHE_GENOME_MAP = [
    # Storm / emergency niches → AGGRESSIVE_STRIKE (wide-net, high urgency)
    (["roofing", "storm_damage", "restoration", "water_damage",
      "mold", "fire_damage", "flood", "hail", "wind",
      "water_mitigation"], "AGGRESSIVE_STRIKE"),
    # Trades with high urgency → AGGRESSIVE_STRIKE
    (["plumbing", "electrical", "hvac", "appliance_repair",
      "emergency", "towing", "ductwork"], "AGGRESSIVE_STRIKE"),
    # High-ticket professional services → RECALL_SNIPER (precision, high-intent)
    (["legal", "lawyer", "attorney", "personal_injury", "mass_tort",
      "insurance", "medicare", "life_insurance", "final_expense",
      "financial", "debt", "mortgage", "investment", "tax",
      "business_loan_broker", "loan_broker", "credit_repair",
      "debt_consolidation"], "RECALL_SNIPER"),
    # Business / tech / professional services → FINANCIAL_STRIKE (tech-heavy channels)
    (["software", "it_services", "technology", "web_development",
      "app_development", "data_science", "ai", "machine_learning",
      "cybersecurity", "cloud", "devops", "saas", "managed_it",
      "staffing", "hr", "payroll", "voip", "merchant_services",
      "property_management", "property_manager"], "FINANCIAL_STRIKE"),
    # Healthcare / senior care / vocational education → FINANCIAL_STRIKE
    (["healthcare", "senior_care", "assisted_living", "home_health",
      "addiction_treatment", "mental_health", "hospice", "dental",
      "nursing_school", "medical_alert_system", "medical_alert",
      "cdl_truck_driving_school", "cdl_school", "truck_driving_school"], "FINANCIAL_STRIKE"),
    # Low-ticket trades + home services → UGLY_BANNER (conservative, no paid)
    (["painting", "landscaping", "lawn_care", "fencing", "cleaning",
      "carpet_cleaning", "moving", "storage", "junk_removal",
      "pest_control", "window_cleaning", "pressure_washing",
      "tree_removal", "tree_service", "general_contractor",
      "gutter", "gutter_cleaning",
      "interior_design", "interior_designer",
      "home_repairs", "home_repair", "handyman",
      "construction", "construction_company"], "UGLY_BANNER"),
    # Solar + remodel → UGLY_BANNER (high ticket but long cycle, conservative approach)
    (["solar", "remodeling", "bath_remodel", "kitchen_remodel",
      "flooring", "concrete"], "UGLY_BANNER"),
    # Automotive → UGLY_BANNER (service trades, low-mid ticket)
    (["auto_repair", "car_dealership", "auto_body_shop", "auto_detailing",
      "car_wash", "auto_glass", "auto_mechanic", "transmission",
      "tire_shop", "oil_change", "auto_loan", "auto_financing"], "UGLY_BANNER"),
    # Hospitality → UGLY_BANNER (service-oriented, moderate ticket)
    (["hotel", "restaurant", "catering", "hospitality",
      "event_venue", "banquet", "bar", "nightclub",
      "bed_and_breakfast", "food_truck", "bakery", "brewery"], "UGLY_BANNER"),
    # Beauty → UGLY_BANNER (personal service, low-ticket)
    (["salon", "barber", "spa", "nail_salon", "beauty",
      "cosmetology", "hair_salon", "massage_therapy", "esthetician",
      "makeup_artist", "lash_studio", "tanning", "tattoo"], "UGLY_BANNER"),
    # Pets → UGLY_BANNER (personal service, low-ticket)
    (["pet_grooming", "veterinary", "pet_sitting", "dog_walking",
      "pet_boarding", "animal_hospital", "pet_care", "pet_store",
      "dog_training", "animal_shelter"], "UGLY_BANNER"),
    # Real estate → RECALL_SNIPER (high-ticket, precision-targeted)
    (["real_estate", "realtor", "real_estate_agent", "home_inspection",
      "property_inspection", "real_estate_investment", "property_investment",
      "real_estate_appraisal", "title_company", "escrow",
      "property_valuation"], "RECALL_SNIPER"),
    # Security → FINANCIAL_STRIKE (business services, recurring contracts)
    (["security", "alarm", "security_system", "security_guard",
      "surveillance", "cctv", "access_control", "home_security",
      "security_consulting", "fire_alarm", "monitoring_service"], "FINANCIAL_STRIKE"),
    # Education → FINANCIAL_STRIKE (professional services, training)
    (["education", "tutoring", "training", "school", "preschool",
      "daycare", "learning_center", "academic", "college", "university",
      "vocational_training", "adult_education", "test_prep"], "FINANCIAL_STRIKE"),
    # Logistics → FINANCIAL_STRIKE (business services, B2B contracts)
    (["logistics", "trucking", "freight", "courier", "delivery_service",
      "warehousing", "supply_chain", "transportation", "shipping",
      "fleet", "dispatch", "cargo"], "FINANCIAL_STRIKE"),
    # Manufacturing → FINANCIAL_STRIKE (B2B, industrial, business services)
    (["manufacturing", "manufacturer", "factory", "industrial",
      "fabrication", "machining", "assembly", "production",
      "warehouse", "distribution", "plant"], "FINANCIAL_STRIKE"),
]


def get_db():
    return sb


def get_pending_contractors(limit: int = 0) -> list[dict]:
    """Fetch contractors with real emails that haven't been intel-enriched yet.

    A contractor is "pending" if:
      - email is present and NOT a placeholder
      - meta.agent_reach_intel is not set (or empty)
    """
    # Fetch all active contractors with real emails
    r = sb.table("contractors") \
        .select("id,name,email,phone,metro,specialties,meta") \
        .eq("active", True) \
        .not_.is_("email", "null") \
        .limit(2000) \
        .execute()

    all_contractors = r.data or []

    # Filter: real email only (no placeholders)
    pending = []
    for c in all_contractors:
        email = (c.get("email") or "").strip()
        if not email or "placeholder" in email.lower() or "prospector" in email.lower():
            continue

        meta = c.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}

        # Skip if already has agent_reach_intel
        if meta.get("agent_reach_intel"):
            continue

        # Parse specialties from JSONB if needed
        specialties = c.get("specialties") or []
        if isinstance(specialties, str):
            try:
                specialties = json.loads(specialties)
            except (json.JSONDecodeError, TypeError):
                specialties = [specialties] if specialties else []

        c["_specialties_parsed"] = specialties if isinstance(specialties, list) else []
        c["_meta_parsed"] = meta
        pending.append(c)

    if limit and limit > 0:
        pending = pending[:limit]

    return pending


def pick_channels(contractor: dict) -> list[str]:
    """Pick the most relevant Agent-Reach channels for this contractor."""
    channels = list(DEFAULT_CHANNELS)  # semantic_search always

    # Add github_search if they're tech-adjacent
    specialties = contractor.get("_specialties_parsed", [])
    if isinstance(specialties, list):
        specs_lower = {s.lower().replace(" ", "_") for s in specialties if isinstance(s, str)}
    # Use same guard as genome_for_contractor: short keywords (< 3 chars)
    # only match exactly to avoid "ai" matching "painting"
    if any(tech in spec and (len(tech) >= 3 or tech == spec)
           for spec in specs_lower for tech in TECH_SPECIALTIES):
        channels.append("github_search")

    return channels


def genome_for_contractor(contractor: dict) -> dict:
    """Derive an SI genome for a contractor based on their specialties.

    Uses NICHE_GENOME_MAP to find the best archetype match, then returns
    the corresponding genome dict. Falls back to STANDARD if no specialty
    matches.

    Args:
        contractor: Contractor dict with _specialties_parsed field

    Returns:
        SI genome dict with aggressiveness, narrow_focus, etc. traits
    """
    specialties = contractor.get("_specialties_parsed", [])
    if not isinstance(specialties, list) or not specialties:
        return GENOME_ARCHETYPES["STANDARD"]["genome"]

    specs_lower = {s.lower().replace(" ", "_").replace("-", "_") for s in
                   specialties if isinstance(s, str)}

    # Use substring matching: check if any NICHE_GENOME_MAP keyword is
    # contained within any normalized specialty string.
    # E.g. "life_insurance_agent" contains "insurance" → RECALL_SNIPER.
    # Short keywords (< 3 chars) only match exactly to avoid false
    # positives (e.g. "ai" in "painting").
    for keywords, archetype_name in NICHE_GENOME_MAP:
        for spec in specs_lower:
            for kw in keywords:
                if kw in spec and (len(kw) >= 3 or kw == spec):
                    return GENOME_ARCHETYPES[archetype_name]["genome"]

    # Fallback: check TECH_SPECIALTIES for broad tech match
    specs_flat = " ".join(specs_lower)
    if any(tech in specs_flat for tech in TECH_SPECIALTIES):
        return GENOME_ARCHETYPES["FINANCIAL_STRIKE"]["genome"]

    return GENOME_ARCHETYPES["STANDARD"]["genome"]


def compute_enrichment_quality_aggregates() -> dict:
    """Query Supabase for all contractor enrichment scores and compute
    per-archetype aggregate quality statistics.

    Reads from contractors.meta.agent_reach_intel.score for every contractor
    that has been enriched, then groups by archetype (inferred from the stored
    score or from the contractor's specialties).

    Returns:
        dict with:
          - archetypes: {archetype_name: {count, mean_overall, mean_quality,
                           mean_richness, priority_distribution: {high, medium, low}}}
          - overall: {total_enriched, mean_overall, mean_quality,
                       enrichment_health (0-1)}
          - trend: {previous_overall, previous_quality} (from stored aggregate
                    in an enrichment_stats table if available)
    """
    try:
        r = sb.table("contractors").select("id,name,specialties,meta").not_.is_("meta", "null").limit(5000).execute()
    except Exception as e:
        log.warning(f"[enrich.aggregate] query failed: {e}")
        return {"error": str(e)}

    if not r.data:
        return {"archetypes": {}, "overall": {"total_enriched": 0, "enrichment_health": 0.5}}

    # Group by archetype
    by_archetype = {}  # archetype_name -> list of scores
    total_enriched = 0

    for c in (r.data or []):
        meta = c.get("meta") or {}
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (json.JSONDecodeError, TypeError):
                meta = {}
        if not isinstance(meta, dict):
            continue

        intel = meta.get("agent_reach_intel", {})
        if not intel:
            continue

        score = intel.get("score") if isinstance(intel, dict) else None
        if not score or not isinstance(score, dict):
            continue

        total_enriched += 1

        # Determine archetype — from stored score context or specialties
        # The score dict itself doesn't store the archetype name, so we
        # back-derive it from the stored genome/archetype in the intel,
        # or fall back to the contractor's specialties
        archetype = intel.get("archetype", "") if isinstance(intel, dict) else ""
        if not archetype:
            # Try to derive from specialties
            specialties = c.get("specialties", [])
            if isinstance(specialties, str):
                try:
                    specialties = json.loads(specialties)
                except (json.JSONDecodeError, TypeError):
                    specialties = [specialties] if specialties else []
            if isinstance(specialties, list):
                specs_lower = {s.lower().replace(" ", "_").replace("-", "_") for s in specialties if isinstance(s, str)}
                for keywords, archetype_name in NICHE_GENOME_MAP:
                    for spec in specs_lower:
                        for kw in keywords:
                            if kw in spec and (len(kw) >= 3 or kw == spec):
                                archetype = archetype_name
                                break
                        if archetype:
                            break
                    if archetype:
                        break
        if not archetype:
            archetype = "UNKNOWN"

        by_archetype.setdefault(archetype, []).append(score)

    # Compute aggregates per archetype
    archetype_results = {}
    for arch, scores in sorted(by_archetype.items()):
        n = len(scores)
        mean_overall = sum(s.get("overall", 0) for s in scores) / n
        mean_quality = sum(s.get("quality", 0) for s in scores) / n
        mean_richness = sum(s.get("intel_richness", 0) for s in scores) / n
        priorities = {"high": 0, "medium": 0, "low": 0}
        for s in scores:
            p = s.get("priority", "low")
            if p in priorities:
                priorities[p] += 1
        archetype_results[arch] = {
            "count": n,
            "mean_overall": round(mean_overall, 4),
            "mean_quality": round(mean_quality, 4),
            "mean_richness": round(mean_richness, 4),
            "priority_distribution": priorities,
        }

    # Overall enrichment health: weighted average across all enriched contractors
    if total_enriched > 0:
        all_overalls = []
        for scores in by_archetype.values():
            all_overalls.extend(s.get("overall", 0) for s in scores)
        overall_mean = sum(all_overalls) / len(all_overalls) if all_overalls else 0.5
        # Enrichment health: 0-1 where <0.4 = poor, >0.7 = good
        enrichment_health = overall_mean
    else:
        overall_mean = 0.5
        enrichment_health = 0.5

    # Overall quality (Bayesian aggregate)
    if total_enriched > 0:
        all_qualities = []
        for scores in by_archetype.values():
            all_qualities.extend(s.get("quality", 0) for s in scores)
        overall_quality = sum(all_qualities) / len(all_qualities) if all_qualities else 0.5
    else:
        overall_quality = 0.5

    return {
        "archetypes": archetype_results,
        "overall": {
            "total_enriched": total_enriched,
            "mean_overall": round(overall_mean, 4),
            "mean_quality": round(overall_quality, 4),
            "enrichment_health": round(enrichment_health, 4),
        },
    }


def score_enrichment(enrichment_result: dict) -> dict:
    """Score an Agent-Reach enrichment result using SI Core Bayesian primitives.

    Produces a Bayesian-calibrated contractor quality score with four dimensions:

      1. intel_richness (0-1): how much useful data was gathered
         - Channel hit rate (60%%): %% of channels that returned successful results
         - Data depth (40%%): total chars collected across all channels (capped at 10KB)

      2. archetype_fit (0-1): whether the SI genome archetype matched well
         - Named archetype (AGGRESSIVE_STRIKE, RECALL_SNIPER, etc.): 0.8
         - STANDARD (no specialty match): 0.5
         - No archetype / error / legacy: 0.3-0.4

      3. quality (0-1): Bayesian-calibrated probability
         - Uses beta_posterior() from SI Core with pseudo-observations
         - Pseudo-wins from intel_richness + archetype_fit signals

      4. overall (0-1): weighted combination
         - 30%% intel_richness + 20%% archetype_fit + 50%% quality

      5. priority: high (>=0.7), medium (>=0.4), low (<0.4)

    Args:
        enrichment_result: Dict with keys channels, results, archetype, total_hits

    Returns:
        Score dict with overall, intel_richness, archetype_fit, quality, priority
    """
    results = enrichment_result.get("results", {})
    channels = enrichment_result.get("channels", [])
    archetype = enrichment_result.get("archetype", "")

    if not channels or enrichment_result.get("error"):
        return {
            "overall": 0.0,
            "intel_richness": 0.0,
            "archetype_fit": 0.3 if enrichment_result.get("error") else 0.5,
            "quality": 0.5,
            "priority": "low",
            "score_version": 1,
        }

    # ── 1. Intel Richness ───────────────────────────────────────
    # Channel hit rate: how many channels returned successful data
    ok_count = 0
    for ch in channels:
        r = results.get(ch, {})
        if isinstance(r, dict) and r.get("ok"):
            ok_count += 1
    hit_rate = ok_count / max(len(channels), 1)

    # Data depth: total characters collected across all successful channels
    total_bytes = 0
    for ch in channels:
        r = results.get(ch, {})
        if not isinstance(r, dict) or not r.get("ok"):
            continue
        data = r.get("data", {})
        if isinstance(data, dict):
            text = data.get("text", "")
            if isinstance(text, str):
                total_bytes += len(text)
            items = data.get("items", [])
            if isinstance(items, list):
                total_bytes += sum(len(json.dumps(i)) for i in items[:20])
            results_list = data.get("results", [])
            if isinstance(results_list, list):
                total_bytes += sum(len(json.dumps(i)) for i in results_list[:20])
        elif isinstance(data, str):
            total_bytes += len(data)

    depth_factor = min(1.0, total_bytes / 10000)  # 10KB = full score
    intel_richness = 0.6 * hit_rate + 0.4 * depth_factor

    # ── 2. Archetype Fit ────────────────────────────────────────
    if archetype and archetype not in ("STANDARD", "custom", "legacy", ""):
        archetype_fit = 0.8  # Well-matched archetype
    elif archetype == "STANDARD":
        archetype_fit = 0.5  # Generic fallback
    elif not archetype:
        archetype_fit = 0.4  # No archetype info (legacy mode)
    else:
        archetype_fit = 0.4  # Custom or unknown

    # ── 3. Quality (Bayesian) ───────────────────────────────────
    # Convert enrichment signals into pseudo-wins/losses for beta posterior.
    # All values are kept as integers to avoid truncation issues with int().
    # Beta(1,1) uniform prior + pseudo-observations.
    pseudo_wins = 0
    pseudo_losses = 0

    # Signal from intel_richness
    if intel_richness > 0.5:
        pseudo_wins += 2  # strong positive signal
    elif intel_richness > 0.3:
        pseudo_wins += 1  # weak positive
    else:
        pseudo_losses += 1  # poor data collection

    # Signal from archetype_fit
    if archetype_fit >= 0.8:
        pseudo_wins += 1  # well-matched archetype
    elif archetype_fit < 0.4:
        pseudo_losses += 1  # poor match

    # Signal from total_hits
    total_hits = enrichment_result.get("total_hits", 0)
    if total_hits >= 5:
        pseudo_wins += 2  # strong signal — lots of data found
    elif total_hits >= 2:
        pseudo_wins += 1  # weak positive
    else:
        pseudo_losses += 1

    # Compute Bayesian posterior with integer pseudo-observations
    post = beta_posterior(pseudo_wins, pseudo_losses)
    quality = post["mean"]

    # ── 4. Overall Score ────────────────────────────────────────
    overall = 0.3 * intel_richness + 0.2 * archetype_fit + 0.5 * quality
    overall = max(0.0, min(1.0, overall))

    # ── 5. Priority ─────────────────────────────────────────────
    if overall >= 0.7:
        priority = "high"
    elif overall >= 0.4:
        priority = "medium"
    else:
        priority = "low"

    return {
        "overall": round(overall, 4),
        "intel_richness": round(intel_richness, 4),
        "archetype_fit": round(archetype_fit, 4),
        "quality": round(quality, 4),
        "priority": priority,
        "score_version": 1,
    }


def archetype_for_genome(genome: dict) -> str:
    """Look up the archetype name that matches a genome dict.

    Returns the archetype name if found, 'custom' if it's a custom genome,
    or 'STANDARD' for the default.
    """
    # Normalize: sort keys to compare dicts
    genome_sorted = tuple(sorted(genome.items()))
    for name, entry in GENOME_ARCHETYPES.items():
        if tuple(sorted(entry["genome"].items())) == genome_sorted:
            return name
    return "custom"


async def enrich_one(
    enricher: AgentReachEnricher,
    contractor: dict,
    dry_run: bool = True,
    genome: dict = None,
    legacy: bool = False,
    genome_tier: str = "SCRAPER_PRO",
) -> dict:
    """Run Agent-Reach enrichment for a single contractor.

    Strategy (in priority order):
      1. If `genome` is provided, use it (global override from CLI).
      2. If `legacy` is True, use pick_channels() (1-2 channel old approach).
      3. Default: derive SI genome from contractor specialties via
         genome_for_contractor() for per-contractor adaptive channel selection.

    Args:
        enricher: AgentReachEnricher instance
        contractor: Contractor dict with _specialties_parsed
        dry_run: If True, just report what would happen
        genome: SI genome dict (global override, or None for per-contractor)
        legacy: If True, use old pick_channels() approach
        genome_tier: Channel pool tier (SCRAPER_PRO or SCRAPER_ENTERPRISE)
    """
    cid = contractor["id"]
    name = contractor.get("name", "Unknown")
    metro = contractor.get("metro", "")
    query = f"{name} {metro} contractor"

    # ── Resolve genome ──
    # If no global genome is provided and not in legacy mode, derive per-contractor
    use_genome = genome
    use_legacy = legacy
    if use_genome is None and not use_legacy:
        use_genome = genome_for_contractor(contractor)

    # Resolve channel pool from tier
    tier_channels = list(TIER_CHANNELS.get(genome_tier, TIER_CHANNELS["SCRAPER_PRO"]))

    if dry_run:
        if use_genome:
            si_channels = AgentReachEnricher._si_select_channels(use_genome, tier_channels)
            vol = AgentReachEnricher._si_volume_multiplier(use_genome)
            archetype = archetype_for_genome(use_genome)
            return {
                "id": cid,
                "name": name,
                "metro": metro,
                "specialties": contractor.get("_specialties_parsed", []),
                "query": query,
                "channels": si_channels,
                "genome": use_genome,
                "archetype": archetype,
                "volume": vol,
                "scaled_max": max(5, int(5 * vol)),
                "dry_run": True,
            }
        else:
            channels = pick_channels(contractor)
            return {
                "id": cid,
                "name": name,
                "metro": metro,
                "specialties": contractor.get("_specialties_parsed", []),
                "query": query,
                "channels": channels,
                "genome": None,
                "dry_run": True,
            }

    # ── Live enrichment ──
    try:
        if use_genome:
            # ── SI-driven: use unified enrich() with genome ──
            result = await enricher.enrich(
                query=query,
                channels=list(tier_channels),
                max_results=5,
                tier=genome_tier,
                save_to_db=False,
                genome=use_genome,
                metadata={
                    "source": "enrich_contractor_agent_reach",
                    "contractor_id": cid,
                    "contractor_name": name,
                },
            )
            if result.get("ok"):
                archetype = archetype_for_genome(use_genome)
                enrichment_dict = {
                    "id": cid,
                    "name": name,
                    "metro": metro,
                    "specialties": contractor.get("_specialties_parsed", []),
                    "query": query,
                    "channels": result["channels_used"],
                    "genome": use_genome,
                    "archetype": archetype,
                    "volume": AgentReachEnricher._si_volume_multiplier(use_genome),
                    "results": result["results"],
                    "total_hits": result["total_hits"],
                    "dry_run": False,
                }
                # Score enrichment using SI Core Bayesian primitives
                enrichment_dict["score"] = score_enrichment(enrichment_dict)
                return enrichment_dict
            else:
                return {
                    "id": cid,
                    "name": name,
                    "error": result.get("error", "SI enrichment failed"),
                    "dry_run": False,
                }
        else:
            # ── Legacy: use pick_channels() + individual channel calls ──
            channels = pick_channels(contractor)
            tasks = []
            for ch in channels:
                if ch == "semantic_search":
                    tasks.append(enricher.semantic_search(query, max_results=5))
                elif ch == "jina_read":
                    tasks.append(enricher.jina_read(query))
                elif ch == "github_search":
                    tasks.append(enricher.github_search(name, max_results=5))

            gathered = await asyncio.gather(*tasks, return_exceptions=True)

            results = {}
            for ch, r in zip(channels, gathered):
                if isinstance(r, Exception):
                    results[ch] = {"ok": False, "error": str(r)[:120]}
                else:
                    results[ch] = r

            return {
                "id": cid,
                "name": name,
                "metro": metro,
                "query": query,
                "channels": channels,
                "genome": None,
                "results": results,
                "dry_run": False,
            }
    except Exception as e:
        return {
            "id": cid,
            "name": name,
            "error": str(e)[:200],
            "genome": genome is not None,
            "dry_run": False,
        }


def write_to_db(enrichment_results: list[dict]):
    """Write Agent-Reach intel back to contractors.meta."""
    written = 0
    errors = 0
    for er in enrichment_results:
        if er.get("dry_run"):
            continue
        if er.get("error"):
            errors += 1
            continue

        cid = er["id"]
        try:
            # Fetch current meta
            cur = sb.table("contractors").select("meta").eq("id", cid).limit(1).execute()
            existing_meta = cur.data[0].get("meta", {}) if cur.data else {}
            if isinstance(existing_meta, str):
                try:
                    existing_meta = json.loads(existing_meta)
                except (json.JSONDecodeError, TypeError):
                    existing_meta = {}
            if not isinstance(existing_meta, dict):
                existing_meta = {}

            # Store intel under meta.agent_reach_intel
            intel_data = {
                "enriched_at": datetime.now(timezone.utc).isoformat(),
                "query": er.get("query", ""),
                "channels_used": er.get("channels", []),
                "results": er.get("results", {}),
            }
            # Include SI Core Bayesian score if computed
            score = er.get("score")
            if score and isinstance(score, dict):
                intel_data["score"] = score
            # Include deep research results if computed
            deep_research = er.get("deep_research")
            if deep_research and isinstance(deep_research, dict):
                intel_data["deep_research"] = deep_research
            existing_meta["agent_reach_intel"] = intel_data

            sb.table("contractors").update({"meta": existing_meta}).eq("id", cid).execute()
            written += 1
        except Exception as e:
            log.warning(f"[agent_reach] write failed for {er.get('name', cid)}: {e}")
            errors += 1

    return written, errors


async def run_enrichment(dry_run: bool = True, limit: int = 0, genome: dict = None,
                         genome_archetype: str = "", legacy: bool = False,
                         genome_tier: str = "SCRAPER_PRO",
                         deep_research: bool = False):
    """Main enrichment loop.

    Args:
        dry_run: If True, report what would happen without calling live APIs
        limit: Max contractors to process (0 = all)
        genome: SI genome dict (global override, or None for per-contractor adaptive)
        genome_archetype: Human-readable archetype name for reporting
        legacy: If True, use old pick_channels() approach instead of SI genome
        genome_tier: Channel pool tier (SCRAPER_PRO or SCRAPER_ENTERPRISE)
    """
    contractors = get_pending_contractors(limit=limit)
    total = len(contractors)

    if not contractors:
        log.info("No contractors need Agent-Reach enrichment — all up to date")
        return

    tier_channels = list(TIER_CHANNELS.get(genome_tier, TIER_CHANNELS["SCRAPER_PRO"]))

    if legacy:
        mode_label = "LEGACY (pick_channels)"
    elif genome:
        mode_label = f"GLOBAL SI GENOME: {genome_archetype}"
    else:
        mode_label = "PER-CONTRACTOR ADAPTIVE SI GENOME"

    log.info(f"{'DRY RUN' if dry_run else 'APPLY'} — {total} contractors pending · {mode_label}")
    log.info(f"Channel pool: {genome_tier} ({len(tier_channels)} channels)")
    if genome:
        vol = AgentReachEnricher._si_volume_multiplier(genome)
        si_channels = AgentReachEnricher._si_select_channels(genome, tier_channels)
        log.info(f"SI genome selects {len(si_channels)}/{len(tier_channels)} channels at {vol:.2f}x volume")
        log.info(f"SI channels: {', '.join(si_channels)}")
    if not dry_run:
        est_minutes = total * RATE_LIMIT_SLEEP / 60
        log.info(f"Rate limit: {RATE_LIMIT_SLEEP}s/contractor · estimated {est_minutes:.0f} min")

    enricher = AgentReachEnricher(get_db=get_db)
    deep_researcher = PredictiveDeepResearchAgent() if deep_research else None
    enrichment_results = []

    for i, c in enumerate(contractors):
        result = await enrich_one(enricher, c, dry_run=dry_run, genome=genome, legacy=legacy,
                                   genome_tier=genome_tier)

        # ── Deep research (after scoring) ──
        if deep_research and deep_researcher and not dry_run and not result.get("error"):
            deep_result = await deep_researcher.research_from_enrichment(
                contractor_name=result.get("name", ""),
                metro=result.get("metro", ""),
                archetype=result.get("archetype", "STANDARD"),
                specialties=result.get("specialties", []),
                enrichment_results=result.get("results", {}),
                channels_used=result.get("channels", []),
            )
            result["deep_research"] = deep_result
            llm = "LLM" if deep_result.get("llm_available") else "no-LLM"
            conf = deep_result.get("analysis", {}).get("confidence", 0)
            log.info(f"  [{i+1:4d}/{total}] DPR {result.get('name','?')[:35]:35s} "
                     f"{llm} conf={conf:.2f}")

        # Progress indicator
        name = c.get("name", "?")[:35]
        channels = result.get("channels", [])
        status = "DRY" if dry_run else "OK"
        if result.get("error"):
            status = "ERR"
        # Show archetype for per-controller adaptive mode
        archetype = result.get("archetype", "")
        if archetype and not genome:
            ch_str = f"{archetype[:12]:12s} {len(channels):2d}ch"
        elif genome:
            ch_str = f"{genome_archetype[:12]:12s} {len(channels):2d}ch"
        else:
            ch_str = str(channels)
        log.info(f"  [{i+1:4d}/{total}] {status} {name:35s} {ch_str}")

        enrichment_results.append(result)

        # Rate-limit sleep (only in live mode)
        if not dry_run and i < total - 1:
            await asyncio.sleep(RATE_LIMIT_SLEEP)

    # ── Write to DB ──
    written = errors = 0
    if not dry_run:
        written, errors = write_to_db(enrichment_results)

    # ── Print summary ──
    total_ok = sum(1 for r in enrichment_results if not r.get("error") and not r.get("dry_run"))
    total_dry = sum(1 for r in enrichment_results if r.get("dry_run"))
    total_err = sum(1 for r in enrichment_results if r.get("error"))

    channel_usage = {}
    archetype_counts = {}
    for r in enrichment_results:
        for ch in r.get("channels", []):
            channel_usage[ch] = channel_usage.get(ch, 0) + 1
        arch = r.get("archetype", "legacy")
        archetype_counts[arch] = archetype_counts.get(arch, 0) + 1

    tier_label = genome_tier.replace("SCRAPER_", "").title()

    if not legacy and not genome:
        # Adaptive mode: count unique per-contractor archetypes used
        unique_archetypes = sorted(archetype_counts.items())
        mode_name = "PER-CONTRACTOR ADAPTIVE SI"
    elif legacy:
        unique_archetypes = []
        mode_name = "LEGACY (pick_channels)"
    else:
        unique_archetypes = []
        mode_name = f"GLOBAL SI: {genome_archetype}"

    print()
    print("=" * 60)
    print(f"  CONTRACTOR AGENT-REACH INTEL — {mode_name}")
    print(f"  {'(DRY RUN)' if dry_run else '(APPLIED)'}")
    print("=" * 60)
    print(f"  Contractors scanned:          {total}")
    print(f"  Enrichment mode:              {mode_name}")
    print(f"  Channel pool tier:            {genome_tier} ({tier_label}, {len(tier_channels)} channels)")
    if genome:
        print(f"  Global archetype:             {genome_archetype}")
        print(f"  SI traits:                    a={genome.get('aggressiveness','?'):>4} n={genome.get('narrow_focus','?'):>4} "
              f"o={genome.get('outreach_intensity','?'):>4} r={genome.get('risk_tolerance','?'):>4} "
              f"p={genome.get('price_premium','?'):>4}")
        vol = AgentReachEnricher._si_volume_multiplier(genome)
        print(f"  Volume multiplier:            {vol:.2f}x (max_results scaled)")
    if unique_archetypes:
        print(f"  Per-contractor archetypes:    {len(unique_archetypes)}")
        for arch, count in unique_archetypes:
            desc = GENOME_ARCHETYPES.get(arch, {}).get("description", "custom")[:50]
            print(f"    {arch:20s} {count:4d} contractors  ({desc})")
        avg_channels = sum(len(r.get("channels", [])) for r in enrichment_results if not r.get("error")) / max(total - total_err, 1)
        print(f"  Avg channels/contractor:      {avg_channels:.1f}")
    print(f"  Successfully enriched:        {total_ok}")
    print(f"  Dry run (no call):            {total_dry}")
    print(f"  Errors:                       {total_err}")
    print(f"  Channel usage:")
    for ch, count in sorted(channel_usage.items()):
        print(f"    {ch:25s} {count:4d}")
    if not dry_run:
        print(f"  Written to DB:                {written}")
        print(f"  Write errors:                 {errors}")
    # Deep research stats
    deep_researched = sum(1 for r in enrichment_results if r.get("deep_research"))
    deep_llm = sum(1 for r in enrichment_results
                    if r.get("deep_research", {}).get("llm_available"))
    if deep_researched:
        print(f"  Deep researched:              {deep_researched}")
        print(f"  With LLM analysis:            {deep_llm}")
    print()

    # Show sample results
    if enrichment_results:
        print("  SAMPLE RESULTS:")
        for r in enrichment_results[:5]:
            name = r.get("name", "?")[:35]
            arch = r.get("archetype", "")
            if r.get("dry_run"):
                channels = r.get("channels", [])
                if r.get("genome"):
                    vol = r.get("volume", 1.0)
                    sm = r.get("scaled_max", 5)
                    specs = r.get("specialties", [])
                    arch_tag = f"{arch:16s}" if arch else ""
                    print(f"    [DRY] {name:35s} {arch_tag} {len(channels)}ch vol={vol:.2f}x max={sm}")
                else:
                    print(f"    [DRY] {name:35s} → {channels}")
                continue
            if r.get("error"):
                print(f"    [ERR] {name:35s} → {r.get('error', '')[:60]}")
                continue
            results = r.get("results", {})
            if not results:
                print(f"    [OK]  {name:35s} {arch} (no per-channel results)")
                continue
            for ch, cr in results.items():
                if cr.get("ok"):
                    data = cr.get("data", {})
                    if isinstance(data, dict) and "text" in data:
                        size = len(data["text"])
                        print(f"    [OK]  {name:35s} {arch:12s} {ch}: {size} chars")
                    elif isinstance(data, dict) and "items" in data:
                        print(f"    [OK]  {name:35s} {arch:12s} {ch}: {len(data['items'])} items")
                    else:
                        print(f"    [OK]  {name:35s} {arch:12s} {ch}: data received")
                else:
                    print(f"    [ERR] {name:35s} {arch:12s} {ch}: {cr.get('error', '?')[:40]}")
        if len(enrichment_results) > 5:
            print(f"    ... and {len(enrichment_results) - 5} more")

    return {
        "dry_run": dry_run,
        "mode": "per_contractor_adaptive" if not genome and not legacy else
                ("global_si_genome" if genome else "legacy"),
        "genome_archetype": genome_archetype if genome else None,
        "genome_tier": genome_tier,
        "archetype_counts": archetype_counts if not genome and not legacy else None,
        "total_scanned": total,
        "total_ok": total_ok,
        "total_errors": total_err,
        "written": written,
        "write_errors": errors,
        "channel_usage": channel_usage,
    }


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    limit = 0
    genome = None
    genome_archetype = ""
    genome_tier = "SCRAPER_PRO"
    legacy = "--legacy" in sys.argv

    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit = int(sys.argv[idx + 1])

    if "--genome" in sys.argv:
        idx = sys.argv.index("--genome")
        if idx + 1 < len(sys.argv):
            try:
                genome = json.loads(sys.argv[idx + 1])
                genome_archetype = "custom"
            except (json.JSONDecodeError, ValueError) as e:
                print(f"Error: --genome must be valid JSON: {e}")
                sys.exit(1)

    if genome is not None and "--genome-archetype" in sys.argv:
        log.warning("Both --genome and --genome-archetype specified. --genome-archetype takes precedence.")

    if "--genome-archetype" in sys.argv:
        idx = sys.argv.index("--genome-archetype")
        if idx + 1 < len(sys.argv):
            archetype_name = sys.argv[idx + 1].upper()
            if archetype_name in GENOME_ARCHETYPES:
                genome = GENOME_ARCHETYPES[archetype_name]["genome"]
                genome_archetype = archetype_name
            else:
                available = ", ".join(GENOME_ARCHETYPES.keys())
                print(f"Error: Unknown archetype '{archetype_name}'. Available: {available}")
                sys.exit(1)

    if "--genome-tier" in sys.argv:
        idx = sys.argv.index("--genome-tier")
        if idx + 1 < len(sys.argv):
            raw_tier = sys.argv[idx + 1].strip().upper()
            valid_tiers = {"SCRAPER_PRO", "SCRAPER_ENTERPRISE"}
            if raw_tier in valid_tiers:
                genome_tier = raw_tier
            else:
                available = ", ".join(sorted(valid_tiers))
                print(f"Error: Unknown tier '{raw_tier}'. Available: {available}")
                sys.exit(1)

    # ── Deep research ──
    deep_research_flag = "--deep-research" in sys.argv

    # ── Show mode on startup ──
    tier_label = genome_tier.replace("SCRAPER_", "").title()
    tier_channels = list(TIER_CHANNELS.get(genome_tier, TIER_CHANNELS["SCRAPER_PRO"]))

    if legacy:
        print(f"Mode: legacy pick_channels (1-2 channels, SI genome disabled, tier={tier_label})")
    elif genome:
        m = f"Mode: global SI genome ({genome_archetype}) — same genome for ALL contractors"
    else:
        m = "Mode: per-contractor adaptive SI genome (default)"
    if deep_research_flag:
        if not dry_run:
            print(f"{m} + DEEP RESEARCH (LLM analysis via AIRouter)\n  Note: adds ~2-5s per contractor for LLM inference")
        else:
            print(f"{m}\n  [--deep-research requires --apply; ignored in dry-run mode]")
    if not genome:
        print(f"  Tier: {tier_label} ({len(tier_channels)} channels)")
        if not legacy:
            print(f"  Each contractor gets a genome matched to their specialties.")
            print(f"  Use --legacy for old 1-2 channel mode, or --genome-archetype to override all.")
    else:
        print(f"  Tier: {tier_label} ({len(tier_channels)} channels)")
        vol = AgentReachEnricher._si_volume_multiplier(genome)
        si_channels = AgentReachEnricher._si_select_channels(genome, tier_channels)
        print(f"  Channels: {len(si_channels)} — {', '.join(si_channels)}")
        print(f"  Volume: {vol:.2f}x — max_results scaled to {max(5, int(5 * vol))}")

    result = asyncio.run(run_enrichment(
        dry_run=dry_run,
        limit=limit,
        genome=genome,
        genome_archetype=genome_archetype,
        legacy=legacy,
        genome_tier=genome_tier,
        deep_research=deep_research_flag,
    ))
    action = "APPLIED" if not result["dry_run"] else "DRY RUN"
    next_step = "--apply" if result["dry_run"] else "(already applied)"
    print(f"\n{action} — use {next_step} to {'write to DB' if result['dry_run'] else 're-run'}")
