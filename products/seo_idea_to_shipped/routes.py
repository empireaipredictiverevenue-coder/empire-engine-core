"""
EMPIRE V49 · SEO IDEA-TO-SHIPPED — API Routes
===============================================
FastAPI endpoints for all 6 modules + the full pipeline.

Routes:
  GET  /api/v1/seo/status                   — Engine health + stats
  POST /api/v1/seo/ranking/predict          — Predict SERP ranking for a URL+keyword
  POST /api/v1/seo/ranking/batch            — Predict rankings for multiple URL+keyword pairs
  POST /api/v1/seo/gap/scan                 — Scan competitor content gaps
  POST /api/v1/seo/gap/compare              — Direct page-to-page comparison
  POST /api/v1/seo/keywords/gaps            — Find keyword gaps
  POST /api/v1/seo/keywords/briefs          — Generate content briefs
  POST /api/v1/seo/video/gaps               — Scan video content gaps
  POST /api/v1/seo/video/brief              — Generate video brief
  POST /api/v1/seo/community/validate       — Validate content idea
  GET  /api/v1/seo/community/trending       — Trending topics in niche
  POST /api/v1/seo/pipeline/run             — Run full Idea-to-Shipped pipeline
  GET  /api/v1/seo/pipeline/report          — Full SEO report for niche

Wired into hub.py:
    from products.seo_idea_to_shipped.routes import register_seo_its_routes
    register_seo_its_routes(app, require_auth=require_auth)
"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query

log = logging.getLogger("empire.seo.its.routes")


def register_seo_its_routes(app, require_auth=None):
    """Register all SEO Idea-to-Shipped endpoints on the FastAPI app."""

    from products.seo_idea_to_shipped.ranking_predictor import RankingPredictor
    from products.seo_idea_to_shipped.gap_scanner import GapScanner
    from products.seo_idea_to_shipped.keyword_gap import KeywordGapTool
    from products.seo_idea_to_shipped.video_gap import VideoGapAnalyzer
    from products.seo_idea_to_shipped.community_validator import CommunityValidator
    from products.seo_idea_to_shipped.idea_to_shipped import IdeaToShipped

    ranking = RankingPredictor()
    scanner = GapScanner()
    keywords = KeywordGapTool()
    video = VideoGapAnalyzer()
    community = CommunityValidator()
    its = IdeaToShipped()

    # ── Status ──────────────────────────────────────────────────────

    @app.get("/api/v1/seo/status")
    async def seo_status(auth=Depends(require_auth) if require_auth else None):
        """Return engine health, all module stats, and configuration."""
        return {
            "ok": True,
            "engine": "SEO Idea-to-Shipped",
            "modules": {
                "ranking_predictor": ranking.snapshot(),
                "gap_scanner": scanner.snapshot(),
                "keyword_gap": keywords.snapshot(),
                "video_gap": video.snapshot(),
                "community_validator": community.snapshot(),
                "idea_to_shipped": its.snapshot(),
            },
        }

    # ── Ranking Predictor ───────────────────────────────────────────

    @app.post("/api/v1/seo/ranking/predict")
    async def seo_ranking_predict(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Predict SERP ranking for a URL + keyword pair.

        Body: {url, keyword, niche?, metro?}
        """
        url = body.get("url", "")
        keyword = body.get("keyword", "")
        if not url or not keyword:
            raise HTTPException(400, "Missing required fields: url, keyword")

        result = await ranking.predict_ranking(
            url=url,
            keyword=keyword,
            niche=body.get("niche", ""),
            metro=body.get("metro", ""),
        )
        return {"ok": True, **result}

    @app.post("/api/v1/seo/ranking/batch")
    async def seo_ranking_batch(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Predict rankings for multiple URL+keyword pairs.

        Body: {pairs: [{url, keyword}, ...], niche?, metro?}
        """
        pairs = body.get("pairs", [])
        if not pairs:
            raise HTTPException(400, "Missing required field: pairs (array)")

        urls = [p.get("url", "") for p in pairs]
        kws = [p.get("keyword", "") for p in pairs]
        results = await ranking.predict_batch(
            urls, kws,
            niche=body.get("niche", ""),
            metro=body.get("metro", ""),
        )
        return {"ok": True, "predictions": results, "count": len(results)}

    # ── Gap Scanner ──────────────────────────────────────────────────

    @app.post("/api/v1/seo/gap/scan")
    async def seo_gap_scan(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Scan competitor content gaps for a niche + keyword.

        Body: {niche, keyword, metro?, top_n?}
        """
        niche = body.get("niche", "")
        if not niche:
            raise HTTPException(400, "Missing required field: niche")

        result = await scanner.scan_gaps(
            niche=niche,
            keyword=body.get("keyword", niche),
            metro=body.get("metro", ""),
            top_n=int(body.get("top_n", 3)),
        )
        return {"ok": True, **result}

    @app.post("/api/v1/seo/gap/compare")
    async def seo_gap_compare(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Direct page-to-page content gap comparison.

        Body: {our_url, competitor_url}
        """
        our_url = body.get("our_url", "")
        competitor_url = body.get("competitor_url", "")
        if not our_url or not competitor_url:
            raise HTTPException(400, "Missing required fields: our_url, competitor_url")

        result = await scanner.compare_page(our_url, competitor_url)
        return {"ok": True, **result}

    # ── Keyword Gap Tool ─────────────────────────────────────────────

    @app.post("/api/v1/seo/keywords/gaps")
    async def seo_keywords_gaps(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Find keyword gaps for a niche + metro.

        Body: {niche, metro?, seed_count?}
        """
        niche = body.get("niche", "")
        if not niche:
            raise HTTPException(400, "Missing required field: niche")

        result = await keywords.find_gaps(
            niche=niche,
            metro=body.get("metro", ""),
            seed_count=int(body.get("seed_count", 15)),
        )
        return {"ok": True, **result}

    @app.post("/api/v1/seo/keywords/briefs")
    async def seo_keywords_briefs(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Generate content briefs for keyword gaps.

        Body: {keywords: [{keyword, ...}], niche, metro?}
        """
        kws = body.get("keywords", [])
        niche = body.get("niche", "")
        if not kws or not niche:
            raise HTTPException(400, "Missing required fields: keywords, niche")

        briefs = await keywords.generate_content_briefs(
            kws, niche, body.get("metro", "")
        )
        return {"ok": True, "briefs": briefs, "count": len(briefs)}

    # ── Video Gap Analyzer ───────────────────────────────────────────

    @app.post("/api/v1/seo/video/gaps")
    async def seo_video_gaps(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Scan for video content gaps in a niche.

        Body: {niche, sub_topic?, max_gaps?}
        """
        niche = body.get("niche", "")
        if not niche:
            raise HTTPException(400, "Missing required field: niche")

        result = await video.scan_video_gaps(
            niche=niche,
            sub_topic=body.get("sub_topic", ""),
            max_gaps=int(body.get("max_gaps", 10)),
        )
        return {"ok": True, **result}

    @app.post("/api/v1/seo/video/brief")
    async def seo_video_brief(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Generate a video content brief from a gap.

        Body: {gap: {topic, ...}, niche?}
        """
        gap = body.get("gap", {})
        if not gap.get("topic"):
            raise HTTPException(400, "Missing required field: gap.topic")

        brief = await video.generate_video_brief(gap)
        return {"ok": True, "brief": brief}

    # ── Community Validator ──────────────────────────────────────────

    @app.post("/api/v1/seo/community/validate")
    async def seo_community_validate(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Validate a content idea against community discussion data.

        Body: {idea, niche?, platform?}
        """
        idea = body.get("idea", "")
        if not idea:
            raise HTTPException(400, "Missing required field: idea")

        result = await community.validate_idea(
            idea=idea,
            niche=body.get("niche", ""),
            platform=body.get("platform", "reddit"),
        )
        return {"ok": True, **result}

    @app.get("/api/v1/seo/community/trending")
    async def seo_community_trending(
        niche: str = Query(..., description="Niche to check trends for"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Get trending topics in a niche's community discussions."""
        if not niche:
            raise HTTPException(400, "Missing required query param: niche")

        result = await community.trending_in_niche(niche)
        return {"ok": True, **result}

    # ── Full Pipeline ────────────────────────────────────────────────

    @app.post("/api/v1/seo/pipeline/run")
    async def seo_pipeline_run(
        body: dict,
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Run the full Idea-to-Shipped pipeline.

        Body: {niche, metro?, idea?, stages?}
        """
        niche = body.get("niche", "")
        if not niche:
            raise HTTPException(400, "Missing required field: niche")

        result = await its.run_pipeline(
            niche=niche,
            metro=body.get("metro", ""),
            idea=body.get("idea", ""),
            stages=body.get("stages"),
        )
        return {"ok": True, **result}

    @app.get("/api/v1/seo/pipeline/report")
    async def seo_pipeline_report(
        niche: str = Query(..., description="Niche for the report"),
        metro: str = Query("", description="Metro area"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Run a full SEO report for a niche + metro."""
        if not niche:
            raise HTTPException(400, "Missing required query param: niche")

        result = await its.full_report(niche, metro)
        return {"ok": True, **result}

    log.info("[seo-its] REST routes registered (13 endpoints)")
