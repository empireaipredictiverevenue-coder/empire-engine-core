"""
EMPIRE V49 · BUSINESS GROWTH AGENT
====================================
Autonomous business growth agent that:
- Analyzes growth funnel across all pipelines (leads → outreach → conversion → revenue)
- Identifies expansion opportunities (new niches, metros, channels)
- Scores market expansion potential
- Auto-triggers growth actions (prospector sweeps, campaign creation, outreach enrollment)
- Generates growth-specific alerts and recommendations

Routes (registered via hub.py):
  GET    /api/growth/overview            — Growth dashboard snapshot
  GET    /api/growth/funnel              — Pipeline funnel analysis with bottleneck detection
  GET    /api/growth/expansion            — Market expansion opportunities scored and ranked
  GET    /api/growth/metrics              — Growth KPIs (MoM/WoW/Daily growth rates)
  GET    /api/growth/opportunities        — Specific actionable growth opportunities
  POST   /api/growth/actions/sweep       — Trigger a prospector sweep for a niche/metro
  POST   /api/growth/actions/campaign    — Create a native ad campaign for a niche
  POST   /api/growth/actions/enroll      — Enroll top potentials into outreach sequences
  GET    /api/growth/snapshot             — Condensed snapshot for fleet dashboard
"""

import json
import logging
import os
import asyncio
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.business_growth_agent")


# ── CONFIG ──────────────────────────────────────────────────────────────
DEFAULT_EXPANSION_MIN_SCORE = 40  # minimum opportunity score to flag
DEFAULT_GROWTH_ALERT_THRESHOLD_PCT = 15  # % drop that triggers growth alert


class BusinessGrowthAgent:
    """Autonomous business growth agent.

    Analyzes the full pipeline for growth signals, identifies expansion
    opportunities, and can trigger automated growth actions.
    """

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._action_history: list[dict] = []
        self._growth_cache: dict = {}
        self._last_refresh: Optional[str] = None

    # ── HELPERS ──────────────────────────────────────────────────────────

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _hours_ago(self, h: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(hours=h)).isoformat()

    def _days_ago(self, d: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()

    # ── DATA SOURCES ─────────────────────────────────────────────────────

    def _count_table(self, table: str, since: Optional[str] = None) -> int:
        """Count rows in a Supabase table, optionally filtered by created_at."""
        try:
            q = self._db().table(table).select("id", count="exact")
            if since:
                q = q.gte("created_at", since)
            r = q.execute()
            return r.count if hasattr(r, "count") else len(r.data or [])
        except Exception as e:
            log.debug(f"[growth] count {table} failed: {e}")
            return 0

    def _sum_table(self, table: str, column: str, since: Optional[str] = None) -> float:
        """Sum a numeric column, optionally filtered."""
        try:
            q = self._db().table(table).select(column)
            if since:
                q = q.gte("created_at", since)
            r = q.execute()
            return sum(float(row.get(column, 0) or 0) for row in (r.data or []))
        except Exception as e:
            log.debug(f"[growth] sum {table}.{column} failed: {e}")
            return 0.0

    def _get_distinct(self, table: str, column: str) -> list[str]:
        """Get distinct values of a column."""
        try:
            r = self._db().table(table).select(column).execute()
            seen = set()
            results = []
            for row in (r.data or []):
                val = row.get(column)
                if val and str(val) not in seen:
                    seen.add(str(val))
                    results.append(str(val))
            return results
        except Exception as e:
            log.debug(f"[growth] distinct {table}.{column} failed: {e}")
            return []

    # ── 1. GROWTH FUNNEL ANALYSIS ───────────────────────────────────────

    def funnel_analysis(self) -> dict:
        """Pipeline funnel analysis: volume at each stage, conversion rates,
        and bottleneck detection.

        Tracks the full funnel:
          Prospects → Contractors → Enriched Leads → Outreach → Replies → Conversions → Revenue
        """
        now = self._now()
        last_7d = self._days_ago(7)
        last_30d = self._days_ago(30)
        last_24h = self._hours_ago(24)

        # ── Volume at each stage ─────────────────────────────────────────
        prospects_7d = self._count_table("prospects", last_7d)
        prospects_30d = self._count_table("prospects", last_30d)
        prospects_24h = self._count_table("prospects", last_24h)

        contractors_7d = self._count_table("contractors", last_7d)
        contractors_30d = self._count_table("contractors", last_30d)

        enriched_leads_7d = self._count_table("enriched_leads", last_7d)
        enriched_leads_30d = self._count_table("enriched_leads", last_30d)

        # SMS sequences active
        seq_active = 0
        seq_sent_7d = 0
        seq_replies_7d = 0
        try:
            r = self._db().table("sms_sequences") \
                .select("id", count="exact") \
                .eq("status", "active") \
                .execute()
            seq_active = r.count if hasattr(r, "count") else len(r.data or [])
        except Exception:
            pass

        try:
            r = self._db().table("sms_log") \
                .select("direction", count="exact") \
                .gte("created_at", last_7d) \
                .execute()
            all_logs = r.count if hasattr(r, "count") else 0
            # Estimate outbound vs inbound from a sample
            r2 = self._db().table("sms_log") \
                .select("direction") \
                .gte("created_at", last_7d) \
                .limit(500) \
                .execute()
            rows = r2.data or []
            outbound = sum(1 for row in rows if row.get("direction") == "outbound")
            inbound = sum(1 for row in rows if row.get("direction") == "inbound")
            if len(rows) > 0:
                ratio = outbound / len(rows)
                seq_sent_7d = int(all_logs * ratio) if ratio > 0 else 0
                seq_replies_7d = int(all_logs * (1 - ratio)) if ratio < 1 else 0
        except Exception:
            pass

        # Dispatches
        dispatches_7d = self._count_table("dispatches", last_7d)
        dispatches_30d = self._count_table("dispatches", last_30d)

        # Fee events (revenue)
        fees_7d = self._count_table("fee_events", last_7d)
        fees_30d = self._count_table("fee_events", last_30d)
        fee_revenue_7d = self._sum_table("fee_events", "fee_amount", last_7d)
        fee_revenue_30d = self._sum_table("fee_events", "fee_amount", last_30d)

        # ── Conversion rates ─────────────────────────────────────────────
        funnel_stages = [
            {"stage": "prospects", "volume_7d": prospects_7d, "volume_30d": prospects_30d,
             "description": "New prospects discovered via Google Places / scraping"},
            {"stage": "contractors", "volume_7d": contractors_7d, "volume_30d": contractors_30d,
             "description": "Contractors bridged from prospects"},
            {"stage": "enriched_leads", "volume_7d": enriched_leads_7d, "volume_30d": enriched_leads_30d,
             "description": "Leads enriched with scoring and metadata"},
            {"stage": "sms_active_sequences", "volume_7d": seq_active, "volume_30d": seq_active,
             "description": "Active SMS outreach sequences"},
            {"stage": "sms_sent_7d", "volume_7d": seq_sent_7d, "volume_30d": seq_sent_7d,
             "description": "SMS messages sent (outbound)"},
            {"stage": "sms_replies_7d", "volume_7d": seq_replies_7d, "volume_30d": seq_replies_7d,
             "description": "SMS replies received (inbound)"},
            {"stage": "dispatches", "volume_7d": dispatches_7d, "volume_30d": dispatches_30d,
             "description": "Contractor dispatches triggered"},
            {"stage": "fee_events", "volume_7d": fees_7d, "volume_30d": fees_30d,
             "description": "Closed fee events (revenue)"},
        ]

        # ── Bottleneck detection ─────────────────────────────────────────
        bottlenecks = []
        # Prospect → Contractor conversion
        if prospects_7d > 0:
            p_to_c_rate = contractors_7d / max(prospects_7d, 1) * 100
            if p_to_c_rate < 10:
                bottlenecks.append({
                    "stage": "prospects → contractors",
                    "rate_pct": round(p_to_c_rate, 1),
                    "severity": "high" if p_to_c_rate < 5 else "medium",
                    "detail": f"Only {round(p_to_c_rate,1)}% of prospects become contractors. Check prospector_bridge config.",
                })

        # Enriched leads → SMS outreach
        if enriched_leads_7d > 0 and seq_sent_7d > 0:
            send_rate = seq_sent_7d / max(enriched_leads_7d, 1)
            if send_rate < 0.5:
                bottlenecks.append({
                    "stage": "enriched_leads → sms_outreach",
                    "rate_pct": round(send_rate * 100, 1),
                    "severity": "medium",
                    "detail": "Low SMS send rate relative to enriched leads. Check lead_converter or compliance filters.",
                })

        # Reply rate
        if seq_sent_7d > 0:
            reply_rate = seq_replies_7d / max(seq_sent_7d, 1) * 100
            if reply_rate < 2:
                bottlenecks.append({
                    "stage": "sms_sent → replies",
                    "rate_pct": round(reply_rate, 1),
                    "severity": "high" if reply_rate < 0.5 else "medium",
                    "detail": f"Only {round(reply_rate,1)}% reply rate. Review SMS templates and targeting.",
                })

        # Dispatch → Fee conversion
        if dispatches_7d > 0 and fees_7d == 0:
            bottlenecks.append({
                "stage": "dispatches → closed_fees",
                "rate_pct": 0,
                "severity": "medium",
                "detail": "Dispatches exist but no fee events closed. Check settlement pipeline.",
            })

        return {
            "ts": now,
            "periods": {"24h": last_24h, "7d": last_7d, "30d": last_30d},
            "funnel_stages": funnel_stages,
            "revenue": {
                "fee_events_7d": fees_7d,
                "fee_events_30d": fees_30d,
                "fee_revenue_7d": round(fee_revenue_7d, 2),
                "fee_revenue_30d": round(fee_revenue_30d, 2),
            },
            "bottlenecks": bottlenecks,
            "bottleneck_count": len(bottlenecks),
        }

    # ── 2. GROWTH METRICS ────────────────────────────────────────────────

    def growth_metrics(self) -> dict:
        """Growth KPIs — daily, weekly, and monthly growth rates across
        key pipeline metrics."""
        now = self._now()
        last_7d = self._days_ago(7)
        last_30d = self._days_ago(30)
        prior_7d = self._days_ago(14)  # 7-14 days ago for WoW comparison
        prior_30d = self._days_ago(60)  # 30-60 days ago for MoM comparison

        # Current period volumes
        prospects_now = self._count_table("prospects", last_7d)
        contractors_now = self._count_table("contractors", last_7d)
        leads_now = self._count_table("enriched_leads", last_7d)
        fees_now = self._count_table("fee_events", last_7d)
        revenue_now = self._sum_table("fee_events", "fee_amount", last_7d)

        # Prior period volumes
        prospects_before = self._count_table("prospects", prior_7d) - prospects_now
        contractors_before = self._count_table("contractors", prior_7d) - contractors_now
        leads_before = self._count_table("enriched_leads", prior_7d) - leads_now
        fees_before = self._count_table("fee_events", prior_7d) - fees_now
        revenue_before = self._sum_table("fee_events", "fee_amount", prior_7d) - revenue_now

        # Monthly comparison
        prospects_month = self._count_table("prospects", last_30d)
        prospects_prior_month = self._count_table("prospects", prior_30d) - prospects_month
        revenue_month = self._sum_table("fee_events", "fee_amount", last_30d)
        revenue_prior_month = self._sum_table("fee_events", "fee_amount", prior_30d) - revenue_month

        def growth_rate(current: float, previous: float) -> float:
            if previous <= 0 and current > 0:
                return 100.0
            if previous <= 0:
                return 0.0
            return round((current - previous) / previous * 100, 1)

        metrics = {
            "prospects": {
                "weekly": {"current": prospects_now, "previous": max(0, prospects_before),
                          "growth_pct": growth_rate(prospects_now, max(0, prospects_before))},
                "monthly": {"current": prospects_month, "previous": max(0, prospects_prior_month),
                           "growth_pct": growth_rate(prospects_month, max(0, prospects_prior_month))},
            },
            "contractors": {
                "weekly": {"current": contractors_now, "previous": max(0, contractors_before),
                          "growth_pct": growth_rate(contractors_now, max(0, contractors_before))},
            },
            "enriched_leads": {
                "weekly": {"current": leads_now, "previous": max(0, leads_before),
                          "growth_pct": growth_rate(leads_now, max(0, leads_before))},
            },
            "fee_events": {
                "weekly": {"current": fees_now, "previous": max(0, fees_before),
                          "growth_pct": growth_rate(fees_now, max(0, fees_before))},
                "monthly": {"current": self._count_table("fee_events", last_30d),
                           "previous": max(0, self._count_table("fee_events", prior_30d) - self._count_table("fee_events", last_30d))},
            },
            "revenue": {
                "weekly": {"current": round(revenue_now, 2), "previous": round(max(0, revenue_before), 2),
                          "growth_pct": growth_rate(revenue_now, max(0, revenue_before))},
                "monthly": {"current": round(revenue_month, 2), "previous": round(max(0, revenue_prior_month), 2),
                           "growth_pct": growth_rate(revenue_month, max(0, revenue_prior_month))},
            },
        }

        # Overall growth health score
        scores = []
        for cat in metrics.values():
            for period, data in cat.items():
                if isinstance(data, dict) and "growth_pct" in data:
                    scores.append(data["growth_pct"])
        avg_growth = round(sum(scores) / max(len(scores), 1), 1) if scores else 0

        return {
            "ts": now,
            "growth_health_score": min(100, max(0, 50 + avg_growth)),
            "growth_health_label": (
                "accelerating" if avg_growth > 20
                else "growing" if avg_growth > 5
                else "stable" if avg_growth > -5
                else "declining" if avg_growth > -20
                else "critical"
            ),
            "metrics": metrics,
            "period_label": {
                "weekly": f"{self._days_ago(7)[:10]} to {now[:10]}",
                "monthly": f"{self._days_ago(30)[:10]} to {now[:10]}",
            },
        }

    # ── 3. MARKET EXPANSION INTELLIGENCE ─────────────────────────────────

    def expansion_opportunities(self) -> dict:
        """Score and rank market expansion opportunities.

        Evaluates:
          - Existing niches and their penetration
          - Niches/metros with high potential but low current activity
          - Untapped niches from the lane config or CPL pricing engine
        """
        now = self._now()

        # ── Current coverage ─────────────────────────────────────────────
        existing_niches = self._get_distinct("enriched_leads", "niche")
        existing_metros = self._get_distinct("contractors", "metro")
        existing_cities = self._get_distinct("enriched_leads", "city")

        # Remove empties
        existing_niches = [n for n in existing_niches if n]
        existing_metros = [m for m in existing_metros if m]
        existing_cities = [c for c in existing_cities if c]

        # ── Count activity per niche ──────────────────────────────────────
        niche_activity = {}
        for niche in existing_niches:
            try:
                r = self._db().table("enriched_leads") \
                    .select("id", count="exact") \
                    .eq("niche", niche) \
                    .execute()
                count = r.count if hasattr(r, "count") else len(r.data or [])
                r2 = self._db().table("enriched_leads") \
                    .select("id", count="exact") \
                    .eq("niche", niche) \
                    .gte("created_at", self._days_ago(7)) \
                    .execute()
                recent = r2.count if hasattr(r2, "count") else 0
                niche_activity[niche] = {"total": count, "recent_7d": recent}
            except Exception:
                niche_activity[niche] = {"total": 0, "recent_7d": 0}

        # ── Score each niche ─────────────────────────────────────────────
        scored_niches = []
        for niche, activity in sorted(niche_activity.items()):
            total = activity["total"]
            recent = activity["recent_7d"]

            # Score: higher is better opportunity
            # Factors: recent activity, total volume, velocity
            volume_score = min(total / 10, 50)  # up to 50 pts for total volume
            velocity_score = min(recent * 5, 30)  # up to 30 pts for recent activity
            penetration_score = max(0, 20 - len(existing_metros) * 2)  # less metro saturation = better

            total_score = round(volume_score + velocity_score + penetration_score, 1)

            scored_niches.append({
                "niche": niche,
                "total_leads": total,
                "recent_7d_leads": recent,
                "velocity": round(recent / max(total, 1) * 100, 1) if total > 0 else 0,
                "score": total_score,
                "opportunity_level": (
                    "high" if total_score >= 60
                    else "medium" if total_score >= 35
                    else "low"
                ),
            })

        scored_niches.sort(key=lambda n: n["score"], reverse=True)

        # ── Metro expansion opportunities ────────────────────────────────
        metro_opportunities = []
        # Key metros to evaluate
        target_metros = ["Dallas", "Houston", "San Antonio", "Austin", "Fort Worth",
                         "Phoenix", "Denver", "Atlanta", "Chicago", "Nashville",
                         "Charlotte", "Tampa", "Orlando", "Miami", "Raleigh"]
        for metro in target_metros:
            already_present = any(metro.lower() in m.lower() for m in existing_metros)
            contractor_count = 0
            try:
                r = self._db().table("contractors") \
                    .select("id", count="exact") \
                    .ilike("metro", f"%{metro}%") \
                    .execute()
                contractor_count = r.count if hasattr(r, "count") else 0
            except Exception:
                pass

            metro_opportunities.append({
                "metro": metro,
                "has_presence": already_present,
                "contractor_count": contractor_count,
                "expansion_priority": (
                    "critical" if contractor_count > 20
                    else "high" if contractor_count > 10
                    else "medium" if contractor_count > 3
                    else "explore"
                ),
            })

        # ── Expansion summary ─────────────────────────────────────────────
        high_opps = [n for n in scored_niches if n["opportunity_level"] == "high"]
        high_metro_opps = [m for m in metro_opportunities
                          if m["expansion_priority"] in ("critical", "high")]

        return {
            "ts": now,
            "current_coverage": {
                "niches": len(existing_niches),
                "metros": len(existing_metros),
                "cities": len(existing_cities),
                "niche_list": sorted(existing_niches),
                "metro_list": sorted(existing_metros),
            },
            "niche_opportunities": scored_niches[:20],  # top 20
            "metro_opportunities": metro_opportunities,
            "expansion_recommendations": [
                {
                    "type": "expand_niche",
                    "target": n["niche"],
                    "priority": n["opportunity_level"],
                    "score": n["score"],
                    "rationale": f"{n['total_leads']} total leads, {n['recent_7d_leads']} in last 7 days",
                }
                for n in high_opps
            ] + [
                {
                    "type": "expand_metro",
                    "target": m["metro"],
                    "priority": m["expansion_priority"],
                    "rationale": f"{m['contractor_count']} contractors in area",
                }
                for m in high_metro_opps if not m["has_presence"]
            ],
            "total_expansion_actions": len(high_opps) + len(high_metro_opps),
        }

    # ── 4. GROWTH OPPORTUNITIES (actionable items) ────────────────────────

    def growth_opportunities(self) -> list[dict]:
        """Generate specific actionable growth opportunities with expected impact."""
        funnel = self.funnel_analysis()
        metrics = self.growth_metrics()
        expansion = self.expansion_opportunities()
        opportunities = []

        # ── From bottlenecks ──────────────────────────────────────────────
        for b in funnel.get("bottlenecks", []):
            if b["severity"] in ("high", "medium"):
                opportunities.append({
                    "id": f"GROWTH-{len(opportunities)+1:04d}",
                    "category": "bottleneck",
                    "title": f"Fix bottleneck: {b['stage']}",
                    "detail": b["detail"],
                    "severity": b["severity"],
                    "expected_impact": "funnel_improvement",
                    "auto_actionable": b["stage"] in (
                        "prospects → contractors",
                        "enriched_leads → sms_outreach",
                    ),
                })

        # ── From expansion opportunities ─────────────────────────────────
        for rec in expansion.get("expansion_recommendations", []):
            opportunities.append({
                "id": f"GROWTH-{len(opportunities)+1:04d}",
                "category": "expansion",
                "title": f"{rec['type'].replace('_', ' ').title()}: {rec['target']}",
                "detail": rec["rationale"],
                "severity": rec["priority"],
                "expected_impact": "new_revenue_stream",
                "auto_actionable": rec["type"] == "expand_niche",
            })

        # ── From growth metrics ───────────────────────────────────────────
        growth_health = metrics.get("growth_health_label", "stable")
        if growth_health in ("declining", "critical"):
            opportunities.append({
                "id": f"GROWTH-{len(opportunities)+1:04d}",
                "category": "health",
                "title": f"Growth is {growth_health} — review strategy",
                "detail": f"Overall growth health score: {metrics.get('growth_health_score', 0)}/100",
                "severity": "high",
                "expected_impact": "recovery",
                "auto_actionable": False,
            })

        # ── Growth velocity opportunity ──────────────────────────────────
        prospects_metric = metrics.get("metrics", {}).get("prospects", {}).get("weekly", {})
        prospect_growth = prospects_metric.get("growth_pct", 0)
        if prospect_growth < 0:
            opportunities.append({
                "id": f"GROWTH-{len(opportunities)+1:04d}",
                "category": "velocity",
                "title": "Prospect generation declining — trigger sweep",
                "detail": f"Prospect growth is {prospect_growth}% WoW. New prospector sweep may be needed.",
                "severity": "medium",
                "expected_impact": "pipeline_replenishment",
                "auto_actionable": True,
            })

        # Sort by severity
        severity_order = {"high": 0, "medium": 1, "low": 2}
        opportunities.sort(key=lambda o: severity_order.get(o["severity"], 99))

        return opportunities

    # ── 5. OVERVIEW (dashboard snapshot) ─────────────────────────────────

    def overview(self) -> dict:
        """Growth dashboard — one-call overview of growth state."""
        funnel = self.funnel_analysis()
        metrics = self.growth_metrics()
        expansion = self.expansion_opportunities()

        return {
            "ts": self._now(),
            "growth_health": {
                "score": metrics.get("growth_health_score", 0),
                "label": metrics.get("growth_health_label", "unknown"),
            },
            "funnel_summary": {
                "stages": len(funnel.get("funnel_stages", [])),
                "bottlenecks": funnel.get("bottleneck_count", 0),
                "revenue_7d": funnel.get("revenue", {}).get("fee_revenue_7d", 0),
                "revenue_30d": funnel.get("revenue", {}).get("fee_revenue_30d", 0),
            },
            "expansion_summary": {
                "existing_niches": expansion.get("current_coverage", {}).get("niches", 0),
                "existing_metros": expansion.get("current_coverage", {}).get("metros", 0),
                "expansion_actions": expansion.get("total_expansion_actions", 0),
            },
            "modified": self._now(),
        }

    # ── 6. AUTO-TRIGGER ACTIONS ──────────────────────────────────────────

    async def trigger_prospector_sweep(self, niche: Optional[str] = None,
                                        metro: Optional[str] = None) -> dict:
        """Trigger a prospector sweep for a niche and/or metro.

        Runs the prospector scan via bots.prospector module.
        Falls back to recording the action if the scanner can't be called.
        """
        action = {
            "action": "prospector_sweep",
            "niche": niche or "all",
            "metro": metro or "all",
            "triggered_at": self._now(),
        }

        try:
            from bots.prospector import run_multi as prospector_run
            metros_list = [metro] if metro else None
            niches_list = [niche] if niche else None
            result = await prospector_run(
                dry_run=False,
                metros=metros_list,
                niches=niches_list,
            )
            action["result"] = result
            action["status"] = "completed"
        except Exception as e:
            log.info(f"[growth] prospector sweep queued for niche={niche}, metro={metro}: {e}")
            action["status"] = "queued"
            action["note"] = f"Prospector module not callable: {e}"

        self._action_history.append(action)
        return action

    async def trigger_campaign_creation(self, niche: str, budget: float = 100.0) -> dict:
        """Create a native ad campaign for a growth niche.

        Records the campaign creation intent. Actual campaign creation
        requires the NativeAdsNetwork instance from the hub.
        """
        action = {
            "action": "create_campaign",
            "niche": niche,
            "budget": budget,
            "triggered_at": self._now(),
            "status": "queued",
            "note": f"Campaign creation for niche '{niche}' queued — trigger via /api/native/campaigns or native_ads.create_campaign()",
        }
        self._action_history.append(action)
        return action

    async def trigger_outreach_enroll(self, niche: str, limit: int = 20) -> dict:
        """Enroll top potentials in a niche into outreach sequences.

        Identifies top enriched_leads without active SMS sequences.
        Records enrollment intent — actual enrollment requires lead_converter.
        """
        action = {
            "action": "outreach_enroll",
            "niche": niche,
            "limit": limit,
            "triggered_at": self._now(),
        }

        try:
            db = self._db()
            r = db.table("enriched_leads") \
                .select("id, phone, name, city, state") \
                .eq("niche", niche) \
                .limit(limit) \
                .execute()
            leads = r.data or []

            if not leads:
                action["status"] = "skipped"
                action["note"] = f"No enriched leads found for niche '{niche}'"
            else:
                action["status"] = "queued"
                action["candidates"] = len(leads)
                action["note"] = f"Outreach enrollment queued for {len(leads)} leads in niche '{niche}' — trigger via lead_converter module"
        except Exception as e:
            action["status"] = "failed"
            action["error"] = str(e)[:200]

        self._action_history.append(action)
        return action

    def action_history(self, limit: int = 20) -> list[dict]:
        """Return recent automated action history."""
        return self._action_history[-limit:]

    # ── SNAPSHOT ─────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Condensed snapshot for the fleet dashboard."""
        overview = self.overview()
        opportunities = self.growth_opportunities()
        return {
            "growth_health_score": overview.get("growth_health", {}).get("score", 0),
            "growth_health_label": overview.get("growth_health", {}).get("label", "unknown"),
            "revenue_7d": overview.get("funnel_summary", {}).get("revenue_7d", 0),
            "revenue_30d": overview.get("funnel_summary", {}).get("revenue_30d", 0),
            "bottlenecks": overview.get("funnel_summary", {}).get("bottlenecks", 0),
            "expansion_actions": overview.get("expansion_summary", {}).get("expansion_actions", 0),
            "niches": overview.get("expansion_summary", {}).get("existing_niches", 0),
            "metros": overview.get("expansion_summary", {}).get("existing_metros", 0),
            "open_opportunities": len(opportunities),
            "auto_actionable": sum(1 for o in opportunities if o.get("auto_actionable")),
            "modified": self._now(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_growth_routes(app, get_db=None, require_auth=None):
    """Register Business Growth Agent routes on a FastAPI app.

    Args:
        app: FastAPI application.
        get_db: Callable returning a Supabase client. Required.
        require_auth: Optional FastAPI dependency for auth.
    """
    from fastapi import Depends, HTTPException, Query

    if get_db is None:
        log.warning("[growth] No get_db provided — agent will return errors on DB calls")

    _growth = BusinessGrowthAgent(get_db=get_db) if get_db else None

    def _get_growth():
        if _growth is None:
            raise HTTPException(503, "Business Growth Agent not initialized (no get_db)")
        return _growth

    # ── GET: Growth Overview ─────────────────────────────────────────────
    @app.get("/api/growth/overview")
    async def growth_overview(auth=Depends(require_auth) if require_auth else None):
        """Growth dashboard overview — health score, funnel summary, expansion summary."""
        return _get_growth().overview()

    # ── GET: Funnel Analysis ─────────────────────────────────────────────
    @app.get("/api/growth/funnel")
    async def growth_funnel(auth=Depends(require_auth) if require_auth else None):
        """Pipeline funnel analysis with bottleneck detection."""
        return _get_growth().funnel_analysis()

    # ── GET: Growth Metrics ──────────────────────────────────────────────
    @app.get("/api/growth/metrics")
    async def growth_metrics(auth=Depends(require_auth) if require_auth else None):
        """Growth KPIs — daily, weekly, monthly growth rates."""
        return _get_growth().growth_metrics()

    # ── GET: Expansion Opportunities ────────────────────────────────────
    @app.get("/api/growth/expansion")
    async def growth_expansion(auth=Depends(require_auth) if require_auth else None):
        """Market expansion opportunities — scored niches and metros."""
        return _get_growth().expansion_opportunities()

    # ── GET: Growth Opportunities ───────────────────────────────────────
    @app.get("/api/growth/opportunities")
    async def growth_opportunities(auth=Depends(require_auth) if require_auth else None):
        """Actionable growth opportunities with expected impact."""
        return {"opportunities": _get_growth().growth_opportunities()}

    # ── POST: Trigger Prospector Sweep ──────────────────────────────────
    @app.post("/api/growth/actions/sweep")
    async def growth_action_sweep(
        niche: str = Query("", description="Target niche"),
        metro: str = Query("", description="Target metro"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Trigger a prospector sweep for a niche and/or metro."""
        result = await _get_growth().trigger_prospector_sweep(
            niche=niche or None,
            metro=metro or None,
        )
        status = 200 if result.get("status") != "failed" else 500
        return result

    # ── POST: Create Campaign ───────────────────────────────────────────
    @app.post("/api/growth/actions/campaign")
    async def growth_action_campaign(
        niche: str = Query(..., description="Target niche for campaign"),
        budget: float = Query(100.0, ge=10, le=10000, description="Daily budget in USD"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Create a native ad campaign targeting a growth niche."""
        result = await _get_growth().trigger_campaign_creation(
            niche=niche,
            budget=budget,
        )
        status = 200 if result.get("status") != "failed" else 500
        return result

    # ── POST: Enroll Outreach ───────────────────────────────────────────
    @app.post("/api/growth/actions/enroll")
    async def growth_action_enroll(
        niche: str = Query(..., description="Target niche"),
        limit: int = Query(20, ge=1, le=100, description="Max leads to enroll"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Enroll top potentials in a niche into outreach sequences."""
        result = await _get_growth().trigger_outreach_enroll(
            niche=niche,
            limit=limit,
        )
        status = 200 if result.get("status") != "failed" else 500
        return result

    # ── GET: Action History ─────────────────────────────────────────────
    @app.get("/api/growth/actions/history")
    async def growth_action_history(
        limit: int = Query(20, ge=1, le=100),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Recent automated action history."""
        return {"actions": _get_growth().action_history(limit=limit)}

    # ── GET: Snapshot ────────────────────────────────────────────────────
    @app.get("/api/growth/snapshot")
    async def growth_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Condensed snapshot for fleet dashboard integration."""
        return _get_growth().snapshot()

    log.info("[growth] Routes registered · /api/growth/*")
