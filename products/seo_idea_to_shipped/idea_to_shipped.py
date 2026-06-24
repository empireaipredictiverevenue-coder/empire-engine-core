"""
EMPIRE V49 · SEO IDEA-TO-SHIPPED — Module 6: ORCHESTRATOR
============================================================
End-to-end "Idea to Shipped" pipeline coordinator.

Wires all 5 modules into a single automated pipeline:
  1. Community Validation — is there real demand?
  2. Keyword Gap Analysis — what keywords should we target?
  3. Competitor Gap Scan — what are competitors doing that we're not?
  4. Video Gap Analysis — what video content is missing?
  5. Ranking Prediction — where will our content rank?

Produces a unified shipping plan: validated ideas → keyword briefs →
content briefs → video briefs → ranking timeline.

Usage:
    its = IdeaToShipped()
    plan = await its.run_pipeline(niche="roofing", metro="Dallas", idea="hail damage roof repair cost")
    report = await its.full_report(niche="roofing", metro="Dallas")
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional

log = logging.getLogger("empire.seo.its")

# Lazy imports to avoid circular dependencies
_ranking_predictor = None
_gap_scanner = None
_keyword_gap = None
_video_gap = None
_community_validator = None


def _get_ranking():
    global _ranking_predictor
    if _ranking_predictor is None:
        from products.seo_idea_to_shipped.ranking_predictor import RankingPredictor
        _ranking_predictor = RankingPredictor()
    return _ranking_predictor


def _get_gap_scanner():
    global _gap_scanner
    if _gap_scanner is None:
        from products.seo_idea_to_shipped.gap_scanner import GapScanner
        _gap_scanner = GapScanner()
    return _gap_scanner


def _get_keyword_gap():
    global _keyword_gap
    if _keyword_gap is None:
        from products.seo_idea_to_shipped.keyword_gap import KeywordGapTool
        _keyword_gap = KeywordGapTool()
    return _keyword_gap


def _get_video_gap():
    global _video_gap
    if _video_gap is None:
        from products.seo_idea_to_shipped.video_gap import VideoGapAnalyzer
        _video_gap = VideoGapAnalyzer()
    return _video_gap


def _get_validator():
    global _community_validator
    if _community_validator is None:
        from products.seo_idea_to_shipped.community_validator import CommunityValidator
        _community_validator = CommunityValidator()
    return _community_validator


class IdeaToShipped:
    """Module 6: "Idea to Shipped" orchestrator.

    The master coordinator. Takes a content idea through all validation
    and planning stages, producing a production-ready shipping plan.

    Pipeline stages:
      1. VALIDATE — Community interest check
      2. KEYWORDS — Gap discovery + content briefs
      3. COMPETE   — Competitor content gap analysis
      4. VIDEO     — Video content gaps + briefs
      5. RANKING   — Predicted ranking positions
      6. PLAN      — Unified shipping plan with priorities
    """

    def __init__(self):
        self.stats = {"pipelines_run": 0, "ideas_validated": 0, "briefs_produced": 0}

    # ── FULL PIPELINE ────────────────────────────────────────────────

    async def run_pipeline(
        self,
        niche: str,
        metro: str = "",
        idea: str = "",
        stages: List[str] = None,
        concurrency: int = 1,
    ) -> Dict[str, Any]:
        """Run the full "Idea to Shipped" pipeline.

        Args:
            niche: Service niche (roofing, hvac, solar, etc.)
            metro: Target metro area for local SEO
            idea: Specific content idea to validate (optional)
            stages: Which stages to run (default: all)
            concurrency: How many stages to run in parallel (1 or more)

        Returns unified shipping plan dict.
        """
        if stages is None:
            stages = ["validate", "keywords", "compete", "video", "ranking"]

        started_at = datetime.now(timezone.utc)
        pipeline_id = f"its-{niche}-{started_at.strftime('%Y%m%d%H%M%S')}"
        log.info(f"[its] pipeline {pipeline_id} starting for niche={niche} metro={metro}")

        plan = {
            "pipeline_id": pipeline_id,
            "niche": niche,
            "metro": metro,
            "idea": idea,
            "stages": {},
            "shipping_plan": [],
            "started_at": started_at.isoformat(),
        }

        # Stage 1: Community Validation
        if "validate" in stages and idea:
            validator = _get_validator()
            validation = await validator.validate_idea(idea, niche)
            plan["stages"]["validate"] = validation
            if validation.get("validated"):
                self.stats["ideas_validated"] += 1
            else:
                # Idea rejected — still return the plan but mark as not proceeding
                plan["status"] = "rejected"
                plan["reason"] = f"Idea rejected by community validation: confidence={validation.get('confidence', 0)}"
                plan["finished_at"] = datetime.now(timezone.utc).isoformat()
                return plan

        # Stage 2: Keyword Gap
        if "keywords" in stages:
            kw_tool = _get_keyword_gap()
            kw_gaps = await kw_tool.find_gaps(niche, metro)
            plan["stages"]["keywords"] = {
                "gaps_found": kw_gaps["true_gaps"],
                "top_gaps": kw_gaps["gaps"][:10],
            }

            # Generate content briefs for top 5 gaps
            if kw_gaps["gaps"]:
                briefs = await kw_tool.generate_content_briefs(
                    kw_gaps["gaps"][:5], niche, metro
                )
                plan["stages"]["keywords"]["briefs"] = briefs
                self.stats["briefs_produced"] += len(briefs)

        # Stage 3: Competitor Gap Scan
        if "compete" in stages:
            scanner = _get_gap_scanner()
            # Use the top keyword from stage 2 if available
            top_kw = (plan["stages"].get("keywords", {}).get("top_gaps", [{}])[0].get("keyword")
                      if "keywords" in plan["stages"] else f"{niche} {metro}".strip())
            gaps = await scanner.scan_gaps(niche, top_kw, metro)
            plan["stages"]["compete"] = {
                "gaps_found": len(gaps.get("gaps", [])),
                "severity": gaps.get("severity", "unknown"),
                "top_gaps": gaps.get("gaps", [])[:5],
                "summary": gaps.get("summary", ""),
            }

        # Stage 4: Video Gap
        if "video" in stages:
            video_analyzer = _get_video_gap()
            video_gaps = await video_analyzer.scan_video_gaps(niche)
            plan["stages"]["video"] = {
                "gaps_found": len(video_gaps.get("gaps", [])),
                "top_gaps": video_gaps.get("gaps", [])[:5],
            }

            # Generate video briefs for top gaps
            for vg in video_gaps.get("gaps", [])[:3]:
                vg["brief"] = await video_analyzer.generate_video_brief(vg)
                self.stats["briefs_produced"] += 1

        # Stage 5: Ranking Prediction
        if "ranking" in stages:
            predictor = _get_ranking()
            # Predict rankings for our key pages
            pages_to_predict = [
                f"/for-{niche}",
                "/pricing",
                "/command",
            ]
            keywords_to_predict = [
                f"{niche} leads {metro or 'near me'}".strip(),
                f"{niche} contractor {metro}".strip(),
                f"storm damage {niche}".strip(),
            ]
            rankings = []
            for page, kw in zip(pages_to_predict, keywords_to_predict):
                rankings.append(await predictor.predict_ranking(page, kw, niche, metro))
            plan["stages"]["ranking"] = {
                "predictions": rankings,
                "best_position": min(r["predicted_position"] for r in rankings) if rankings else 50,
            }

        # Build unified shipping plan
        plan["shipping_plan"] = self._build_shipping_plan(plan["stages"], niche, metro)

        plan["status"] = "complete"
        plan["finished_at"] = datetime.now(timezone.utc).isoformat()
        self.stats["pipelines_run"] += 1

        log.info(f"[its] pipeline {pipeline_id} complete: {len(plan['shipping_plan'])} shipping items")
        return plan

    async def full_report(self, niche: str, metro: str = "") -> Dict[str, Any]:
        """Run ALL stages and return a comprehensive SEO report."""
        return await self.run_pipeline(
            niche=niche,
            metro=metro,
            idea=f"Create content for {niche} {metro or 'nationwide'}",
            stages=["keywords", "compete", "video", "ranking"],
        )

    # ── SHIPPING PLAN BUILDER ────────────────────────────────────────

    def _build_shipping_plan(
        self, stages: dict, niche: str, metro: str
    ) -> List[Dict]:
        """Compile all stage outputs into a prioritized shipping plan."""
        plan = []
        priority = 1

        # From keywords: content briefs
        kw_stage = stages.get("keywords", {})
        for brief in kw_stage.get("briefs", []):
            plan.append({
                "priority": priority,
                "type": "content",
                "keyword": brief.get("keyword", ""),
                "title": brief.get("title_tag", ""),
                "outline": brief.get("outline", []),
                "word_count": brief.get("word_count_target", 1200),
                "action": f"Write {brief.get('content_type', 'landing_page')}: {brief.get('title_tag', '')}",
            })
            priority += 1

        # From gaps: content to create
        compete_stage = stages.get("compete", {})
        for gap in compete_stage.get("top_gaps", []):
            if gap.get("priority", 0) >= 7:
                plan.append({
                    "priority": priority,
                    "type": "gap_fill",
                    "topic": gap.get("topic", ""),
                    "action": gap.get("recommended_action", ""),
                })
                priority += 1

        # From video: video briefs
        video_stage = stages.get("video", {})
        for vg in video_stage.get("top_gaps", []):
            brief = vg.get("brief", {})
            if brief:
                plan.append({
                    "priority": priority,
                    "type": "video",
                    "title": brief.get("title", vg.get("topic", "")),
                    "format": brief.get("format", "shorts"),
                    "duration": brief.get("duration_seconds", 45),
                    "action": f"Produce {brief.get('format', 'shorts')}: {brief.get('title', '')}",
                })
                priority += 1

        # From ranking: SEO improvements
        ranking_stage = stages.get("ranking", {})
        for pred in ranking_stage.get("predictions", []):
            if pred.get("predicted_position", 50) > 10:
                for action in pred.get("actions", [])[:2]:
                    plan.append({
                        "priority": priority,
                        "type": "seo_fix",
                        "keyword": pred.get("keyword", ""),
                        "action": action,
                    })
                    priority += 1

        # Sort by priority
        plan.sort(key=lambda x: x["priority"])
        return plan

    def snapshot(self) -> dict:
        return {
            **self.stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
