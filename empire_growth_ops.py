"""
EMPIRE V49 · GROWTH OPS DIRECTORATE
======================================
Unified command center for non-core operations: marketing hacks, competitor
intelligence, media production (video/design/content), and reconnaissance.

This directorate coordinates four child agents:
  - hacker_agent          → marketing hacks, content arbitrage, social hijacking
  - competitor_intel      → competitor tracking, intelligence briefs, landscape maps
  - media_lab             → video production, design generation, content creation
  - reconnaissance        → web scraping, trend monitoring, opportunity scanning

Fleet parent: None (top-level directorate)
Routes:
  GET   /api/growth-ops/overview     — Unified dashboard across all child ops
  GET   /api/growth-ops/snapshot     — Condensed fleet snapshot
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Callable

log = logging.getLogger("empire.growth_ops")


class GrowthOpsDirectorate:
    """Coordinates all growth ops child agents and provides unified dashboards."""

    def __init__(self, get_db: Callable):
        self.get_db = get_db

        # Child agents — lazily imported
        self._hacker = None
        self._competitor_intel = None
        self._media_lab = None
        self._recon = None

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _get_hacker(self):
        if self._hacker is None:
            try:
                from empire_ai_hacking_agent import AIHackingAgent
                self._hacker = AIHackingAgent(get_db=self.get_db)
            except Exception as e:
                log.debug(f"[growth_ops] hacker unavailable: {e}")
                self._hacker = False
        return self._hacker if self._hacker else None

    def _get_competitor_intel(self):
        if self._competitor_intel is None:
            try:
                from empire_competitor_intel import CompetitorIntelAgent
                self._competitor_intel = CompetitorIntelAgent(get_db=self.get_db)
            except Exception as e:
                log.debug(f"[growth_ops] competitor_intel unavailable: {e}")
                self._competitor_intel = False
        return self._competitor_intel if self._competitor_intel else None

    def _get_media_lab(self):
        if self._media_lab is None:
            try:
                from empire_media_lab import MediaLabAgent
                self._media_lab = MediaLabAgent(get_db=self.get_db)
            except Exception as e:
                log.debug(f"[growth_ops] media_lab unavailable: {e}")
                self._media_lab = False
        return self._media_lab if self._media_lab else None

    def _get_recon(self):
        if self._recon is None:
            try:
                from empire_reconnaissance import ReconAgent
                self._recon = ReconAgent(get_db=self.get_db)
            except Exception as e:
                log.debug(f"[growth_ops] reconnaissance unavailable: {e}")
                self._recon = False
        return self._recon if self._recon else None

    def overview(self) -> dict:
        """Unified dashboard across all child ops — includes predictive revenue context."""
        now = self._now()

        # ── Predictive Cloud context ────────────────────────────────
        pred = self._get_predictive_context()

        # Aggregate from each child agent
        hacker = self._get_hacker()
        comp = self._get_competitor_intel()
        media = self._get_media_lab()
        recon = self._get_recon()

        hacker_snap = hacker.snapshot() if hacker else {"active_niches": 0, "content_generated": 0}
        comp_snap = comp.snapshot() if comp else {"competitors_tracked": 0, "briefs_generated": 0}
        media_snap = media.snapshot() if media else {"videos_rendered": 0, "designs_created": 0, "content_pieces": 0}
        recon_snap = recon.snapshot() if recon else {"targets_scanned": 0, "trends_detected": 0}

        return {
            "ts": now,
            "predictive_cloud": pred,
            "hacker": hacker_snap,
            "competitor_intel": comp_snap,
            "media_lab": media_snap,
            "reconnaissance": recon_snap,
            "totals": {
                "active_ops": 4,  # one per child agent
                "ops_available": sum(1 for x in [hacker, comp, media, recon] if x is not None),
                "projected_mrr": pred.get("mrr_projected", 0),
                "revenue_health": pred.get("health", {}).get("status", "unknown"),
            },
        }

    def _get_predictive_context(self) -> dict:
        """Fetch predictive revenue context from the predictive engine."""
        try:
            from bots import predictive_revenue
            forecast = predictive_revenue.per_lane_forecast() or {}
            health = predictive_revenue.revenue_health_check() or {}
            close_rate = predictive_revenue.get_close_rate()
            sms_signal = predictive_revenue.get_sms_log_signal()

            totals = forecast.get("totals", {})
            niche_summary = forecast.get("niche_summary", {})

            # Top niches by MRR
            top_niches = []
            for n, ns in sorted(niche_summary.items(), key=lambda x: x[1].get("mrr_projected", 0), reverse=True)[:5]:
                top_niches.append({
                    "niche": n,
                    "mrr_projected": ns.get("mrr_projected", 0),
                    "revenue_24h": ns.get("revenue_24h", 0),
                    "active_buyers": ns.get("active_buyers", 0),
                    "calls_24h": ns.get("calls_24h", 0),
                })

            return {
                "mrr_projected": totals.get("mrr_projected", 0),
                "revenue_24h": totals.get("revenue_24h", 0),
                "active_buyers": totals.get("active_buyers", 0),
                "lanes_active": totals.get("lanes_active", 0),
                "close_rate": round(close_rate, 3) if isinstance(close_rate, float) else 0.15,
                "sms_reply_rate": sms_signal.get("global_reply_rate", 0),
                "health": health,
                "top_niches": top_niches,
                "source": "predictive_cloud",
            }
        except Exception as e:
            log.debug(f"[growth_ops] predictive cloud unavailable: {e}")
            return {
                "mrr_projected": 0,
                "revenue_24h": 0,
                "active_buyers": 0,
                "lanes_active": 0,
                "close_rate": 0.15,
                "sms_reply_rate": 0,
                "health": {"status": "unknown", "alerts": []},
                "top_niches": [],
                "source": "unavailable",
            }

    def snapshot(self) -> dict:
        """Condensed snapshot for fleet dashboard."""
        o = self.overview()
        totals = o.get("totals", {})
        return {
            "ops_available": totals.get("ops_available", 0),
            "hacker_opportunities": o.get("hacker", {}).get("high_impact_opportunities", 0),
            "competitors_tracked": o.get("competitor_intel", {}).get("competitors_tracked", 0),
            "media_produced": (
                o.get("media_lab", {}).get("videos_rendered", 0)
                + o.get("media_lab", {}).get("designs_created", 0)
                + o.get("media_lab", {}).get("content_pieces", 0)
            ),
            "targets_scanned": o.get("reconnaissance", {}).get("targets_scanned", 0),
            "modified": self._now(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_growth_ops_routes(app, get_db=None, require_auth=None):
    """Register Growth Ops directorate routes on a FastAPI app."""
    from fastapi import Depends, HTTPException, Query

    if get_db is None:
        log.warning("[growth_ops] No get_db — directorate will return errors")
    _go = GrowthOpsDirectorate(get_db=get_db) if get_db else None

    def _get_go():
        if _go is None:
            raise HTTPException(503, "Growth Ops not initialized (no get_db)")
        return _go

    @app.get("/api/growth-ops/overview")
    async def growth_ops_overview(auth=Depends(require_auth) if require_auth else None):
        """Unified dashboard across all growth ops child agents."""
        return _get_go().overview()

    @app.get("/api/growth-ops/snapshot")
    async def growth_ops_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Condensed fleet snapshot."""
        return _get_go().snapshot()

    log.info("[growth_ops] Routes registered · /api/growth-ops/{overview,snapshot}")
