"""
EMPIRE V49 · DATABASE SEED MODULE
==================================
Bootstraps the 6 new tables (seo_audits, seo_keywords, seo_content,
seo_genome_history, panel_court_decisions, dream_memory) with sample
data so SPA panels have something to render before real audits complete.

WIRE-UP
-------
    POST /api/admin/seed   →  calls seed_all()
"""
import os
import logging
from typing import Dict, List
from supabase import create_client

log = logging.getLogger("empire.seed")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")


def _client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


# ── Seed payloads ───────────────────────────────────────────────────────
SEO_AUDITS_ROWS = [
    {"url": "https://empire-ai.co.uk", "niche": "Local SEO & HVAC",
     "overall_score": 78, "meta_score": 82, "content_score": 75, "technical_score": 77,
     "issues_json": {"meta_desc_missing": False, "h1_issues": 1, "schema_org": False},
     "recommended_title": "Empire AI — AI-Powered Revenue Operations",
     "recommended_description": "AI-driven lead generation, voice outreach, and SEO for service businesses.",
     "priority_actions": ["Add schema.org LocalBusiness", "Compress hero images", "Add FAQ schema"]},
    {"url": "https://example-hvac-wichita.com", "niche": "Local SEO & HVAC",
     "overall_score": 62, "meta_score": 55, "content_score": 70, "technical_score": 60,
     "issues_json": {"meta_desc_missing": True, "slow_lcp": True},
     "recommended_title": "Wichita HVAC Repair — Same Day Service",
     "recommended_description": "Same-day HVAC repair in Wichita, KS. Licensed, insured, 4.9★ rated.",
     "priority_actions": ["Write 150-char meta description", "Optimize LCP under 2.5s", "Add service area pages"]},
    {"url": "https://premier-roofing-wichita.com", "niche": "Local SEO & HVAC",
     "overall_score": 88, "meta_score": 90, "content_score": 85, "technical_score": 89,
     "issues_json": {},
     "recommended_title": "Premier Roofing Wichita — Storm Damage Experts",
     "recommended_description": "Storm damage roofing in Wichita. Free inspections, insurance claim help.",
     "priority_actions": ["Maintain review velocity", "Add storm-damage blog series"]},
    {"url": "https://eaton-roofing-exteriors.com", "niche": "Local SEO & HVAC",
     "overall_score": 71, "meta_score": 68, "content_score": 74, "technical_score": 71,
     "issues_json": {"thin_content": 1},
     "recommended_title": "Eaton Roofing & Exteriors",
     "recommended_description": "Roofing, siding, and exteriors across Kansas and Missouri.",
     "priority_actions": ["Expand service pages to 800+ words", "Add before/after gallery"]},
    {"url": "https://heritage-roofing-wichita.com", "niche": "Local SEO & HVAC",
     "overall_score": 55, "meta_score": 50, "content_score": 60, "technical_score": 55,
     "issues_json": {"no_ssl": False, "duplicate_h1": 1},
     "recommended_title": "Heritage Roofing & Exteriors — Wichita",
     "recommended_description": "Heritage Roofing serving Wichita and surrounding areas since 1998.",
     "priority_actions": ["Fix duplicate H1 across service pages", "Add trust badges to homepage"]},
    {"url": "https://apple-roofing.com", "niche": "Local SEO & HVAC",
     "overall_score": 82, "meta_score": 85, "content_score": 80, "technical_score": 81,
     "issues_json": {},
     "recommended_title": "Apple Roofing — Wichita Roofing Pros",
     "recommended_description": "Apple Roofing offers residential and commercial roofing in Wichita.",
     "priority_actions": ["Add 3 more city landing pages"]},
]

SEO_KEYWORDS_ROWS = [
    {"keyword": "roofing repair wichita ks", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "intent_score": 92, "volume_estimate": "high", "competition": "high", "category": "transactional",
     "conversions": 14, "impressions": 1820, "conversion_rate": 0.077, "total_revenue": 4280.00, "last_outcome": "booked"},
    {"keyword": "emergency hvac repair near me", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "intent_score": 95, "volume_estimate": "high", "competition": "medium", "category": "transactional",
     "conversions": 22, "impressions": 2410, "conversion_rate": 0.091, "total_revenue": 6720.00, "last_outcome": "booked"},
    {"keyword": "roof inspection wichita", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "intent_score": 78, "volume_estimate": "medium", "competition": "low", "category": "transactional",
     "conversions": 8, "impressions": 1200, "conversion_rate": 0.067, "total_revenue": 1840.00, "last_outcome": "booked"},
    {"keyword": "best roofing company wichita", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "intent_score": 88, "volume_estimate": "medium", "competition": "high", "category": "commercial",
     "conversions": 6, "impressions": 3100, "conversion_rate": 0.019, "total_revenue": 1240.00, "last_outcome": "clicked"},
    {"keyword": "hvac tune up cost", "niche": "Local SEO & HVAC", "metro": "national",
     "intent_score": 70, "volume_estimate": "medium", "competition": "medium", "category": "informational",
     "conversions": 3, "impressions": 4200, "conversion_rate": 0.007, "total_revenue": 0.00, "last_outcome": "read"},
    {"keyword": "roofing insurance claim help", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "intent_score": 85, "volume_estimate": "low", "competition": "low", "category": "transactional",
     "conversions": 9, "impressions": 880, "conversion_rate": 0.102, "total_revenue": 3120.00, "last_outcome": "booked"},
    {"keyword": "ac not cooling", "niche": "Local SEO & HVAC", "metro": "national",
     "intent_score": 72, "volume_estimate": "high", "competition": "low", "category": "informational",
     "conversions": 4, "impressions": 5600, "conversion_rate": 0.007, "total_revenue": 0.00, "last_outcome": "read"},
    {"keyword": "storm damage roof repair", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "intent_score": 90, "volume_estimate": "medium", "competition": "medium", "category": "transactional",
     "conversions": 11, "impressions": 1440, "conversion_rate": 0.076, "total_revenue": 3850.00, "last_outcome": "booked"},
    {"keyword": "new roof cost wichita", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "intent_score": 80, "volume_estimate": "medium", "competition": "high", "category": "commercial",
     "conversions": 5, "impressions": 2100, "conversion_rate": 0.024, "total_revenue": 950.00, "last_outcome": "clicked"},
    {"keyword": "24/7 hvac wichita", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "intent_score": 89, "volume_estimate": "low", "competition": "low", "category": "transactional",
     "conversions": 7, "impressions": 720, "conversion_rate": 0.097, "total_revenue": 2310.00, "last_outcome": "booked"},
]

SEO_CONTENT_ROWS = [
    {"keyword": "roofing repair wichita ks", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "title_tag": "Wichita Roofing Repair — Same Day Storm Response",
     "meta_description": "Fast roofing repair in Wichita, KS. Storm damage specialists. Free inspections. Call (316) 555-0142.",
     "h1": "Wichita Roofing Repair You Can Count On",
     "body": "When hail or wind damages your Wichita roof, you need repairs done fast. Our licensed crews respond same-day across Sedgwick County, working directly with your insurance adjuster to make the process painless.",
     "cta": "Call now for a free inspection",
     "secondary_keywords": ["hail damage repair", "insurance claim help", "emergency roof tarping"],
     "converted": True, "attributed_lead_id": "lead_abc123"},
    {"keyword": "emergency hvac repair near me", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "title_tag": "Emergency HVAC Repair Wichita — 24/7 Service",
     "meta_description": "24/7 emergency HVAC repair in Wichita. NATE-certified techs arrive in under 60 minutes. No overtime fees.",
     "h1": "Emergency HVAC Repair, Day or Night",
     "body": "AC died at 2am? Furnace out in a Kansas cold snap? Our emergency HVAC team is on call 24/7 with fully-stocked trucks and NATE-certified technicians.",
     "cta": "Call (316) 555-HVAC",
     "secondary_keywords": ["ac repair", "furnace repair", "no overtime fees"],
     "converted": True, "attributed_lead_id": "lead_def456"},
    {"keyword": "roof inspection wichita", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "title_tag": "Free Roof Inspection in Wichita — 21-Point Report",
     "meta_description": "Free 21-point roof inspection in Wichita. We document every issue with photos. Insurance-ready reports in 24 hours.",
     "h1": "Get a Free Roof Inspection in Wichita",
     "body": "A roof inspection is the first step to protecting your home. Our inspectors check 21 critical points and deliver a photo-rich report you can hand to your insurance company or use to plan repairs.",
     "cta": "Schedule your free inspection",
     "secondary_keywords": ["roof inspection", "insurance report", "21-point check"],
     "converted": True, "attributed_lead_id": "lead_ghi789"},
    {"keyword": "storm damage roof repair", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "title_tag": "Storm Damage Roof Repair — Wichita Hail Specialists",
     "meta_description": "Wichita hail and wind damage? We handle the full repair, working directly with your insurance company.",
     "h1": "Storm Damage Repair Wichita Trusts",
     "body": "From hail-pummeled shingles to wind-torn flashing, our storm response crews have restored over 2,000 Wichita roofs since 2018. We work with State Farm, Allstate, Farmers, and more.",
     "cta": "Book a free storm assessment",
     "secondary_keywords": ["hail damage", "wind damage", "insurance restoration"],
     "converted": True, "attributed_lead_id": "lead_jkl012"},
    {"keyword": "best roofing company wichita", "niche": "Local SEO & HVAC", "metro": "Wichita",
     "title_tag": "The 5 Best Roofing Companies in Wichita (2026 Guide)",
     "meta_description": "Looking for the best roofer in Wichita? We rank the top 5 based on reviews, licensing, and warranty terms.",
     "h1": "Top 5 Roofing Companies in Wichita",
     "body": "Choosing a roofer in Wichita is harder than it should be. We evaluated 38 local roofers across reviews, licensing, insurance, and warranty terms to find the top 5.",
     "cta": "See the full ranking",
     "secondary_keywords": ["roofing reviews", "wichita roofers", "best roofers"],
     "converted": None, "attributed_lead_id": None},
]

SEO_GENOME_HISTORY_ROWS = [
    {"generation": 1, "genome": {"keyword_competitiveness": 0.50, "local_intent": 0.50, "content_depth": 0.50, "technical_rigor": 0.50, "link_authority": 0.50},
     "top_keywords": ["roofing repair wichita", "hvac tune up"], "avg_conversion_rate": 0.045, "sample_size": 120},
    {"generation": 2, "genome": {"keyword_competitiveness": 0.55, "local_intent": 0.60, "content_depth": 0.55, "technical_rigor": 0.52, "link_authority": 0.50},
     "top_keywords": ["roofing repair wichita", "emergency hvac near me"], "avg_conversion_rate": 0.058, "sample_size": 240},
    {"generation": 3, "genome": {"keyword_competitiveness": 0.62, "local_intent": 0.68, "content_depth": 0.60, "technical_rigor": 0.55, "link_authority": 0.52},
     "top_keywords": ["roofing repair wichita ks", "storm damage roof repair"], "avg_conversion_rate": 0.067, "sample_size": 410},
    {"generation": 4, "genome": {"keyword_competitiveness": 0.70, "local_intent": 0.75, "content_depth": 0.65, "technical_rigor": 0.58, "link_authority": 0.55},
     "top_keywords": ["roofing repair wichita ks", "storm damage roof repair", "emergency hvac near me"], "avg_conversion_rate": 0.074, "sample_size": 620},
    {"generation": 5, "genome": {"keyword_competitiveness": 0.78, "local_intent": 0.82, "content_depth": 0.70, "technical_rigor": 0.62, "link_authority": 0.58},
     "top_keywords": ["roofing repair wichita ks", "storm damage roof repair", "roof inspection wichita", "24/7 hvac wichita"], "avg_conversion_rate": 0.082, "sample_size": 980},
    {"generation": 6, "genome": {"keyword_competitiveness": 0.82, "local_intent": 0.88, "content_depth": 0.74, "technical_rigor": 0.65, "link_authority": 0.61},
     "top_keywords": ["roofing repair wichita ks", "storm damage roof repair", "emergency hvac repair near me", "roof inspection wichita"], "avg_conversion_rate": 0.089, "sample_size": 1420},
]

PANEL_COURT_DECISIONS_ROWS = [
    {"case_id": "case_2026_06_09_001", "panel_size": 10, "consensus_score": 0.87, "decision": "GO", "confidence": 0.92,
     "votes": ["yes","yes","yes","yes","yes","yes","yes","yes","yes","abstain"],
     "reasoning": "Lead from storm-damage campaign in Wichita shows strong storm_state signals. Audience match: high. Expected ROI >4x.",
     "niches": ["Local SEO & HVAC", "Roofing Restoration"]},
    {"case_id": "case_2026_06_09_002", "panel_size": 10, "consensus_score": 0.62, "decision": "GO_CAUTIOUS", "confidence": 0.71,
     "votes": ["yes","yes","yes","yes","abstain","abstain","yes","no","yes","yes"],
     "reasoning": "Mass tort lead from MAHURKAR catheter recall. Compliance review needed before outreach. Good fit but legal risk.",
     "niches": ["Mass Tort Legal"]},
    {"case_id": "case_2026_06_09_003", "panel_size": 10, "consensus_score": 0.95, "decision": "GO", "confidence": 0.97,
     "votes": ["yes","yes","yes","yes","yes","yes","yes","yes","yes","yes"],
     "reasoning": "Consumer CPA lead from financial_strike. Clean offer, strong expected EPC, 9/10 panel votes yes.",
     "niches": ["Consumer CPA"]},
    {"case_id": "case_2026_06_08_001", "panel_size": 10, "consensus_score": 0.45, "decision": "NO_GO", "confidence": 0.68,
     "votes": ["no","no","abstain","no","no","yes","abstain","no","no","abstain"],
     "reasoning": "HVAC lead from non-storm metro. Conversion historical rate <2%. Reject.",
     "niches": ["Local SEO & HVAC"]},
    {"case_id": "case_2026_06_08_002", "panel_size": 10, "consensus_score": 0.79, "decision": "GO", "confidence": 0.85,
     "votes": ["yes","yes","yes","yes","yes","abstain","yes","yes","yes","yes"],
     "reasoning": "Roofing lead with insurance claim signal. Strong audience, high intent, recent storm in metro.",
     "niches": ["Local SEO & HVAC", "Roofing Restoration"]},
]

DREAM_MEMORY_ROWS = [
    {"dream_cycle": 1, "collection_window_hours": 24,
     "sources": ["brain", "panel_court", "seo"],
     "sample_sizes": {"brain": 420, "panel_court": 87, "seo": 156},
     "insights": ["Local SEO conversion rate is climbing across the genome",
                  "Panel Court consensus is highly correlated with confidence",
                  "Storm-state metros outperform national averages 3:1"],
     "rule_suggestions": ["increase_local_intent_weight", "boost_storm_state_priority"],
     "wisdom_context": "Empire is finding product-market fit in storm-affected metros with local-intent campaigns.",
     "narrative": "Dream #1 reviewed 24h of activity. 3 insights surfaced, 2 rule suggestions applied, 0 risks detected.",
     "risk_flags": []},
    {"dream_cycle": 2, "collection_window_hours": 24,
     "sources": ["brain", "panel_court", "seo", "voice"],
     "sample_sizes": {"brain": 510, "panel_court": 102, "seo": 198, "voice": 64},
     "insights": ["Voice pickup rates >75% on emergency HVAC offers",
                  "Panel Court NO_GO rate climbed slightly — compliance tightening",
                  "Roofing niche outperforming HVAC in storm metros"],
     "rule_suggestions": ["scale_emergency_hvac_voice", "tighten_compliance_filter"],
     "wisdom_context": "Empire is shifting weight toward voice + storm-state SEO. Compliance tightening is a feature, not a bug.",
     "narrative": "Dream #2: voice is the new top channel. Compliance tightening is intentional. Roofing is the lead vertical.",
     "risk_flags": ["compliance_filter_aggressive"]},
    {"dream_cycle": 3, "collection_window_hours": 24,
     "sources": ["brain", "panel_court", "seo", "voice", "si"],
     "sample_sizes": {"brain": 612, "panel_court": 119, "seo": 234, "voice": 88, "si": 41},
     "insights": ["SI strategy engine successfully applied dream rules to SEO genome",
                  "Genome drift: keyword_competitiveness +0.07, local_intent +0.12",
                  "CPA flat — needs new offer angle"],
     "rule_suggestions": ["raise_keyword_competitiveness_to_0_82", "launch_cpa_refresh_offer"],
     "wisdom_context": "Empire genome is adapting in real-time to dream rules. SI is the feedback loop. CPA vertical needs creative refresh.",
     "narrative": "Dream #3: SI is closing the loop. CPA needs creative refresh. Genome evolving as designed.",
     "risk_flags": ["cpa_creative_fatigue", "compliance_filter_aggressive"]},
]


def _strip_timestamps(rows: List[dict]) -> List[dict]:
    """Remove created_at / last_researched / last_outcome_ts so the table
    default (now()) populates them — avoids collisions on re-seed."""
    drop = {"created_at", "last_researched", "last_outcome_ts"}
    return [{k: v for k, v in r.items() if k not in drop} for r in rows]


def seed_all() -> Dict[str, int]:
    """Insert sample rows into all 6 tables. Returns {table: count}."""
    sb = _client()
    counts: Dict[str, int] = {}

    try:
        sb.table("seo_audits").insert(SEO_AUDITS_ROWS).execute()
        counts["seo_audits"] = len(SEO_AUDITS_ROWS)
    except Exception as e:
        counts["seo_audits"] = 0
        log.warning(f"[seed] seo_audits failed: {e}")

    try:
        sb.table("seo_keywords").upsert(_strip_timestamps(SEO_KEYWORDS_ROWS),
                                        on_conflict="keyword,niche,metro").execute()
        counts["seo_keywords"] = len(SEO_KEYWORDS_ROWS)
    except Exception as e:
        counts["seo_keywords"] = 0
        log.warning(f"[seed] seo_keywords failed: {e}")

    try:
        sb.table("seo_content").insert(SEO_CONTENT_ROWS).execute()
        counts["seo_content"] = len(SEO_CONTENT_ROWS)
    except Exception as e:
        counts["seo_content"] = 0
        log.warning(f"[seed] seo_content failed: {e}")

    try:
        sb.table("seo_genome_history").insert(SEO_GENOME_HISTORY_ROWS).execute()
        counts["seo_genome_history"] = len(SEO_GENOME_HISTORY_ROWS)
    except Exception as e:
        counts["seo_genome_history"] = 0
        log.warning(f"[seed] seo_genome_history failed: {e}")

    try:
        sb.table("panel_court_decisions").insert(PANEL_COURT_DECISIONS_ROWS).execute()
        counts["panel_court_decisions"] = len(PANEL_COURT_DECISIONS_ROWS)
    except Exception as e:
        counts["panel_court_decisions"] = 0
        log.warning(f"[seed] panel_court_decisions failed: {e}")

    try:
        sb.table("dream_memory").insert(DREAM_MEMORY_ROWS).execute()
        counts["dream_memory"] = len(DREAM_MEMORY_ROWS)
    except Exception as e:
        counts["dream_memory"] = 0
        log.warning(f"[seed] dream_memory failed: {e}")

    log.info(f"[seed] seeded {sum(counts.values())} rows across {len(counts)} tables")
    return counts
