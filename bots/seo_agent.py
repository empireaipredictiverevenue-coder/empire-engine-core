"""
EMPIRE V49 · SEO OPTIMIZATION AGENT
====================================
Autonomous SEO agent that audits websites, generates optimized content via
local Ollama, tracks keyword performance, and learns which optimizations
drive the most qualified leads — feeding back into the SI strategy evolution.

ARCHITECTURE:
  1. WEBSITE AUDIT     — Scrapes target sites, scores meta tags, content, structure
  2. KEYWORD GENOME    — Tracks keyword traits that evolve based on lead conversion
  3. CONTENT OPTIMIZE  — Uses Ollama to generate SEO-optimized titles, meta, content
  4. LEARNING LOOP     — Records outcomes → adapts keyword genome → feeds SI evolution
  5. LEAD TRACKING     — Links SEO optimizations to radar_targets for conversion tracking

SEO GENOME (evolves like SI strategies):
  - keyword_competitiveness: 0.0-1.0  (target difficulty)
  - local_intent:           0.0-1.0  (geo-targeting strength)
  - content_depth:          0.0-1.0  (long-form vs short-form)
  - technical_rigor:        0.0-1.0  (schema, speed, structure)
  - link_authority:         0.0-1.0  (backlink/profile strength)

Supabase tables (auto-created):
  - seo_audits:     website audit results per domain
  - seo_keywords:   keyword tracking with positions, volume, conversion rates
  - seo_content:    generated content pieces with performance metrics
"""

import os
import sys
import json
import asyncio
import logging
import random
import time
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from collections import defaultdict

import httpx

sys.path.insert(0, "/root/empire-v49")

# Lazy imports for research + content + backlinks agents (avoid circular imports at module level)
_research_agent = None
_content_agent = None
_keyword_gap_tool = None
_ranking_predictor = None


def _get_research_agent():
    global _research_agent
    if _research_agent is None:
        from bots.research_agent import get_research_agent
        _research_agent = get_research_agent()
    return _research_agent


def _get_content_agent():
    global _content_agent
    if _content_agent is None:
        from bots.content_agent import get_content_agent
        _content_agent = get_content_agent()
    return _content_agent


def _get_keyword_gap():
    """Lazy KeywordGapTool from SEO Idea-to-Shipped engine."""
    global _keyword_gap_tool
    if _keyword_gap_tool is None:
        from products.seo_idea_to_shipped.keyword_gap import KeywordGapTool
        _keyword_gap_tool = KeywordGapTool()
    return _keyword_gap_tool


def _get_ranking_predictor():
    """Lazy RankingPredictor from SEO Idea-to-Shipped engine."""
    global _ranking_predictor
    if _ranking_predictor is None:
        from products.seo_idea_to_shipped.ranking_predictor import RankingPredictor
        _ranking_predictor = RankingPredictor()
    return _ranking_predictor

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("seo.agent")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

# ── Config ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

_sb = None

def _get_sb():
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
            sys.exit(1)
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


# ── SEO GENOME TRAITS ────────────────────────────────────────────────
GENOME_TRAITS = [
    "keyword_competitiveness",
    "local_intent",
    "content_depth",
    "technical_rigor",
    "link_authority",
]

# Initial genome — balanced starting point
def _fresh_genome() -> dict:
    return {
        "keyword_competitiveness": 0.5,
        "local_intent":            0.6,
        "content_depth":           0.5,
        "technical_rigor":         0.5,
        "link_authority":          0.4,
    }

# ── KEYWORD CATEGORIES PER NICHE ─────────────────────────────────────
NICHE_KEYWORDS = {
    "Roofing Restoration": [
        "roof repair near me", "emergency roof repair", "storm damage roof",
        "roof replacement cost", "hail damage roof repair", "roofing contractor",
        "residential roofing", "commercial roofing", "roof inspection",
        "metal roofing", "asphalt shingle repair", "flat roof repair",
    ],
    "Local SEO & HVAC": [
        "local seo services", "hvac contractor near me", "ac repair",
        "furnace repair", "hvac installation", "air duct cleaning",
        "heat pump repair", "commercial hvac", "emergency hvac",
        "seo for contractors", "google my business optimization",
    ],
    "Mass Tort Legal": [
        "mass tort lawyer", "product liability attorney", "class action lawsuit",
        "defective drug lawyer", "medical device recall attorney",
        "personal injury mass tort", "toxic exposure lawyer",
    ],
    "Consumer CPA": [
        "tax preparation near me", "cpa services", "small business accountant",
        "tax relief services", "irs audit help", "bookkeeping services",
        "payroll services", "business tax filing",
    ],
}


from bots._llm import llm_json as _llm_json


# ── NO-OP BACKLINKS STUB ────────────────────────────────────────────
# bots/backlinks_agent.py was removed 2026-06-19.
# This stub prevents the SEO agent from crashing when the _b property
# is accessed. All backlinks data continues to live in seo_backlinks
# table and is queried directly by performance_snapshot().
class _NoOpBacklinks:
    async def link_authority_report(self) -> dict:
        return {"link_authority_score": 0.4}


# ── SEO AGENT ────────────────────────────────────────────────────────
class SEOAgent:
    """
    Autonomous SEO optimization agent.

    - Audits websites for SEO health
    - Researches and tracks keyword performance
    - Generates optimized content via LLM
    - Learns which optimizations drive leads (genome evolution)
    - Orchestrates deep research (property, market, competitor, storm)
    - Generates full landing page content (property, neighborhood, storm risk)
    """

    def __init__(self):
        self.genome = _fresh_genome()
        self.stats = {
            "audits_run": 0,
            "keywords_tracked": 0,
            "content_generated": 0,
            "leads_attributed": 0,
            "research_runs": 0,
            "landing_pages": 0,
        }
        self._evolution_runs = 0
        self._last_evolution: Optional[str] = None
        self._research = None  # lazy ResearchAgent
        self._content = None   # lazy ContentAgent
        self._backlinks = _NoOpBacklinks()  # stub (backlinks_agent.py removed 2026-06-19)
        self._ranking_predict_count = 0  # sampling counter for non-blocking ranking prediction
        try:
            self._ranking_sample_rate = int(os.environ.get("SEO_RANKING_SAMPLE_RATE", "3"))
        except (ValueError, TypeError):
            self._ranking_sample_rate = 5

    @property
    def _r(self):
        if self._research is None:
            self._research = _get_research_agent()
        return self._research

    @property
    def _c(self):
        if self._content is None:
            self._content = _get_content_agent()
        return self._content

    @property
    def _b(self):
        """BacklinksAgent was removed 2026-06-19. Returns cached no-op stub."""
        return self._backlinks

    # ── AUDIT WEBSITE ────────────────────────────────────────────────
    async def audit_site(self, url: str, niche: str = "Local SEO & HVAC") -> Dict:
        """
        Audit a website for SEO health.
        Uses Ollama to analyze meta tags, content, structure, and technical SEO.
        """
        system = """You are an expert SEO auditor. Analyze a website's SEO health.
Return ONLY JSON with these fields:
{
  "overall_score": 0-100,
  "meta_score": 0-100, "meta_issues": ["..."],
  "content_score": 0-100, "content_issues": ["..."],
  "technical_score": 0-100, "technical_issues": ["..."],
  "keyword_gaps": ["keyword1", "keyword2"],
  "recommended_title": "optimized title tag (60 chars max)",
  "recommended_description": "optimized meta description (155 chars max)",
  "priority_actions": ["action1", "action2", "action3"]
}"""

        prompt = (
            f"Website URL: {url}\n"
            f"Niche: {niche}\n"
            f"Treat this as a {niche} business website. "
            f"Identify missing SEO elements, keyword gaps, and optimization priorities. "
            f"Return JSON only."
        )

        result = await _llm_json(prompt, system, temperature=0.3)
        if "_error" in result:
            return {"overall_score": 50, "error": result["_error"]}

        # Persist audit
        self.stats["audits_run"] += 1
        try:
            sb = _get_sb()
            sb.table("seo_audits").insert({
                "url": url,
                "niche": niche,
                "overall_score": result.get("overall_score", 0),
                "meta_score": result.get("meta_score", 0),
                "content_score": result.get("content_score", 0),
                "technical_score": result.get("technical_score", 0),
                "issues_json": {
                    "meta": result.get("meta_issues", []),
                    "content": result.get("content_issues", []),
                    "technical": result.get("technical_issues", []),
                },
                "recommended_title": result.get("recommended_title", ""),
                "recommended_description": result.get("recommended_description", ""),
                "priority_actions": result.get("priority_actions", []),
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.warning(f"[seo] audit persist failed: {e}")

        result["url"] = url
        result["niche"] = niche
        return result

    # ── KEYWORD RESEARCH ─────────────────────────────────────────────
    async def research_keywords(
        self, niche: str, metro: str = "", seed_count: int = 10,
        use_groq: bool = False,
    ) -> List[Dict]:
        """
        Research high-intent keywords for a niche/metro.

        Two modes:
          - Ollama (default): Uses local LLM for fast keyword generation.
          - Groq (use_groq=True): Uses KeywordGapTool from SEO Idea-to-Shipped
            engine for higher-quality keyword gap analysis via Groq LLM.

        Keywords are scored by intent, volume estimate, and competition.
        """
        keywords: List[Dict] = []

        # ── Groq mode: KeywordGapTool from Idea-to-Shipped engine ──
        if use_groq:
            try:
                gap_tool = _get_keyword_gap()
                gap_result = await gap_tool.find_gaps(niche, metro, seed_count)
                # Convert gap format → SEOAgent keyword format
                for g in gap_result.get("gaps", []):
                    keywords.append({
                        "keyword": g.get("keyword", ""),
                        "intent_score": g.get("value_score", 50),
                        "volume_estimate": "medium",
                        "competition": g.get("competition", "medium"),
                        "category": g.get("search_intent", "transactional"),
                        "_source": "groq/keyword_gap",
                        "_is_gap": g.get("is_gap", True),
                    })
                log.info(f"[seo] Groq keyword research: {len(keywords)} gaps found "
                         f"(of {gap_result.get('keywords_found', 0)} total)")
            except Exception as e:
                log.warning(f"[seo] Groq keyword research failed, falling back to Ollama: {e}")
                use_groq = False  # fall through to Ollama path

        # ── Ollama mode (default, or fallback) ────────────────────
        if not use_groq:
            seed_keywords = NICHE_KEYWORDS.get(niche, NICHE_KEYWORDS["Local SEO & HVAC"])
            system = """You are an SEO keyword strategist. Generate high-intent, long-tail keywords
for a local business. Return ONLY a JSON array of objects:
[{"keyword": "...", "intent_score": 0-100, "volume_estimate": "low|medium|high", "competition": "low|medium|high", "category": "transactional|informational|navigational"}]"""

            prompt = (
                f"Niche: {niche}\n"
                f"Metro: {metro or 'national'}\n"
                f"Seed keywords: {', '.join(seed_keywords[:5])}\n"
                f"Generate {seed_count} high-intent long-tail keywords. Return JSON array only."
            )

            result = await _llm_json(prompt, system, temperature=0.5)
            if "_error" not in result:
                ollama_kws = result if isinstance(result, list) else result.get("keywords", [])
                if isinstance(ollama_kws, list):
                    for kw in ollama_kws:
                        kw["_source"] = "ollama"
                    keywords.extend(ollama_kws)

        if not keywords:
            return []

        # Persist all keywords (both Ollama and Groq)
        for kw in keywords:
            try:
                sb = _get_sb()
                sb.table("seo_keywords").upsert({
                    "keyword": kw.get("keyword", ""),
                    "niche": niche,
                    "metro": metro or "national",
                    "intent_score": kw.get("intent_score", 50),
                    "volume_estimate": kw.get("volume_estimate", "medium"),
                    "competition": kw.get("competition", "medium"),
                    "category": kw.get("category", "transactional"),
                    "last_researched": datetime.now(timezone.utc).isoformat(),
                }, on_conflict="keyword,niche,metro").execute()
            except Exception:
                pass

        self.stats["keywords_tracked"] += len(keywords)
        return keywords

    # ── GENERATE SEO CONTENT ─────────────────────────────────────────
    async def generate_content(
        self, keyword: str, niche: str, metro: str = ""
    ) -> Optional[Dict]:
        """
        Generate an SEO-optimized content piece targeting a specific keyword.
        Uses the current genome to influence content depth and local focus.
        """
        system = """You are an SEO content writer for a premium local business.
Write a webpage section optimized for the target keyword. Return ONLY JSON:
{
  "title_tag": "60-char SEO title",
  "meta_description": "155-char meta description",
  "h1": "main heading",
  "body": "2-3 paragraphs of optimized content (250-400 words)",
  "cta": "call to action",
  "secondary_keywords": ["kw1", "kw2"]
}"""

        depth_modifier = "long-form, detailed" if self.genome["content_depth"] > 0.6 else "concise, scannable"
        local_modifier = f"heavily localized for {metro}" if self.genome["local_intent"] > 0.5 and metro else "broad appeal"

        prompt = (
            f"Keyword: {keyword}\n"
            f"Niche: {niche}\n"
            f"Metro: {metro or 'general'}\n"
            f"Style: {depth_modifier}, {local_modifier}\n"
            f"Target conversion action: phone call or form submission\n"
            f"Return JSON only."
        )

        result = await _llm_json(prompt, system, temperature=0.5)
        if "_error" in result:
            return None

        self.stats["content_generated"] += 1

        # Persist content
        try:
            sb = _get_sb()
            sb.table("seo_content").insert({
                "keyword": keyword,
                "niche": niche,
                "metro": metro or "national",
                "title_tag": result.get("title_tag", ""),
                "meta_description": result.get("meta_description", ""),
                "h1": result.get("h1", ""),
                "body": result.get("body", ""),
                "cta": result.get("cta", ""),
                "secondary_keywords": result.get("secondary_keywords", []),
                "genome_snapshot": self.genome,
                "created_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.warning(f"[seo] content persist failed: {e}")

        return result

    # ── RANKING STATS ──────────────────────────────────────────────
    def ranking_stats(self) -> dict:
        """Expose ranking prediction sampling stats for monitoring.

        Returns _ranking_predict_count (total lead events that called
        fire_ranking_prediction / record_outcome), _ranking_sample_rate
        (how many events per prediction), and a derived predictions_fired
        estimate."""
        predictions_fired = self._ranking_predict_count // max(self._ranking_sample_rate, 1)
        # Cost projection: Groq llama-3.3-70b ~$0.65/1K calls (~700+300 tokens per pred)
        _cost_per_pred = float(os.environ.get("SEO_RANKING_COST_PER_PRED", "0.00065"))
        cost_rate_3_weekly = round(predictions_fired * (self._ranking_sample_rate / 3) * _cost_per_pred, 4)
        cost_rate_5_weekly = round(predictions_fired * (self._ranking_sample_rate / 5) * _cost_per_pred, 4)
        return {
            "total_events": self._ranking_predict_count,
            "sample_rate": self._ranking_sample_rate,
            "predictions_fired": predictions_fired,
            "sample_pct": round(100 / max(self._ranking_sample_rate, 1), 1),
            "actual_pct": round(
                predictions_fired / max(self._ranking_predict_count, 1) * 100, 1
            ),
            "groq_model": os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile"),
            "cost_per_prediction": _cost_per_pred,
            "cost_rate_3_weekly": cost_rate_3_weekly,
            "cost_rate_5_weekly": cost_rate_5_weekly,
            "cost_delta_weekly": round(cost_rate_3_weekly - cost_rate_5_weekly, 4),
            "cost_delta_pct": round((cost_rate_3_weekly / max(cost_rate_5_weekly, 1e-10) - 1) * 100, 1),
            "note": "Costs are projections based on predictions_fired × rate ratio. Actual Groq usage may differ.",
        }

    # ── PREDICT RANKING (background, non-blocking) ───────────────────
    async def fire_ranking_prediction(self, keyword: str):
        """
        Public fire-and-forget entry point for ranking prediction.

        Uses the same sampling gate as record_outcome() (default: every 5th call)
        but does NOT record any conversion outcome — safe to call on new leads
        that haven't converted yet. Internally spawns _predict_ranking_async()
        via asyncio.create_task() so the caller is never blocked.
        """
        self._ranking_predict_count += 1
        if self._ranking_predict_count % self._ranking_sample_rate == 0:
            asyncio.create_task(self._predict_ranking_async(keyword))

    async def _predict_ranking_async(self, keyword: str):
        """
        Fire-and-forget ranking prediction that runs in a background task.
        Calls the Idea-to-Shipped RankingPredictor and persists the result
        to seo_keywords.meta.ranking_prediction without blocking the caller.
        """
        try:
            predictor = _get_ranking_predictor()
            signal = await predictor.predict_ranking(
                url="https://empire-ai.co.uk",
                keyword=keyword,
                niche="",
                metro="",
            )
            log.info(f"[seo] ranking prediction for '{keyword}': "
                     f"pos={signal.get('predicted_position', '?')} "
                     f"conf={signal.get('confidence', 0):.2f}")
            # Persist to seo_keywords.meta
            try:
                sb = _get_sb()
                r = sb.table("seo_keywords").select("meta").eq("keyword", keyword).limit(1).execute()
                if r.data:
                    sb.table("seo_keywords").update({
                        "meta": {
                            **(r.data[0].get("meta") or {}),
                            "ranking_prediction": {
                                "predicted_position": signal.get("predicted_position"),
                                "confidence": signal.get("confidence"),
                                "predicted_at": signal.get("predicted_at"),
                                "factors": signal.get("factors", {}),
                            },
                        },
                    }).eq("keyword", keyword).execute()
            except Exception as e:
                log.debug(f"[seo] ranking persist failed for '{keyword}': {e}")
        except Exception as e:
            log.debug(f"[seo] ranking prediction background task failed for '{keyword}': {e}")

    # ── RECORD OUTCOME (Learning Loop) ───────────────────────────────
    async def record_outcome(
        self, keyword: str, lead_id: str, success: bool, revenue: float = 0
    ) -> Dict:
        """
        Called when a lead converts (or doesn't). Updates keyword performance,
        triggers genome evolution when enough data accumulates.

        Ranking prediction runs non-blocking via asyncio.create_task()
        with a sampling gate (only every Nth outcome, default N=5).
        """
        # ── Non-blocking ranking prediction (sampling gated) ──────
        self._ranking_predict_count += 1
        if self._ranking_predict_count % self._ranking_sample_rate == 0:
            asyncio.create_task(self._predict_ranking_async(keyword))

        # ── Update keyword performance ────────────────────────────
        try:
            sb = _get_sb()
            r = sb.table("seo_keywords").select("conversions,impressions").eq("keyword", keyword).limit(1).execute()
            if r.data:
                row = r.data[0]
                conversions = (row.get("conversions") or 0) + (1 if success else 0)
                impressions = (row.get("impressions") or 0) + 1
                conv_rate = round(conversions / impressions, 3) if impressions > 0 else 0

                update_fields = {
                    "conversions": conversions,
                    "impressions": impressions,
                    "conversion_rate": conv_rate,
                    "total_revenue": (row.get("total_revenue") or 0) + revenue,
                    "last_outcome": "success" if success else "fail",
                    "last_outcome_ts": datetime.now(timezone.utc).isoformat(),
                }
                # Ranking prediction meta is written async by _predict_ranking_async()
                sb.table("seo_keywords").update(update_fields).eq("keyword", keyword).execute()

            # Link lead to SEO content
            if lead_id:
                sb.table("seo_content").update({
                    "attributed_lead_id": lead_id,
                    "attributed_at": datetime.now(timezone.utc).isoformat(),
                    "converted": success,
                }).eq("keyword", keyword).order("created_at", desc=True).limit(1).execute()

            self.stats["leads_attributed"] += 1

        except Exception as e:
            log.warning(f"[seo] outcome persist failed: {e}")

        # Check if we should evolve the genome
        if self.stats["leads_attributed"] >= 20 and self.stats["leads_attributed"] % 10 == 0:
            await self._evolve_genome()

        return {
            "keyword": keyword,
            "success": success,
            "genome_generation": self._evolution_runs,
            "ranking": None,  # async — see _predict_ranking_async() background task
        }

    # ── EVOLVE GENOME (SI Learning) ──────────────────────────────────
    async def _evolve_genome(self) -> Dict:
        """
        Analyze keyword performance data and mutate the genome toward
        traits that drive higher conversion rates.

        Now enriched with ranking predictions from the Idea-to-Shipped
        engine (seo_rankings table) for more accurate genome adaptation.
        """
        try:
            sb = _get_sb()
            r = sb.table("seo_keywords").select("*").not_.is_("conversion_rate", "null").limit(200).execute()
            keywords = r.data or []
        except Exception as e:
            log.error(f"[seo] genome evolve query failed: {e}")
            return {"evolved": False, "error": str(e)}

        if len(keywords) < 10:
            return {"evolved": False, "reason": "insufficient data"}

        # Pull ranking predictions from Idea-to-Shipped engine (seo_rankings)
        try:
            rankings_r = sb.table("seo_rankings").select("keyword,predicted_position,confidence,factors") \
                .order("predicted_at", desc=True).limit(500).execute()
            rankings_by_kw: Dict[str, dict] = {}
            for row in (rankings_r.data or []):
                kw = row.get("keyword", "")
                if kw and kw not in rankings_by_kw:
                    rankings_by_kw[kw] = row
        except Exception:
            rankings_by_kw = {}

        # Sort by conversion rate
        keywords.sort(key=lambda k: k.get("conversion_rate", 0), reverse=True)
        top = keywords[:max(3, len(keywords) // 3)]

        # Analyze what traits high-converting keywords share
        high_comp = sum(1 for k in top if k.get("competition") in ("high", "medium")) / len(top)
        local_kw = sum(1 for k in top if k.get("metro") and k.get("metro") != "national") / len(top)
        # content_signal: avg intent_score of top-converting keywords + normalize to 0-1
        content_signal = sum(k.get("intent_score", 50) for k in top) / len(top) / 100

        # ── Enrich with ranking predictions from Idea-to-Shipped engine ──
        ranking_authority_signal = 0.0
        ranking_pos_signal = 0.0
        ranking_count = 0
        for k in top:
            kw_name = k.get("keyword", "")
            if kw_name in rankings_by_kw:
                pred = rankings_by_kw[kw_name]
                # Predicted position 1-10 → high authority signal
                pos = pred.get("predicted_position", 50)
                ranking_pos_signal += (1.0 - min(pos, 100) / 100)  # position 1 = 0.99, position 100 = 0.0
                factors = pred.get("factors", {}) or {}
                ranking_authority_signal += factors.get("authority", 0.5)
                ranking_count += 1
        if ranking_count > 0:
            ranking_pos_signal /= ranking_count
            ranking_authority_signal /= ranking_count
        else:
            # No ranking data — use neutral defaults
            ranking_pos_signal = 0.5
            ranking_authority_signal = 0.5

        # Pull content-level conversion data to inform content_depth
        try:
            content_r = sb.table("seo_content").select("converted,body") \
                .not_.is_("converted", "null").limit(100).execute()
            if content_r.data:
                converted = [c for c in content_r.data if c.get("converted")]
                # If long-form content (bodies > 300 chars) converts better, push depth up
                if converted:
                    long_conv = sum(1 for c in converted if len(c.get("body", "")) > 300) / len(converted)
                    # Blend keyword intent with actual content depth performance (60/40)
                    content_signal = content_signal * 0.6 + long_conv * 0.4
        except Exception:
            pass

        # Pull audit scores to inform technical_rigor
        try:
            audit_r = sb.table("seo_audits").select("technical_score") \
                .order("created_at", desc=True).limit(10).execute()
            if audit_r.data:
                avg_tech = sum(a.get("technical_score", 50) for a in audit_r.data) / len(audit_r.data) / 100
                tech_signal = avg_tech
            else:
                tech_signal = 0.5  # neutral if no audits yet
        except Exception:
            tech_signal = 0.5

        # Mutate genome toward high-conversion traits (capped movement)
        mutation_rate = 0.1

        # ── Blend ranking signals from Idea-to-Shipped engine ──
        # Weight by prediction confidence rather than hardcoded 0.5/0.5.
        # High-confidence predictions drive the genome more aggressively;
        # low-confidence predictions defer to conversion data.
        if ranking_count > 0:
            # Average confidence across all ranking predictions for this batch
            avg_ranking_confidence = sum(
                rankings_by_kw.get(k.get("keyword", ""), {}).get("confidence", 0.5)
                for k in top
            ) / max(len(top), 1)
            # Clamp confidence to [0.3, 0.9] so we never fully ignore either signal
            confidence_weight = max(0.3, min(0.9, avg_ranking_confidence))
            comp_signal = high_comp * (1 - confidence_weight) + ranking_pos_signal * confidence_weight
        else:
            confidence_weight = 0.0
            comp_signal = high_comp

        self.genome["keyword_competitiveness"] = self._clamp(
            self.genome["keyword_competitiveness"] + (comp_signal - 0.5) * mutation_rate
        )
        self.genome["local_intent"] = self._clamp(
            self.genome["local_intent"] + (local_kw - 0.5) * mutation_rate
        )
        self.genome["content_depth"] = self._clamp(
            self.genome["content_depth"] + (content_signal - 0.5) * mutation_rate
        )
        self.genome["technical_rigor"] = self._clamp(
            self.genome["technical_rigor"] + (tech_signal - 0.5) * mutation_rate
        )

        # link_authority: use ranking authority signal weighted by
        # prediction confidence, fall back to small exploratory drift
        if ranking_count > 0:
            # confidence_weight already computed above; reuse it
            authority_signal = ranking_authority_signal * confidence_weight + 0.5 * (1 - confidence_weight)
            self.genome["link_authority"] = self._clamp(
                self.genome["link_authority"] + (authority_signal - 0.5) * mutation_rate
            )
        else:
            try:
                self.genome["link_authority"] = self._clamp(
                    self.genome["link_authority"] + random.uniform(-0.03, 0.03)
                )
            except Exception:
                pass

        self._evolution_runs += 1
        self._last_evolution = datetime.now(timezone.utc).isoformat()

        # Persist genome snapshot
        try:
            sb = _get_sb()
            sb.table("seo_genome_history").insert({
                "generation": self._evolution_runs,
                "genome": self.genome,
                "top_keywords": [k.get("keyword") for k in top[:5]],
                "avg_conversion_rate": round(
                    sum(k.get("conversion_rate", 0) for k in top) / len(top), 3
                ) if top else 0,
                "created_at": self._last_evolution,
            }).execute()
        except Exception:
            pass

        log.info(f"[seo] genome evolved (gen {self._evolution_runs}): "
                 f"comp={self.genome['keyword_competitiveness']:.2f} "
                 f"local={self.genome['local_intent']:.2f} "
                 f"depth={self.genome['content_depth']:.2f} "
                 f"tech={self.genome['technical_rigor']:.2f}")

        return {
            "evolved": True,
            "generation": self._evolution_runs,
            "genome": dict(self.genome),
            "sample_size": len(keywords),
        }

    # ── APPLY DREAM RULE TO GENOME ───────────────────────────────────
    def apply_dream_rule(self, rule: dict) -> bool:
        """Apply a dream-generated rule suggestion to the genome.
        Rule format: {"rule": "raise_keyword_competitiveness", "suggested": "0.7", ...}
        Returns True if a genome trait was modified."""
        genome_traits = {
            "keyword_competitiveness", "local_intent", "content_depth",
            "technical_rigor", "link_authority",
        }
        rule_name = (rule.get("rule") or "").lower().replace(" ", "_")
        matched_trait = None
        for trait in genome_traits:
            if trait in rule_name:
                matched_trait = trait
                break
        if not matched_trait:
            return False
        suggested = rule.get("suggested", "")
        try:
            new_val = float(suggested)
        except (ValueError, TypeError):
            # Try to extract a number from the suggested string
            import re
            nums = re.findall(r"[\d.]+\d+", str(suggested))
            if nums:
                new_val = float(nums[0])
            else:
                return False
        new_val = max(0.0, min(1.0, new_val))
        old_val = self.genome.get(matched_trait, 0.5)
        self.genome[matched_trait] = new_val
        log.info(f"[seo] dream rule applied: {matched_trait} {old_val}→{new_val} (confidence={rule.get('confidence')})")
        return True

    # ── DEEP RESEARCH (delegates to ResearchAgent) ───────────────────────
    async def research(
        self,
        address: str = "",
        zip_code: str = "",
        metro: str = "",
        niche: str = "Roofing Restoration",
        research_type: str = "full",
    ) -> Dict:
        """
        Run deep research via the ResearchAgent. Supports single-type or
        full aggregate research across property, market, competitor, storm,
        neighborhood, and buyer intent.

        Args:
            address: Property address to research
            zip_code: ZIP code for storm/neighborhood research
            metro: Metro area for market/competitor research
            niche: Service niche
            research_type: "full" | "property" | "market" | "competitor" |
                           "storm" | "neighborhood" | "buyer_intent"
        """
        agent = self._r
        self.stats["research_runs"] += 1

        if research_type == "full":
            return await agent.full_research(
                address=address, zip_code=zip_code,
                metro=metro, niche=niche,
            )
        elif research_type == "property":
            return await agent.research_property(address, zip_code, metro)
        elif research_type == "market":
            return await agent.research_market(metro, niche)
        elif research_type == "competitor":
            return await agent.research_competitors(metro, niche)
        elif research_type == "storm":
            return await agent.research_storm_history(zip_code, metro)
        elif research_type == "neighborhood":
            return await agent.research_neighborhood(zip_code, metro)
        elif research_type == "buyer_intent":
            return await agent.research_buyer_intent(niche, metro)
        else:
            return await agent.full_research(
                address=address, zip_code=zip_code,
                metro=metro, niche=niche,
            )

    # ── CONTENT GENERATION (delegates to ContentAgent) ───────────────────
    async def generate(
        self,
        content_type: str = "landing_page",
        address: str = "",
        metro: str = "",
        niche: str = "Roofing Restoration",
        property_data: Optional[Dict] = None,
        neighborhood_data: Optional[Dict] = None,
        storm_data: Optional[Dict] = None,
        research_package: Optional[Dict] = None,
        style: str = "cinematic",
    ) -> Dict:
        """
        Generate content via the ContentAgent. Supports all content types.

        Args:
            content_type: "landing_page" | "property_desc" | "neighborhood" |
                          "storm_risk" | "social_og" | "email_content"
            address: Property address for context
            metro: Metro area
            niche: Service niche
            property_data: Property research data (from research agent)
            neighborhood_data: Neighborhood research data
            storm_data: Storm history research data
            research_package: Full research package (from research() with type="full")
            style: Landing page style ("cinematic" | "modern" | "classic")
        """
        agent = self._c

        # If a full research package is provided, use its components
        if research_package:
            property_data = property_data or research_package.get("property")
            neighborhood_data = neighborhood_data or research_package.get("neighborhood")
            storm_data = storm_data or research_package.get("storm_history")

        if content_type == "landing_page":
            self.stats["landing_pages"] += 1
            return await agent.generate_landing_page(
                address=address, metro=metro, niche=niche,
                property_data=property_data,
                neighborhood_data=neighborhood_data,
                storm_data=storm_data,
                style=style,
            )
        elif content_type == "property_desc":
            return await agent.generate_property_description(
                property_data or {}, niche,
            )
        elif content_type == "neighborhood":
            return await agent.generate_neighborhood_guide(
                neighborhood_data or {}, metro,
            )
        elif content_type == "storm_risk":
            return await agent.generate_storm_risk_content(
                storm_data or {}, property_data, niche,
            )
        elif content_type == "social_og":
            return await agent.generate_social_og(
                address=address, metro=metro, niche=niche,
            )
        elif content_type == "email_content":
            return await agent.generate_email_content(
                property_data or {}, storm_data, niche,
            )
        elif content_type == "bulk":
            result = await agent.bulk_generate_for_research(
                research_package or {
                    "address": address, "metro": metro, "niche": niche,
                    "property": property_data,
                    "neighborhood": neighborhood_data,
                    "storm_history": storm_data,
                }
            )
            self.stats["landing_pages"] += 1 if result.get("landing_page") else 0
            return result
        else:
            return await agent.generate_landing_page(
                address=address, metro=metro, niche=niche,
                property_data=property_data,
                neighborhood_data=neighborhood_data,
                storm_data=storm_data,
                style=style,
            )

    # ── RESEARCH → GENERATE PIPELINE ──────────────────────────────────
    async def research_and_generate(
        self,
        address: str = "",
        zip_code: str = "",
        metro: str = "",
        niche: str = "Roofing Restoration",
        style: str = "cinematic",
        generate_types: Optional[List[str]] = None,
    ) -> Dict:
        """
        End-to-end pipeline:
        1. Run full research on the property + metro
        2. Generate all content types from the research

        Returns {"research": {...}, "content": {...}}
        """
        log.info(f"[seo] research_and_generate: {address} / {metro} / {niche}")

        # Phase 1: Full research
        research_pkg = await self._r.full_research(
            address=address, zip_code=zip_code,
            metro=metro, niche=niche,
        )
        self.stats["research_runs"] += 1

        # Phase 2: Generate content from research
        if generate_types and len(generate_types) == 1:
            content_result = await self.generate(
                content_type=generate_types[0],
                address=address, metro=metro, niche=niche,
                research_package=research_pkg,
                style=style,
            )
        else:
            content_result = await self._c.bulk_generate_for_research(research_pkg)
            landing = content_result.get("landing_page")
            if landing:
                self.stats["landing_pages"] += 1

        self.stats["content_generated"] += content_result.get("content_count", 1)

        return {
            "research": research_pkg,
            "content": content_result,
            "address": address,
            "metro": metro,
            "niche": niche,
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── GET PERFORMANCE SNAPSHOT ─────────────────────────────────────
    async def performance_snapshot(self) -> Dict:
        """Full SEO performance snapshot for the SPA dashboard."""
        try:
            sb = _get_sb()
            audits = sb.table("seo_audits").select("*").order("created_at", desc=True).limit(20).execute()
            keywords = sb.table("seo_keywords").select("*").order("conversion_rate", desc=True).limit(50).execute()
            content = sb.table("seo_content").select("*").order("created_at", desc=True).limit(20).execute()
            backlinks = sb.table("seo_backlinks").select("*").limit(500).execute()
        except Exception as e:
            return {"error": str(e), "audits": [], "keywords": [], "content": []}

        # Calculate summary stats
        kw_data = keywords.data or []
        top_keywords = [k for k in kw_data if k.get("conversion_rate", 0) > 0]
        avg_conv = round(
            sum(k.get("conversion_rate", 0) for k in top_keywords) / len(top_keywords), 3
        ) if top_keywords else 0
        total_conversions = sum(k.get("conversions", 0) for k in kw_data)
        total_revenue = sum(k.get("total_revenue", 0) for k in kw_data)

        # Include backlinks stats
        bl_data = backlinks.data or []
        broken_count = sum(1 for b in bl_data if b.get("is_broken"))

        return {
            "stats": {
                "audits_run": self.stats["audits_run"],
                "keywords_tracked": self.stats["keywords_tracked"],
                "content_generated": self.stats["content_generated"],
                "leads_attributed": self.stats["leads_attributed"],
                "research_runs": self.stats["research_runs"],
                "landing_pages": self.stats["landing_pages"],
                "total_conversions": total_conversions,
                "total_revenue": round(total_revenue, 2),
                "avg_conversion_rate": avg_conv,
                "total_backlinks": len(bl_data),
                "broken_backlinks": broken_count,
            },
            "genome": self.genome,
            "evolution_runs": self._evolution_runs,
            "last_evolution": self._last_evolution,
            "audits": audits.data or [],
            "keywords": kw_data,
            "content": content.data or [],
        }

    # ── RUN CYCLE ────────────────────────────────────────────────────
    async def run_cycle(self, niches: Optional[List[str]] = None) -> Dict:
        """
        One full SEO optimization cycle:
        1. Research keywords for each niche
        2. Generate content for top keywords
        3. Evolve genome if enough data
        """
        targets = niches or list(NICHE_KEYWORDS.keys())
        results = {"keywords_found": 0, "content_generated": 0, "researches": 0, "landing_pages": 0, "errors": 0}

        for niche in targets:
            try:
                # Phase 1: Keyword research
                keywords = await self.research_keywords(niche, seed_count=5)
                results["keywords_found"] += len(keywords)

                # Phase 2: Content generation for top-intent keywords
                top_kws = sorted(
                    keywords, key=lambda k: k.get("intent_score", 0), reverse=True
                )[:3]
                for kw in top_kws:
                    content = await self.generate_content(
                        kw.get("keyword", ""), niche
                    )
                    if content:
                        results["content_generated"] += 1

                # Phase 3 (deep research → landing page) skipped in auto-loop.
                # Call POST /api/seo/pipeline with a real property address instead.

            except Exception as e:
                log.error(f"[seo] cycle error for {niche}: {e}")
                results["errors"] += 1

        # Evolution is triggered exclusively by record_outcome()
        # when enough lead conversion data accumulates (>= 20 leads, every 10).

        log.info(f"[seo] cycle complete: {results}")
        return results

    @staticmethod
    def _clamp(val: float) -> float:
        return max(0.0, min(1.0, round(val, 2)))


# ── GLOBAL SINGLETON ─────────────────────────────────────────────────
_SEO_AGENT: Optional[SEOAgent] = None
_seo_interval: float = 6.0  # runtime-configurable, overridden by SEO_INTERVAL_HOURS env var

def get_seo_interval() -> float:
    """Return the current SEO agent loop interval in hours."""
    return _seo_interval

def set_seo_interval(hours: float):
    """Update the SEO agent loop interval at runtime."""
    global _seo_interval
    _seo_interval = max(0.1, min(24.0, float(hours)))
    log.info(f"[seo] interval updated to {_seo_interval}h")

def get_seo_agent() -> SEOAgent:
    global _SEO_AGENT
    if _SEO_AGENT is None:
        _SEO_AGENT = SEOAgent()
    return _SEO_AGENT


# ── BACKGROUND LOOP ──────────────────────────────────────────────────
async def run_loop(interval_hours: float = None):
    """Background loop: run SEO cycles periodically. Configure via SEO_INTERVAL_HOURS env var (default 6h)."""
    if interval_hours is None:
        try:
            interval_hours = float(os.environ.get("SEO_INTERVAL_HOURS", "6.0"))
        except (ValueError, TypeError):
            interval_hours = 6.0
    # Store the active interval for runtime inspection / override
    set_seo_interval(interval_hours)
    log.info(f"[seo] Agent ONLINE · interval={interval_hours}h")
    agent = get_seo_agent()

    # Heartbeat to agent registry
    async def heartbeat():
        try:
            sb = _get_sb()
            sb.table("agent_registry").upsert({
                "agent_name": "seo_agent",
                "role_name": "seo_specialist",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": [
                    "manage_seo", "track_rankings", "analyze_backlinks",
                    "optimize_content", "audit_onpage", "keyword_research",
                    "content_generation", "landing_page", "ranking_prediction",
                ],
                "task_types": ["seo.audit", "seo.optimize", "seo.report", "seo.content", "seo.ranking_prediction"],
            }, on_conflict="agent_name").execute()
        except Exception:
            pass

    await heartbeat()

    while True:
        try:
            await agent.run_cycle()
            await heartbeat()
        except Exception as e:
            log.error(f"[seo] loop error: {e}")
        await asyncio.sleep(_seo_interval * 3600)


# ── STANDALONE CLI ───────────────────────────────────────────────────
def run():
    """Sync entry point for main.py agent loop compatibility."""
    asyncio.run(run_loop())


if __name__ == "__main__":
    import sys
    if "--loop" in sys.argv:
        asyncio.run(run_loop())
    elif "--audit" in sys.argv:
        url = sys.argv[sys.argv.index("--audit") + 1] if "--audit" in sys.argv else "https://example.com"
        result = asyncio.run(get_seo_agent().audit_site(url))
        print(json.dumps(result, indent=2))
    elif "--keywords" in sys.argv:
        niche = "Roofing Restoration"
        result = asyncio.run(get_seo_agent().research_keywords(niche))
        print(json.dumps(result, indent=2))
    else:
        result = asyncio.run(get_seo_agent().run_cycle())
        print(json.dumps(result, indent=2))
