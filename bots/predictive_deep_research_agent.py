"""
EMPIRE V49 · PREDICTIVE DEEP RESEARCH AGENT
============================================
AI-powered deep research on contractors using enrichment intel.

Takes Agent-Reach enrichment results and performs structured strategic
analysis via the local LLM (Ollama through AIRouter). Produces:

  - Company intelligence (size, positioning, online presence)
  - Pain points and business needs
  - Recommended outreach angle and strategy
  - Risk assessment and confidence scoring

Integration:
  Agent-Reach Enrichment → Deep Research → Score → DB Write

Usage:
    from bots.predictive_deep_research_agent import PredictiveDeepResearchAgent

    agent = PredictiveDeepResearchAgent()
    research = await agent.research_from_enrichment(
        contractor_name="ABC Roofing",
        metro="Dallas, TX",
        archetype="AGGRESSIVE_STRIKE",
        specialties=["roofing", "storm_damage"],
        enrichment_results={...},
        channels_used=["semantic_search", "github_search"],
    )
"""

import os
import re
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

log = logging.getLogger("predictive.deep_research_agent")

# ── System prompt for deep research analysis ──────────────────────────
DEEP_RESEARCH_SYSTEM = """You are the Predictive Deep Research Agent for Empire AI, a company that 
connects contractors with high-value leads through multi-source intelligence.

Your job: analyze a contractor's enrichment data and produce structured 
strategic intelligence for outreach planning.

Analyze these dimensions:
1. **Company Intelligence** — size, reputation, digital presence, positioning
2. **Pain Points** — likely business needs and growth challenges
3. **Outreach Angle** — recommended approach for first contact
4. **Risk Assessment** — red flags, competitive conflicts, dead ends
5. **Confidence** — how confident you are in this assessment (0.0-1.0)

Be specific and actionable. Base your analysis on the enrichment data provided.
If data is sparse, say so and suggest what additional info would help.

Return ONLY valid JSON with keys: company_summary, pain_points (list),
outreach_angle, risk_factors (list), confidence (float 0-1),
key_findings (list of strings)."""


class PredictiveDeepResearchAgent:
    """Deep research agent that analyzes enrichment intel using local LLM."""

    def __init__(self):
        self._router = None
        self._lazy_router_warned = False

    # ── Lazy init for AIRouter (avoids import errors at module level) ──
    @property
    def router(self):
        if self._router is None:
            try:
                from empire_ai_router import AIRouter
                self._router = AIRouter()
            except Exception as e:
                if not self._lazy_router_warned:
                    log.warning(f"[DeepResearch] AIRouter unavailable: {e}")
                    self._lazy_router_warned = True
                return None
        return self._router

    # ── LLM analysis ────────────────────────────────────────────────
    async def _analyze_with_llm(self, prompt: str, system: str) -> dict:
        """Analyze via AIRouter if available; return structured result."""
        router = self.router
        if router is not None:
            try:
                result = await router.generate_json(
                    prompt=prompt,
                    task="deep_research",
                    system=system,
                    temperature=0.3,
                    max_tokens=1200,
                )
                if result and not result.get("_error"):
                    return result
                log.warning(f"[DeepResearch] LLM returned error: {result.get('_error')}")
            except Exception as e:
                log.warning(f"[DeepResearch] LLM call failed: {e}")
        else:
            # Fallback: structured analysis without LLM
            return self._fallback_analysis(prompt)

        return self._fallback_analysis(prompt)

    def _fallback_analysis(self, prompt: str) -> dict:
        """Produce structured analysis when LLM is unavailable."""
        return {
            "company_summary": "LLM unavailable — analysis based on raw enrichment data only.",
            "pain_points": ["Unknown — enable Ollama/AIRouter for deep analysis"],
            "outreach_angle": "Standard outreach — run deep research for personalized angle",
            "risk_factors": ["Unknown — run deep research for risk assessment"],
            "confidence": 0.3,
            "key_findings": [
                "Deep research requires local LLM (Ollama) running",
                "Without LLM, analysis is limited to raw enrichment data"
            ],
        }

    # ── URL extraction from enrichment results ──────────────────────
    @staticmethod
    def _extract_urls_from_results(
        enrichment_results: dict,
        channels_used: list[str],
    ) -> list[str]:
        """Extract URLs from Agent-Reach enrichment channel results."""
        urls = set()

        for channel in channels_used:
            ch_result = enrichment_results.get(channel, {})
            if not isinstance(ch_result, dict) or not ch_result.get("ok"):
                continue

            data = ch_result.get("data", {})
            if not isinstance(data, dict):
                continue

            # semantic_search returns Exa results with 'results' key
            items = data.get("results") or data.get("items") or []
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        url = item.get("url") or item.get("link") or ""
                        if isinstance(url, str) and url.startswith("http"):
                            urls.add(url)

        return sorted(urls)[:10]

    @staticmethod
    def _extract_text_from_results(
        enrichment_results: dict,
        channels_used: list[str],
        max_chars: int = 3000,
    ) -> str:
        """Extract readable text snippets from enrichment results."""
        snippets = []
        total = 0

        for channel in channels_used:
            ch_result = enrichment_results.get(channel, {})
            if not isinstance(ch_result, dict) or not ch_result.get("ok"):
                continue

            data = ch_result.get("data", {})
            if not isinstance(data, dict):
                continue

            # Text content
            text = data.get("text", "")
            if isinstance(text, str) and len(text) > 20:
                snippet = text[:800].strip()
                snippets.append(f"[{channel}] {snippet}")
                total += len(snippet)

            # Items/results
            items = data.get("results") or data.get("items") or []
            if isinstance(items, list):
                for item in items[:5]:
                    if isinstance(item, dict):
                        snippet = json.dumps({k: v for k, v in item.items()
                                              if isinstance(v, (str, int, float))
                                              and not k.startswith("_")},
                                             ensure_ascii=False)[:300]
                        snippets.append(f"  → {snippet}")

            if total >= max_chars:
                break

        return "\n".join(snippets)[:max_chars]

    # ── Main public method: research from enrichment ────────────────
    async def research_from_enrichment(
        self,
        contractor_name: str,
        metro: str,
        archetype: str,
        specialties: list,
        enrichment_results: dict,
        channels_used: list,
        enriched_at: Optional[str] = None,
    ) -> dict:
        """Perform deep research on a contractor using their enrichment data.

        Args:
            contractor_name: Name of the contractor company.
            metro: Metro/location string.
            archetype: SI genome archetype name (or STANDARD).
            specialties: List of contractor specialty labels.
            enrichment_results: Dict of channel → result from Agent-Reach.
            channels_used: List of channel names that were run.
            enriched_at: ISO timestamp of when enrichment was done.

        Returns:
            Dict with urls_found, analysis (structured),
            llm_available, depth, researched_at.
        """
        urls_found = self._extract_urls_from_results(enrichment_results, channels_used)
        text_snippets = self._extract_text_from_results(enrichment_results, channels_used)

        # Build analysis prompt from enrichment data
        specialties_str = ", ".join(specialties) if isinstance(specialties, list) else str(specialties)
        urls_str = "\n".join(f"  - {u}" for u in urls_found) if urls_found else "  None found"

        prompt = f"""Analyze this contractor for outreach intelligence:

CONTRACTOR
  Name: {contractor_name}
  Location: {metro}
  Archetype: {archetype}
  Specialties: {specialties_str}

URLS FOUND VIA ENRICHMENT
{urls_str}

ENRICHMENT DATA SNIPPETS
{text_snippets[:2000]}

Provide structured strategic analysis for outreach planning."""

        analysis = await self._analyze_with_llm(prompt, DEEP_RESEARCH_SYSTEM)
        llm_available = self.router is not None

        result = {
            "urls_found": urls_found,
            "analysis": analysis,
            "llm_available": llm_available,
            "depth": "deep_llm" if llm_available else "fallback_structured",
            "researched_at": datetime.now(timezone.utc).isoformat(),
        }

        log.info(
            f"[DeepResearch] Researched {contractor_name[:30]} — "
            f"{len(urls_found)} urls, confidence={analysis.get('confidence', 0):.2f}, "
            f"depth={result['depth']}"
        )

        return result

    # ── Company-level research (original interface, kept for compatibility) ──
    async def research_company(self, domain: str, niche: str) -> Dict[str, Any]:
        """Research a company by domain name (original interface).

        This is a convenience wrapper that enriches a domain query and
        runs deep research on the results.
        """
        log.info(f"[DeepResearch] Researching {domain} ({niche})")

        # Quick semantic search for background
        try:
            from products.agent_reach_enrichment import AgentReachEnricher
            enricher = AgentReachEnricher(get_db=lambda: None)
            search_result = await enricher.semantic_search(
                query=f"{domain} {niche} company",
                max_results=5,
            )
            results = {"semantic_search": search_result}
            channels = ["semantic_search"]
        except Exception:
            results = {}
            channels = []

        return await self.research_from_enrichment(
            contractor_name=domain,
            metro="",
            archetype=niche,
            specialties=[niche],
            enrichment_results=results,
            channels_used=channels,
        )

    # ── Batch research ─────────────────────────────────────────────
    async def run_cycle(self, opportunities: list) -> list:
        """Run deep research on a batch of enrichment results.

        Args:
            opportunities: List of enrichment result dicts (must have
                name, metro, archetype, specialties, results, channels).

        Returns:
            List of research result dicts.
        """
        results = []
        for opp in opportunities[:10]:
            try:
                research = await self.research_from_enrichment(
                    contractor_name=opp.get("name", ""),
                    metro=opp.get("metro", ""),
                    archetype=opp.get("archetype", "STANDARD"),
                    specialties=opp.get("specialties", []),
                    enrichment_results=opp.get("results", {}),
                    channels_used=opp.get("channels", []),
                )
                research["contractor_id"] = opp.get("id")
                results.append(research)
            except Exception as e:
                log.warning(f"[DeepResearch] Batch item failed: {e}")
                results.append({"error": str(e), "contractor_id": opp.get("id")})

        return results


async def run_continuously():
    """Background loop (for main.py integration)."""
    agent = PredictiveDeepResearchAgent()
    while True:
        log.info("[DeepResearch] Idle — waiting for enrichment results...")
        await asyncio.sleep(600)


if __name__ == "__main__":
    import asyncio
    asyncio.run(run_continuously())
