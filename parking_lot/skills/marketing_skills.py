"""
EMPIRE V49 · MARKETING SKILLS
==============================
Concrete skill implementations mapped from the marketing skills repo
(coreyhaines31/marketingskills). Each skill wraps a SKILL.md prompt
template and executes via LLM or analysis mode.

Skills directory: skills/marketingskills/skills/{name}/SKILL.md

When executed, the skill reads the SKILL.md instructions, builds a
prompt from the user's params, and returns guidance/recommendations.
"""

import os
import json
import time
import logging
from typing import Any, Callable, Optional

from skills.base import BaseSkill, SkillInput, SkillOutput, SkillMetrics

log = logging.getLogger("empire.skills.marketing")

# ── Path to the cloned marketing skills repo ─────────────────────────
_MARKETING_SKILLS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skills",
    "marketingskills",
    "skills",
)


# ── Helper: load a SKILL.md file ─────────────────────────────────────


def _load_skill_md(name: str) -> str:
    """Load the SKILL.md content for a marketing skill.

    Returns the full file content (frontmatter + body) or an error message
    if the file is missing.
    """
    path = os.path.join(_MARKETING_SKILLS_DIR, name, "SKILL.md")
    if not os.path.exists(path):
        return f"SKILL.md not found at {path}"
    try:
        with open(path, "r") as f:
            return f.read(15000)
    except Exception as e:
        return f"Error reading SKILL.md: {e}"


# ── Base class for all marketing skills ──────────────────────────────


class MarketingSkill(BaseSkill):
    """Base class for marketing skills that load SKILL.md prompt templates.

    Each subclass maps to a SKILL.md file in the marketing skills repo.
    The execute() method loads the SKILL.md, constructs a prompt from
    the instructions + user params, and returns the guidance.
    """

    name = "marketing.base"  # Abstract base — not registered directly
    skill_name: str = ""  # Directory name within skills/marketingskills/skills/
    timeout_seconds = 60.0
    max_retries = 2

    def __init__(self):
        super().__init__()
        self.ask_llm: Optional[Callable[[str, str], Any]] = None

    async def validate(self, input: SkillInput) -> bool:
        return True

    async def execute(self, input: SkillInput) -> SkillOutput:
        start = time.time()

        # Load the SKILL.md content
        md_content = _load_skill_md(self.skill_name)

        # Build output from the skill instructions + user params
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
                parts.append(
                    f"Revenue 24h: ${totals.get('revenue_24h', 0)} | "
                    f"MRR: ${totals.get('mrr_projected', 0)}"
                )
            if parts:
                agi_block = "\n".join(parts)

        result = {
            "skill": self.name,
            "skill_description": self.description,
            "skill_file": f"skills/marketingskills/skills/{self.skill_name}/SKILL.md",
            "instructions": md_content[:3000],  # Truncated for response size
            "input_params": input.params,
            "agi_context": {
                "agi_governor": agi,
                "si_strategy": si,
                "predictive_revenue": pr,
            },
            "note": (
                "This skill provides expert guidance based on the SKILL.md prompt template. "
                "To execute the full skill (with LLM), wire an ask_llm callable. "
                "Without LLM, the skill returns the instructions for manual execution."
            ),
        }

        # If LLM is available, execute the full skill
        if self.ask_llm is not None:
            try:
                system = (
                    f"You are executing marketing skill '{self.name}'.\n"
                    f"{self.description}\n\n"
                    f"## Skill Instructions\n{md_content}\n\n"
                )
                if agi_block:
                    system += (
                        f"## Live System Context\n{agi_block}\n\n"
                        f"Use this context to align your recommendations with current "
                        f"strategy (AGI Governor), SI genome traits, and revenue targets. "
                        f"For example, if AGI strategy is 'cost-optimization', "
                        f"prioritize low-cost channels.\n\n"
                    )
                system += (
                    f"Apply these instructions to the user's request below. "
                    f"Be thorough and actionable."
                )
                user = "\n".join(user_context) if user_context else "Execute the skill's guidance."
                llm_result = await self.ask_llm(system, user)
                result["llm_output"] = llm_result
                result["execution_mode"] = "llm"
            except Exception as e:
                result["llm_error"] = str(e)
                result["execution_mode"] = "analysis_only"

        elapsed_ms = int((time.time() - start) * 1000)
        return SkillOutput(
            success=True,
            data=result,
            metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=1 if self.ask_llm else 0),
        )


# ═════════════════════════════════════════════════════════════════════
# MARKETING SKILL DEFINITIONS
# ═════════════════════════════════════════════════════════════════════
#
# Each skill maps to skills/marketingskills/skills/{name}/SKILL.md
# ──

# 1. Product Marketing
class ProductMarketingSkill(MarketingSkill):
    name = "marketing.product"
    version = "2.0.0"
    description = "Product marketing strategy — positioning, messaging, pricing, GTM, competitive differentiation"
    tags = ["domain:marketing", "product", "strategy"]
    skill_name = "product-marketing"

# 2. Email Sequence Design
class EmailsSkill(MarketingSkill):
    name = "marketing.emails"
    version = "2.0.0"
    description = "Email sequence design — drip campaigns, welcome series, lifecycle emails, behavior-triggered flows"
    tags = ["domain:marketing", "email", "sequence"]
    skill_name = "emails"

# 3. Referral Programs
class ReferralsSkill(MarketingSkill):
    name = "marketing.referrals"
    version = "2.0.0"
    description = "Referral program design — customer referrals, affiliate schemes, ambassador programs, viral loops"
    tags = ["domain:marketing", "referrals", "growth"]
    skill_name = "referrals"

# 4. Paid Advertising
class AdsSkill(MarketingSkill):
    name = "marketing.ads"
    version = "2.0.1"
    description = "Paid advertising campaigns — strategy, bidding, platform selection, optimization"
    tags = ["domain:marketing", "ads", "paid-media"]
    skill_name = "ads"

# 5. Copywriting
class CopywritingSkill(MarketingSkill):
    name = "marketing.copywriting"
    version = "2.0.0"
    description = "Copywriting for landing pages, emails, ads, social, and web copy"
    tags = ["domain:marketing", "copy", "content"]
    skill_name = "copywriting"

# 6. A/B Testing
class ABTestingSkill(MarketingSkill):
    name = "marketing.ab-testing"
    version = "2.0.0"
    description = "A/B testing design — hypothesis formulation, test design, statistical significance, analysis"
    tags = ["domain:marketing", "testing", "cro"]
    skill_name = "ab-testing"

# 7. Ad Creative
class AdCreativeSkill(MarketingSkill):
    name = "marketing.ad-creative"
    version = "1.0.0"
    description = "Ad creative strategy — visual concepts, copy angles, creative testing frameworks"
    tags = ["domain:marketing", "ads", "creative"]
    skill_name = "ad-creative"

# 8. Onboarding
class OnboardingSkill(MarketingSkill):
    name = "marketing.onboarding"
    version = "1.0.0"
    description = "User onboarding design — activation flows, time-to-value, retention mechanics"
    tags = ["domain:marketing", "onboarding", "product"]
    skill_name = "onboarding"

# 9. Signup Optimization
class SignupSkill(MarketingSkill):
    name = "marketing.signup"
    version = "1.0.0"
    description = "Signup flow optimization — form design, friction reduction, conversion rate"
    tags = ["domain:marketing", "cro", "signup"]
    skill_name = "signup"

# 10. Offers & Promotions
class OffersSkill(MarketingSkill):
    name = "marketing.offers"
    version = "1.0.0"
    description = "Offer strategy — discount design, bundling, pricing promotions, urgency tactics"
    tags = ["domain:marketing", "offers", "pricing"]
    skill_name = "offers"

# 11. Lead Magnets
class LeadMagnetsSkill(MarketingSkill):
    name = "marketing.lead-magnets"
    version = "1.0.0"
    description = "Lead magnet design — content upgrades, gated assets, value exchange optimization"
    tags = ["domain:marketing", "lead-gen", "content"]
    skill_name = "lead-magnets"

# 12. Popups & Overlays
class PopupsSkill(MarketingSkill):
    name = "marketing.popups"
    version = "1.0.0"
    description = "Popup and overlay strategy — timing, targeting, design, conversion optimization"
    tags = ["domain:marketing", "cro", "popups"]
    skill_name = "popups"

# 13. Paywalls
class PaywallsSkill(MarketingSkill):
    name = "marketing.paywalls"
    version = "1.0.0"
    description = "Paywall strategy — metering, hard walls, dynamic paywalls, subscriber conversion"
    tags = ["domain:marketing", "monetization", "paywalls"]
    skill_name = "paywalls"

# 14. Launch Strategy
class LaunchSkill(MarketingSkill):
    name = "marketing.launch"
    version = "1.0.0"
    description = "Product launch strategy — pre-launch, launch day, post-launch campaigns and timing"
    tags = ["domain:marketing", "launch", "gtm"]
    skill_name = "launch"

# 15. Customer Research
class CustomerResearchSkill(MarketingSkill):
    name = "marketing.customer-research"
    version = "1.0.0"
    description = "Customer research — surveys, interviews, persona development, jobs-to-be-done"
    tags = ["domain:marketing", "research", "customers"]
    skill_name = "customer-research"

# 16. Marketing Ideas & Brainstorming
class MarketingIdeasSkill(MarketingSkill):
    name = "marketing.ideas"
    version = "1.0.0"
    description = "Marketing idea generation — channel brainstorming, creative concepts, growth experiments"
    tags = ["domain:marketing", "ideas", "growth"]
    skill_name = "marketing-ideas"

# 17. Public Relations
class PublicRelationsSkill(MarketingSkill):
    name = "marketing.pr"
    version = "1.0.0"
    description = "Public relations — press outreach, media kits, announcement strategy, crisis comms"
    tags = ["domain:marketing", "pr", "communications"]
    skill_name = "public-relations"

# 18. Co-Marketing
class CoMarketingSkill(MarketingSkill):
    name = "marketing.co-marketing"
    version = "1.0.0"
    description = "Co-marketing partnerships — partner selection, joint campaigns, co-branded content"
    tags = ["domain:marketing", "partnerships", "growth"]
    skill_name = "co-marketing"

# 19. Community Marketing
class CommunityMarketingSkill(MarketingSkill):
    name = "marketing.community"
    version = "1.0.0"
    description = "Community marketing — building, engaging, and monetizing online communities"
    tags = ["domain:marketing", "community", "engagement"]
    skill_name = "community-marketing"

# 20. Video Marketing
class VideoSkill(MarketingSkill):
    name = "marketing.video"
    version = "1.0.0"
    description = "Video marketing strategy — content types, distribution, optimization, platforms"
    tags = ["domain:marketing", "video", "content"]
    skill_name = "video"

# 21. Image & Visual Content
class ImageSkill(MarketingSkill):
    name = "marketing.image"
    version = "1.0.0"
    description = "Visual content strategy — infographics, data visualization, branded imagery"
    tags = ["domain:marketing", "visual", "content"]
    skill_name = "image"

# 22. Copy Editing
class CopyEditingSkill(MarketingSkill):
    name = "marketing.copy-editing"
    version = "1.0.0"
    description = "Copy editing — clarity, concision, tone, grammar, brand voice consistency"
    tags = ["domain:marketing", "copy", "editing"]
    skill_name = "copy-editing"

# 23. SEO — Programmatic
class ProgrammaticSEOSkill(MarketingSkill):
    name = "marketing.programmatic-seo"
    version = "1.0.0"
    description = "Programmatic SEO — template-based landing pages, structured data, scalable content"
    tags = ["domain:marketing", "seo", "programmatic"]
    skill_name = "programmatic-seo"

# 24. SEO — Schema Markup
class SchemaSkill(MarketingSkill):
    name = "marketing.schema"
    version = "1.0.0"
    description = "Schema markup strategy — structured data, rich snippets, knowledge graph"
    tags = ["domain:marketing", "seo", "technical"]
    skill_name = "schema"

# 25. AI SEO
class AISeOSkill(MarketingSkill):
    name = "marketing.ai-seo"
    version = "1.0.0"
    description = "AI-powered SEO — LLM content optimization, AI search readiness, generative engine optimization"
    tags = ["domain:marketing", "seo", "ai"]
    skill_name = "ai-seo"

# 26. App Store Optimization (ASO)
class ASOSkill(MarketingSkill):
    name = "marketing.aso"
    version = "1.0.0"
    description = "App Store Optimization — keyword strategy, conversion rate, creative optimization"
    tags = ["domain:marketing", "aso", "mobile"]
    skill_name = "aso"

# 27. Prospecting
class ProspectingSkill(MarketingSkill):
    name = "marketing.prospecting"
    version = "1.0.0"
    description = "B2B prospecting — ICP definition, lead sourcing, enrichment, sequencing"
    tags = ["domain:marketing", "sales", "prospecting"]
    skill_name = "prospecting"

# 28. RevOps
class RevOpsSkill(MarketingSkill):
    name = "marketing.revops"
    version = "1.0.0"
    description = "Revenue operations — funnel metrics, attribution, pipeline management, tooling stack"
    tags = ["domain:marketing", "operations", "revenue"]
    skill_name = "revops"

# 29. Free Tools Strategy
class FreeToolsSkill(MarketingSkill):
    name = "marketing.free-tools"
    version = "1.0.0"
    description = "Free tools as marketing — interactive tools, calculators, generators for lead gen"
    tags = ["domain:marketing", "lead-gen", "tools"]
    skill_name = "free-tools"

# 30. Directory Submissions
class DirectorySubmissionsSkill(MarketingSkill):
    name = "marketing.directory-submissions"
    version = "1.0.0"
    description = "Directory submission strategy — citation building, local SEO, niche directories"
    tags = ["domain:marketing", "seo", "local"]
    skill_name = "directory-submissions"

# 31. Analytics
class AnalyticsSkill(MarketingSkill):
    name = "marketing.analytics"
    version = "1.0.0"
    description = "Marketing analytics — metrics frameworks, dashboard design, attribution, KPI tracking"
    tags = ["domain:marketing", "analytics", "data"]
    skill_name = "analytics"

# 32. Churn Prevention
class ChurnPreventionSkill(MarketingSkill):
    name = "marketing.churn-prevention"
    version = "1.0.0"
    description = "Churn prevention — retention strategies, win-back campaigns, at-risk detection"
    tags = ["domain:marketing", "retention", "churn"]
    skill_name = "churn-prevention"

# 33. Cold Email
class ColdEmailSkill(MarketingSkill):
    name = "marketing.cold-email"
    version = "1.0.0"
    description = "Cold email outreach — copy templates, sequencing, deliverability, personalization"
    tags = ["domain:marketing", "email", "outreach"]
    skill_name = "cold-email"

# 34. Competitor Profiling
class CompetitorProfilingSkill(MarketingSkill):
    name = "marketing.competitor-profiling"
    version = "1.0.0"
    description = "Competitor profiling — intelligence gathering, positioning analysis, SWOT"
    tags = ["domain:marketing", "competitors", "research"]
    skill_name = "competitor-profiling"

# 35. Competitors (head-to-head analysis)
class CompetitorsSkill(MarketingSkill):
    name = "marketing.competitors"
    version = "1.0.0"
    description = "Competitive analysis — feature comparison, pricing parity, differentiation"
    tags = ["domain:marketing", "competitors", "strategy"]
    skill_name = "competitors"

# 36. Content Strategy
class ContentStrategySkill(MarketingSkill):
    name = "marketing.content-strategy"
    version = "1.0.0"
    description = "Content strategy — editorial planning, topic clusters, content lifecycle"
    tags = ["domain:marketing", "content", "strategy"]
    skill_name = "content-strategy"

# 37. Conversion Rate Optimization (CRO)
class CROSkill(MarketingSkill):
    name = "marketing.cro"
    version = "1.0.0"
    description = "Conversion rate optimization — funnel analysis, UX testing, landing page optimization"
    tags = ["domain:marketing", "cro", "optimization"]
    skill_name = "cro"

# 38. Marketing Plan
class MarketingPlanSkill(MarketingSkill):
    name = "marketing.marketing-plan"
    version = "1.0.0"
    description = "Marketing plan creation — channel mix, budget allocation, quarterly roadmaps"
    tags = ["domain:marketing", "strategy", "planning"]
    skill_name = "marketing-plan"

# 39. Marketing Psychology
class MarketingPsychologySkill(MarketingSkill):
    name = "marketing.marketing-psychology"
    version = "1.0.0"
    description = "Marketing psychology — persuasion triggers, cognitive biases, behavioral economics"
    tags = ["domain:marketing", "psychology", "persuasion"]
    skill_name = "marketing-psychology"

# 40. Pricing Strategy
class PricingSkill(MarketingSkill):
    name = "marketing.pricing"
    version = "1.0.0"
    description = "Pricing strategy — value-based pricing, tiering, packaging, discount psychology"
    tags = ["domain:marketing", "pricing", "monetization"]
    skill_name = "pricing"

# 41. Sales Enablement
class SalesEnablementSkill(MarketingSkill):
    name = "marketing.sales-enablement"
    version = "1.0.0"
    description = "Sales enablement — battle cards, collateral, objection handling, playbooks"
    tags = ["domain:marketing", "sales", "enablement"]
    skill_name = "sales-enablement"

# 42. SEO Audit
class SEOAuditSkill(MarketingSkill):
    name = "marketing.seo-audit"
    version = "1.0.0"
    description = "SEO audit — technical SEO review, content gap analysis, competitor benchmarking"
    tags = ["domain:marketing", "seo", "audit"]
    skill_name = "seo-audit"

# 43. Site Architecture
class SiteArchitectureSkill(MarketingSkill):
    name = "marketing.site-architecture"
    version = "1.0.0"
    description = "Site architecture for SEO — information architecture, internal linking, URL structure"
    tags = ["domain:marketing", "seo", "technical"]
    skill_name = "site-architecture"

# 44. SMS Marketing
class SMSSkill(MarketingSkill):
    name = "marketing.sms"
    version = "1.0.0"
    description = "SMS marketing — campaign strategy, compliance (TCPA), automation, segmentation"
    tags = ["domain:marketing", "sms", "messaging"]
    skill_name = "sms"

# 45. Social Media
class SocialSkill(MarketingSkill):
    name = "marketing.social"
    version = "1.0.0"
    description = "Social media marketing — platform strategy, content calendar, community management"
    tags = ["domain:marketing", "social", "content"]
    skill_name = "social"


# ═════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═════════════════════════════════════════════════════════════════════

MARKETING_SKILL_CLASSES = [
    ProductMarketingSkill,
    EmailsSkill,
    ReferralsSkill,
    AdsSkill,
    CopywritingSkill,
    ABTestingSkill,
    AdCreativeSkill,
    OnboardingSkill,
    SignupSkill,
    OffersSkill,
    LeadMagnetsSkill,
    PopupsSkill,
    PaywallsSkill,
    LaunchSkill,
    CustomerResearchSkill,
    MarketingIdeasSkill,
    PublicRelationsSkill,
    CoMarketingSkill,
    CommunityMarketingSkill,
    VideoSkill,
    ImageSkill,
    CopyEditingSkill,
    ProgrammaticSEOSkill,
    SchemaSkill,
    AISeOSkill,
    ASOSkill,
    ProspectingSkill,
    RevOpsSkill,
    FreeToolsSkill,
    DirectorySubmissionsSkill,
    AnalyticsSkill,
    ChurnPreventionSkill,
    ColdEmailSkill,
    CompetitorProfilingSkill,
    CompetitorsSkill,
    ContentStrategySkill,
    CROSkill,
    MarketingPlanSkill,
    MarketingPsychologySkill,
    PricingSkill,
    SalesEnablementSkill,
    SEOAuditSkill,
    SiteArchitectureSkill,
    SMSSkill,
    SocialSkill,
]


def register_marketing_skills(registry, ask_llm=None) -> None:
    """Register all marketing skills into a SkillRegistry.

    If ask_llm is provided (async callable(system, user) -> str),
    it is wired as a dependency on every marketing skill so they
    can execute their SKILL.md instructions via LLM.
    """
    for cls in MARKETING_SKILL_CLASSES:
        registry.register(cls)

    # Wire ask_llm on all marketing skills if provided
    if ask_llm is not None:
        for cls in MARKETING_SKILL_CLASSES:
            try:
                registry.wire_dependency(cls.name, "ask_llm", ask_llm)
            except Exception as e:
                log.warning(f"[marketing.skills] failed to wire ask_llm on {cls.name}: {e}")

    log.info(f"[marketing.skills] registered {len(MARKETING_SKILL_CLASSES)} marketing skills"
             f"{' · LLM wired' if ask_llm else ' · analysis-only mode'}")


def get_marketing_skill_names() -> list[str]:
    """Return all marketing skill names for reference."""
    return [cls.name for cls in MARKETING_SKILL_CLASSES]
