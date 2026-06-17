"""
EMPIRE V49 · TRAFFIC SPECIALIST BOT
====================================
Autonomous traffic generation & optimization agent that coordinates every
traffic method — paid and free — to drive leads to Empire AI's pipeline.

PAID TRAFFIC CHANNELS:
  1. NATIVE ADS NETWORK  → create/activate/manage campaigns on our own ad server
  2. PPC / PAY-PER-CALL  → optimize inbound call routing, bid management
  3. AFFILIATE NETWORK   → recruit affiliates, distribute tracking links
  4. SOCIAL ADS          → budget allocation by ROAS across platforms
  5. SEARCH ADS          → keyword bidding optimization (Google/Bing)

FREE TRAFFIC CHANNELS:
  6. SEO OPTIMIZATION    → coordinate with SEO agent for content/backlinks/keywords
  7. CONTENT DISTRIBUTION → social posting, blog syndication, guest posts
  8. EMAIL/SMS OUTREACH  → drip campaigns via strike campaigns engine
  9. ORGANIC SOCIAL      → automated posting framework
  10. COMMUNITY ENGAGE   → forum, Q&A, referral program participation

INTELLIGENCE LAYER:
  - Traffic Mix Optimization   → ROAS-based budget allocation across channels
  - Channel Switching          → shift budget to best-performing channels
  - Trend Detection            → identify rising traffic opportunities
  - Attribution                → track which channels drive conversions
  - Weekly Traffic Report      → narrative summary of all channel performance

Wire-up in hub.py startup:
    from bots.traffic_specialist import run_loop as traffic_specialist_run_loop
    asyncio.create_task(traffic_specialist_run_loop())

Routes (registered on hub):
    GET  /api/v1/traffic-specialist/snapshot    — full traffic mix status
    GET  /api/v1/traffic-specialist/channels    — per-channel performance
    GET  /api/v1/traffic-specialist/recommend   — recommendations for next actions
    POST /api/v1/traffic-specialist/run-cycle   — force a cycle
"""

import os
import sys
import json
import asyncio
import logging
import random
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Callable, Any
from collections import defaultdict

import httpx

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("empire.traffic_specialist")

# ── CONFIG ───────────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
HUB_URL = os.environ.get("PUBLIC_BASE_URL", "http://localhost:8000")
HUB_TOKEN = os.environ.get("HUB_TOKEN", "dev-token-insecure")

_sb = None

def _get_sb():
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
            sys.exit(1)
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


# ── CHANNEL DEFINITIONS ─────────────────────────────────────────────
# Every traffic method the bot can activate.
# cost_model: "cpc" | "cpm" | "cpa" | "flat" | "zero"
# traffic_type: "paid" | "free"
# status: "active" | "standby" | "inactive"
# channel_id is used throughout the bot as the canonical key.

TRAFFIC_CHANNELS = [
    {
        "channel_id": "native_ads",
        "name": "Native Ads Network",
        "traffic_type": "paid",
        "cost_model": "cpm",
        "priority": 1,
        "description": "Our own ad server — campaigns on empire-ai.co.uk and publisher network",
        "budget_monthly": 2000,
        "status": "standby",
        "requires_action": "Seed first campaign and activate",
    },
    {
        "channel_id": "ppc_inbound",
        "name": "PPC / Pay-Per-Call",
        "traffic_type": "paid",
        "cost_model": "cpa",
        "priority": 2,
        "description": "Inbound call routing: connect live callers to buyers",
        "budget_monthly": 5000,
        "status": "active",
        "requires_action": "",
    },
    {
        "channel_id": "affiliate_network",
        "name": "Affiliate Network",
        "traffic_type": "paid",
        "cost_model": "cpa",
        "priority": 3,
        "description": "Affiliate partners driving traffic via referral links",
        "budget_monthly": 3000,
        "status": "standby",
        "requires_action": "Recruit affiliates and distribute tracking links",
    },
    {
        "channel_id": "seo_organic",
        "name": "SEO / Organic",
        "traffic_type": "free",
        "cost_model": "zero",
        "priority": 4,
        "description": "Search engine optimization — content, keywords, backlinks",
        "budget_monthly": 0,
        "status": "active",
        "requires_action": "",
    },
    {
        "channel_id": "email_outreach",
        "name": "Email / SMS Outreach",
        "traffic_type": "free",
        "cost_model": "flat",
        "priority": 5,
        "description": "Drip campaigns via Strike Campaigns engine",
        "budget_monthly": 500,
        "status": "active",
        "requires_action": "",
    },
    {
        "channel_id": "content_distribution",
        "name": "Content Distribution",
        "traffic_type": "free",
        "cost_model": "zero",
        "priority": 6,
        "description": "Social posting, blog syndication, guest posts, directories",
        "budget_monthly": 0,
        "status": "standby",
        "requires_action": "Create content distribution targets and schedule",
    },
    {
        "channel_id": "community_engagement",
        "name": "Community Engagement",
        "traffic_type": "free",
        "cost_model": "zero",
        "priority": 7,
        "description": "Forum, Q&A, industry communities, referral programs",
        "budget_monthly": 0,
        "status": "standby",
        "requires_action": "Build target community list and engagement templates",
    },
    {
        "channel_id": "search_ads",
        "name": "Search Ads (Google/Bing)",
        "traffic_type": "paid",
        "cost_model": "cpc",
        "priority": 8,
        "description": "Paid search campaigns on Google Ads and Bing Ads",
        "budget_monthly": 3000,
        "status": "inactive",
        "requires_action": "Connect Google Ads API and create campaigns",
    },
    {
        "channel_id": "social_ads",
        "name": "Social Ads (Meta/LinkedIn/TikTok)",
        "traffic_type": "paid",
        "cost_model": "cpc",
        "priority": 9,
        "description": "Paid social campaigns on Meta, LinkedIn, TikTok",
        "budget_monthly": 2500,
        "status": "inactive",
        "requires_action": "Connect ad platform APIs and create campaigns",
    },
]

# Sort by priority
TRAFFIC_CHANNELS.sort(key=lambda c: c["priority"])


class TrafficSpecialist:
    """
    Autonomous traffic generation & optimization bot.

    Orchestrates all traffic methods — paid and free — to drive
    qualified leads. Runs on a configurable interval and can be
    triggered manually via API.
    """

    def __init__(self):
        self.channels = {c["channel_id"]: dict(c) for c in TRAFFIC_CHANNELS}
        self.stats = {
            "cycles_run": 0,
            "campaigns_created": 0,
            "channels_activated": 0,
            "recommendations_generated": 0,
            "total_traffic_estimate": 0,
            "errors": 0,
        }
        self._last_cycle: Optional[str] = None
        self._narrative_cache: Optional[str] = None
        self._narrative_ts: Optional[str] = None

    # ── CHANNEL STATUS ───────────────────────────────────────────────

    def get_channel(self, channel_id: str) -> Optional[dict]:
        return self.channels.get(channel_id)

    def set_channel_status(self, channel_id: str, status: str):
        if channel_id in self.channels:
            self.channels[channel_id]["status"] = status

    def set_channel_budget(self, channel_id: str, budget: float):
        if channel_id in self.channels:
            self.channels[channel_id]["budget_monthly"] = max(0, budget)

    # ── QUERY ACTUAL SYSTEM DATA ─────────────────────────────────────

    def _query_native_ads_stats(self) -> dict:
        """Query the native ads network for campaign stats."""
        try:
            sb = _get_sb()
            campaigns = sb.table("ad_campaigns").select("*").execute()
            creatives = sb.table("ad_creatives").select("*").execute()
            impressions = sb.table("ad_impressions").select("id").execute()
            clicks = sb.table("ad_clicks").select("id").execute()

            camp_data = campaigns.data or []
            active = [c for c in camp_data if c.get("status") == "active"]
            total_budget = sum(float(c.get("daily_budget", 0) or 0) * 30 for c in camp_data)

            return {
                "total_campaigns": len(camp_data),
                "active_campaigns": len(active),
                "total_creatives": len(creatives.data or []),
                "total_impressions": len(impressions.data or []),
                "total_clicks": len(clicks.data or []),
                "monthly_budget": round(total_budget, 2),
                "ctr": round(len(clicks.data or []) / max(len(impressions.data or []), 1) * 100, 2),
            }
        except Exception as e:
            log.warning(f"[traffic_specialist] native_ads query: {e}")
            return {}

    def _query_affiliate_stats(self) -> dict:
        """Query the affiliate network for link/click stats."""
        try:
            sb = _get_sb()
            links = sb.table("affiliate_links").select("id,click_count,active").execute()
            link_data = links.data or []
            active_links = [l for l in link_data if l.get("active")]
            total_clicks = sum(l.get("click_count", 0) or 0 for l in link_data)

            # Count attributed calls
            codes = [l.get("code") for l in link_data if l.get("code")]
            attributed_calls = 0
            if codes:
                calls = sb.table("call_logs").select("id").in_("affiliate_code", codes).execute()
                attributed_calls = len(calls.data or [])

            return {
                "total_links": len(link_data),
                "active_links": len(active_links),
                "total_clicks": total_clicks,
                "attributed_calls": attributed_calls,
            }
        except Exception as e:
            log.warning(f"[traffic_specialist] affiliate query: {e}")
            return {}

    def _query_seo_stats(self) -> dict:
        """Query SEO agent performance from DB tables."""
        try:
            sb = _get_sb()
            audits = sb.table("seo_audits").select("id").execute()
            keywords = sb.table("seo_keywords").select("conversions,impressions,conversion_rate").execute()
            content = sb.table("seo_content").select("id").execute()
            backlinks = sb.table("seo_backlinks").select("id,is_broken").execute()

            kw_data = keywords.data or []
            total_conversions = sum(k.get("conversions", 0) or 0 for k in kw_data)
            total_impressions_kw = sum(k.get("impressions", 0) or 0 for k in kw_data)
            bl_data = backlinks.data or []
            broken = sum(1 for b in bl_data if b.get("is_broken"))

            return {
                "total_audits": len(audits.data or []),
                "keywords_tracked": len(kw_data),
                "content_pieces": len(content.data or []),
                "total_conversions": total_conversions,
                "total_keyword_impressions": total_impressions_kw,
                "total_backlinks": len(bl_data),
                "broken_backlinks": broken,
            }
        except Exception as e:
            log.warning(f"[traffic_specialist] seo query: {e}")
            return {}

    def _query_email_sms_stats(self) -> dict:
        """Query email/SMS outreach stats."""
        try:
            sb = _get_sb()
            # Email drafts / sends
            drafts = sb.table("email_drafts").select("status").execute()
            drafts_data = drafts.data or []
            sent = sum(1 for d in drafts_data if d.get("status") == "sent")
            pending = sum(1 for d in drafts_data if d.get("status") == "pending")

            # SMS sequences
            sms = sb.table("sms_sequences").select("status").execute()
            sms_data = sms.data or []
            active_sms = sum(1 for s in sms_data if s.get("status") == "active")

            # Strike campaigns
            campaigns = sb.table("strike_campaigns").select("status").execute()
            camp_data = campaigns.data or []
            active_camps = sum(1 for c in camp_data if c.get("status") in ("active", "running"))

            # Outreach_log
            outreach = sb.table("outreach_log").select("id").execute()

            return {
                "emails_sent": sent,
                "emails_pending": pending,
                "active_sms_sequences": active_sms,
                "active_strike_campaigns": active_camps,
                "total_outreach_events": len(outreach.data or []),
            }
        except Exception as e:
            log.warning(f"[traffic_specialist] email/sms query: {e}")
            return {}

    def _query_revenue_activity(self) -> dict:
        """Query overall revenue activity as a proxy for traffic quality."""
        try:
            sb = _get_sb()
            # Recent call logs
            calls = sb.table("call_logs").select("fee_earned,qualified,channel").execute()
            call_data = calls.data or []
            total_revenue = sum(float(c.get("fee_earned", 0) or 0) for c in call_data)
            qualified = sum(1 for c in call_data if c.get("qualified"))

            # Channel breakdown
            by_channel = defaultdict(lambda: {"calls": 0, "revenue": 0.0, "qualified": 0})
            for c in call_data:
                ch = c.get("channel", "unknown")
                by_channel[ch]["calls"] += 1
                by_channel[ch]["revenue"] += float(c.get("fee_earned", 0) or 0)
                if c.get("qualified"):
                    by_channel[ch]["qualified"] += 1

            return {
                "total_calls": len(call_data),
                "total_revenue": round(total_revenue, 2),
                "qualified_calls": qualified,
                "by_channel": dict(by_channel),
            }
        except Exception as e:
            log.warning(f"[traffic_specialist] revenue query: {e}")
            return {"total_calls": 0, "total_revenue": 0, "qualified_calls": 0, "by_channel": {}}

    # ── CORE: PERFORM ONE CYCLE ──────────────────────────────────────

    async def run_cycle(self) -> Dict:
        """
        One full traffic specialist cycle:

        1. Assess all channel statuses from live data
        2. Generate budget allocation recommendations
        3. Recommend specific actions for each channel
        4. Generate traffic mix narrative
        5. Log snapshot to traffic_activity table
        """
        self.stats["cycles_run"] += 1
        self._last_cycle = datetime.now(timezone.utc).isoformat()

        # Gather live data from all channels
        native_stats = self._query_native_ads_stats()
        affiliate_stats = self._query_affiliate_stats()
        seo_stats = self._query_seo_stats()
        email_sms_stats = self._query_email_sms_stats()
        revenue_stats = self._query_revenue_activity()

        # Update channel statuses based on real data
        self._update_channel_statuses(native_stats, affiliate_stats, seo_stats, email_sms_stats)

        # Generate budget allocation
        budget_plan = self._generate_budget_plan(revenue_stats)

        # Generate channel actions
        actions = self._generate_actions(native_stats, affiliate_stats, seo_stats, email_sms_stats, revenue_stats)

        # Generate narrative
        narrative = self._generate_narrative(native_stats, affiliate_stats, seo_stats, email_sms_stats, revenue_stats, budget_plan, actions)
        self._narrative_cache = narrative
        self._narrative_ts = datetime.now(timezone.utc).isoformat()

        # Build snapshot
        snapshot = {
            "timestamp": self._last_cycle,
            "cycle": self.stats["cycles_run"],
            "channels": self._channels_snapshot(),
            "budget_plan": budget_plan,
            "actions": actions,
            "stats": {
                "native_ads": native_stats,
                "affiliate": affiliate_stats,
                "seo": seo_stats,
                "email_sms": email_sms_stats,
                "revenue": {k: v for k, v in revenue_stats.items() if k != "by_channel"},
            },
            "narrative": narrative,
        }

        # Persist cycle snapshot
        self._persist_snapshot(snapshot)

        self.stats["recommendations_generated"] += len(actions)
        log.info(f"[traffic_specialist] cycle {self.stats['cycles_run']} complete — {len(actions)} actions, {len(budget_plan.get('allocations', []))} budget lines")

        return snapshot

    def _update_channel_statuses(self, native: dict, affiliate: dict, seo: dict, email_sms: dict):
        """Update channel statuses based on whether they have real activity."""
        # Native ads: active if there are active campaigns
        if native.get("active_campaigns", 0) > 0:
            self.channels["native_ads"]["status"] = "active"
            self.channels["native_ads"]["requires_action"] = ""

        # Affiliate: active if there are links with clicks
        if affiliate.get("active_links", 0) > 0:
            self.channels["affiliate_network"]["status"] = "active" if affiliate.get("total_clicks", 0) > 0 else "standby"
            if affiliate.get("total_clicks", 0) > 0:
                self.channels["affiliate_network"]["requires_action"] = ""

        # SEO: active if there are keywords tracked
        if seo.get("keywords_tracked", 0) > 0:
            self.channels["seo_organic"]["status"] = "active"

        # Email/SMS: active if there are sequences or campaigns
        if email_sms.get("active_sms_sequences", 0) > 0 or email_sms.get("active_strike_campaigns", 0) > 0:
            self.channels["email_outreach"]["status"] = "active"

    def _channels_snapshot(self) -> List[Dict]:
        """Return current state of all traffic channels with computed metrics."""
        snap = []
        for cid, ch in self.channels.items():
            snap.append({
                "channel_id": cid,
                "name": ch["name"],
                "traffic_type": ch["traffic_type"],
                "cost_model": ch["cost_model"],
                "priority": ch["priority"],
                "status": ch["status"],
                "budget_monthly": ch["budget_monthly"],
                "requires_action": ch["requires_action"],
            })
        return snap

    def _generate_budget_plan(self, revenue_stats: dict) -> Dict:
        """
        Generate optimal budget allocation across channels based on
        current performance data and statuses.
        """
        by_channel = revenue_stats.get("by_channel", {})
        total_budget = sum(c["budget_monthly"] for c in self.channels.values())

        allocations = []
        available_budget = total_budget

        # Active paid channels get budget based on ROAS signal
        # Standby channels get minimum to activate
        # Inactive channels get $0

        for cid, ch in self.channels.items():
            if ch["traffic_type"] == "free":
                # Free channels don't consume budget
                allocations.append({
                    "channel_id": cid,
                    "name": ch["name"],
                    "type": "free",
                    "allocated": 0,
                    "pct_of_total": 0,
                    "rationale": "Free channel — no budget required",
                })
                continue

            if ch["status"] == "inactive":
                allocations.append({
                    "channel_id": cid,
                    "name": ch["name"],
                    "type": "paid",
                    "allocated": 0,
                    "pct_of_total": 0,
                    "rationale": "Inactive — requires API setup",
                })
                continue

            if ch["status"] == "standby":
                # Small allocation to activate
                seed = min(500, ch["budget_monthly"])
                allocations.append({
                    "channel_id": cid,
                    "name": ch["name"],
                    "type": "paid",
                    "allocated": seed,
                    "pct_of_total": round(seed / max(total_budget, 1) * 100, 1),
                    "rationale": f"Standby — seed ${seed} to activate",
                })
                available_budget -= seed
                continue

            # Active paid channel — allocate based on revenue signal
            channel_rev = 0
            for src_ch, src_data in by_channel.items():
                if cid in src_ch or src_ch in cid:
                    channel_rev += src_data.get("revenue", 0)

            if channel_rev > 0 and available_budget > 0:
                # Weight by revenue contribution
                max_budget = min(ch["budget_monthly"], available_budget)
                allocated = round(max_budget * 0.7, 0)  # 70% of max
            else:
                # No revenue signal — base allocation
                allocated = min(ch["budget_monthly"] * 0.3, available_budget, 1000)

            allocated = min(allocated, available_budget)
            pct = round(allocated / max(total_budget, 1) * 100, 1)
            allocations.append({
                "channel_id": cid,
                "name": ch["name"],
                "type": "paid",
                "allocated": round(allocated, 2),
                "pct_of_total": pct,
                "rationale": f"Active — ${channel_rev:.0f} revenue attributed" if channel_rev > 0 else "Active — base allocation",
            })
            available_budget -= allocated

        return {
            "total_budget": total_budget,
            "allocated": round(total_budget - available_budget, 2),
            "unallocated": round(available_budget, 2),
            "allocations": allocations,
        }

    def _generate_actions(
        self, native: dict, affiliate: dict, seo: dict,
        email_sms: dict, revenue: dict,
    ) -> List[Dict]:
        """
        Generate actionable recommendations for each channel.
        Prioritizes high-impact, low-effort actions first.
        """
        actions = []

        # ── NATIVE ADS ───────────────────────────────────────────────
        if native.get("active_campaigns", 0) == 0:
            actions.append({
                "priority": "P1",
                "channel": "native_ads",
                "action": "Seed first ad campaign",
                "impact": "high",
                "effort": "low",
                "detail": "Create at least one campaign + creative in the ad_campaigns table so the /api/v1/ads/serve endpoint has inventory to serve.",
            })
        elif native.get("total_impressions", 0) == 0:
            actions.append({
                "priority": "P1",
                "channel": "native_ads",
                "action": "Embed ads on Empire AI pages",
                "impact": "high",
                "effort": "low",
                "detail": "Add the publisher embed snippet to splash page, /ppl, /pricing to start serving ads to existing traffic.",
            })
        else:
            actions.append({
                "priority": "P2",
                "channel": "native_ads",
                "action": f"Recruit publishers — {native.get('total_impressions', 0)} impressions delivered",
                "impact": "high",
                "effort": "medium",
                "detail": "Distribute publisher embed snippet to contractor network and partner sites.",
            })

        # ── AFFILIATE ────────────────────────────────────────────────
        if affiliate.get("active_links", 0) == 0:
            actions.append({
                "priority": "P1",
                "channel": "affiliate_network",
                "action": "Create initial affiliate referral links",
                "impact": "high",
                "effort": "low",
                "detail": "Create referral links for existing buyers so they can start promoting Empire AI.",
            })
        elif affiliate.get("total_clicks", 0) == 0:
            actions.append({
                "priority": "P2",
                "channel": "affiliate_network",
                "action": "Distribute affiliate links to partners",
                "impact": "medium",
                "effort": "medium",
                "detail": f"{affiliate.get('active_links', 0)} links exist but 0 clicks — send links to affiliate partners.",
            })
        else:
            actions.append({
                "priority": "P3",
                "channel": "affiliate_network",
                "action": f"Recruit new affiliates — {affiliate.get('active_links', 0)} links, {affiliate.get('total_clicks', 0)} clicks",
                "impact": "medium",
                "effort": "medium",
                "detail": "Current affiliates active. Expand by recruiting more buyers as affiliates.",
            })

        # ── SEO ──────────────────────────────────────────────────────
        if seo.get("keywords_tracked", 0) == 0:
            actions.append({
                "priority": "P1",
                "channel": "seo_organic",
                "action": "Start SEO keyword research and content generation",
                "impact": "high",
                "effort": "low",
                "detail": "The SEO Agent auto-loop is running — verify it's cycling and keywords are being tracked.",
            })
        else:
            kw = seo.get("keywords_tracked", 0)
            conv = seo.get("total_conversions", 0)
            bl = seo.get("total_backlinks", 0)
            actions.append({
                "priority": "P2",
                "channel": "seo_organic",
                "action": f"SEO active: {kw} keywords, {conv} conversions, {bl} backlinks",
                "impact": "high",
                "effort": "low",
                "detail": "SEO agent is running. Monitor keyword rankings and backlink growth.",
            })

        # ── CONTENT DISTRIBUTION ─────────────────────────────────────
        if self.channels["content_distribution"]["status"] == "standby":
            actions.append({
                "priority": "P2",
                "channel": "content_distribution",
                "action": "Set up content distribution pipeline",
                "impact": "medium",
                "effort": "medium",
                "detail": "Create distribution list: social media profiles, blog syndication sites, industry directories, guest post targets.",
            })

        # ── SEARCH ADS ───────────────────────────────────────────────
        if self.channels["search_ads"]["status"] == "inactive":
            actions.append({
                "priority": "P3",
                "channel": "search_ads",
                "action": "Connect Google Ads API and create search campaigns",
                "impact": "high",
                "effort": "high",
                "detail": "Set up Google Ads account, generate API credentials, create initial search campaigns for high-intent keywords.",
            })

        # ── OUTPUT VOLUME ────────────────────────────────────────────
        total_calls = revenue.get("total_calls", 0)
        if total_calls == 0:
            actions.append({
                "priority": "P0",
                "channel": "all",
                "action": "Zero revenue calls — increase traffic volume from ANY channel",
                "impact": "critical",
                "effort": "varies",
                "detail": "No calls have been logged. Prioritize seeding native ads, activating affiliates, and accelerating SEO to generate first leads.",
            })

        return actions

    def _generate_narrative(
        self, native: dict, affiliate: dict, seo: dict,
        email_sms: dict, revenue: dict, budget_plan: dict, actions: list,
    ) -> str:
        """Generate a human-readable traffic mix narrative."""
        lines = []
        lines.append(f"Traffic Specialist Report · {self._last_cycle or datetime.now(timezone.utc).isoformat()}")
        lines.append("━" * 60)
        lines.append("")

        # Revenue overview
        total_calls = revenue.get("total_calls", 0)
        total_rev = revenue.get("total_revenue", 0)
        qualified = revenue.get("qualified_calls", 0)

        lines.append(f"REVENUE: {total_calls} total calls · ${total_rev:.0f} revenue · {qualified} qualified")
        lines.append("")

        # Channel status summary
        active = [c for c in self.channels.values() if c["status"] == "active"]
        standby = [c for c in self.channels.values() if c["status"] == "standby"]
        inactive = [c for c in self.channels.values() if c["status"] == "inactive"]
        lines.append(f"CHANNELS: {len(active)} active · {len(standby)} standby · {len(inactive)} inactive")

        for c in self.channels.values():
            icon = "✅" if c["status"] == "active" else ("⏸️" if c["status"] == "standby" else "❌")
            lines.append(f"  {icon} {c['name']:25s} [{c['status']:8s}] · ${c['budget_monthly']:>5,.0f}/mo")
            if c["requires_action"]:
                lines.append(f"     → {c['requires_action']}")

        lines.append("")

        # Active channel details
        if native.get("active_campaigns", 0) > 0:
            lines.append(f"NATIVE ADS: {native['active_campaigns']} active campaigns, {native['total_impressions']} impressions, {native['total_clicks']} clicks (CTR {native.get('ctr', 0)}%)")
        if affiliate.get("total_clicks", 0) > 0:
            lines.append(f"AFFILIATES: {affiliate['active_links']} links, {affiliate['total_clicks']} clicks, {affiliate['attributed_calls']} attributed calls")
        if seo.get("keywords_tracked", 0) > 0:
            lines.append(f"SEO: {seo['keywords_tracked']} keywords, {seo['content_pieces']} content pieces, {seo['total_conversions']} conversions, {seo['total_backlinks']} backlinks")
        if email_sms.get("emails_sent", 0) > 0 or email_sms.get("active_sms_sequences", 0) > 0:
            lines.append(f"EMAIL/SMS: {email_sms['emails_sent']} sent, {email_sms['active_sms_sequences']} active SMS sequences, {email_sms['active_strike_campaigns']} strike campaigns")

        lines.append("")

        # Budget
        lines.append(f"BUDGET: ${budget_plan['total_budget']:,.0f} total · ${budget_plan['allocated']:,.0f} allocated · ${budget_plan['unallocated']:,.0f} available")
        for a in budget_plan.get("allocations", []):
            if a["allocated"] > 0:
                lines.append(f"  {a['name']:25s} ${a['allocated']:>6,.0f} ({a['pct_of_total']}%) · {a['rationale']}")

        lines.append("")

        # Top actions
        lines.append("TOP ACTIONS:")
        p1 = [a for a in actions if a["priority"] == "P1" or a["priority"] == "P0"]
        for a in p1[:5]:
            lines.append(f"  🔴 [{a['priority']}] {a['action']} — {a['detail'][:100]}")

        return "\n".join(lines)

    def _persist_snapshot(self, snapshot: dict):
        """Save cycle snapshot to traffic_activity table for history and SPA."""
        try:
            sb = _get_sb()
            sb.table("traffic_activity").insert({
                "cycle": snapshot["cycle"],
                "timestamp": snapshot["timestamp"],
                "snapshot": {
                    "channels": snapshot["channels"],
                    "budget_plan": snapshot["budget_plan"],
                    "actions": snapshot["actions"],
                    "stats": snapshot["stats"],
                },
                "narrative": snapshot["narrative"],
            }).execute()
        except Exception:
            log.debug("[traffic_specialist] persist_snapshot skipped")
            pass

    # ── API METHODS ──────────────────────────────────────────────────

    def snapshot(self) -> Dict:
        """Return full traffic specialist snapshot for SPA and API."""
        native_stats = self._query_native_ads_stats()
        affiliate_stats = self._query_affiliate_stats()
        seo_stats = self._query_seo_stats()
        email_sms_stats = self._query_email_sms_stats()
        revenue_stats = self._query_revenue_activity()

        active = sum(1 for c in self.channels.values() if c["status"] == "active")
        standby = sum(1 for c in self.channels.values() if c["status"] == "standby")
        inactive = sum(1 for c in self.channels.values() if c["status"] == "inactive")

        total_budget = sum(c["budget_monthly"] for c in self.channels.values())
        paid_budget = sum(c["budget_monthly"] for c in self.channels.values() if c["traffic_type"] == "paid")

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "last_cycle": self._last_cycle,
            "cycles_run": self.stats["cycles_run"],
            "channels": {
                "active": active,
                "standby": standby,
                "inactive": inactive,
                "total": len(self.channels),
                "list": self._channels_snapshot(),
            },
            "budget": {
                "total_monthly": total_budget,
                "paid_monthly": paid_budget,
                "free_monthly": total_budget - paid_budget,
            },
            "live_stats": {
                "native_ads": native_stats,
                "affiliate": affiliate_stats,
                "seo": seo_stats,
                "email_sms": email_sms_stats,
                "revenue": {k: v for k, v in revenue_stats.items() if k != "by_channel"},
            },
        }

    def recommendations(self) -> List[Dict]:
        """Return current actions/recommendations without running a full cycle."""
        native_stats = self._query_native_ads_stats()
        affiliate_stats = self._query_affiliate_stats()
        seo_stats = self._query_seo_stats()
        email_sms_stats = self._query_email_sms_stats()
        revenue_stats = self._query_revenue_activity()

        return self._generate_actions(native_stats, affiliate_stats, seo_stats, email_sms_stats, revenue_stats)

    def narrative(self) -> Dict:
        """Return the cached narrative, or generate a fresh one if stale."""
        if self._narrative_cache and self._narrative_ts:
            age = datetime.now(timezone.utc) - datetime.fromisoformat(self._narrative_ts)
            if age < timedelta(hours=1):
                return {"narrative": self._narrative_cache, "generated_at": self._narrative_ts, "cached": True}

        # Generate fresh
        native_stats = self._query_native_ads_stats()
        affiliate_stats = self._query_affiliate_stats()
        seo_stats = self._query_seo_stats()
        email_sms_stats = self._query_email_sms_stats()
        revenue_stats = self._query_revenue_activity()
        budget_plan = self._generate_budget_plan(revenue_stats)
        actions = self._generate_actions(native_stats, affiliate_stats, seo_stats, email_sms_stats, revenue_stats)
        narrative = self._generate_narrative(native_stats, affiliate_stats, seo_stats, email_sms_stats, revenue_stats, budget_plan, actions)

        self._narrative_cache = narrative
        self._narrative_ts = datetime.now(timezone.utc).isoformat()

        return {"narrative": narrative, "generated_at": self._narrative_ts, "cached": False}


# ── GLOBAL SINGLETON ─────────────────────────────────────────────────
_TRAFFIC_SPECIALIST: Optional[TrafficSpecialist] = None


def get_traffic_specialist() -> TrafficSpecialist:
    global _TRAFFIC_SPECIALIST
    if _TRAFFIC_SPECIALIST is None:
        _TRAFFIC_SPECIALIST = TrafficSpecialist()
    return _TRAFFIC_SPECIALIST


# ── BACKGROUND LOOP ──────────────────────────────────────────────────
async def run_loop(interval_minutes: int = 30):
    """
    Background loop: run traffic specialist cycles periodically.
    Configure via TRAFFIC_SPECIALIST_INTERVAL env var (default 30 min).
    """
    if interval_minutes is None:
        try:
            interval_minutes = int(os.environ.get("TRAFFIC_SPECIALIST_INTERVAL", "30"))
        except (ValueError, TypeError):
            interval_minutes = 30

    log.info(f"[traffic_specialist] Bot ONLINE · interval={interval_minutes}m")
    specialist = get_traffic_specialist()

    # Heartbeat to agent registry — register as Traffic Director role
    async def heartbeat():
        try:
            sb = _get_sb()
            sb.table("agent_registry").upsert({
                "agent_name": "traffic_specialist",
                "role_name": "traffic_director",
                "status": "ACTIVE",
                "last_ping": datetime.now(timezone.utc).isoformat(),
                "enabled": True,
                "capabilities": [
                    "allocate_budget", "set_traffic_strategy", "monitor_all_channels",
                    "generate_traffic_report", "optimize_channel_mix",
                    "manage_native_ads", "manage_affiliates", "manage_seo",
                    "manage_email", "manage_sms", "traffic_generation",
                    "budget_optimization", "channel_orchestration",
                ],
                "task_types": [
                    "traffic.allocate", "traffic.report", "traffic.optimize",
                    "native.optimize", "affiliate.recruit", "seo.audit",
                    "email.optimize", "sms.optimize",
                ],
            }, on_conflict="agent_name").execute()
        except Exception:
            pass

    await heartbeat()

    while True:
        try:
            log.info("[traffic_specialist] Running cycle...")
            result = await specialist.run_cycle()
            actions = len(result.get("actions", []))
            log.info(f"[traffic_specialist] Cycle complete — {actions} recommendations")
            await heartbeat()
        except Exception as e:
            log.error(f"[traffic_specialist] Cycle error: {e}")
            specialist.stats["errors"] += 1

        await asyncio.sleep(interval_minutes * 60)


# ── FASTAPI ROUTES ──────────────────────────────────────────────────
def register_traffic_specialist_routes(
    app: "FastAPI",
    *,
    require_auth: Callable,
):
    """
    Wire traffic specialist API routes on the hub.

    GET  /api/v1/traffic-specialist/snapshot      — full traffic mix status
    GET  /api/v1/traffic-specialist/channels       — per-channel performance
    GET  /api/v1/traffic-specialist/recommend      — recommendations for next actions
    POST /api/v1/traffic-specialist/run-cycle      — force a cycle
    GET  /api/v1/traffic-specialist/narrative      — human-readable traffic report
    """
    from fastapi import Depends

    specialist = get_traffic_specialist()

    @app.get("/api/v1/traffic-specialist/snapshot")
    async def ts_snapshot(auth: bool = Depends(require_auth)):
        return specialist.snapshot()

    @app.get("/api/v1/traffic-specialist/channels")
    async def ts_channels(auth: bool = Depends(require_auth)):
        return {
            "channels": specialist._channels_snapshot(),
            "total": len(specialist.channels),
            "active": sum(1 for c in specialist.channels.values() if c["status"] == "active"),
            "standby": sum(1 for c in specialist.channels.values() if c["status"] == "standby"),
            "inactive": sum(1 for c in specialist.channels.values() if c["status"] == "inactive"),
        }

    @app.get("/api/v1/traffic-specialist/recommend")
    async def ts_recommend(auth: bool = Depends(require_auth)):
        recs = specialist.recommendations()
        return {"recommendations": recs, "count": len(recs)}

    @app.post("/api/v1/traffic-specialist/run-cycle")
    async def ts_run_cycle(auth: bool = Depends(require_auth)):
        result = await specialist.run_cycle()
        return {"ok": True, "cycle": result["cycle"], "actions": len(result.get("actions", [])), "timestamp": result["timestamp"]}

    @app.get("/api/v1/traffic-specialist/narrative")
    async def ts_narrative(auth: bool = Depends(require_auth)):
        return specialist.narrative()

    log.info("[traffic_specialist] Routes registered · /api/v1/traffic-specialist/{snapshot,channels,recommend,run-cycle,narrative}")


# ── STANDALONE CLI ───────────────────────────────────────────────────
def run():
    """Sync entry point for main.py agent loop compatibility."""
    asyncio.run(run_loop())


if __name__ == "__main__":
    import sys
    if "--cycle" in sys.argv:
        result = asyncio.run(get_traffic_specialist().run_cycle())
        print(json.dumps(result, indent=2))
    elif "--snapshot" in sys.argv:
        snap = get_traffic_specialist().snapshot()
        print(json.dumps(snap, indent=2))
    elif "--recommend" in sys.argv:
        recs = get_traffic_specialist().recommendations()
        print(json.dumps(recs, indent=2))
    else:
        asyncio.run(run_loop())
