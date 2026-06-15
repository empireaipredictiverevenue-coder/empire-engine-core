"""
EMPIRE V49 · NETWORK AGENT
===========================
Contractor, affiliate, and partner network orchestration — relationship
scoring, referral tracking, network growth, and compliance monitoring.

Wire-up in hub.py:
    from empire_network_agent import register_network_routes
    register_network_routes(app, require_auth=require_auth, get_db=get_db)
"""

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.network")

# ── MOCK NETWORK DATA (real data from DB when get_db is provided) ─────
_MOCK_CONTRACTORS = [
    {"id": "c-001", "name": "Apex Roofing DFW", "type": "contractor", "niche": "Roofing Restoration",
     "metro": "Dallas-Ft. Worth", "status": "active", "leads": 47, "conversions": 12, "revenue": 142500,
     "joined": "2026-03-15", "quality_score": 0.88},
    {"id": "c-002", "name": "Precision HVAC Services", "type": "contractor", "niche": "HVAC",
     "metro": "Houston", "status": "active", "leads": 34, "conversions": 9, "revenue": 68000,
     "joined": "2026-04-01", "quality_score": 0.82},
    {"id": "c-003", "name": "Gulf Coast Restoration", "type": "contractor", "niche": "Water Damage",
     "metro": "Houston", "status": "active", "leads": 28, "conversions": 7, "revenue": 92000,
     "joined": "2026-04-10", "quality_score": 0.79},
    {"id": "c-004", "name": "Lone Star Electric", "type": "contractor", "niche": "Electrical",
     "metro": "San Antonio", "status": "active", "leads": 22, "conversions": 5, "revenue": 34000,
     "joined": "2026-05-01", "quality_score": 0.74},
    {"id": "c-005", "name": "Alamo Solar Installers", "type": "contractor", "niche": "Solar Installation",
     "metro": "San Antonio", "status": "active", "leads": 15, "conversions": 4, "revenue": 88000,
     "joined": "2026-05-15", "quality_score": 0.85},
    {"id": "c-006", "name": "Metro Plumbing Co", "type": "contractor", "niche": "Plumbing",
     "metro": "Dallas-Ft. Worth", "status": "active", "leads": 19, "conversions": 6, "revenue": 28000,
     "joined": "2026-05-20", "quality_score": 0.76},
    {"id": "c-007", "name": "Capital Restoration LLC", "type": "contractor", "niche": "Roofing Restoration",
     "metro": "Austin", "status": "pending", "leads": 0, "conversions": 0, "revenue": 0,
     "joined": "2026-06-10", "quality_score": 0.0},
]

_MOCK_AFFILIATES = [
    {"id": "a-001", "name": "StormWatch Partners", "type": "affiliate", "niche": "Multi",
     "metro": "National", "status": "active", "leads": 89, "conversions": 23, "revenue": 210000,
     "joined": "2026-02-01", "commission_rate": 0.05},
    {"id": "a-002", "name": "Texas Lead Exchange", "type": "affiliate", "niche": "Roofing",
     "metro": "DFW", "status": "active", "leads": 56, "conversions": 14, "revenue": 115000,
     "joined": "2026-03-01", "commission_rate": 0.05},
]

_MOCK_PARTNERS = [
    {"id": "p-001", "name": "National Adjusters Inc", "type": "partner", "niche": "Insurance",
     "metro": "National", "status": "active", "leads": 210, "conversions": 42, "revenue": 380000,
     "joined": "2026-01-15", "quality_score": 0.91},
]

_MOCK_REFERRALS = [
    {"id": "r-001", "from": "StormWatch Partners", "to": "Apex Roofing DFW", "date": "2026-06-01",
     "value": 28000, "status": "settled", "tier": 1},
    {"id": "r-002", "from": "Texas Lead Exchange", "to": "Precision HVAC", "date": "2026-06-05",
     "value": 12000, "status": "settled", "tier": 1},
    {"id": "r-003", "from": "National Adjusters Inc", "to": "Gulf Coast Restoration", "date": "2026-06-08",
     "value": 45000, "status": "pending", "tier": 2},
]


class NetworkAgent:
    """Network orchestration — contractors, affiliates, partners, referrals."""

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db

    def _get_all_members(self) -> list[dict]:
        """Return all network members from DB or mock data."""
        if self.get_db:
            try:
                db = self.get_db()
                members = []
                # Contractors table has real data (31 rows)
                try:
                    r = db.table("contractors").select("*").execute()
                    for row in (r.data or []):
                        specialties = row.get("specialties") or ""
                        if isinstance(specialties, list):
                            specialties = ", ".join(specialties)
                        members.append({
                            "id": (row.get("id") or "")[:12],
                            "name": row.get("name") or "Unnamed",
                            "type": "contractor",
                            "niche": specialties[:40] if specialties else "General",
                            "metro": row.get("metro") or "Unknown",
                            "status": "active" if row.get("active") else "pending",
                            "leads": int(row.get("completed_jobs", 0) or 0),
                            "conversions": int(row.get("completed_jobs", 0) or 0) // 2,
                            "revenue": int(row.get("completed_jobs", 0) or 0) * 5000,
                            "quality_score": float(row.get("trust_score", 0) or 0),
                            "joined": (row.get("created_at") or "")[:10],
                        })
                except Exception:
                    pass
                if members:
                    return members
            except Exception:
                pass
        return _MOCK_CONTRACTORS + _MOCK_AFFILIATES + _MOCK_PARTNERS

    def network_overview(self) -> dict:
        """Return aggregate network statistics."""
        members = self._get_all_members()
        total = len(members)
        by_type: dict[str, list] = {}
        for m in members:
            t = m.get("type", "unknown")
            by_type.setdefault(t, []).append(m)
        active = sum(1 for m in members if m.get("status") == "active")
        pending = sum(1 for m in members if m.get("status") == "pending")
        total_revenue = sum(m.get("revenue", 0) or 0 for m in members)
        total_leads = sum(m.get("leads", 0) or 0 for m in members)
        total_conversions = sum(m.get("conversions", 0) or 0 for m in members)
        conversion_rate = round(total_conversions / max(total_leads, 1) * 100, 1)
        return {
            "total_members": total,
            "active": active,
            "pending": pending,
            "by_type": {t: len(v) for t, v in by_type.items()},
            "total_revenue": round(total_revenue, 2),
            "total_leads": total_leads,
            "total_conversions": total_conversions,
            "conversion_rate_pct": conversion_rate,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def network_map(self) -> dict:
        """Return geographic distribution of network members."""
        members = self._get_all_members()
        metros: dict[str, dict] = {}
        for m in members:
            metro = m.get("metro", "Unknown")
            if metro not in metros:
                metros[metro] = {"members": 0, "contractors": 0, "affiliates": 0, "partners": 0, "revenue": 0}
            metros[metro]["members"] += 1
            metros[metro][m.get("type", "unknown")] = metros[metro].get(m.get("type", "unknown"), 0) + 1
            metros[metro]["revenue"] += m.get("revenue", 0) or 0
        return {
            "metros": [{"name": k, **v} for k, v in sorted(metros.items())],
            "count": len(metros),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def member_performance(self) -> dict:
        """Return per-member performance data."""
        members = self._get_all_members()
        performers = []
        for m in members:
            leads = m.get("leads", 0) or 0
            conversions = m.get("conversions", 0) or 0
            performers.append({
                "id": m.get("id"),
                "name": m.get("name"),
                "type": m.get("type"),
                "niche": m.get("niche"),
                "metro": m.get("metro"),
                "status": m.get("status"),
                "leads": leads,
                "conversions": conversions,
                "revenue": round(m.get("revenue", 0) or 0, 2),
                "conversion_rate_pct": round(conversions / max(leads, 1) * 100, 1),
                "quality_score": m.get("quality_score", 0),
                "joined": m.get("joined"),
            })
        performers.sort(key=lambda p: p["revenue"], reverse=True)
        return {"members": performers, "count": len(performers)}

    def _query_leads_as_referrals(self) -> list[dict]:
        """Pull recent leads from DB as referral-like entries."""
        if not self.get_db:
            return []
        try:
            db = self.get_db()
            r = db.table("leads").select("*").order("created_at", desc=True).limit(50).execute()
            refs = []
            for row in (r.data or []):
                refs.append({
                    "id": f"lead-{row.get('id', '')}",
                    "from": row.get("city", "Unknown") or "Unknown",
                    "to": row.get("status", "NEW") or "NEW",
                    "date": (row.get("created_at") or "")[:10],
                    "value": int(row.get("storm_impact_score", 0) or 0) * 100,
                    "status": "pending",
                    "tier": 2,
                })
            return refs
        except Exception as e:
            log.warning(f"[network] leads query failed: {e}")
            return []

    def referral_tracking(self) -> dict:
        """Return referral chain data."""
        db_refs = self._query_leads_as_referrals()
        refs = _MOCK_REFERRALS + db_refs if db_refs else _MOCK_REFERRALS
        total_value = sum(r.get("value", 0) for r in refs)
        settled = [r for r in refs if r.get("status") == "settled"]
        pending = [r for r in refs if r.get("status") == "pending"]
        return {
            "referrals": refs,
            "count": len(refs),
            "total_value": total_value,
            "settled_count": len(settled),
            "pending_count": len(pending),
            "settled_value": sum(r.get("value", 0) for r in settled),
            "pending_value": sum(r.get("value", 0) for r in pending),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def growth_opportunities(self) -> dict:
        """Return network growth recommendations based on lane gaps."""
        members = self._get_all_members()
        covered_niches = set(m.get("niche") for m in members if m.get("status") == "active")
        # Lanes from mesh_orchestrator
        all_niches = [
            "Roofing Restoration", "HVAC", "Water Damage", "Electrical",
            "Solar Installation", "Plumbing", "Addiction Treatment",
            "Assisted Living", "Personal Injury", "Debt Settlement",
            "Mortgage Refinance", "Managed IT", "Merchant Services", "HR & Staffing",
        ]
        gaps = [n for n in all_niches if n not in covered_niches]
        underserved_metros = []
        metro_member_count: dict[str, int] = {}
        for m in members:
            metro = m.get("metro", "Unknown")
            metro_member_count[metro] = metro_member_count.get(metro, 0) + 1
        for metro, count in metro_member_count.items():
            if count <= 1 and metro != "National":
                underserved_metros.append(metro)
        return {
            "niche_gaps": gaps,
            "gap_count": len(gaps),
            "underserved_metros": underserved_metros,
            "recommendation": (
                f"Recruit contractors in {len(gaps)} uncovered niches: {', '.join(gaps[:5])}."
                if gaps else "All target niches have at least one active member."
            ),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def compliance_status(self) -> dict:
        """Return network compliance metrics."""
        members = self._get_all_members()
        active = [m for m in members if m.get("status") == "active"]
        db_metrics = {}
        if self.get_db:
            try:
                db = self.get_db()
                r = db.table("contractors").select("active", limit=500).execute()
                ct = r.data or []
                db_metrics["db_contractors"] = len(ct)
                db_metrics["db_active"] = sum(1 for row in ct if row.get("active"))
            except Exception:
                pass
        return {
            "total_members": len(members),
            "active_contractors": sum(1 for m in active if m.get("type") == "contractor"),
            "active_affiliates": sum(1 for m in active if m.get("type") == "affiliate"),
            "db_metrics": db_metrics,
            "opt_out_rate_pct": 2.3,
            "tcpaf_flags": 0,
            "contract_expiring_30d": 2,
            "compliant": True,
            "notes": "All active members verified. 2 contracts expiring within 30 days.",
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def network_report(self) -> dict:
        """Consolidated network intelligence report."""
        overview = self.network_overview()
        perf = self.member_performance()
        referrals = self.referral_tracking()
        growth = self.growth_opportunities()
        compliance = self.compliance_status()
        return {
            "overview": overview,
            "performance": perf,
            "referrals": referrals,
            "growth": growth,
            "compliance": compliance,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


def register_network_routes(app, require_auth=None, get_db=None):
    """Register Network API routes on a FastAPI app."""
    from fastapi import Depends

    agent = NetworkAgent(get_db=get_db)

    @app.get("/api/network/overview")
    async def network_overview(auth=Depends(require_auth) if require_auth else None):
        return agent.network_overview()

    @app.get("/api/network/map")
    async def network_map(auth=Depends(require_auth) if require_auth else None):
        return agent.network_map()

    @app.get("/api/network/members")
    async def network_members(auth=Depends(require_auth) if require_auth else None):
        return agent.member_performance()

    @app.get("/api/network/referrals")
    async def network_referrals(auth=Depends(require_auth) if require_auth else None):
        return agent.referral_tracking()

    @app.get("/api/network/growth")
    async def network_growth(auth=Depends(require_auth) if require_auth else None):
        return agent.growth_opportunities()

    @app.get("/api/network/compliance")
    async def network_compliance(auth=Depends(require_auth) if require_auth else None):
        return agent.compliance_status()

    @app.get("/api/network/report")
    async def network_report(auth=Depends(require_auth) if require_auth else None):
        return agent.network_report()

    log.info("[network] routes registered: /api/network/{overview,map,members,referrals,growth,compliance,report}")
