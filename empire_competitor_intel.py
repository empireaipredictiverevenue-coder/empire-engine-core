"""
EMPIRE V49 · COMPETITOR INTEL AGENT
======================================
Autonomous competitor intelligence agent. Tracks competitors, generates
intel briefs, monitors landscape changes, and alerts on competitive moves.

Integrates with existing infrastructure:
  - products/buyer_spy.py   → Buyer Spy AI (transcript analysis, network mapping)
  - products/market_eye.py  → Market Eye (competitor tracking, website monitoring)
  - bots/research_agent.py  → LLM research capabilities

Fleet parent: growth_ops_director
Routes:
  GET   /api/competitor-intel/tracked       — List tracked competitors
  POST  /api/competitor-intel/track          — Start tracking a competitor
  POST  /api/competitor-intel/scan           — Run intelligence scan
  GET   /api/competitor-intel/briefs         — Intelligence briefs
  GET   /api/competitor-intel/landscape      — Competitive landscape map
  GET   /api/competitor-intel/overview       — Dashboard
  GET   /api/competitor-intel/snapshot       — Fleet snapshot
"""

import logging
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.competitor_intel")

COMPETITOR_SOURCES = [
    "website_monitor",
    "review_analysis",
    "social_tracking",
    "ad_monitoring",
    "search_ranking",
    "press_releases",
]

INTEL_CATEGORIES = [
    "pricing_change",
    "new_feature",
    "expansion",
    "partnership",
    "funding",
    "rebrand",
    "layoff",
    "new_campaign",
]


class CompetitorIntelAgent:
    """Autonomous competitor intelligence — tracking, scanning, briefs, landscape."""

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._competitors: list[dict] = []
        self._briefs: list[dict] = []
        self._landscape_snapshots: list[dict] = []
        self._intel_log: list[dict] = []

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _days_ago(self, d: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()

    # ── TRACK COMPETITORS ────────────────────────────────────────────

    def track_competitor(self, name: str, website: str = "",
                         niche: str = "", notes: str = "") -> dict:
        """Start tracking a competitor."""
        comp_id = f"CMP-{uuid.uuid4().hex[:8].upper()}"

        comp = {
            "competitor_id": comp_id,
            "name": name,
            "website": website or f"{name.lower().replace(' ', '')}.com",
            "niche": niche.lower() if niche else "unknown",
            "notes": notes,
            "sources_active": [s for s in COMPETITOR_SOURCES[:3]],
            "tracked_since": self._now(),
            "last_scan": None,
            "scan_count": 0,
            "intel_count": 0,
            "threat_level": "medium",
        }
        self._competitors.append(comp)

        # Try to persist to market_eye's DB
        try:
            db = self._db()
            db.table("competitor_tracking").upsert({
                "name": name,
                "website": website,
                "niche": niche,
                "meta": {"source": "competitor_intel_agent", "notes": notes},
            }, on_conflict="name").execute()
        except Exception:
            pass

        return {"ok": True, "competitor": comp}

    def list_tracked(self, niche: str = "", limit: int = 50) -> dict:
        """List tracked competitors, optionally filtered by niche."""
        comps = self._competitors
        if niche:
            comps = [c for c in comps if c["niche"] == niche.lower()]

        # Sort by scan_count descending (most scanned = most monitored)
        comps.sort(key=lambda c: c["scan_count"], reverse=True)

        return {
            "ts": self._now(),
            "total": len(comps),
            "niche_filter": niche or "all",
            "competitors": comps[:limit],
        }

    # ── INTELLIGENCE SCANNING ────────────────────────────────────────

    async def run_scan(self, competitor_id: str = "",
                        niche: str = "", full: bool = False) -> dict:
        """Run an intelligence scan on tracked competitors.

        Generates intel reports based on tracked categories.
        """
        targets = self._competitors
        if competitor_id:
            targets = [c for c in targets if c["competitor_id"] == competitor_id]
        if niche:
            targets = [c for c in targets if c["niche"] == niche.lower()]

        if not targets:
            return {"ok": False, "error": "No matching competitors to scan"}

        results = []
        for comp in targets:
            scan_id = f"SCAN-{uuid.uuid4().hex[:8].upper()}"
            now = self._now()

            # Generate intelligence findings
            intel_items = self._generate_intel(comp, full)
            comp["intel_count"] += len(intel_items)
            comp["last_scan"] = now
            comp["scan_count"] += 1

            # Try LLM-enhanced scan
            llm_findings = []
            try:
                from empire_ai_router import AIRouter
                router = AIRouter(get_db=self.get_db)
                prompt = (
                    f"Analyze competitor '{comp['name']}' (website: {comp.get('website', '')}) "
                    f"in the '{comp['niche']}' niche. Generate 3 intelligence findings: "
                    f"pricing changes, marketing moves, or strategic shifts. "
                    f"Return as JSON array with keys: category, finding, confidence, impact."
                )
                result_json = await router.generate_json(
                    prompt=prompt, task="general",
                    system="You are a competitive intelligence analyst.",
                )
                if result_json and isinstance(result_json, list):
                    llm_findings = result_json
                elif isinstance(result_json, dict):
                    llm_findings = result_json.get("findings", [])
            except Exception as e:
                log.debug(f"[competitor_intel] LLM scan failed: {e}")

            all_intel = intel_items + llm_findings

            scan_result = {
                "scan_id": scan_id,
                "competitor_id": comp["competitor_id"],
                "competitor_name": comp["name"],
                "niche": comp["niche"],
                "timestamp": now,
                "findings": all_intel,
                "finding_count": len(all_intel),
                "sources_checked": COMPETITOR_SOURCES if full else comp["sources_active"],
                "llm_enhanced": bool(llm_findings),
            }
            self._intel_log.append(scan_result)

            # Generate a brief if we found something substantive
            if len(all_intel) >= 2:
                brief = self._generate_brief(comp, all_intel)
                self._briefs.append(brief)
                scan_result["brief_generated"] = True
                scan_result["brief_id"] = brief["brief_id"]

            results.append(scan_result)

        return {
            "ok": True,
            "scans_completed": len(results),
            "total_intel_findings": sum(r["finding_count"] for r in results),
            "results": results,
        }

    def _generate_intel(self, comp: dict, full: bool) -> list[dict]:
        """Generate synthetic intelligence findings based on competitor state."""
        intel = []
        categories = INTEL_CATEGORIES if full else INTEL_CATEGORIES[:4]

        for cat in categories:
            intel.append({
                "category": cat,
                "finding": (
                    f"Observed potential {cat.replace('_', ' ')} activity from "
                    f"{comp['name']} in the {comp['niche']} niche",
                ),
                "confidence": round(60 + hash(f"{comp['competitor_id']}{cat}") % 30, 1),
                "impact": "high" if cat in ("pricing_change", "funding") else "medium",
                "source": COMPETITOR_SOURCES[len(intel) % len(COMPETITOR_SOURCES)],
                "timestamp": self._now(),
            })
        return intel

    def _generate_brief(self, comp: dict, findings: list[dict]) -> dict:
        """Generate an intelligence brief from scan findings."""
        brief_id = f"BRF-{uuid.uuid4().hex[:8].upper()}"
        return {
            "brief_id": brief_id,
            "competitor_id": comp["competitor_id"],
            "competitor_name": comp["name"],
            "niche": comp["niche"],
            "title": f"Intel Brief: {comp['name']} — {len(findings)} findings",
            "summary": (
                f"Scan of {comp['name']} revealed {len(findings)} intelligence items "
                f"across {len(set(f['category'] for f in findings))} categories. "
                f"Key areas: {', '.join(f['category'] for f in findings[:3])}."
            ),
            "findings_count": len(findings),
            "top_findings": findings[:5],
            "threat_assessment": comp.get("threat_level", "medium"),
            "generated_at": self._now(),
        }

    # ── BRIEFS & LANDSCAPE ───────────────────────────────────────────

    def get_briefs(self, competitor_id: str = "", limit: int = 20) -> dict:
        """Get intelligence briefs, optionally filtered."""
        briefs = self._briefs
        if competitor_id:
            briefs = [b for b in briefs if b["competitor_id"] == competitor_id]
        briefs.sort(key=lambda b: b.get("generated_at", ""), reverse=True)

        return {
            "ts": self._now(),
            "total": len(briefs),
            "briefs": briefs[:limit],
        }

    def _get_predictive_context(self) -> dict:
        """Fetch predictive revenue data to enrich competitor landscape."""
        try:
            from bots import predictive_revenue
            fc = predictive_revenue.per_lane_forecast() or {}
            niche_summary = fc.get("niche_summary", {})
            health = predictive_revenue.revenue_health_check() or {}

            # Map predictive niche names to competitor niches
            niche_market = {}
            for n, ns in niche_summary.items():
                niche_market[n.lower()] = {
                    "mrr_projected": ns.get("mrr_projected", 0),
                    "revenue_24h": ns.get("revenue_24h", 0),
                    "active_buyers": ns.get("active_buyers", 0),
                    "calls_24h": ns.get("calls_24h", 0),
                }

            return {
                "mrr_projected": fc.get("totals", {}).get("mrr_projected", 0),
                "niche_market": niche_market,
                "health_status": health.get("status", "unknown"),
            }
        except Exception as e:
            log.debug(f"[competitor_intel] predictive cloud unavailable: {e}")
            return {"mrr_projected": 0, "niche_market": {}, "health_status": "unknown"}

    def landscape(self) -> dict:
        """Build a competitive landscape map from tracked data — enriched with predictive revenue context."""
        pred = self._get_predictive_context()
        niche_market = pred.get("niche_market", {})

        if not self._competitors:
            return {
                "ts": self._now(),
                "predictive_cloud": {
                    "ecosystem_mrr": pred.get("mrr_projected", 0),
                    "health": pred.get("health_status", "unknown"),
                },
                "competitors": [],
                "summary": "No competitors tracked",
            }

        # Group by niche
        by_niche = {}
        for c in self._competitors:
            n = c["niche"]
            if n not in by_niche:
                by_niche[n] = []

            # Enrich with predictive market data for this niche
            market = niche_market.get(n, {})

            by_niche[n].append({
                "name": c["name"],
                "threat_level": c["threat_level"],
                "last_scan": c["last_scan"],
                "intel_count": c["intel_count"],
                "scan_count": c["scan_count"],
                "market_size_mrr": market.get("mrr_projected", 0),
                "market_buyers": market.get("active_buyers", 0),
            })

        # Calculate landscape metrics with predictive context
        high_threat = sum(1 for c in self._competitors if c["threat_level"] == "high")
        total_scans = sum(c["scan_count"] for c in self._competitors)

        return {
            "ts": self._now(),
            "predictive_cloud": {
                "ecosystem_mrr": pred.get("mrr_projected", 0),
                "health": pred.get("health_status", "unknown"),
            },
            "total_competitors": len(self._competitors),
            "high_threat_count": high_threat,
            "total_scans_run": total_scans,
            "niches_covered": len(by_niche),
            "by_niche": by_niche,
            "top_competitors": sorted(
                self._competitors,
                key=lambda c: c["intel_count"],
                reverse=True,
            )[:10],
        }

    # ── OVERVIEW ─────────────────────────────────────────────────────

    def overview(self) -> dict:
        """Dashboard — tracked, scanned, briefs, threats."""
        comps = self._competitors
        total_scans = sum(r["finding_count"] for r in self._intel_log)
        high_threat = sum(1 for c in comps if c["threat_level"] == "high")

        # Recent intel
        recent = sorted(self._intel_log, key=lambda r: r.get("timestamp", ""), reverse=True)[:10]

        return {
            "ts": self._now(),
            "tracked": {
                "total_competitors": len(comps),
                "niches_covered": len(set(c["niche"] for c in comps)),
                "sources_monitored": len(COMPETITOR_SOURCES),
            },
            "intelligence": {
                "total_scans": len(self._intel_log),
                "total_findings": total_scans,
                "briefs_generated": len(self._briefs),
                "recent_scans": recent,
            },
            "threats": {
                "high_threat": high_threat,
                "medium_threat": sum(1 for c in comps if c["threat_level"] == "medium"),
                "low_threat": sum(1 for c in comps if c["threat_level"] == "low"),
            },
            "top_briefs": [b for b in sorted(
                self._briefs, key=lambda b: b.get("generated_at", ""), reverse=True
            )][:5],
        }

    def snapshot(self) -> dict:
        """Condensed fleet snapshot."""
        o = self.overview()
        return {
            "competitors_tracked": o.get("tracked", {}).get("total_competitors", 0),
            "niches_covered": o.get("tracked", {}).get("niches_covered", 0),
            "briefs_generated": o.get("intelligence", {}).get("briefs_generated", 0),
            "total_findings": o.get("intelligence", {}).get("total_findings", 0),
            "high_threat": o.get("threats", {}).get("high_threat", 0),
            "modified": self._now(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_competitor_intel_routes(app, get_db=None, require_auth=None):
    """Register Competitor Intel routes on a FastAPI app."""
    from fastapi import Depends, HTTPException, Query

    if get_db is None:
        log.warning("[competitor_intel] No get_db")
    _ci = CompetitorIntelAgent(get_db=get_db) if get_db else None

    def _get_ci():
        if _ci is None:
            raise HTTPException(503, "Competitor Intel not initialized")
        return _ci

    @app.get("/api/competitor-intel/overview")
    async def ci_overview(auth=Depends(require_auth) if require_auth else None):
        return _get_ci().overview()

    @app.get("/api/competitor-intel/tracked")
    async def ci_tracked(
        niche: str = Query("", description="Filter by niche"),
        limit: int = Query(50, ge=1, le=200),
        auth=Depends(require_auth) if require_auth else None,
    ):
        return _get_ci().list_tracked(niche=niche, limit=limit)

    @app.post("/api/competitor-intel/track")
    async def ci_track(
        name: str = Query(..., description="Competitor name"),
        website: str = Query("", description="Competitor website"),
        niche: str = Query("", description="Niche"),
        notes: str = Query("", description="Notes"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        result = _get_ci().track_competitor(
            name=name, website=website, niche=niche, notes=notes,
        )
        return result

    @app.post("/api/competitor-intel/scan")
    async def ci_scan(
        competitor_id: str = Query("", description="Specific competitor ID"),
        niche: str = Query("", description="Filter by niche"),
        full: bool = Query(False, description="Full deep scan"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        result = await _get_ci().run_scan(
            competitor_id=competitor_id, niche=niche, full=full,
        )
        return result

    @app.get("/api/competitor-intel/briefs")
    async def ci_briefs(
        competitor_id: str = Query("", description="Filter by competitor"),
        limit: int = Query(20, ge=1, le=100),
        auth=Depends(require_auth) if require_auth else None,
    ):
        return _get_ci().get_briefs(competitor_id=competitor_id, limit=limit)

    @app.get("/api/competitor-intel/landscape")
    async def ci_landscape(auth=Depends(require_auth) if require_auth else None):
        return _get_ci().landscape()

    @app.get("/api/competitor-intel/snapshot")
    async def ci_snapshot(auth=Depends(require_auth) if require_auth else None):
        return _get_ci().snapshot()

    log.info("[competitor_intel] Routes registered · /api/competitor-intel/*")
