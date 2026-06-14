"""
EMPIRE V49 · PROFIT MARGIN & MAXIMISER AGENT
==============================================
Dedicated profit intelligence agent that:
- Computes per-lane P&L (revenue - acquisition cost = margin)
- Ranks lanes by profitability, ROI, and volume
- Detects margin bottlenecks (high-CPL, low-sell-price, underperforming niches)
- Suggests optimal sell prices per lane for target margin targets
- Tracks margin trends over time (daily snapshots)
- Generates maximiser signals: where to invest more, reprice, or cut

Data sources:
  - CPLPricingEngine (CPL benchmarks + margin_calculator + roi_estimate)
  - payout_log table (settlements, fees earned, USDC paid out)
  - call_logs table (call volume, revenue per lane)
  - buyers table (fee rates, retainer, base payout per niche)
  - predictive_revenue.per_lane_forecast (per-lane revenue metrics)

Routes:
  GET  /api/profit-margin/overview      — Aggregate P&L snapshot
  GET  /api/profit-margin/lanes          — Per-lance P&L breakdown + ranking
  GET  /api/profit-margin/bottlenecks    — Margin bottlenecks + opportunities
  GET  /api/profit-margin/optimize       — Pricing + volume optimisation suggestions
  GET  /api/profit-margin/trends         — Margin trend data (time series)
  GET  /api/profit-margin/narrative      — LLM-generated profit narrative
"""

import json
import math
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable, Dict, Any

log = logging.getLogger("empire.profit_margin")

# ── Default target margin used across all pricing suggestions ──────────
DEFAULT_TARGET_MARGIN_PCT = 60.0


class ProfitMarginAgent:
    """
    Profit intelligence agent.

    Combines CPL benchmark data, live settlement/payout records, and
    per-lane revenue forecasts to produce a complete profitability picture
    with actionable maximiser signals.
    """

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        self._margin_snapshot_cache: dict = {}
        self._last_snapshot_ts: Optional[str] = None

    # ── HELPERS ────────────────────────────────────────────────────────────

    def _get_pricing_engine(self):
        """Lazy import CPLPricingEngine to avoid circular deps."""
        try:
            from empire_pricing import CPLPricingEngine
            return CPLPricingEngine
        except ImportError:
            return None

    def _get_revenue_forecast(self) -> dict:
        """Fetch per-lane revenue forecast from predictive_revenue."""
        out = {"lanes": [], "totals": {}}
        try:
            from bots import predictive_revenue
            pl = predictive_revenue.per_lane_forecast() or {}
            out["lanes"] = pl.get("lanes", [])
            out["totals"] = pl.get("totals", {})
        except Exception as e:
            log.debug(f"[profit_margin] revenue forecast failed: {e}")
        return out

    def _get_payout_stats(self) -> dict:
        """Read payout + call stats from DB tables if available."""
        out = {
            "settlements_seen": 0,
            "payouts_executed": 0,
            "usdc_paid_out": 0,
            "last_settlement": None,
            "total_fees_24h": 0,
        }
        db = self.get_db() if self.get_db else None
        if not db:
            return out

        try:
            res = db.table("payout_log").select(
                "amount_usdc, status, created_at, recipient_type"
            ).order("created_at", desc=True).limit(500).execute()
            rows = res.data or []
            out["settlements_seen"] = len(rows)
            out["usdc_paid_out"] = sum(
                float(r["amount_usdc"]) for r in rows
                if r.get("status") == "sent"
            )
            out["payouts_executed"] = len([
                r for r in rows if r.get("status") == "sent"
            ])
            if rows:
                out["last_settlement"] = rows[0].get("created_at")
        except Exception as e:
            log.debug(f"[profit_margin] payout_log query failed: {e}")

        # 24h fee revenue from call_logs
        try:
            since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
            res = db.table("call_logs").select(
                "fee_earned, is_billable"
            ).gte("created_at", since).limit(2000).execute()
            for row in (res.data or []):
                if row.get("is_billable"):
                    out["total_fees_24h"] += float(row.get("fee_earned", 0))
        except Exception as e:
            log.debug(f"[profit_margin] call_logs query failed: {e}")

        return out

    # ── PER-LANE P&L ───────────────────────────────────────────────────────

    def lane_pnl(self) -> list[dict]:
        """
        Compute per-lane profit & loss for all 38 lanes.

        For each lane with CPL data, calculates:
          - CPL midpoint (acquisition cost per lead)
          - Suggested sell price (at 60% target margin) or actual sell price
          - Monthly margin at default volume
          - ROI %
          - Profitability tier (green/amber/red)

        Falls back gracefully for SEO/service lanes with no CPL data.
        """
        engine = self._get_pricing_engine()
        if not engine:
            return [{"error": "CPLPricingEngine not available"}]

        forecast = self._get_revenue_forecast()
        forecast_lanes = {str(l.get("lane_id", l.get("lane", ""))): l for l in forecast.get("lanes", [])}

        # Get lane pricing data at default volume
        pricing_data = engine.lane_pricing(model="ppl", monthly_volume=100)
        lanes_in = pricing_data.get("lanes", [])

        results = []
        for lp in lanes_in:
            lane_id = lp["lane_id"]
            niche = lp["niche"]
            sub_niche = lp["sub_niche"]

            # Forecast data for this lane (if available)
            fl = forecast_lanes.get(str(lane_id), {})

            cpl = lp.get("cpl", {})
            ppl = cpl.get("ppl", {}) if cpl else {}
            cpl_low = ppl.get("low")
            cpl_high = ppl.get("high")
            cpl_mid = round(((cpl_low or 0) + (cpl_high or 0)) / 2, 2) if cpl_low and cpl_high else None

            suggested_pricing = lp.get("suggested_pricing", {}) or {}

            # Sell price: use suggested if available, otherwise estimate
            sell_price = suggested_pricing.get("suggested_sell_price")
            if not sell_price:
                sell_price = round(cpl_mid * 2.5, 2) if cpl_mid else None

            # Monthly margin estimates at 100 leads/mo
            monthly_volume = 100
            if cpl_mid and sell_price:
                acquisition_cost = cpl_mid * monthly_volume
                revenue = sell_price * monthly_volume
                gross_profit = revenue - acquisition_cost
                margin_pct = round((gross_profit / revenue) * 100, 1) if revenue > 0 else 0
                roi_pct = round((gross_profit / acquisition_cost) * 100, 1) if acquisition_cost > 0 else 0

                # Profitability tier
                if margin_pct >= 60:
                    tier = "green"
                elif margin_pct >= 35:
                    tier = "amber"
                else:
                    tier = "red"
            else:
                gross_profit = None
                margin_pct = None
                roi_pct = None
                tier = "gray"  # No data

            # Revenue from forecast (24h actuals)
            rev_24h = fl.get("revenue_24h", 0)
            calls_24h = fl.get("calls_24h", 0)

            results.append({
                "lane_id": lane_id,
                "niche": niche,
                "sub_niche": sub_niche,
                "strategy": lp.get("strategy", ""),
                "best_model": lp.get("best_model", "both"),
                "cpl_midpoint": cpl_mid,
                "cpl_range": cpl,
                "sell_price": sell_price,
                "suggested_price": suggested_pricing.get("suggested_sell_price"),
                "markup_multiple": round(sell_price / cpl_mid, 2) if sell_price and cpl_mid else None,
                "monthly_volume": monthly_volume,
                "monthly_acquisition_cost": round(cpl_mid * monthly_volume, 2) if cpl_mid else None,
                "monthly_revenue": round(sell_price * monthly_volume, 2) if sell_price else None,
                "monthly_gross_profit": round(gross_profit, 2) if gross_profit is not None else None,
                "margin_pct": margin_pct,
                "roi_pct": roi_pct,
                "tier": tier,
                "revenue_24h": rev_24h,
                "calls_24h": calls_24h,
                "trigger": lp.get("trigger", ""),
            })

        # Sort by margin_pct descending (profitable first), None last
        results.sort(key=lambda r: (
            r["margin_pct"] is not None,
            r["margin_pct"] or 0,
        ), reverse=True)

        return results

    # ── AGGREGATE P&L OVERVIEW ─────────────────────────────────────────────

    def overview(self) -> dict:
        """
        Aggregate profit & loss snapshot across all lanes.
        """
        lanes = self.lane_pnl()
        revenue_forecast = self._get_revenue_forecast()
        payout_stats = self._get_payout_stats()

        with_data = [l for l in lanes if l["margin_pct"] is not None]
        no_data = [l for l in lanes if l["margin_pct"] is None]

        total_monthly_acq = sum(
            l["monthly_acquisition_cost"] or 0 for l in with_data
        )
        total_monthly_rev = sum(
            l["monthly_revenue"] or 0 for l in with_data
        )
        total_monthly_profit = sum(
            l["monthly_gross_profit"] or 0 for l in with_data
        )

        weighted_margin = round(
            (total_monthly_profit / total_monthly_rev) * 100, 1
        ) if total_monthly_rev > 0 else 0

        # Segment counts
        green = len([l for l in with_data if l["tier"] == "green"])
        amber = len([l for l in with_data if l["tier"] == "amber"])
        red = len([l for l in with_data if l["tier"] == "red"])
        gray = len(no_data)

        # Top/bottom performers
        top_5 = lanes[:5] if len(lanes) >= 5 else lanes
        bottom_5 = [l for l in reversed(lanes) if l["margin_pct"] is not None][-5:] if len(with_data) >= 5 else with_data[-5:] if with_data else []

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "total_lanes": len(lanes),
            "lanes_with_data": len(with_data),
            "lanes_no_cpl": gray,
            "total_monthly_acquisition_cost": round(total_monthly_acq, 2),
            "total_monthly_revenue": round(total_monthly_rev, 2),
            "total_monthly_profit": round(total_monthly_profit, 2),
            "weighted_margin_pct": weighted_margin,
            "avg_margin_pct": round(
                sum(l["margin_pct"] or 0 for l in with_data) / len(with_data), 1
            ) if with_data else 0,
            "avg_roi_pct": round(
                sum(l["roi_pct"] or 0 for l in with_data) / len(with_data), 1
            ) if with_data else 0,
            "segments": {
                "green": green,
                "amber": amber,
                "red": red,
                "gray": gray,
            },
            "top_5": top_5,
            "bottom_5": bottom_5,
            "payout_stats": payout_stats,
            "revenue_24h": revenue_forecast.get("totals", {}).get("revenue_24h", 0),
            "mrr_projected": revenue_forecast.get("totals", {}).get("mrr_projected", 0),
        }

    # ── BOTTLENECKS ─────────────────────────────────────────────────────────

    def bottlenecks(self) -> list[dict]:
        """
        Detect margin bottlenecks and opportunities across lanes.

        Returns a prioritized list of issues:
          - High CPL (cost too high relative to niche avg)
          - Low margin (margin < 35%)
          - No pricing data (CPL unavailable)
          - Volume opportunity (high margin but low volume)
          - Repricing opportunity (margin < 60% and room to increase sell price)
        """
        lanes = self.lane_pnl()
        recs = []

        # 1. Red-tier lanes (margin < 35%)
        red_lanes = [l for l in lanes if l["tier"] == "red"]
        if red_lanes:
            recs.append({
                "type": "low_margin",
                "priority": "high",
                "title": f"{len(red_lanes)} lanes with margin below 35%",
                "detail": [f"Lane {l['lane_id']}: {l['niche']}/{l['sub_niche']} — {l['margin_pct']}% margin, ${l['cpl_midpoint']} CPL"
                          for l in red_lanes[:5]],
                "action": "Review CPL benchmarks and consider repricing or switching model (PPL → PPC)",
            })

        # 2. Gray-tier lanes (no CPL data)
        gray_lanes = [l for l in lanes if l["tier"] == "gray"]
        if gray_lanes:
            recs.append({
                "type": "no_cpl_data",
                "priority": "medium",
                "title": f"{len(gray_lanes)} lanes without CPL pricing data",
                "detail": [f"Lane {l['lane_id']}: {l['niche']}/{l['sub_niche']}"
                          for l in gray_lanes],
                "action": "Research CPL benchmarks and add pricing data to enable margin tracking",
            })

        # 3. Repricing opportunity (amber tier — good but could be better)
        amber_lanes = [l for l in lanes
                      if l["tier"] == "amber" and l["sell_price"] and l["cpl_midpoint"]]
        if amber_lanes:
            # Calculate potential improvement from 35% → 60% margin
            for al in amber_lanes[:5]:
                cpl = al["cpl_midpoint"]
                current_sell = al["sell_price"]
                target_margin_price = round(cpl / (1 - 0.60), 2)  # 60% margin
                price_increase = round(target_margin_price - current_sell, 2)
                if price_increase > 5:  # meaningful increase
                    recs.append({
                        "type": "repricing_opportunity",
                        "priority": "medium",
                        "title": f"Reprice Lane {al['lane_id']} ({al['sub_niche']})",
                        "detail": [
                            f"Current sell: ${current_sell} → Target (60% margin): ${target_margin_price}",
                            f"Increase of ${price_increase} per lead ({round(price_increase/current_sell*100, 0)}% bump)",
                        ],
                        "action": f"Increase sell price from ${current_sell} to ${target_margin_price} to achieve 60% margin",
                    })

        # 4. Volume opportunity (green-tier with high margin but low forecasted volume)
        green_lanes = [l for l in lanes if l["tier"] == "green" and l.get("revenue_24h", 0) == 0]
        if green_lanes:
            recs.append({
                "type": "volume_opportunity",
                "priority": "medium",
                "title": f"{len(green_lanes)} high-margin lanes with zero 24h revenue",
                "detail": [f"Lane {l['lane_id']}: {l['niche']}/{l['sub_niche']} — {l['margin_pct']}% margin, ${l['sell_price']}/lead"
                          for l in green_lanes[:5]],
                "action": "Increase outreach volume on these lanes to capture unrealised margin",
            })

        # 5. High CPL outliers (CPL significantly above niche average)
        # Calculate average CPL per niche and flag outliers
        niche_cpls: dict[str, list[float]] = {}
        for l in lanes:
            if l["cpl_midpoint"] and l["niche"]:
                niche_cpls.setdefault(l["niche"], []).append(l["cpl_midpoint"])

        for l in lanes:
            if not l["cpl_midpoint"] or l["niche"] not in niche_cpls:
                continue
            niche_avg = sum(niche_cpls[l["niche"]]) / len(niche_cpls[l["niche"]])
            if l["cpl_midpoint"] > niche_avg * 1.5:  # 50% above niche avg
                recs.append({
                    "type": "high_cpl",
                    "priority": "high",
                    "title": f"High CPL in Lane {l['lane_id']} ({l['sub_niche']})",
                    "detail": [
                        f"CPL: ${l['cpl_midpoint']} vs niche avg: ${round(niche_avg, 2)}",
                        f"Margin: {l['margin_pct']}%",
                    ],
                    "action": f"Switch to PPC model or find lower-cost lead source for {l['sub_niche']}",
                })

        # Sort by priority
        priority_order = {"high": 0, "medium": 1, "low": 2}
        recs.sort(key=lambda r: priority_order.get(r.get("priority", "low"), 99))

        return recs

    # ── OPTIMISATION SUGGESTIONS ────────────────────────────────────────────

    def optimize(self, target_margin_pct: float = DEFAULT_TARGET_MARGIN_PCT) -> dict:
        """
        Generate per-lane optimization suggestions.

        For each lane with CPL data, suggests:
          - Optimal sell price to hit target margin
          - Better model (PPL vs PPC) if the other has better margin characteristics
          - Volume sweet spot (leads/mo for max profit without saturating)

        Returns ranked recommendations.
        """
        engine = self._get_pricing_engine()
        if not engine:
            return {"error": "CPLPricingEngine not available"}

        lanes = self.lane_pnl()
        suggestions = []

        for l in lanes:
            cpl_mid = l["cpl_midpoint"]
            if not cpl_mid:
                continue

            niche = l["niche"]
            sub_niche = l["sub_niche"]

            # 1. Optimal sell price for target margin
            optimal_price = engine.suggest_sell_price(
                niche, sub_niche, target_margin_pct=target_margin_pct, model="ppl"
            ) if engine else {}
            optimal_sell = optimal_price.get("suggested_sell_price")
            actual_margin = optimal_price.get("actual_margin_pct")

            # 2. Compare PPL vs PPC margin
            ppc_optimal = engine.suggest_sell_price(
                niche, sub_niche, target_margin_pct=target_margin_pct, model="ppc"
            ) if engine else {}

            # 3. Model recommendation
            best_model = l.get("best_model", "both")

            # 4. Volume analysis — estimate profit at different volumes
            volume_scenarios = {}
            for vol in [50, 100, 250, 500]:
                if optimal_sell:
                    acq = cpl_mid * vol
                    rev = optimal_sell * vol
                    profit = rev - acq
                    margin = round((profit / rev) * 100, 1) if rev > 0 else 0
                    volume_scenarios[str(vol)] = {
                        "monthly_acquisition_cost": round(acq, 2),
                        "monthly_revenue": round(rev, 2),
                        "monthly_profit": round(profit, 2),
                        "margin_pct": margin,
                    }

            # Current vs optimal
            current_sell = l["sell_price"]
            current_margin = l["margin_pct"]
            price_diff = round(optimal_sell - current_sell, 2) if optimal_sell and current_sell else None

            suggestions.append({
                "lane_id": l["lane_id"],
                "niche": niche,
                "sub_niche": sub_niche,
                "current_sell_price": current_sell,
                "current_margin_pct": current_margin,
                "optimal_sell_price": optimal_sell,
                "optimal_margin_pct": actual_margin,
                "price_adjustment": price_diff,
                "model_recommendation": best_model,
                "alternative_model": "ppc" if best_model == "ppl" else "ppl",
                "alternative_sell_price": ppc_optimal.get("suggested_sell_price"),
                "alternative_margin_pct": ppc_optimal.get("actual_margin_pct"),
                "volume_scenarios": volume_scenarios,
                "best_model_volume_recommendation": (
                    "increase" if current_margin and current_margin >= 60 else
                    "maintain" if current_margin and current_margin >= 35 else
                    "reduce"
                ),
            })

        # Sort by optimisation potential (largest price adjustment first)
        suggestions.sort(key=lambda s: abs(s["price_adjustment"] or 0), reverse=True)

        return {
            "target_margin_pct": target_margin_pct,
            "lanes_analysed": len(suggestions),
            "total_annual_profit_potential": round(
                sum(
                    (s.get("volume_scenarios", {}).get("100", {}).get("monthly_profit", 0) or 0) * 12
                    for s in suggestions
                ), 2
            ),
            "suggestions": suggestions,
        }

    # ── MARGIN TRENDS ───────────────────────────────────────────────────────

    def trends(self, days: int = 30) -> dict:
        """
        Build margin trend data from historical payout_log records.

        Groups settlements by day and computes daily revenue, fees, and
        implied margin. Returns time series for the dashboard chart.
        """
        daily: dict[str, dict] = {}

        try:
            db = self.get_db() if self.get_db else None
            if db:
                since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
                res = db.table("payout_log").select(
                    "amount_usdc, status, created_at, recipient_type"
                ).gte("created_at", since).order("created_at", desc=True).limit(2000).execute()
                rows = res.data or []

                # Also get call_logs revenue data
                call_res = db.table("call_logs").select(
                    "fee_earned, is_billable, created_at"
                ).gte("created_at", since).limit(2000).execute() if hasattr(db, "table") else {"data": []}
                call_rows = call_res.data if hasattr(call_res, "data") else []

                for row in rows:
                    day = (row.get("created_at") or "")[:10]
                    if not day:
                        continue
                    bucket = daily.setdefault(day, {
                        "revenue": 0, "cost": 0, "profit": 0,
                        "settlements": 0, "payouts": 0,
                    })
                    amt = float(row.get("amount_usdc", 0))
                    if row.get("recipient_type") == "vault":
                        bucket["revenue"] += amt
                    elif row.get("status") == "sent":
                        bucket["cost"] += amt
                        bucket["payouts"] += 1
                    bucket["settlements"] += 1

                # Add call-based revenue
                for row in call_rows:
                    day = (row.get("created_at") or "")[:10]
                    if not day:
                        continue
                    bucket = daily.setdefault(day, {
                        "revenue": 0, "cost": 0, "profit": 0,
                        "settlements": 0, "payouts": 0,
                    })
                    fee = float(row.get("fee_earned", 0))
                    if row.get("is_billable"):
                        bucket["revenue"] += fee
        except Exception as e:
            log.debug(f"[profit_margin] trend query failed: {e}")

        if not daily:
            return {
                "days": days,
                "total_revenue": 0,
                "total_cost": 0,
                "total_profit": 0,
                "daily_trend": [],
                "message": "No historical payout/call data available for trend analysis",
            }

        # Compute profit and margin for each day
        sorted_days = sorted(daily.keys())
        for day, bucket in daily.items():
            bucket["profit"] = round(bucket["revenue"] - bucket["cost"], 2)
            bucket["margin_pct"] = round(
                (bucket["profit"] / bucket["revenue"]) * 100, 1
            ) if bucket["revenue"] > 0 else 0

        trend = [
            {"day": day, **daily[day]}
            for day in sorted_days[-days:]
        ]

        total_revenue = sum(b["revenue"] for b in daily.values())
        total_cost = sum(b["cost"] for b in daily.values())
        total_profit = total_revenue - total_cost
        weighted_margin = round(
            (total_profit / total_revenue) * 100, 1
        ) if total_revenue > 0 else 0

        return {
            "days": days,
            "total_revenue": round(total_revenue, 2),
            "total_cost": round(total_cost, 2),
            "total_profit": round(total_profit, 2),
            "weighted_margin_pct": weighted_margin,
            "daily_trend": trend,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }

    # ── MAXIMISER REPORTS ──────────────────────────────────────────────────

    def maximiser_report(self) -> dict:
        """
        Generate the "Maximiser" — a consolidated action report combining
        bottlenecks, optimization suggestions, and revenue signals into
        a ranked set of actions that would most improve profitability.

        Returns:
          - invest: lanes to invest more in (high margin, high opportunity)
          - reprice: lanes that need pricing adjustment
          - cut: lanes to reduce or cut (low margin, high cost, no data)
          - quick_wins: high-impact, low-effort actions
        """
        overview_data = self.overview()
        bottleneck_list = self.bottlenecks()
        optimization = self.optimize()
        lanes = self.lane_pnl()

        # Invest signals: green tier + high ROI + room for volume
        invest = []
        for l in lanes:
            if l["tier"] == "green" and l["roi_pct"] and l["roi_pct"] >= 100:
                invest.append({
                    "lane_id": l["lane_id"],
                    "niche": l["niche"],
                    "sub_niche": l["sub_niche"],
                    "margin_pct": l["margin_pct"],
                    "roi_pct": l["roi_pct"],
                    "sell_price": l["sell_price"],
                    "reason": f"{l['margin_pct']}% margin with {l['roi_pct']}% ROI — increase volume",
                })

        # Reprice signals: amber tier with room to increase sell price
        reprice = []
        for opt in optimization.get("suggestions", []):
            if opt.get("price_adjustment") and opt["price_adjustment"] > 0:
                reprice.append({
                    "lane_id": opt["lane_id"],
                    "niche": opt["niche"],
                    "sub_niche": opt["sub_niche"],
                    "current_price": opt["current_sell_price"],
                    "optimal_price": opt["optimal_sell_price"],
                    "adjustment": opt["price_adjustment"],
                    "current_margin": opt["current_margin_pct"],
                    "potential_margin": opt["optimal_margin_pct"],
                })

        # Cut signals: red tier with sustained low performance
        cut = []
        for l in lanes:
            if l["tier"] == "red" and l["cpl_midpoint"] and l["sell_price"]:
                cut.append({
                    "lane_id": l["lane_id"],
                    "niche": l["niche"],
                    "sub_niche": l["sub_niche"],
                    "margin_pct": l["margin_pct"],
                    "cpl_midpoint": l["cpl_midpoint"],
                    "reason": f"Only {l['margin_pct']}% margin — consider pausing or switching model",
                })

        # Quick wins: lanes that can go from red to green with simple repricing
        quick_wins = []
        for r in reprice[:3]:
            if r.get("current_margin") and r["current_margin"] < 35 and r.get("potential_margin") and r["potential_margin"] >= 50:
                quick_wins.append({
                    "lane_id": r["lane_id"],
                    "niche": r["niche"],
                    "sub_niche": r["sub_niche"],
                    "adjustment": f"Reprice ${r['current_price']} → ${r['optimal_price']} (improves margin from {r['current_margin']}% to {r['potential_margin']}%)",
                })

        return {
            "ts": datetime.now(timezone.utc).isoformat(),
            "total_profit_potential": overview_data.get("total_monthly_profit", 0),
            "annual_profit_potential": round(
                (overview_data.get("total_monthly_profit", 0) or 0) * 12, 2
            ),
            "invest": invest[:10],
            "reprice": reprice[:10],
            "cut": cut[:10],
            "quick_wins": quick_wins[:5],
            "bottlenecks": bottleneck_list[:8],
            "summary": {
                "invest_count": len(invest),
                "reprice_count": len(reprice),
                "cut_count": len(cut),
                "quick_win_count": len(quick_wins),
            },
        }

    # ── NARRATIVE ───────────────────────────────────────────────────────────

    def generate_narrative(self) -> dict:
        """
        Generate an LLM-powered profit narrative using local Ollama.
        Falls back to a template if Ollama is unavailable.
        """
        overview_data = self.overview()
        max_report = self.maximiser_report()

        try:
            import httpx

            prompt = f"""You are a profit optimisation analyst for an AI-powered lead generation platform.
Write a concise profit narrative (2-3 paragraphs) based on:

Total lanes: {overview_data.get('total_lanes', 0)}
Lanes with margin data: {overview_data.get('lanes_with_data', 0)}
Total monthly profit: ${overview_data.get('total_monthly_profit', 0)}
Weighted margin: {overview_data.get('weighted_margin_pct', 0)}%
Avg margin: {overview_data.get('avg_margin_pct', 0)}%
Avg ROI: {overview_data.get('avg_roi_pct', 0)}%
Green (high margin): {overview_data.get('segments', {}).get('green', 0)} lanes
Amber (medium margin): {overview_data.get('segments', {}).get('amber', 0)} lanes
Red (low margin): {overview_data.get('segments', {}).get('red', 0)} lanes
Invest opportunities: {max_report.get('summary', {}).get('invest_count', 0)}
Reprice opportunities: {max_report.get('summary', {}).get('reprice_count', 0)}
Quick wins: {max_report.get('summary', {}).get('quick_win_count', 0)}

Focus on: overall profitability health, the biggest margin opportunities,
and the single most impactful action to take next."""

            r = httpx.post(
                "http://localhost:11434/api/generate",
                json={
                    "model": "llama3.1:latest",
                    "prompt": prompt,
                    "stream": False,
                    "options": {"temperature": 0.6, "num_predict": 512},
                },
                timeout=30.0,
            )
            if r.status_code == 200:
                data = r.json()
                narrative = data.get("response", "").strip()
                if narrative:
                    return {
                        "narrative": narrative,
                        "source": "llm",
                        "model": "llama3.1:latest",
                    }
        except Exception as e:
            log.debug(f"[profit_margin] LLM narrative failed: {e}")

        # Fallback template
        total_profit = overview_data.get("total_monthly_profit", 0) or 0
        green = overview_data.get("segments", {}).get("green", 0)
        amber = overview_data.get("segments", {}).get("amber", 0)
        red = overview_data.get("segments", {}).get("red", 0)

        parts = [
            f"Profit engine covers {overview_data.get('total_lanes', 0)} lanes "
            f"({green} high-margin, {amber} medium-margin, {red} low-margin).",
        ]

        if total_profit > 0:
            parts.append(
                f"Monthly profit across all lanes: ${total_profit:.2f} "
                f"at {overview_data.get('weighted_margin_pct', 0)}% weighted margin."
            )

        invest = max_report.get("invest", [])
        quick_wins = max_report.get("quick_wins", [])

        if quick_wins:
            parts.append(
                f"Quick win: {quick_wins[0]['adjustment']} on Lane {quick_wins[0]['lane_id']} "
                f"({quick_wins[0]['sub_niche']})."
            )
        if invest:
            parts.append(
                f"Top investment signal: Lane {invest[0]['lane_id']} "
                f"({invest[0]['sub_niche']}) at {invest[0]['margin_pct']}% margin — increase volume."
            )
        if not quick_wins and not invest:
            parts.append(
                "All lanes operating within expected margin ranges. "
                "Continue monitoring and running margin optimisation cycles."
            )

        return {
            "narrative": " ".join(parts),
            "source": "template",
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────────

def register_profit_margin_routes(app, require_auth=None, get_db=None):
    """
    Register Profit Margin Agent endpoints on a FastAPI app.
    """
    agent = ProfitMarginAgent(get_db=get_db)

    if require_auth:

        @app.get("/api/profit-margin/overview")
        async def _overview(auth=Depends(require_auth)):
            return agent.overview()

        @app.get("/api/profit-margin/lanes")
        async def _lanes(auth=Depends(require_auth)):
            return agent.lane_pnl()

        @app.get("/api/profit-margin/bottlenecks")
        async def _bottlenecks(auth=Depends(require_auth)):
            return agent.bottlenecks()

        @app.get("/api/profit-margin/optimize")
        async def _optimize(auth=Depends(require_auth)):
            return agent.optimize()

        @app.get("/api/profit-margin/trends")
        async def _trends(auth=Depends(require_auth)):
            return agent.trends()

        @app.get("/api/profit-margin/maximiser")
        async def _maximiser(auth=Depends(require_auth)):
            return agent.maximiser_report()

        @app.get("/api/profit-margin/narrative")
        async def _narrative(auth=Depends(require_auth)):
            return agent.generate_narrative()

    else:

        @app.get("/api/profit-margin/overview")
        async def _overview():
            return agent.overview()

        @app.get("/api/profit-margin/lanes")
        async def _lanes():
            return agent.lane_pnl()

        @app.get("/api/profit-margin/bottlenecks")
        async def _bottlenecks():
            return agent.bottlenecks()

        @app.get("/api/profit-margin/optimize")
        async def _optimize():
            return agent.optimize()

        @app.get("/api/profit-margin/trends")
        async def _trends():
            return agent.trends()

        @app.get("/api/profit-margin/maximiser")
        async def _maximiser():
            return agent.maximiser_report()

        @app.get("/api/profit-margin/narrative")
        async def _narrative():
            return agent.generate_narrative()

    log.info("[profit_margin] Routes registered · /api/profit-margin/*")


# Lazy import for FastAPI Depends
from fastapi import Depends  # noqa: E402
