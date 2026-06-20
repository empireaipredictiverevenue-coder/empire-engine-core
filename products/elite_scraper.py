"""
EMPIRE V49 · PRODUCT: ELITE SCRAPER V2 (Predictive Revenue Fleet)
==================================================================
AI-powered predictive scraper fleet using camofox-browser for stealth
scraping across 36+ lanes + Agent-Reach multi-channel intelligence
+ AGI Governor strategy routing + SI Strategy genome enrichment.

Scraper agents in the fleet:
  - bots/predictive_camofox_scraper.py — Main B2B scraper using camofox-browser.
    Scrapes 6 niches (roofing, hvac, solar, restoration, public_adjuster, commercial)
    across 4 metros (TX, FL, CA, AZ). Feeds Predictive Revenue Fleet.

  - bots/predictive_youtube_scraper.py — YouTube video + transcript scraper.
    Extracts transcripts via camofox-browser, feeds to Synthetic Brain for
    idea/strategy/niche extraction.

  - bots/predictive_prospector_agent.py — Lead discovery prospector.
    Google-free prospecting using camofox-browser + search macros.
    Supports 36+ niches with AGI self-improvement.

  - products/agent_reach_enrichment.py — Agent-Reach multi-channel intelligence.
    9 channels: GitHub search, semantic search, Jina Reader, RSS feeds,
    YouTube transcripts, V2EX, Bilibili, Twitter, Reddit.

  - empire_agi_governor.py — AGI Governor: per-niche strategy selection
    via SI StrategyEvolution, win-rate tracking, outcome recording.

  - empire_si_strategy.py — SI StrategyEvolution: genome-driven strategy
    evolution with mutation, cross-pollination, and deactivation.

Empire AI provides:
  - Hosted camofox-browser infrastructure
  - Agent-Reach multi-channel intelligence layer (9 channels)
  - AGI Governor strategy routing per niche
  - SI Strategy genome enrichment + outcome feedback loop
  - Managed data pipelines into Supabase
  - Centralized user management + billing
  - Custom niche/metro configuration per client

Integration:
    scraper = EliteScraperProduct(suite_guard, suite_subscriptions)
    result = await scraper.run_job(account_id, niches=["roofing", "hvac"])
"""

import os
import logging
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("empire.product.elite_scraper")

# Elite Scraper tiers for resale
ELITE_SCRAPER_TIERS = {
    "SCRAPER_STARTER": {
        "price": 149,
        "description": "Single-niche B2B lead scraping via camofox-browser with basic enrichment, Jina Reader web intel, and weekly delivery",
        "features": [
            "1 niche (roofing, hvac, solar, restoration, PA, or commercial)",
            "100 leads/month",
            "Camofox-browser stealth scraping",
            "Agent-Reach: Jina Reader — read any web page as clean text",
            "Basic enrichment (name, phone, address)",
            "Weekly delivery via CSV or API",
            "Email support",
        ],
        "agent_reach_channels": ["jina_read"],
    },
    "SCRAPER_PRO": {
        "price": 599,
        "description": "Multi-niche scraping with Agent-Reach intelligence (GitHub, semantic search, RSS, Jina), predictive scoring, and real-time delivery",
        "features": [
            "Up to 3 niches across 4 metros",
            "500 leads/month",
            "Camofox-browser + search macros (@yelp_search, @google_search)",
            "Agent-Reach: GitHub intel — find companies by tech stack",
            "Agent-Reach: Semantic search — free Google alternative",
            "Agent-Reach: RSS monitoring — passive lead generation",
            "Agent-Reach: Jina Reader — intelligent web browsing",
            "YouTube transcript scraping + Synthetic Brain analysis",
            "Predictive lead scoring (LLM + rules hybrid)",
            "Smart deduplication across sources",
            "Real-time delivery via API/webhook",
            "Priority email support",
        ],
        "agent_reach_channels": ["jina_read", "semantic_search", "rss_fetch", "github_search"],
    },
    "SCRAPER_ENTERPRISE": {
        "price": 2499,
        "description": "Full-scale predictive scraper fleet with all 36+ niches, all 7 Agent-Reach channels, Prospector agent, proxy rotation, and managed deployment",
        "features": [
            "All 6+ niches across all 4+ metros (36+ lanes)",
            "5,000+ leads/month",
            "Camofox-browser with full proxy rotation + session persistence",
            "Agent-Reach: ALL 7 channels — GitHub, semantic search, RSS, Jina, YouTube, V2EX, Bilibili",
            "Agent-Reach: V2EX + Bilibili — Chinese market intelligence",
            "Predictive Prospector Agent for lead discovery",
            "YouTube scraper for competitive content intel",
            "Synthetic Brain integration for deep reasoning",
            "AGI self-improvement (adaptive weights)",
            "API-first integration with webhooks",
            "99.9% SLA",
            "Dedicated support engineer",
        ],
        "agent_reach_channels": ["jina_read", "semantic_search", "rss_fetch", "github_search",
                                  "youtube_transcript", "v2ex_browse", "bilibili_search"],
    },
}


class EliteScraperProduct:
    """Elite Scraper v2 — Predictive Revenue Fleet scraping infrastructure.

    Three scraper agents + Agent-Reach intelligence layer:
      - Camofox Scraper: B2B lead scraping via stealth browser
      - YouTube Scraper: Transcripts + content intelligence
      - Prospector Agent: Lead discovery across 36+ lanes
      - Agent-Reach: 7-channel multi-source intelligence (GitHub, semantic
        search, RSS, Jina Reader, YouTube, V2EX, Bilibili)

    Resold through the Empire AI Suite with three tiers:
      - Starter ($149/mo): Single-niche, weekly delivery, Jina Reader
      - Pro ($599/mo): Multi-niche, Agent-Reach intel, real-time
      - Enterprise ($2,499/mo): Full fleet, all 7 channels, managed
    """

    def __init__(
        self,
        guard: Optional[Callable] = None,     # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,  # SuiteGuard.log_usage
        enricher = None,                       # AgentReachEnricher instance
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.enricher = enricher
        self.stats = {"jobs_run": 0, "leads_collected": 0, "blocked": 0, "errors": 0}

    async def check_entitlement(self, account_id: str) -> dict:
        if not self.guard:
            return {"ok": False, "error": "No guard configured"}
        return self.guard(account_id, "elite_scraper")

    async def run_job(self, account_id: str, config: dict) -> dict:
        """Execute a scraping job for an account.

        Args:
            account_id: Customer account ID
            config: {
                tier: "SCRAPER_STARTER" | "SCRAPER_PRO" | "SCRAPER_ENTERPRISE",
                niches: list of niche names,
                metros: list of metro regions,
                max_leads: int,
                delivery: "csv" | "api" | "webhook",
                webhook_url: optional,
                use_agent_reach: bool (default: True) — run Agent-Reach enrichment,
                agent_reach_query: str — optional custom query for enrichment,
                use_agi_si: bool (default: True) — AGI strategy + SI genome enrichment,
            }
        """
        tier = config.get("tier", "SCRAPER_STARTER")
        tier_config = ELITE_SCRAPER_TIERS.get(tier)
        if not tier_config:
            self.stats["blocked"] += 1
            return {"ok": False, "error": f"Unknown tier: {tier}"}

        # Entitlement check
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["blocked"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        from uuid import uuid4
        job_id = str(uuid4())
        niches = config.get("niches", [])
        metros = config.get("metros", [])
        max_leads = min(config.get("max_leads", 100), 5000)
        use_agent_reach = config.get("use_agent_reach", True)
        use_agi_si = config.get("use_agi_si", True)

        self.stats["jobs_run"] += 1
        self.stats["leads_collected"] += max_leads

        # ── AGI + SI Strategy Routing (per-niche best strategy) ──
        agi_strategies = {}
        agi_genomes = {}
        if use_agi_si and niches:
            try:
                from empire_agi_governor import governor as _agi_gov
                si_strategy = _agi_gov.get_si_strategy()
                for niche in niches:
                    # Get the best evolved strategy for this niche from AGI Governor
                    strategy = _agi_gov.strategy_for_niche(niche)
                    agi_strategies[niche] = strategy
                    # Get the strategy genome (aggressiveness, risk_tolerance, etc.)
                    if si_strategy:
                        genome = si_strategy.get_genome(strategy, niche)
                        agi_genomes[niche] = {
                            "strategy": strategy,
                            "genome": genome,
                            "win_rate": _agi_gov.get_niche_win_rate(niche),
                        }
                    else:
                        agi_genomes[niche] = {
                            "strategy": strategy,
                            "genome": {},
                            "win_rate": 0.0,
                        }
                log.info(f"[elite_scraper] AGI strategies: {agi_strategies}")
            except Exception as e:
                log.warning(f"[elite_scraper] AGI strategy lookup failed: {e}")

        # ── Agent-Reach Enrichment (if enricher is wired) ──
        agent_reach_result = None
        if use_agent_reach and self.enricher:
            try:
                query = config.get("agent_reach_query") or (
                    f"{', '.join(niches or ['roofing'])} contractors {', '.join(metros or ['Texas'])}"
                )
                channels = tier_config.get("agent_reach_channels", ["jina_read"])
                agent_reach_result = await self.enricher.enrich(
                    query=query,
                    channels=channels,
                    max_results=min(max_leads, 25),
                    tier=tier,
                    save_to_db=True,
                    metadata={
                        "job_id": job_id,
                        "account_id": account_id,
                        "niches": niches,
                        "metros": metros,
                        "agi_strategies": agi_strategies,
                    },
                )
                if agent_reach_result.get("ok"):
                    ar_hits = agent_reach_result.get("total_hits", 0)
                    self.stats["leads_collected"] += ar_hits
                    log.info(f"[elite_scraper] Agent-Reach: {ar_hits} hits across "
                             f"{len(agent_reach_result.get('channels_used',[]))} channels")
            except Exception as e:
                log.warning(f"[elite_scraper] Agent-Reach enrichment failed: {e}")
                agent_reach_result = {"ok": False, "error": str(e)[:200]}

        # ── AGI + SI Outcome Recording (close the feedback loop) ──
        # Only record outcomes when Agent-Reach actually executed
        outcome_recorded = 0
        if use_agi_si and agi_strategies and agent_reach_result is not None:
            try:
                from empire_agi_governor import governor as _agi_gov
                for niche, strategy in agi_strategies.items():
                    # Record a positive outcome when Agent-Reach succeeds
                    success = bool(agent_reach_result.get("ok"))
                    revenue = float(tier_config.get("price", 0) or 0)
                    _agi_gov.record_strategy_outcome(
                        strategy=strategy,
                        niche=niche,
                        success=success,
                        revenue=revenue,
                    )
                    outcome_recorded += 1
                log.info(f"[elite_scraper] AGI outcomes recorded: {outcome_recorded} niches")
            except Exception as e:
                log.warning(f"[elite_scraper] AGI outcome recording failed: {e}")

        # Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "elite_scraper", "job",
                               q=1, m={
                                   "tier": tier,
                                   "job_id": job_id,
                                   "niches": niches,
                                   "metros": metros,
                                   "max_leads": max_leads,
                                   "agent_reach_channels": tier_config.get("agent_reach_channels", []),
                                   "agi_strategies": agi_strategies,
                                   "agi_genomes": {n: g.get("strategy") for n, g in agi_genomes.items()},
                               })
            except Exception:
                pass

        return {
            "ok": True,
            "account_id": account_id,
            "job_id": job_id,
            "tier": tier,
            "price": tier_config["price"],
            "features": tier_config["features"],
            "max_leads": max_leads,
            "niches": niches or ["All configured niches"],
            "metros": metros or ["All configured metros"],
            "delivery": config.get("delivery", "api"),
            "agent_reach_channels": tier_config.get("agent_reach_channels", []),
            "agent_reach_result": agent_reach_result,
            "agi_strategies": agi_strategies,
            "agi_genomes": agi_genomes,
            "agi_outcomes_recorded": outcome_recorded,
            "deployment_guide": self._deployment_guide(tier, config),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def _deployment_guide(self, tier: str, config: dict) -> str:
        guides = {
            "SCRAPER_STARTER": (
                "1. Empire AI activates your niche on the camofox-browser scraper\\n"
                "2. Agent-Reach Jina Reader enriches leads with web page intel\\n"
                "3. Leads are collected weekly and delivered via CSV or API\\n"
                "4. Access your leads at your dashboard or download endpoint\\n"
                "5. Basic enrichment includes name, phone, and address"
            ),
            "SCRAPER_PRO": (
                "1. Empire AI configures up to 3 niches across 4 metros\\n"
                "2. Camofox-browser runs with search macros (@yelp_search, @google_search)\\n"
                "3. Agent-Reach multi-channel intel: GitHub, semantic search, RSS, Jina\\n"
                "4. YouTube scraper monitors relevant channels for competitive intel\\n"
                "5. Predictive brain scores and ranks every lead\\n"
                "6. Real-time delivery via API or webhook"
            ),
            "SCRAPER_ENTERPRISE": (
                "1. Empire AI provisions dedicated camofox-browser infrastructure\\n"
                "2. All 6+ niches and 4+ metros active (36+ lanes)\\n"
                "3. Agent-Reach ALL 7 channels: GitHub, semantic, RSS, Jina, YouTube, V2EX, Bilibili\\n"
                "4. Prospector Agent discovers new leads autonomously\\n"
                "5. YouTube scraper feeds competitive intel to Synthetic Brain\\n"
                "6. Proxy rotation + session persistence active\\n"
                "7. AGI self-improvement adapts scraping strategy\\n"
                "8. API/webhook integration with full fleet pipeline"
            ),
        }
        return guides.get(tier, "Contact Empire AI ops for deployment instructions.")

    def snapshot(self) -> dict:
        return {**self.stats}


class EliteScraperRoutes:
    """Wire Elite Scraper endpoints into the FastAPI app."""

    def __init__(self, scraper: EliteScraperProduct, *,
                 require_auth: Optional[Callable] = None,
                 enricher = None):
        self.scraper = scraper
        self.require_auth = require_auth
        self.enricher = enricher or scraper.enricher

    def register(self, app):
        from fastapi import Depends, HTTPException, Request
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/suite/scraper/run")
        async def scraper_run(request: Request, auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Run a scraping job for an account.
            Body: {account_id, config: {tier, niches, ...}}
            """
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")

            account_id = (body.get("account_id") or "").strip()
            config = body.get("config") or {}
            if not account_id:
                raise HTTPException(400, "account_id required")
            if not isinstance(config, dict):
                raise HTTPException(400, "config must be an object")

            result = await self.scraper.run_job(account_id, config)
            status = 403 if not result.get("ok") else 200
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/scraper/tiers")
        async def scraper_tiers(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Return Elite Scraper pricing tiers and features."""
            return JSONResponse({
                "tiers": {
                    slug: {
                        "price": t["price"],
                        "description": t["description"],
                        "features": t["features"],
                    }
                    for slug, t in ELITE_SCRAPER_TIERS.items()
                }
            })

        @app.get("/api/v6/suite/scraper/stats")
        async def scraper_stats(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            return JSONResponse(self.scraper.snapshot())

        # ── Agent-Reach powered enrichment endpoint ──
        if self.enricher:
            @app.post("/api/v6/suite/scraper/enrich")
            async def scraper_enrich(request: Request, auth: bool = Depends(self.require_auth) if self.require_auth else None):
                """Run Agent-Reach enrichment via Elite Scraper.
                Body: {query, channels?, tier?, max_results?}
                """
                try:
                    body = await request.json()
                except Exception:
                    raise HTTPException(400, "Invalid JSON")
                query = (body.get("query") or "").strip()
                if not query:
                    raise HTTPException(400, "query required")
                result = await self.enricher.enrich(
                    query=query,
                    channels=body.get("channels"),
                    max_results=int(body.get("max_results", 10)),
                    tier=body.get("tier", "SCRAPER_PRO"),
                )
                return JSONResponse(result)

        log.info("[elite_scraper] Routes registered · /api/v6/suite/scraper/*")
