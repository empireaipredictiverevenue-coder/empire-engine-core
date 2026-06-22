"""
EMPIRE V49 · EMAIL MARKETING SKILLS
=====================================
Concrete skill implementations for the Email Marketing OS. Each skill
provides expert guidance across email strategy, deliverability, compliance,
sequences, copywriting, analytics, and provider integrations.

When executed, the skill returns structured guidance based on input
parameters. With an ask_llm callable wired, it executes the full
email skill via LLM reasoning.
"""

import json
import time
import logging
from typing import Any, Callable, Optional

from skills.base import BaseSkill, SkillInput, SkillOutput, SkillMetrics

log = logging.getLogger("empire.skills.email")


# ── Base class for all email skills ──────────────────────────────


class EmailSkill(BaseSkill):
    """Base class for email marketing skills that provide expert guidance.

    Each subclass represents a specific email discipline. The execute()
    method constructs a structured prompt and returns guidance.
    """

    name = "email.base"  # Abstract base — not registered directly
    email_domain: str = ""  # Email domain identifier
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
        if input.context:
            agi = input.context.get("agi_governor") or {}
            si = input.context.get("si_strategy") or {}
            pr = input.context.get("predictive_revenue") or {}
            parts = []
            if agi.get("strategy"):
                parts.append(f"AGI Strategy: {agi['strategy']}")
            if si.get("best_per_niche"):
                parts.append(f"SI Best Strategies (per niche): {si['best_per_niche']}")
            if pr.get("close_rate"):
                parts.append(f"Current Close Rate: {pr['close_rate']}")
            if pr.get("forecast"):
                totals = pr["forecast"].get("totals", {})
                parts.append(f"Revenue 24h: ${totals.get('revenue_24h', 0)} | MRR: ${totals.get('mrr_projected', 0)}")
            if parts:
                agi_block = "\\n".join(parts)

        system_prompt = (
            f"You are the Empire AI Email Marketing Agent executing skill '{self.name}'.\\n"
            f"{self.description}\\n\\n"
            f"## Email Domain\\n{self.email_domain}\\n\\n"
            f"Apply your email marketing expertise to the user's request below. "
            f"Be thorough and actionable. Provide specific recommendations "
            f"with rationale, alternatives, and edge cases. Consider deliverability, "
            f"compliance, and engagement best practices."
        )

        if agi_block:
            system_prompt += (
                f"\\n\\n## Live System Context\\n{agi_block}\\n"
                f"Use this context to align your recommendations with current "
                f"strategy, SI genome traits, and revenue targets."
            )

        result = {
            "skill": self.name,
            "skill_description": self.description,
            "email_domain": self.email_domain,
            "input_params": input.params,
            "agi_context": {
                "agi_governor": agi,
                "si_strategy": si,
                "predictive_revenue": pr,
            },
        }

        if self.ask_llm is not None:
            try:
                user = "\\n".join(user_context) if user_context else "Provide expert email marketing guidance."
                llm_result = await self.ask_llm(system_prompt, user)
                result["llm_output"] = llm_result
                result["execution_mode"] = "llm"
            except Exception as e:
                result["llm_error"] = str(e)
                result["execution_mode"] = "analysis_only"
        else:
            result["execution_mode"] = "analysis_only"
            result["note"] = (
                "This skill provides email marketing guidance based on its domain expertise. "
                "To execute with full LLM reasoning, wire an ask_llm callable."
            )

        elapsed_ms = int((time.time() - start) * 1000)
        return SkillOutput(
            success=True,
            data=result,
            metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=1 if self.ask_llm else 0),
        )


# ═════════════════════════════════════════════════════════════════════
# EMAIL SKILL DEFINITIONS
# ═════════════════════════════════════════════════════════════════════

# ── Strategy & Planning ───────────────────────────────────────────

class EmailStrategySkill(EmailSkill):
    name = "email.strategy"
    version = "1.0.0"
    description = "Develop email marketing strategy — channel positioning, lifecycle mapping, campaign calendar, KPI framework"
    tags = ["domain:email", "strategy", "planning"]
    email_domain = "Email Marketing Strategy — channel positioning, lifecycle mapping, campaign architecture, and measurement frameworks"


class EmailCalendarSkill(EmailSkill):
    name = "email.calendar"
    version = "1.0.0"
    description = "Design email campaign calendar — cadence planning, seasonal campaigns, trigger-based scheduling"
    tags = ["domain:email", "strategy", "calendar"]
    email_domain = "Email Campaign Calendar — cadence planning, seasonal timing, trigger scheduling, promotional alignment"


# ── Sequence & Campaign Design ────────────────────────────────────

class EmailSequenceSkill(EmailSkill):
    name = "email.sequence"
    version = "1.0.0"
    description = "Design multi-step email sequences — welcome, onboarding, nurturing, re-engagement, post-purchase"
    tags = ["domain:email", "sequences", "campaigns"]
    email_domain = "Email Sequence Design — multi-step flow design, timing, triggers, fallback rules, and success metrics"


class EmailDripSkill(EmailSkill):
    name = "email.drip"
    version = "1.0.0"
    description = "Design drip campaigns — automated behavior-triggered email flows with branching logic"
    tags = ["domain:email", "sequences", "automation"]
    email_domain = "Drip Campaign Design — behavior-triggered flows, branching conditions, timing rules, and conversion optimization"


class EmailNurtureSkill(EmailSkill):
    name = "email.nurture"
    version = "1.0.0"
    description = "Design lead nurture sequences — educational value sequences that build trust and move prospects through the funnel"
    tags = ["domain:email", "sequences", "nurture"]
    email_domain = "Lead Nurture Design — educational sequences, trust building, content mapping, and progression triggers"


class EmailReEngagementSkill(EmailSkill):
    name = "email.re-engagement"
    version = "1.0.0"
    description = "Design re-engagement and win-back sequences — dormant subscriber revival, churn prevention, sunset policies"
    tags = ["domain:email", "sequences", "re-engagement"]
    email_domain = "Re-Engagement Sequence Design — dormant subscriber revival, win-back offers, sunset policies, and list reactivation"


# ── Copy & Creative ──────────────────────────────────────────────

class EmailCopySubjectSkill(EmailSkill):
    name = "email.copy-subject"
    version = "1.0.0"
    description = "Write and optimize email subject lines — preview text, emoji strategy, personalization, A/B variants"
    tags = ["domain:email", "copy", "subject-lines"]
    email_domain = "Email Subject Line Optimization — preview text, emoji strategy, personalization, length optimization, A/B variants"


class EmailCopyBodySkill(EmailSkill):
    name = "email.copy-body"
    version = "1.0.0"
    description = "Write email body copy — persuasive, value-driven content with CTAs that convert"
    tags = ["domain:email", "copy", "body"]
    email_domain = "Email Body Copywriting — persuasive content, value articulation, CTA design, personalization, and scannability"


class EmailCopyCTASkill(EmailSkill):
    name = "email.copy-cta"
    version = "1.0.0"
    description = "Design email CTAs — button copy, placement, design, urgency tactics, click-through optimization"
    tags = ["domain:email", "copy", "cta"]
    email_domain = "Email CTA Design — button copy, placement, visual design, urgency tactics, accessibility, and conversion optimization"


# ── Deliverability & Infrastructure ──────────────────────────────

class EmailDeliverabilitySkill(EmailSkill):
    name = "email.deliverability"
    version = "1.0.0"
    description = "Optimize email deliverability — sender reputation, authentication (SPF/DKIM/DMARC), ISP relationships, blocklist recovery"
    tags = ["domain:email", "deliverability", "infrastructure"]
    email_domain = "Email Deliverability Optimization — authentication, reputation management, blocklist recovery, and ISP best practices"


class EmailAuthenticationSkill(EmailSkill):
    name = "email.authentication"
    version = "1.0.0"
    description = "Configure and audit email authentication — SPF record, DKIM signing, DMARC policy, BIMI, MTA-STS"
    tags = ["domain:email", "deliverability", "authentication"]
    email_domain = "Email Authentication — SPF, DKIM, DMARC, BIMI, MTA-STS configuration and auditing"


class EmailWarmupSkill(EmailSkill):
    name = "email.warmup"
    version = "1.0.0"
    description = "Plan email warmup — gradual volume ramp, engagement targeting, reputation building, seed list management"
    tags = ["domain:email", "deliverability", "warmup"]
    email_domain = "Email Warmup Planning — gradual volume ramp, engagement seeding, reputation building, provider-specific guidance"


class EmailListHygieneSkill(EmailSkill):
    name = "email.list-hygiene"
    version = "1.0.0"
    description = "Manage list hygiene — bounce handling, suppression lists, list decay, re-verification cadence, sunset policies"
    tags = ["domain:email", "deliverability", "list-hygiene"]
    email_domain = "Email List Hygiene — bounce handling, suppression rules, re-verification cadence, engagement-based sunset policies"


# ── Compliance & Legal ───────────────────────────────────────────

class EmailComplianceCANSPAMSkill(EmailSkill):
    name = "email.compliance-can-spam"
    version = "1.0.0"
    description = "CAN-SPAM compliance review — unsubscribe mechanism, physical address, sender identification, subject accuracy"
    tags = ["domain:email", "compliance", "can-spam"]
    email_domain = "CAN-SPAM Compliance — unsubscribe mechanism, physical address, sender identification, subject accuracy, commercial disclosure"


class EmailComplianceGDPRSkill(EmailSkill):
    name = "email.compliance-gdpr"
    version = "1.0.0"
    description = "GDPR compliance for email marketing — consent records, data processing, right to erasure, privacy policy"
    tags = ["domain:email", "compliance", "gdpr"]
    email_domain = "GDPR Compliance — consent records, data processing, right to erasure, privacy policy linkage, DPA requirements"


class EmailComplianceCASLSkill(EmailSkill):
    name = "email.compliance-casl"
    version = "1.0.0"
    description = "CASL compliance for Canadian email — express consent verification, implied consent rules, sender identification"
    tags = ["domain:email", "compliance", "casl"]
    email_domain = "CASL Compliance — express consent, implied consent rules, sender identification, unsubscribe mechanism, record-keeping"


# ── Analytics & Optimization ──────────────────────────────────────

class EmailAnalyticsSkill(EmailSkill):
    name = "email.analytics"
    version = "1.0.0"
    description = "Design email analytics framework — KPI selection, dashboard design, attribution modeling, cohort analysis"
    tags = ["domain:email", "analytics", "reporting"]
    email_domain = "Email Analytics — KPI frameworks, dashboard design, attribution modeling, cohort analysis, and reporting cadence"


class EmailABTestingSkill(EmailSkill):
    name = "email.ab-testing"
    version = "1.0.0"
    description = "Design email A/B tests — test hypothesis, variant design, sample size calculation, statistical significance"
    tags = ["domain:email", "analytics", "testing"]
    email_domain = "Email A/B Testing — hypothesis design, variant creation, sample size calculation, significance analysis, and iteration"


class EmailOptimizationSkill(EmailSkill):
    name = "email.optimization"
    version = "1.0.0"
    description = "Optimize email performance — send time optimization, frequency tuning, engagement analysis, revenue per email"
    tags = ["domain:email", "analytics", "optimization"]
    email_domain = "Email Performance Optimization — send time tuning, frequency optimization, engagement analysis, and revenue improvement"


# ── Technical & Infrastructure ────────────────────────────────────

class EmailAPISkill(EmailSkill):
    name = "email.api"
    version = "1.0.0"
    description = "Design email API integrations — Resend API, webhook handling, bounce/complaint processing, event tracking"
    tags = ["domain:email", "technical", "api"]
    email_domain = "Email API Integration — provider API wiring, webhook handling, event tracking, error handling, rate limiting"


class EmailTemplateSkill(EmailSkill):
    name = "email.template"
    version = "1.0.0"
    description = "Design email HTML templates — responsive design, email client compatibility, dark mode, accessibility, tracking"
    tags = ["domain:email", "technical", "templates"]
    email_domain = "Email Template Design — responsive HTML, client compatibility, dark mode styling, accessibility markup, tracking integration"


class EmailPersonalizationSkill(EmailSkill):
    name = "email.personalization"
    version = "1.0.0"
    description = "Design email personalization strategy — dynamic content, merge tags, behavioral triggers, predictive personalization"
    tags = ["domain:email", "technical", "personalization"]
    email_domain = "Email Personalization — dynamic content, merge fields, behavioral triggers, predictive personalization, fallback defaults"


class EmailInboundSkill(EmailSkill):
    name = "email.inbound"
    version = "1.0.0"
    description = "Design inbound email handling — reply management, auto-responders, ticket creation, sentiment routing"
    tags = ["domain:email", "technical", "inbound"]
    email_domain = "Inbound Email Handling — reply management, auto-responders, classification, routing rules, escalation paths"


# ── Provider & Platform ──────────────────────────────────────────

class EmailProviderResendSkill(EmailSkill):
    name = "email.provider-resend"
    version = "1.0.0"
    description = "Resend-specific configuration — API key management, domain setup, sending quotas, webhook wiring, bounce handling"
    tags = ["domain:email", "provider", "resend"]
    email_domain = "Resend Provider Configuration — domain setup, API integration, quota management, webhook handling, template setup"


class EmailProviderListmonkSkill(EmailSkill):
    name = "email.provider-listmonk"
    version = "1.0.0"
    description = "ListMonk-specific configuration — self-hosted setup, campaign management, subscriber management, template system"
    tags = ["domain:email", "provider", "listmonk"]
    email_domain = "ListMonk Configuration — self-hosted email platform setup, campaign management, subscriber management, template customization"


# ═════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═════════════════════════════════════════════════════════════════════

EMAIL_SKILL_CLASSES = [
    # Strategy & Planning
    EmailStrategySkill,
    EmailCalendarSkill,
    # Sequence & Campaign
    EmailSequenceSkill,
    EmailDripSkill,
    EmailNurtureSkill,
    EmailReEngagementSkill,
    # Copy & Creative
    EmailCopySubjectSkill,
    EmailCopyBodySkill,
    EmailCopyCTASkill,
    # Deliverability & Infrastructure
    EmailDeliverabilitySkill,
    EmailAuthenticationSkill,
    EmailWarmupSkill,
    EmailListHygieneSkill,
    # Compliance & Legal
    EmailComplianceCANSPAMSkill,
    EmailComplianceGDPRSkill,
    EmailComplianceCASLSkill,
    # Analytics & Optimization
    EmailAnalyticsSkill,
    EmailABTestingSkill,
    EmailOptimizationSkill,
    # Technical & Infrastructure
    EmailAPISkill,
    EmailTemplateSkill,
    EmailPersonalizationSkill,
    EmailInboundSkill,
    # Provider & Platform
    EmailProviderResendSkill,
    EmailProviderListmonkSkill,
]


def register_email_skills(registry, ask_llm=None) -> None:
    """Register all email skills into a SkillRegistry.

    If ask_llm is provided (async callable(system, user) -> str),
    it is wired as a dependency on every email skill so they can
    execute their guidance via LLM.
    """
    for cls in EMAIL_SKILL_CLASSES:
        registry.register(cls)

    if ask_llm is not None:
        for cls in EMAIL_SKILL_CLASSES:
            try:
                registry.wire_dependency(cls.name, "ask_llm", ask_llm)
            except Exception as e:
                log.warning(f"[email.skills] failed to wire ask_llm on {cls.name}: {e}")

    log.info(f"[email.skills] registered {len(EMAIL_SKILL_CLASSES)} email skills"
             f"{' · LLM wired' if ask_llm else ' · analysis-only mode'}")


def get_email_skill_names() -> list[str]:
    """Return all email skill names for reference."""
    return [cls.name for cls in EMAIL_SKILL_CLASSES]
