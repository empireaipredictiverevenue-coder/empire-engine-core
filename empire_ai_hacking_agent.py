"""
EMPIRE V49 · AI HACKING AGENT (MARKETING & LEAD GEN)
======================================================
Aggressive, creative marketing automation agent. Uses unconventional
tactics to generate leads, traffic, and brand presence across channels.

Capabilities:
- Content arbitrage & virality (trend monitoring, auto-generation, cross-posting)
- Social conversation hijacking (forum monitoring, value-first replies)
- Ad creative automation (variant generation, A/B testing, optimization)
- Cross-channel arbitrage (cheap traffic detection, channel flooding)
- Lead gen hacking (directory scraping, trigger event detection)
- Trend/opportunity scoring and prioritization

Routes:
  GET   /api/hacking/overview       — Dashboard snapshot
  GET   /api/hacking/opportunities  — High-impact marketing opportunities scored
  GET   /api/hacking/trends         — Trending topics and content angles
  POST  /api/hacking/generate       — Generate content/creative variants
  POST  /api/hacking/syndicate      — Record content syndication action
  GET   /api/hacking/snapshot       — Condensed fleet dashboard snapshot
"""

import json
import logging
import os
import uuid
import hashlib
from datetime import datetime, timezone, timedelta
from typing import Optional, Callable

log = logging.getLogger("empire.ai_hacking_agent")

# ── Channel scoring weights ─────────────────────────────────────────
_CHANNEL_WEIGHTS = {
    "seo":       {"traffic_potential": 8,  "effort": 6, "speed": 3, "cost": 9},
    "social":    {"traffic_potential": 9,  "effort": 4, "speed": 8, "cost": 8},
    "forums":    {"traffic_potential": 6,  "effort": 5, "speed": 7, "cost": 10},
    "ads":       {"traffic_potential": 10, "effort": 3, "speed": 9, "cost": 3},
    "email":     {"traffic_potential": 7,  "effort": 5, "speed": 6, "cost": 7},
    "voice":     {"traffic_potential": 5,  "effort": 4, "speed": 5, "cost": 5},
    "affiliate": {"traffic_potential": 8,  "effort": 6, "speed": 4, "cost": 6},
    "referral":  {"traffic_potential": 9,  "effort": 7, "speed": 2, "cost": 10},
}

# ── Predefined trend sources for monitoring ─────────────────────────
_TREND_NICHES = {
    "roofing":        ["hail damage", "storm season", "roof replacement cost", "insurance claim roofing"],
    "hvac":           ["heat wave", "ac repair cost", "furnace replacement", "energy efficiency rebate"],
    "mass tort":      ["class action lawsuit", "mesothelioma", "paragard lawsuit", "roundup cancer"],
    "debt relief":    ["credit card debt forgiveness", "student loan forgiveness", "debt consolidation"],
    "solar":          ["solar tax credit", "solar panel cost", "net metering", "solar financing"],
    "pest control":   ["termite season", "bed bug treatment", "rodent infestation", "mosquito control"],
}


class AIHackingAgent:
    """Multi-purpose ops agent. Finds unconventional growth channels,
    generates content/creative variants, detects opportunities, engineers
    viral patterns, exploits audience gaps, and floods channels with
    targeted content. The tactical swiss army knife of the fleet."""

    def __init__(self, get_db: Callable):
        self.get_db = get_db
        self._content_history: list[dict] = []
        self._syndication_history: list[dict] = []
        self._audience_insights: list[dict] = []
        self._channel_floods: list[dict] = []
        self._viral_patterns: list[dict] = []

    def _db(self):
        return self.get_db()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _days_ago(self, d: int) -> str:
        return (datetime.now(timezone.utc) - timedelta(days=d)).isoformat()

    # ── DATA SOURCES ─────────────────────────────────────────────────

    def _get_active_niches(self) -> list[str]:
        """Get niches with active activity."""
        try:
            r = self._db().table("enriched_leads") \
                .select("niche") \
                .limit(500) \
                .execute()
            niches = set()
            for row in (r.data or []):
                n = row.get("niche")
                if n and n.strip():
                    niches.add(n.strip().lower())
            return sorted(niches)
        except Exception:
            return list(_TREND_NICHES.keys())

    def _get_revenue_stats(self) -> dict:
        """Quick revenue stats."""
        out = {"total_24h": 0, "mrr_projected": 0, "active_buyers": 0, "total_outreach": 0}
        try:
            from bots import predictive_revenue
            pl = predictive_revenue.per_lane_forecast() or {}
            out.update(pl.get("totals", {}))
        except Exception:
            pass
        return out

    def _get_channel_stats(self) -> dict:
        """Get activity per channel — cached per-call, 8 individual queries.
        Cache lives for the lifetime of the stats dict to avoid redundant
        queries within a single request cycle."""
        if hasattr(self, '_channel_stats_cache'):
            return self._channel_stats_cache
        stats = {}
        for ch in _CHANNEL_WEIGHTS:
            try:
                # Use different tables as rough proxies per channel
                table = {
                    "seo": "contractors",
                    "social": "enriched_leads",
                    "forums": "prospects",
                    "ads": "enriched_leads",
                    "email": "fee_events",
                    "voice": "fee_events",
                    "affiliate": "contractors",
                    "referral": "contractors",
                }.get(ch, "sms_log")
                r = self._db().table(table) \
                    .select("id", count="exact") \
                    .gte("created_at", self._days_ago(7)) \
                    .execute()
                stats[ch] = r.count if hasattr(r, "count") else 0
            except Exception:
                stats[ch] = 10  # small default to avoid divide-by-zero
        self._channel_stats_cache = stats
        return stats

    # ── OPPORTUNITY SCORING ──────────────────────────────────────────

    def _score_opportunity(self, niche: str, channel: str,
                           existing_volume: int) -> dict:
        """Score a niche+channel combination as a growth hacking opportunity.

        Higher score = more potential for unconventional growth.
        Factors: low existing activity, high channel potential, niche relevance.
        """
        ch_w = _CHANNEL_WEIGHTS.get(channel, {})
        traffic_potential = ch_w.get("traffic_potential", 5)
        speed = ch_w.get("speed", 5)
        cost = ch_w.get("cost", 5)
        effort = ch_w.get("effort", 5)

        # Low existing activity = higher hacking opportunity
        saturation_penalty = min(existing_volume / 10, 30)  # -30 pts max

        # High traffic potential + low cost = ideal hack target
        hack_score = (traffic_potential * 3) + (speed * 2) + (cost * 2) - saturation_penalty

        # Niche bonus — some niches respond better to unconventional tactics
        NICHE_BONUS = {
            "roofing": 5, "hvac": 5, "solar": 8, "mass tort": 10,
            "debt relief": 8, "pest control": 5, "legal": 10,
        }
        niche_bonus = 0
        for kw, bonus in NICHE_BONUS.items():
            if kw in niche.lower():
                niche_bonus = max(niche_bonus, bonus)

        total = max(0, min(100, hack_score + niche_bonus))

        return {
            "score": round(total, 1),
            "traffic_potential": traffic_potential,
            "speed_to_market": speed,
            "cost_efficiency": cost,
            "effort_required": effort,
            "saturation_penalty": round(saturation_penalty, 1),
            "niche_bonus": niche_bonus,
        }

    # ── 1. OVERVIEW ──────────────────────────────────────────────────

    def overview(self) -> dict:
        """Dashboard snapshot — channel health, recent hacks, opportunity count."""
        niches = self._get_active_niches()
        channel_stats = self._get_channel_stats()
        rev = self._get_revenue_stats()

        # Score all niche+channel combinations
        opportunities = []
        for niche in niches[:10]:
            for channel in _CHANNEL_WEIGHTS:
                vol = channel_stats.get(channel, 0)
                score = self._score_opportunity(niche, channel, vol)
                if score["score"] >= 50:
                    opportunities.append({
                        "niche": niche,
                        "channel": channel,
                        **score,
                    })

        opportunities.sort(key=lambda o: o["score"], reverse=True)

        return {
            "ts": self._now(),
            "active_niches": len(niches),
            "high_impact_opportunities": len([o for o in opportunities if o["score"] >= 70]),
            "total_opportunities": len(opportunities),
            "top_opportunities": opportunities[:10],
            "channel_activity_7d": channel_stats,
            "revenue": {
                "revenue_24h": rev.get("total_24h", 0),
                "mrr_projected": rev.get("mrr_projected", 0),
            },
            "content_generated": len(self._content_history),
            "syndications": len(self._syndication_history),
            "audience_gaps_detected": len(self._audience_insights),
            "channel_floods_active": len(self._channel_floods),
            "viral_patterns_engineered": len(self._viral_patterns),
            "exploitable_channels": list(set(
                g for insight in self._audience_insights
                for g in insight.get("exploitable_channels", [])
            )),
        }

    # ── 2. OPPORTUNITIES ─────────────────────────────────────────────

    def opportunities(self) -> list[dict]:
        """Score and rank all niche+channel combinations for hacking potential."""
        niches = self._get_active_niches()
        channel_stats = self._get_channel_stats()
        results = []

        for niche in niches[:20]:
            for channel in _CHANNEL_WEIGHTS:
                vol = channel_stats.get(channel, 0)
                score = self._score_opportunity(niche, channel, vol)
                results.append({
                    "id": f"HACK-{hashlib.md5(f'{niche}{channel}'.encode()).hexdigest()[:6].upper()}",
                    "niche": niche,
                    "channel": channel,
                    **score,
                    "tactic": self._recommend_tactic(niche, channel, score["score"]),
                })

        results.sort(key=lambda r: r["score"], reverse=True)

        # Group by priority
        critical = [r for r in results if r["score"] >= 75]
        high = [r for r in results if 60 <= r["score"] < 75]
        medium = [r for r in results if 40 <= r["score"] < 60]
        low = [r for r in results if r["score"] < 40]

        return {
            "total": len(results),
            "critical": critical[:15],
            "high": high[:15],
            "medium": medium[:15],
            "summary": {
                "critical": len(critical),
                "high": len(high),
                "medium": len(medium),
                "low": len(low),
                "avg_score": round(
                    sum(r["score"] for r in results) / max(len(results), 1), 1
                ) if results else 0,
            },
        }

    def _recommend_tactic(self, niche: str, channel: str,
                           score: float) -> dict:
        """Recommend a specific growth hacking tactic for niche+channel."""
        tactics = {
            "seo": {
                "high": f"Create 5 long-tail landing pages targeting '{niche} [city] [urgent need]' — capture bottom-of-funnel intent",
                "medium": f"Write guest posts for top {niche} blogs with backlinks to Empire AI",
                "low": f"Optimize existing {niche} content for featured snippets",
            },
            "social": {
                "high": f"Post daily {niche} tips on Reddit/Nextdoor — include subtle CTA to Empire AI",
                "medium": f"Create 30s {niche} explainer videos for TikTok/Reels with link in bio",
                "low": f"Join {niche} Facebook groups and participate in discussions",
            },
            "forums": {
                "high": f"Monitor Reddit r/{niche} and Quora for recommendation threads — auto-reply with value-first response",
                "medium": f"Create 'I am a {niche} expert — AMA' thread on relevant subreddits",
                "low": f"Answer {niche} questions on Quora with Empire AI as case study",
            },
            "ads": {
                "high": f"Create 10 ad variants for '{niche} near me' long-tail — A/B test headlines, images, offers",
                "medium": f"Retarget {niche} website visitors with native ads showcasing free quote",
                "low": f"Run tiny $5/day Facebook ad targeting {niche} interest groups",
            },
            "email": {
                "high": f"Scrape {niche} business directories for emails — send personalized outreach at CEO level",
                "medium": f"Create {niche}-specific industry report as lead magnet, gate behind email capture",
                "low": f"Send re-engagement email to stale {niche} leads with trending topic hook",
            },
            "affiliate": {
                "high": f"Recruit {niche} influencers/affiliates with 20% commission — target existing audiences",
                "medium": f"Offer {niche} bloggers free trial of Empire AI in exchange for review post",
                "low": f"Add {niche} affiliate link to relevant resource pages",
            },
            "referral": {
                "high": f"Launch '{niche} contractor referral program' — $500 per referred contractor who closes first deal",
                "medium": f"Email existing {niche} contractors asking for referrals in exchange for free priority dispatch",
                "low": f"Add 'refer a colleague' CTA to {niche} SMS sequences",
            },
        }

        chan_tactics = tactics.get(channel, {})
        if score >= 70:
            label = "high"
        elif score >= 50:
            label = "medium"
        else:
            label = "low"

        return {
            "label": label,
            "description": chan_tactics.get(label, f"Research {channel} growth tactics for {niche}"),
        }

    # ── 3. TRENDS ────────────────────────────────────────────────────

    def trends(self) -> dict:
        """Trending topics and content angles per niche.

        Uses predefined trend keywords + LLM knowledge. In production this
        would scrape Reddit, Google Trends, and news APIs.
        """
        niches = self._get_active_niches()
        trend_data = {}

        for niche in niches:
            keywords = _TREND_NICHES.get(niche, [f"{niche} services", f"{niche} cost", f"{niche} near me"])
            trend_data[niche] = {
                "keywords": keywords,
                "content_angles": self._generate_angles(niche, keywords),
                "estimated_search_volume": len(keywords) * 1000,
                "competition_level": "low" if niche in ("solar", "mass tort", "debt relief") else "medium",
            }

        return {
            "ts": self._now(),
            "trends": trend_data,
            "total_niches": len(trend_data),
            "top_keywords": [
                kw for niche_data in trend_data.values()
                for kw in niche_data.get("keywords", [])
            ][:30],
        }

    def _generate_angles(self, niche: str, keywords: list[str]) -> list[dict]:
        """Generate content angles for a niche based on keywords."""
        ANGLE_TEMPLATES = [
            ("how_to", f"How to Find the Best {niche.title()} Services in [City]"),
            ("cost", f"2026 {niche.title()} Cost Guide: What You'll Really Pay"),
            ("comparison", f"{niche.title()} Companies Near You: Ranked and Reviewed"),
            ("urgent", f"Signs You Need {niche.title()} Services Immediately"),
            ("myth", f"5 Myths About {niche.title()} That Are Costing You Money"),
            ("guide", f"The Complete Guide to {niche.title()} in 2026"),
            ("case_study", f"How One Homeowner Saved $5K Using Empire AI for {niche.title()}"),
            ("seasonal", f"Is {keywords[0] if keywords else niche} Season Here? What to Do Now"),
        ]
        return [
            {"type": t[0], "title": t[1], "est_engagement": round(80 - i * 8, 1)}
            for i, t in enumerate(ANGLE_TEMPLATES)
        ]

    # ── 4. GENERATE CONTENT / CREATIVES ──────────────────────────────

    async def generate_variants(self, niche: str, channel: str,
                                 count: int = 5) -> dict:
        """Generate content/creative variants for a niche+channel.

        Uses LLM when available, falls back to template-based generation.
        """
        action = {
            "action": "generate_variants",
            "niche": niche,
            "channel": channel,
            "count": count,
            "triggered_at": self._now(),
        }

        # Try LLM generation
        try:
            from empire_ai_router import AIRouter
            router = AIRouter(get_db=self.get_db)
            prompt = (
                f"Generate {count} {channel} content variants for the '{niche}' niche. "
                f"Each variant should be a complete {channel}-optimized piece: "
                f"headline, body (under 200 words), CTA, and estimated engagement score (0-100). "
                f"Focus on unconventional, high-impact angles that would perform well for "
                f"an AI-powered lead generation platform called Empire AI. "
                f"Return as JSON with key 'variants' containing an array of objects with keys: headline, body, cta, engagement_score."
            )
            result_json = await router.generate_json(
                prompt=prompt,
                task="general",
                system="You are a creative marketing strategist. Generate unconventional, high-impact content variants.",
            )
            if result_json and isinstance(result_json, dict):
                variants = result_json.get("variants", [])
                if variants:
                    action["variants"] = variants
                    action["status"] = "completed"
                    action["source"] = "llm"
                    self._content_history.append(action)
                    return action
        except Exception as e:
            log.debug(f"[hacking] LLM generation failed: {e}")

        # Fallback template-based generation
        variants = []
        ANGLES = [
            f"Don't Pay Full Price for {niche.title()} — Here's How AI Finds You a Better Deal",
            f"Your {niche.title()} Questions Answered in 30 Seconds (Free AI Tool)",
            f"The {niche.title()} Industry Doesn't Want You to Know This",
            f"Why Most {niche.title()} Companies Are Overpriced (And How to Find the Good Ones)",
            f"This AI Found Me a {niche.title()} Contractor in 2 Minutes — Here's How",
        ]
        for i in range(min(count, len(ANGLES))):
            variants.append({
                "variant_id": f"VAR-{hashlib.md5(f'{niche}{channel}{i}'.encode()).hexdigest()[:6].upper()}",
                "channel": channel,
                "niche": niche,
                "headline": ANGLES[i],
                "body": (f"Finding the right {niche} contractor is hard. "
                         f"Empire AI does the work for you — analyzes storm data, "
                         f"qualifies contractors, and connects you with the best match. "
                         f"Free to use. No obligation."),
                "cta": "Try Empire AI Free →",
                "estimated_engagement": round(70 - i * 8, 1),
            })

        action["variants"] = variants
        action["status"] = "completed"
        action["source"] = "template"
        self._content_history.append(action)
        return action

    # ── 5. AUDIENCE EXPLOITATION ─────────────────────────────────────

    def detect_audience_gaps(self, niche: str = "") -> dict:
        """Find audience segments that are underserved or exploitable.

        Analyzes channel activity to identify gaps where competitors
        are underinvested and where unconventional tactics can win.
        """
        gap_id = f"GAP-{uuid.uuid4().hex[:8].upper()}"
        channel_stats = self._get_channel_stats()

        gaps = []
        for ch, stats in _CHANNEL_WEIGHTS.items():
            vol = channel_stats.get(ch, 0)
            traffic = stats.get("traffic_potential", 5)
            cost = stats.get("cost", 5)
            effort = stats.get("effort", 5)

            # Gap score: high traffic + low effort + low current activity = exploit gap
            gap_score = (traffic * 2) + (cost * 1.5) - (effort * 0.5) - min(vol / 10, 20)

            if gap_score >= 30:
                gaps.append({
                    "channel": ch,
                    "gap_score": round(gap_score, 1),
                    "traffic_potential": traffic,
                    "cost_efficiency": cost,
                    "effort_required": effort,
                    "current_volume": vol,
                    "exploit_tactic": self._recommend_exploit(ch, niche),
                })

        gaps.sort(key=lambda g: g["gap_score"], reverse=True)

        insight = {
            "gap_id": gap_id,
            "niche": niche or "cross_niche",
            "gaps_detected": len(gaps),
            "top_gaps": gaps[:5],
            "exploitable_channels": [g["channel"] for g in gaps],
            "detected_at": self._now(),
        }
        self._audience_insights.append(insight)

        return insight

    def _recommend_exploit(self, channel: str, niche: str) -> str:
        """Recommend an audience exploitation tactic for a channel."""
        exploits = {
            "seo": f"Create {niche} content targeting 'why [competitor] is bad' keywords — capture competitor churn audience",
            "social": f"Monitor {niche} hashtags and insert Empire AI into conversations with value-first replies",
            "forums": f"Find {niche} recommendation threads on Reddit and Quora — be the top-voted helpful answer",
            "ads": f"Run tiny $3/day ads targeting {niche} competitor brand terms — capture comparison shoppers",
            "email": f"Scrape {niche} trade show attendee lists — send personalized cold email sequence",
            "affiliate": f"Recruit {niche} YouTubers with affiliate codes — let them sell for you",
            "referral": f"Offer existing {niche} partners a referral bounty — turn them into your sales team",
        }
        return exploits.get(channel, f"Research {channel} exploitation tactics for {niche}")

    # ── 6. CHANNEL FLOODING ──────────────────────────────────────────

    async def flood_channel(self, niche: str, channel: str,
                             intensity: str = "standard",
                             count: int = 5) -> dict:
        """Flood a channel with targeted content variants.

        Generates multiple content pieces and distributes them across
        the target channel for maximum saturation.
        """
        flood_id = f"FLOOD-{uuid.uuid4().hex[:8].upper()}"
        now = self._now()

        # Generate content variants
        gen = await self.generate_variants(niche=niche, channel=channel, count=count)
        variants = gen.get("variants", [])

        flood = {
            "flood_id": flood_id,
            "niche": niche,
            "channel": channel,
            "intensity": intensity,
            "variants_generated": len(variants),
            "target_segments": [
                f"{niche.title()} decision makers on {channel}",
                f"{niche.title()} comparison shoppers",
                f"{niche.title()} professionals active in forums",
            ],
            "variants": variants,
            "status": "queued",
            "created_at": now,
            "note": f"Channel flood queued for {channel}. Auto-posting requires platform API keys." if channel not in ("ads", "email") else f"Ready to deploy to {channel}.",
        }
        self._channel_floods.append(flood)

        return {"ok": True, "flood": flood}

    # ── 7. VIRAL ENGINEERING ─────────────────────────────────────────

    def engineer_viral_pattern(self, niche: str = "") -> dict:
        """Engineer a viral content pattern for a niche.

        Analyzes viral triggers (emotion, novelty, utility, identity)
        and generates content frameworks designed for maximum shareability.
        """
        pattern_id = f"VIRAL-{uuid.uuid4().hex[:8].upper()}"

        VIRAL_TRIGGERS = [
            {
                "trigger": "identity_reinforcement",
                "hook": f"Real {niche} professionals do THIS — everyone else is wrong",
                "predicted_virality": 0.85,
                "best_channel": "linkedin",
                "time_to_peak_hours": 12,
            },
            {
                "trigger": "novelty_shock",
                "hook": f"This {niche} AI tool just saved {3} businesses in {niche} from disaster",
                "predicted_virality": 0.78,
                "best_channel": "tiktok",
                "time_to_peak_hours": 6,
            },
            {
                "trigger": "utility_share",
                "hook": f"Free {niche} checklist: {7} things every {niche} pro should know in 2026",
                "predicted_virality": 0.72,
                "best_channel": "facebook",
                "time_to_peak_hours": 24,
            },
            {
                "trigger": "outrage_curiosity",
                "hook": f"Why {niche} companies are hiding THIS from their customers",
                "predicted_virality": 0.90,
                "best_channel": "reddit",
                "time_to_peak_hours": 4,
            },
            {
                "trigger": "community_inside_joke",
                "hook": f"Every {niche} contractor knows this pain — and it's finally fixed",
                "predicted_virality": 0.68,
                "best_channel": "nextdoor",
                "time_to_peak_hours": 18,
            },
        ]

        pattern = {
            "pattern_id": pattern_id,
            "niche": niche or "cross_niche",
            "patterns": VIRAL_TRIGGERS,
            "avg_virality_score": round(sum(p["predicted_virality"] for p in VIRAL_TRIGGERS) / len(VIRAL_TRIGGERS), 2),
            "best_channels": sorted(
                set(p["best_channel"] for p in VIRAL_TRIGGERS)
            ),
            "recommended_fastest": max(VIRAL_TRIGGERS, key=lambda p: p["predicted_virality"]),
            "engineered_at": self._now(),
        }
        self._viral_patterns.append(pattern)

        return pattern

    # ── 8. SYNDICATE ─────────────────────────────────────────────────

    async def syndicate(self, niche: str, channel: str,
                         content: str = "", platform: str = "") -> dict:
        """Record a content syndication action.

        In production this would auto-post to the target platform.
        Currently records the intent and generates a shareable link.
        """
        action = {
            "action": "syndicate",
            "niche": niche,
            "channel": channel,
            "platform": platform or channel,
            "triggered_at": self._now(),
            "status": "queued",
            "note": f"Content ready for {channel} syndication targeting {niche}. "
                    f"Auto-post requires platform API keys.",
            "preview": content[:200] if content else f"[{channel.upper()} content for {niche}]",
        }

        # Try to generate content if none provided
        if not content:
            gen = await self.generate_variants(niche, channel, count=1)
            variants = gen.get("variants", [])
            if variants:
                action["preview"] = variants[0].get("body", action["preview"])
                action["variant_id"] = variants[0].get("variant_id", "")

        self._syndication_history.append(action)
        return action

    # ── SNAPSHOT ─────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """Condensed snapshot for fleet dashboard."""
        overview = self.overview()
        return {
            "active_niches": overview.get("active_niches", 0),
            "high_impact_opportunities": overview.get("high_impact_opportunities", 0),
            "total_opportunities": overview.get("total_opportunities", 0),
            "content_generated": overview.get("content_generated", 0),
            "syndications": overview.get("syndications", 0),
            "audience_gaps": overview.get("audience_gaps_detected", 0),
            "channel_floods": overview.get("channel_floods_active", 0),
            "viral_patterns": overview.get("viral_patterns_engineered", 0),
            "mrr_projected": overview.get("revenue", {}).get("mrr_projected", 0),
            "revenue_24h": overview.get("revenue", {}).get("revenue_24h", 0),
            "modified": self._now(),
        }


# ── FASTAPI ROUTES ──────────────────────────────────────────────────────

def register_hacking_routes(app, get_db=None, require_auth=None):
    """Register AI Hacking Agent routes on a FastAPI app."""
    from fastapi import Depends, HTTPException, Query

    if get_db is None:
        log.warning("[hacking] No get_db — agent will return errors on DB calls")
    _hack = AIHackingAgent(get_db=get_db) if get_db else None

    def _get_hack():
        if _hack is None:
            raise HTTPException(503, "AI Hacking Agent not initialized (no get_db)")
        return _hack

    @app.get("/api/hacking/overview")
    async def hack_overview(auth=Depends(require_auth) if require_auth else None):
        """Dashboard — channel health, recent hacks, opportunity count."""
        return _get_hack().overview()

    @app.get("/api/hacking/opportunities")
    async def hack_opportunities(auth=Depends(require_auth) if require_auth else None):
        """Score and rank all niche+channel combinations for hacking potential."""
        return _get_hack().opportunities()

    @app.get("/api/hacking/trends")
    async def hack_trends(auth=Depends(require_auth) if require_auth else None):
        """Trending topics and content angles per niche."""
        return _get_hack().trends()

    @app.post("/api/hacking/generate")
    async def hack_generate(
        niche: str = Query(..., description="Target niche"),
        channel: str = Query("social", description="Target channel (seo, social, forums, ads, email)"),
        count: int = Query(5, ge=1, le=20, description="Number of variants"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Generate content/creative variants for a niche+channel."""
        result = await _get_hack().generate_variants(
            niche=niche, channel=channel, count=count,
        )
        status = 200 if result.get("status") != "failed" else 500
        return result

    @app.post("/api/hacking/syndicate")
    async def hack_syndicate(
        niche: str = Query(..., description="Target niche"),
        channel: str = Query(..., description="Target channel"),
        platform: str = Query("", description="Platform name"),
        content: str = Query("", description="Content body"),
        auth=Depends(require_auth) if require_auth else None,
    ):
        """Record and queue a content syndication action."""
        result = await _get_hack().syndicate(
            niche=niche, channel=channel,
            platform=platform, content=content,
        )
        status = 200 if result.get("status") != "failed" else 500
        return result

    @app.get("/api/hacking/snapshot")
    async def hack_snapshot(auth=Depends(require_auth) if require_auth else None):
        """Condensed snapshot for fleet dashboard."""
        return _get_hack().snapshot()

    log.info("[hacking] Routes registered · /api/hacking/*")
