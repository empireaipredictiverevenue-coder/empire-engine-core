"""
EMPIRE V49 · BUSINESS PLANNER AGENT
=====================================
Generates quarterly business plans by synthesizing data from:
  - SelfAwarenessEngine (system model, anomalies, improvements)
  - LoopAgent (Rank & Rent scores, evolution history, lane performance)
  - PsychologyMindMap (effectiveness data per niche/persona/principle)
  - StrategistAgent (overview, recommendations, trends)
  - BusinessManagementAgent (exec report, OKRs, health)

Produces structured quarterly plans with:
  - Executive summary with revenue targets
  - Niche-by-niche action plans
  - Resource allocation recommendations
  - Risk assessment and mitigation
  - Action item roadmap with priorities
"""

import logging
from datetime import datetime, timezone
from typing import Optional, Callable

log = logging.getLogger("empire.business_planner")


class BusinessPlannerAgent:
    """Generates quarterly business plans from live system intelligence.

    Data sources can be injected via constructor for testing or override.
    """

    def __init__(
        self,
        get_db: Optional[Callable] = None,
        *,
        self_awareness: Optional[object] = None,
        loop_agent: Optional[object] = None,
        psychology_mind_map: Optional[object] = None,
        strategist: Optional[object] = None,
        business_mgmt: Optional[object] = None,
    ):
        self.get_db = get_db
        self._self_awareness = self_awareness
        self._loop_agent = loop_agent
        self._psychology_mind_map = psychology_mind_map
        self._strategist = strategist
        self._business_mgmt = business_mgmt

    # ── DATA SOURCES ─────────────────────────────────────────────────────────

    def _get_self_awareness(self) -> dict:
        """Snapshot from SelfAwarenessEngine."""
        if self._self_awareness is not None:
            return self._self_awareness.snapshot()
        try:
            from empire_self_awareness import SelfAwarenessEngine
            engine = SelfAwarenessEngine()
            return engine.snapshot()
        except Exception as e:
            log.debug(f"[planner] self-awareness failed: {e}")
            return {}

    def _get_loop_data(self) -> dict:
        """Data from LoopAgent: Rank & Rent, evolution, overview."""
        out = {"rank_rent": [], "overview": {}, "evolutions": [], "suggestions": []}
        if self._loop_agent is not None:
            a = self._loop_agent
            out["rank_rent"] = a.all_rank_rent_scores() or []
            out["overview"] = a.loop_overview() or {}
            out["evolutions"] = a.evolution_history() or []
            out["suggestions"] = a.optimization_suggestions() or []
            return out
        try:
            from empire_loop_agent import LoopAgent
            a = LoopAgent()
            out["rank_rent"] = a.all_rank_rent_scores() or []
            out["overview"] = a.loop_overview() or {}
            out["evolutions"] = a.evolution_history() or []
            out["suggestions"] = a.optimization_suggestions() or []
        except Exception as e:
            log.debug(f"[planner] loop agent failed: {e}")
        return out

    def _get_psychology_data(self) -> dict:
        """Effectiveness data from PsychologyMindMap."""
        out = {"effectiveness": {}, "snapshot": {}, "profiles": []}
        if self._psychology_mind_map is not None:
            pm = self._psychology_mind_map
            out["effectiveness"] = pm.get_effectiveness_summary() or {}
            out["snapshot"] = pm.snapshot() or {}
            profiles = pm.get_all_niche_profiles() or []
            out["profiles"] = profiles
            return out
        try:
            from empire_psychology_mind_map import PsychologyMindMap
            pm = PsychologyMindMap()
            out["effectiveness"] = pm.get_effectiveness_summary() or {}
            out["snapshot"] = pm.snapshot() or {}
            profiles = pm.get_all_niche_profiles() or []
            out["profiles"] = profiles
        except Exception as e:
            log.debug(f"[planner] psychology failed: {e}")
        return out

    def _get_strategist_data(self) -> dict:
        """Data from StrategistAgent."""
        out = {"overview": {}, "recommendations": [], "trends": {}, "narrative": ""}
        if self._strategist is not None:
            s = self._strategist
            out["overview"] = s.overview() or {}
            out["recommendations"] = s.recommendations() or []
            out["trends"] = s.trends() or {}
            narr = s.generate_narrative() or {}
            out["narrative"] = narr.get("narrative", "")
            return out
        try:
            from empire_strategist import StrategistAgent
            s = StrategistAgent()
            out["overview"] = s.overview() or {}
            out["recommendations"] = s.recommendations() or []
            out["trends"] = s.trends() or {}
            narr = s.generate_narrative() or {}
            out["narrative"] = narr.get("narrative", "")
        except Exception as e:
            log.debug(f"[planner] strategist failed: {e}")
        return out

    def _get_business_data(self) -> dict:
        """Data from BusinessManagementAgent."""
        out = {"exec_report": {}, "okrs": {}, "health": {}}
        if self._business_mgmt is not None:
            b = self._business_mgmt
            out["exec_report"] = b.exec_report() or {}
            out["okrs"] = b.okrs() or {}
            out["health"] = b.health() or {}
            return out
        try:
            from empire_business_mgmt_agent import BusinessManagementAgent
            b = BusinessManagementAgent()
            out["exec_report"] = b.exec_report() or {}
            out["okrs"] = b.okrs() or {}
            out["health"] = b.health() or {}
        except Exception as e:
            log.debug(f"[planner] business mgmt failed: {e}")
        return out

    # ── QUARTERLY PLAN GENERATION ───────────────────────────────────────────

    def quarterly_plan(self, quarter: str = "Q2 2026") -> dict:
        """Generate a complete quarterly business plan from all data sources."""
        sa = self._get_self_awareness()
        loop = self._get_loop_data()
        psych = self._get_psychology_data()
        strat = self._get_strategist_data()
        biz = self._get_business_data()

        overview = loop.get("overview", {})
        rank_rent = loop.get("rank_rent", [])
        evolutions = loop.get("evolutions", [])
        exec_rep = biz.get("exec_report", {})
        okrs = biz.get("okrs", {})
        health = biz.get("health", {})
        anomalies = sa.get("anomalies", [])
        improvements = sa.get("improvements", [])
        psych_eff = psych.get("effectiveness", {})

        # ── 1. Executive Summary ────────────────────────────────────────────
        current_mrr = exec_rep.get("revenue", {}).get("mrr_projected", 0)
        revenue_24h = exec_rep.get("revenue", {}).get("revenue_24h", 0)
        health_score = exec_rep.get("health_score", 0)
        total_lanes = overview.get("total_lanes", 0)
        total_runs = overview.get("total_runs", 0)
        total_wins = overview.get("total_wins", 0)
        overall_win_rate = overview.get("overall_win_rate", 0)

        target_mrr = max(10000, round(current_mrr * 3))  # 3x MRR target
        target_niches = min(12, max(5, len(rank_rent)))  # cover all rankable niches

        # Determine health label and focus direction
        health_label = exec_rep.get("health_label", "stable")
        if health_score < 30:
            health_status = "critical"
            focus = "Restore system health before scaling"
        elif health_score < 50:
            health_status = "attention"
            focus = "Address anomalies and strengthen core metrics"
        elif health_score < 70:
            health_status = "improving"
            focus = "Scale proven niches and expand into adjacent markets"
        else:
            health_status = "healthy"
            focus = "Maximum growth — push all high-potential niches"

        exec_summary = {
            "quarter": quarter,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "health_status": health_status,
            "focus": focus,
            "current_state": {
                "health_score": health_score,
                "health_label": exec_rep.get("health_label", "unknown"),
                "current_mrr": current_mrr,
                "revenue_24h": revenue_24h,
                "total_lanes": total_lanes,
                "total_runs": total_runs,
                "total_wins": total_wins,
                "overall_win_rate": round(overall_win_rate * 100, 1),
                "active_niches": len(rank_rent),
                "evolution_cycles": len(evolutions),
            },
            "targets": {
                "target_mrr": target_mrr,
                "target_mrr_date": f"{quarter} end",
                "target_niches": target_niches,
                "target_win_rate_pct": min(85, round(overall_win_rate * 100 * 1.3, 1)),
                "target_health_score": min(90, health_score + 20),
            },
            "confidence_score": round(
                min(
                    (health_score * 0.3 +
                     min(current_mrr / target_mrr, 1) * 100 * 0.3 +
                     overall_win_rate * 100 * 0.2 +
                     len(rank_rent) / target_niches * 100 * 0.2),
                    100
                ), 1
            ),
        }

        # ── 2. Niche-by-Niche Plans ──────────────────────────────────────────
        niche_plans = []
        for item in rank_rent:
            niche = item.get("niche", "unknown")
            score = item.get("score", 0)
            verdict = item.get("verdict", "WEAK")
            price_model = item.get("price_model", "flat_rent")
            estimated_revenue = item.get("estimated_monthly_revenue", 0)
            competition = item.get("competition", "medium")
            lead_value = item.get("typical_lead_value_usd", 0)

            # Find psychology profile if available
            psych_profile = None
            for prof in psych.get("profiles", []):
                if isinstance(prof, dict) and prof.get("niche", "").lower() in niche.lower():
                    psych_profile = prof
                    break

            # Determine priority based on Rank & Rent score + system state
            priority = "low"
            if score >= 70 and verdict in ("STRONG_RENT", "RENTABLE"):
                priority = "critical"
            elif score >= 50:
                priority = "high"
            elif score >= 30:
                priority = "medium"

            # Strategy recommendation from evolution history
            evo_for_niche = [
                e for e in evolutions
                if e.get("niche", "").lower() in niche.lower() or
                   e.get("old_strategy", "").lower() in niche.lower()
            ]
            evolution_count = len(evo_for_niche)
            last_evolution = evo_for_niche[-1].get("ts", "") if evo_for_niche else ""

            # Psychology recommendations
            psych_recommendation = None
            if psych_profile:
                persona = psych_profile.get("recommended_persona") or \
                          psych_profile.get("best_persona") or \
                          psych_eff.get("best_persona")
                princ = psych_profile.get("best_principle") or \
                        psych_eff.get("best_principle")
                if persona or princ:
                    psych_recommendation = {
                        "persona": persona,
                        "principle": princ,
                    }

            niche_plans.append({
                "niche": niche,
                "priority": priority,
                "rank_rent_score": score,
                "verdict": verdict,
                "price_model": price_model,
                "current_monthly_revenue_est": estimated_revenue,
                "competition": competition,
                "lead_value": lead_value,
                "evolution_count": evolution_count,
                "last_evolution": last_evolution,
                "psychology_recommendation": psych_recommendation,
                "actions": self._recommend_niche_actions(
                    niche, score, verdict, competition, psych_recommendation,
                ),
            })

        # Sort by priority: critical → high → medium → low
        priority_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
        niche_plans.sort(key=lambda n: priority_order.get(n["priority"], 99))

        # ── 3. Resource Allocation ───────────────────────────────────────────
        resource_plan = self._generate_resource_plan(
            niche_plans, loop, biz, psych,
        )

        # ── 4. Risk Assessment ───────────────────────────────────────────────
        risk_plan = self._generate_risk_plan(anomalies, improvements, sa, biz)

        # ── 5. Action Item Roadmap ───────────────────────────────────────────
        actions = self._generate_action_roadmap(
            niche_plans, anomalies, improvements, psych_eff, biz,
        )

        # ── 6. Psychology Effectiveness Insights ─────────────────────────────
        psych_insights = {
            "overall_conversion_rate": psych_eff.get("overall_conversion_rate", 0),
            "total_attempts": psych_eff.get("total_attempts", 0),
            "total_successes": psych_eff.get("total_successes", 0),
            "combinations_tracked": psych_eff.get("total_combinations_tracked", 0),
            "best_persona": psych_eff.get("best_persona"),
            "best_principle": psych_eff.get("best_principle"),
            "best_niche": psych_eff.get("best_niche"),
        }

        return {
            "quarter": quarter,
            "generated_at": exec_summary["generated_at"],
            "executive_summary": exec_summary,
            "niche_plans": niche_plans,
            "resource_allocation": resource_plan,
            "risk_assessment": risk_plan,
            "action_roadmap": actions,
            "psychology_insights": psych_insights,
            "strategist_narrative": strat.get("narrative", ""),
            "okr_summary": okrs.get("summary", {}),
            "anomalies": [
                {"title": a.get("title", a.get("type", "?")),
                 "severity": a.get("severity", "info"),
                 "details": str(a.get("details", ""))}
                for a in anomalies
            ],
            "total_niches_planned": len(niche_plans),
            "total_actions": len(actions),
        }

    def niche_plan(self, niche: str) -> dict:
        """Generate a plan for a single niche."""
        full = self.quarterly_plan()
        niche_plan = None
        for np in full.get("niche_plans", []):
            if np["niche"].lower() == niche.lower():
                niche_plan = np
                break
        if not niche_plan:
            niche_plan = {
                "niche": niche,
                "priority": "unknown",
                "error": "Niche not found in Rank & Rent data",
                "actions": [{"action": "gather_data", "detail": "Run Rank & Rent analysis for this niche"}],
            }

        return {
            "quarter": full["quarter"],
            "generated_at": full["generated_at"],
            "niche_plan": niche_plan,
            "executive_summary": full["executive_summary"],
            "psychology_insight": next(
                (p.get("psychology_recommendation") for p in full.get("niche_plans", [])
                 if p["niche"].lower() == niche.lower()), None
            ),
            "anomalies_relevant": [
                a for a in full.get("anomalies", [])
                if niche.lower() in a.get("title", "").lower() or
                   niche.lower() in a.get("details", "").lower()
            ],
        }

    def plan_summary(self) -> dict:
        """Return a condensed executive summary without full niche breakdown."""
        full = self.quarterly_plan()
        exec_sum = full.get("executive_summary", {})
        critical = [n for n in full.get("niche_plans", []) if n["priority"] == "critical"]
        high = [n for n in full.get("niche_plans", []) if n["priority"] == "high"]

        return {
            "quarter": full["quarter"],
            "generated_at": full["generated_at"],
            "executive_summary": exec_sum,
            "top_priorities": {
                "critical_niches": [n["niche"] for n in critical],
                "high_priority_niches": [n["niche"] for n in high],
            },
            "action_count": full.get("total_actions", 0),
            "niche_count": full.get("total_niches_planned", 0),
            "narrative": full.get("strategist_narrative", ""),
            "okr_summary": full.get("okr_summary", {}),
        }

    # ── INTERNAL HELPERS ────────────────────────────────────────────────────

    def _recommend_niche_actions(
        self,
        niche: str,
        score: float,
        verdict: str,
        competition: str,
        psych_rec: Optional[dict],
    ) -> list[dict]:
        """Generate recommended actions for a single niche."""
        actions = []

        # Rank & Rent action
        if score >= 50 or verdict in ("STRONG_RENT", "RENTABLE"):
            # Determine best pricing model
            model_detail = ""
            if score >= 80:
                model_detail = "Premium pricing viable — push PPL or flat monthly retainer"
            elif score >= 60:
                model_detail = "Competitive pricing — split between PPL and flat rent"
            else:
                model_detail = "Entry pricing — start with PPL to win market share"
            actions.append({
                "action": "launch_or_scale",
                "category": "revenue",
                "priority": "critical" if score >= 70 else "high",
                "detail": f"Rank & Rent score {score}. {model_detail}",
                "expected_impact": f"~${score * 50} monthly",
            })

        # Psychology action
        if psych_rec:
            persona = psych_rec.get("persona")
            principle = psych_rec.get("principle")
            parts = ["Apply psychology framework"]
            if persona:
                parts.append(f"persona={persona}")
            if principle:
                parts.append(f"principle={principle}")
            actions.append({
                "action": "apply_psychology",
                "category": "optimization",
                "priority": "high",
                "detail": " · ".join(parts),
                "expected_impact": "Improved conversion through persona-matched messaging",
            })

        # Competition action
        if competition in ("high", "very_high") and score >= 50:
            actions.append({
                "action": "differentiate",
                "category": "strategy",
                "priority": "high",
                "detail": f"High competition ({competition}) — focus on unique value props and niche specialization",
                "expected_impact": "Reduced cost per lead through differentiation",
            })
        elif competition in ("low", "very_low"):
            actions.append({
                "action": "dominate",
                "category": "strategy",
                "priority": "critical",
                "detail": f"Low competition ({competition}) — aggressive capture of market share",
                "expected_impact": "Fast market dominance at lower acquisition cost",
            })

        # Data gathering
        if score < 30:
            actions.append({
                "action": "gather_data",
                "category": "research",
                "priority": "high",
                "detail": "Low Rank & Rent score — validate market demand and refine niche targeting",
                "expected_impact": "Clearer go/no-go decision for this niche",
            })

        return actions

    def _generate_resource_plan(
        self,
        niche_plans: list[dict],
        loop: dict,
        biz: dict,
        psych: dict,
    ) -> dict:
        """Generate resource allocation recommendations."""
        critical = [n for n in niche_plans if n["priority"] == "critical"]
        high = [n for n in niche_plans if n["priority"] == "high"]

        # Recommended allocation percentages
        total = len([n for n in niche_plans if n["priority"] in ("critical", "high", "medium")])
        if total == 0:
            allocation_pct = {}
        else:
            critical_pct = min(60, max(20, len(critical) * 15))
            high_pct = min(40, max(10, len(high) * 10))
            medium_pct = max(5, 100 - critical_pct - high_pct)
            allocation_pct = {
                "critical_niches": min(critical_pct, 60),
                "high_priority_niches": min(high_pct, 40),
                "medium_priority_niches": max(medium_pct, 5),
                "low_priority_niches": 5,
            }

        return {
            "recommended_focus": {
                "niches_to_prioritize": [n["niche"] for n in critical + high],
                "niches_to_monitor": [n["niche"] for n in niche_plans if n["priority"] == "medium"],
                "niches_to_reassess": [n["niche"] for n in niche_plans if n["priority"] == "low"],
            },
            "allocation_pct": allocation_pct,
            "resource_notes": [
                "Prioritize critical and high-priority niches first",
                "Allocate psychology persona matching to top 3 revenue niches",
                f"Evolution cycles: {len(loop.get('evolutions', []))} runs available for strategy mutation",
            ],
        }

    def _generate_risk_plan(
        self,
        anomalies: list,
        improvements: list,
        sa: dict,
        biz: dict,
    ) -> dict:
        """Generate risk assessment and mitigation plan."""
        risks = []
        for anom in anomalies:
            title = anom.get("title", anom.get("type", "Unknown"))
            severity = anom.get("severity", "info")
            details = str(anom.get("details", ""))
            risks.append({
                "risk": title,
                "severity": severity,
                "finding": details,
                "recommended_action": self._mitigation_for_anomaly(title),
            })

        # Generate from improvements too
        for imp in improvements:
            title = imp.get("title", imp.get("type", "Unknown"))
            risks.append({
                "risk": title,
                "severity": "info",
                "finding": str(imp.get("detail", "")),
                "recommended_action": str(imp.get("suggestion", "Review and act")),
            })

        # Business health risks
        exec_rep = biz.get("exec_report", {})
        health_score = exec_rep.get("health_score", 0)
        if health_score < 40:
            risks.append({
                "risk": "low_system_health",
                "severity": "critical",
                "finding": f"System health score is {health_score}/100",
                "recommended_action": "Address critical anomalies and improve base metrics before expanding",
            })

        return {
            "risks": risks,
            "total_risks": len(risks),
            "critical_risks": sum(1 for r in risks if r["severity"] == "critical"),
            "warning_risks": sum(1 for r in risks if r["severity"] in ("warning", "high")),
        }

    def _mitigation_for_anomaly(self, title: str) -> str:
        """Return a recommended mitigation for a known anomaly type."""
        mitigations = {
            "zero_revenue_24h": "Verify buyer pipeline, check call routing, review payout settlement",
            "low_win_rate": "Run strategy evolution cycle, adjust lane configuration",
            "stale_agent": "Restart the agent via Process Manager or PM2",
            "no_evolution": "Trigger forced evolution run on underperforming lanes",
            "agent_count_low": "Register missing agents in agent_registry",
        }
        for key, mitigation in mitigations.items():
            if key in title.lower():
                return mitigation
        return "Investigate and determine root cause"

    def _generate_action_roadmap(
        self,
        niche_plans: list,
        anomalies: list,
        improvements: list,
        psych_eff: dict,
        biz: dict,
    ) -> list[dict]:
        """Generate a prioritized action item roadmap."""
        actions = []
        action_id = 1

        # Critical items from anomalies
        for anom in anomalies:
            title = anom.get("title", anom.get("type", "Unknown"))
            severity = anom.get("severity", "info")
            if severity in ("critical", "warning", "high"):
                actions.append({
                    "id": f"ACT-{action_id:03d}",
                    "action": f"Resolve: {title}",
                    "category": "immediate",
                    "priority": severity,
                    "timeline": "this_week",
                    "owner": "system",
                })
                action_id += 1

        # Critical and high priority niche actions
        for np in niche_plans:
            if np["priority"] in ("critical", "high"):
                for act in np.get("actions", []):
                    if act.get("priority") in ("critical", "high"):
                        actions.append({
                            "id": f"ACT-{action_id:03d}",
                            "action": f"[{np['niche']}] {act['action']}: {act['detail'][:60]}",
                            "category": "niche_growth",
                            "priority": act["priority"],
                            "timeline": "next_2_weeks" if act["priority"] == "critical" else "this_month",
                            "owner": "operator",
                            "expected_impact": act.get("expected_impact", ""),
                        })
                        action_id += 1

        # Psychology optimization actions
        if psych_eff.get("overall_conversion_rate", 0) < 0.3 and psych_eff.get("total_attempts", 0) > 0:
            actions.append({
                "id": f"ACT-{action_id:03d}",
                "action": "Improve psychology effectiveness — current conversion rate below 30%",
                "category": "optimization",
                "priority": "high",
                "timeline": "this_month",
                "owner": "operator",
                "expected_impact": "Higher conversion through better persona/message matching",
            })
            action_id += 1

        # Strategy evolution action
        actions.append({
            "id": f"ACT-{action_id:03d}",
            "action": "Run quarterly strategy evolution cycle across all niches",
            "category": "strategy",
            "priority": "medium",
            "timeline": "next_30_days",
            "owner": "system",
            "expected_impact": "Fresh strategy variants with potentially higher win rates",
        })
        action_id += 1

        # Reassess low priority niches
        low_niches = [n for n in niche_plans if n["priority"] == "low"]
        if low_niches:
            actions.append({
                "id": f"ACT-{action_id:03d}",
                "action": f"Reassess {len(low_niches)} low-priority niches for potential deprecation",
                "category": "triage",
                "priority": "low",
                "timeline": "next_quarter",
                "owner": "operator",
                "expected_impact": "Cleaner focus on highest-ROI niches",
            })
            action_id += 1

        return actions


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────────

def register_business_planner_routes(app, require_auth=None):
    """Register Business Planner Agent API routes."""
    planner = BusinessPlannerAgent()

    from fastapi import Depends, HTTPException, Query

    @app.get("/api/business-planner/plan")
    async def get_quarterly_plan(
        quarter: str = Query("Q2 2026"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Full quarterly business plan combining all data sources."""
        return planner.quarterly_plan(quarter=quarter)

    @app.get("/api/business-planner/plan/{niche}")
    async def get_niche_plan(
        niche: str,
        quarter: str = Query("Q2 2026"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Business plan for a single niche."""
        return planner.niche_plan(niche)

    @app.get("/api/business-planner/summary")
    async def get_plan_summary(
        quarter: str = Query("Q2 2026"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Condensed executive summary of the quarterly plan."""
        return planner.plan_summary()

    @app.post("/api/business-planner/regenerate")
    async def regenerate_plan(
        quarter: str = Query("Q2 2026"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Force-regenerate the quarterly plan with fresh data."""
        return planner.quarterly_plan(quarter=quarter)

    log.info("[business-planner] Routes registered · /api/business-planner/*")
