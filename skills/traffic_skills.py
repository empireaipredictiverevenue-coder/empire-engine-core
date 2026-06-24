"""
EMPIRE V49 · TRAFFIC SKILLS
=============================
Concrete skill implementations for the Traffic Specialist (traffic_director)
role. Each skill provides expert guidance across traffic channel management,
budget allocation, channel optimization, ad spend, and reporting.

When executed, the skill returns structured guidance based on input
parameters. With an ask_llm callable wired, it executes the full
traffic skill via LLM reasoning.
"""

import json
import time
import logging
from typing import Any, Callable, Optional

from skills.base import BaseSkill, SkillInput, SkillOutput, SkillMetrics

log = logging.getLogger("empire.skills.traffic")


# ── Base class for all traffic skills ──────────────────────────────


class TrafficSkill(BaseSkill):
    """Base class for traffic management skills.

    Each subclass represents a specific traffic discipline. The execute()
    method constructs a structured prompt from the instructions + user
    params and returns guidance. With ask_llm wired, it executes via LLM.
    """

    name = "traffic.base"  # Abstract base — not registered directly
    traffic_domain: str = ""  # Traffic domain identifier
    timeout_seconds = 60.0
    max_retries = 2

    def __init__(self):
        super().__init__()
        self.ask_llm: Optional[Callable[[str, str], Any]] = None

    async def validate(self, input: SkillInput) -> bool:
        return True

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()

        user_context = []
        for key, value in input.params.items():
            if isinstance(value, (dict, list)):
                user_context.append(f"{key}: {json.dumps(value, indent=2)}")
            else:
                user_context.append(f"{key}: {value}")

        # ── Build AGI/SI/PR context block (from harness injection) ──
        agi_block = ""
        agi = si = pr = {}
        if input.context:
            agi = input.context.get("agi_governor") or {}
            si = input.context.get("si_strategy") or {}
            pr = input.context.get("predictive_revenue") or {}
            parts = []
            if agi.get("strategy"):
                parts.append(f"AGI Strategy: {agi['strategy']}")
            if agi.get("health"):
                parts.append(f"AGI Health: {agi['health']}")
            if si.get("best_per_niche"):
                parts.append(f"SI Best Strategies (per niche): {si['best_per_niche']}")
            if pr.get("close_rate"):
                parts.append(f"Current Close Rate: {pr['close_rate']}")
            if pr.get("forecast"):
                totals = pr["forecast"].get("totals", {})
                parts.append(f"Revenue 24h: ${totals.get('revenue_24h', 0)} | MRR: ${totals.get('mrr_projected', 0)}")
            if parts:
                agi_block = "\n".join(parts)

        system_prompt = (
            f"You are the Empire AI Traffic Director executing skill '{self.name}'.\n"
            f"{self.description}\n\n"
            f"## Traffic Domain\n{self.traffic_domain}\n\n"
            f"Apply your traffic management expertise to the user's request below. "
            f"Be thorough and actionable. Provide specific recommendations "
            f"with rationale, alternatives, and edge cases. Consider ROAS, "
            f"channel diversification, and cost-per-lead across all channels."
        )

        if agi_block:
            system_prompt += (
                f"\n\n## Live System Context\n{agi_block}\n"
                f"Use this context to align your recommendations with current "
                f"strategy (AGI Governor), SI genome traits, and revenue targets."
            )

        result = {
            "skill": self.name,
            "skill_description": self.description,
            "traffic_domain": self.traffic_domain,
            "input_params": input.params,
            "agi_context": {
                "agi_governor": agi,
                "si_strategy": si,
                "predictive_revenue": pr,
            },
        }

        if self.ask_llm is not None:
            try:
                user = "\n".join(user_context) if user_context else "Provide expert traffic management guidance."
                llm_result = await self.ask_llm(system_prompt, user)
                result["llm_output"] = llm_result
                result["execution_mode"] = "llm"
            except Exception as e:
                result["llm_error"] = str(e)
                result["execution_mode"] = "analysis_only"
        else:
            result["execution_mode"] = "analysis_only"
            result["note"] = (
                "This skill provides traffic management guidance based on its domain expertise. "
                "To execute with full LLM reasoning, wire an ask_llm callable."
            )

        elapsed_ms = int((time.time() - start) * 1000)
        return SkillOutput(
            success=True,
            data=result,
            metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=1 if self.ask_llm else 0),
        )


# ═════════════════════════════════════════════════════════════════════
# TRAFFIC SKILL DEFINITIONS
# ═════════════════════════════════════════════════════════════════════

# ── Budget & Allocation ────────────────────────────────────────────

class TrafficBudgetAllocationSkill(TrafficSkill):
    name = "traffic.budget-allocation"
    version = "1.0.0"
    description = "Allocate traffic budget across channels — ROAS-based distribution, standby seeding, inactive channel deferral"
    tags = ["domain:traffic", "budget", "allocation"]
    traffic_domain = "Budget Allocation — distributing monthly budget across paid and free channels based on revenue attribution and channel maturity"


class TrafficMixOptimizationSkill(TrafficSkill):
    name = "traffic.mix-optimization"
    version = "1.0.0"
    description = "Optimize the traffic channel mix — channel diversification, concentration risk, cost-per-lead balancing, ROAS targets"
    tags = ["domain:traffic", "channels", "optimization"]
    traffic_domain = "Traffic Mix Optimization — balancing paid vs free channels, diversification strategy, concentration risk management, and ROAS targets"


# ── Channel-Specific Skills ────────────────────────────────────────

class TrafficNativeAdsSkill(TrafficSkill):
    name = "traffic.native-ads"
    version = "1.0.0"
    description = "Manage native ad campaigns — campaign seeding, creative optimization, CTR improvement, publisher recruitment"
    tags = ["domain:traffic", "native-ads", "paid"]
    traffic_domain = "Native Ads Network Management — campaign strategy, creative optimization, publisher network expansion, CPM optimization"


class TrafficPPCSkill(TrafficSkill):
    name = "traffic.ppc"
    version = "1.0.0"
    description = "Optimize PPC and pay-per-call campaigns — bid management, call routing, inbound optimization, conversion tracking"
    tags = ["domain:traffic", "ppc", "pay-per-call"]
    traffic_domain = "PPC and Pay-Per-Call Management — bid optimization, call routing strategy, inbound conversion tracking, CPA targets"


class TrafficAffiliateSkill(TrafficSkill):
    name = "traffic.affiliate"
    version = "1.0.0"
    description = "Manage affiliate network — partner recruitment, link distribution, commission optimization, performance tracking"
    tags = ["domain:traffic", "affiliate", "partners"]
    traffic_domain = "Affiliate Network Management — partner recruitment and onboarding, commission structure optimization, link distribution, and performance attribution"


class TrafficSEOSkill(TrafficSkill):
    name = "traffic.seo"
    version = "1.0.0"
    description = "Coordinate SEO traffic channel — keyword tracking, content alignment, backlink strategy, organic conversion optimization"
    tags = ["domain:traffic", "seo", "organic"]
    traffic_domain = "SEO Traffic Coordination — keyword performance tracking, content gap analysis, backlink acquisition strategy, and organic conversion optimization"


class TrafficEmailSMSSkill(TrafficSkill):
    name = "traffic.email-sms"
    version = "1.0.0"
    description = "Optimize email and SMS outreach channel — drip sequence performance, deliverability, strike campaign coordination"
    tags = ["domain:traffic", "email", "sms"]
    traffic_domain = "Email and SMS Outreach Optimization — drip sequence performance analysis, deliverability health, strike campaign coordination, and compliance-aware volume management"


class TrafficContentDistributionSkill(TrafficSkill):
    name = "traffic.content-distribution"
    version = "1.0.0"
    description = "Plan content distribution strategy — social posting, blog syndication, guest post targets, directory submissions"
    tags = ["domain:traffic", "content", "distribution"]
    traffic_domain = "Content Distribution Planning — social media amplification, blog syndication networks, guest post targeting, directory and citation distribution"


class TrafficCommunityEngagementSkill(TrafficSkill):
    name = "traffic.community-engagement"
    version = "1.0.0"
    description = "Plan community engagement strategy — forum participation, Q&A platforms, industry communities, referral programs"
    tags = ["domain:traffic", "community", "engagement"]
    traffic_domain = "Community Engagement Strategy — industry forum participation, Q&A platform presence, referral program design, and community growth tactics"


# ── Reporting & Analytics ──────────────────────────────────────────

class TrafficReportingSkill(TrafficSkill):
    name = "traffic.reporting"
    version = "1.0.0"
    description = "Generate traffic performance reports — channel-by-channel breakdown, budget utilization, trend analysis, actionable recommendations"
    tags = ["domain:traffic", "reporting", "analytics"]
    traffic_domain = "Traffic Performance Reporting — channel-by-channel KPI reporting, budget utilization analysis, week-over-week trend detection, and prioritized action recommendations"


class TrafficChannelActivationSkill(TrafficSkill):
    name = "traffic.channel-activation"
    version = "1.0.0"
    description = "Activate dormant traffic channels — seed campaigns for standby channels, API setup for inactive channels, step-by-step launch plans"
    tags = ["domain:traffic", "channels", "activation"]
    traffic_domain = "Channel Activation Planning — step-by-step launch plans for dormant channels, API credential setup guides, campaign seeding strategy, and first-pipeline buildout"


# ── Search & Social Ads (inactive channels) ─────────────────────────

class TrafficSearchAdsSkill(TrafficSkill):
    name = "traffic.search-ads"
    version = "1.0.0"
    description = "Plan search ad campaigns — Google Ads and Bing Ads setup, keyword targeting, bidding strategy, campaign structure"
    tags = ["domain:traffic", "search-ads", "paid"]
    traffic_domain = "Search Ads Campaign Planning — Google Ads and Bing Ads account setup, keyword research and targeting, bidding strategy, campaign structure, and performance benchmarks"


class TrafficSocialAdsSkill(TrafficSkill):
    name = "traffic.social-ads"
    version = "1.0.0"
    description = "Plan social ad campaigns — Meta, LinkedIn, TikTok ad strategy, audience targeting, creative formats, budget allocation"
    tags = ["domain:traffic", "social-ads", "paid"]
    traffic_domain = "Social Ads Campaign Planning — platform selection (Meta, LinkedIn, TikTok), audience targeting strategy, creative format selection, budget allocation, and ROAS benchmarks"


# ═════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═════════════════════════════════════════════════════════════════════

TRAFFIC_SKILL_CLASSES = [
    # Budget & Allocation
    TrafficBudgetAllocationSkill,
    TrafficMixOptimizationSkill,
    # Channel-Specific
    TrafficNativeAdsSkill,
    TrafficPPCSkill,
    TrafficAffiliateSkill,
    TrafficSEOSkill,
    TrafficEmailSMSSkill,
    TrafficContentDistributionSkill,
    TrafficCommunityEngagementSkill,
    # Reporting & Analytics
    TrafficReportingSkill,
    TrafficChannelActivationSkill,
    # Search & Social Ads
    TrafficSearchAdsSkill,
    TrafficSocialAdsSkill,
]


def register_traffic_skills(registry, ask_llm=None) -> None:
    """Register all traffic skills into a SkillRegistry.

    If ask_llm is provided (async callable(system, user) -> str),
    it is wired as a dependency on every traffic skill so they can
    execute their guidance via LLM.
    """
    for cls in TRAFFIC_SKILL_CLASSES:
        registry.register(cls)

    if ask_llm is not None:
        for cls in TRAFFIC_SKILL_CLASSES:
            try:
                registry.wire_dependency(cls.name, "ask_llm", ask_llm)
            except Exception as e:
                log.warning(f"[traffic.skills] failed to wire ask_llm on {cls.name}: {e}")

    log.info(f"[traffic.skills] registered {len(TRAFFIC_SKILL_CLASSES)} traffic skills"
             f"{' · LLM wired' if ask_llm else ' · analysis-only mode'}")


def get_traffic_skill_names() -> list[str]:
    """Return all traffic skill names for reference."""
    return [cls.name for cls in TRAFFIC_SKILL_CLASSES]
