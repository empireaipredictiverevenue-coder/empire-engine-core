"""
EMPIRE V49 · DESIGN SKILLS
============================
Concrete skill implementations for the Design OS. Each skill provides
expert guidance and recommendations across UI, UX, visual, motion,
accessibility, and design ops disciplines.

When executed, the skill returns structured guidance based on input
parameters. With an ask_llm callable wired, it executes the full
design skill via LLM reasoning.
"""

import os
import json
import time
import logging
from typing import Any, Callable, Optional

from skills.base import BaseSkill, SkillInput, SkillOutput, SkillMetrics

log = logging.getLogger("empire.skills.design")


# ── Base class for all design skills ──────────────────────────────


class DesignSkill(BaseSkill):
    """Base class for design skills that provide expert guidance.

    Each subclass represents a specific design discipline. The execute()
    method constructs a structured prompt from the instructions + user
    params and returns guidance. With ask_llm wired, it executes via LLM.
    """

    name = "design.base"  # Abstract base — not registered directly
    design_domain: str = ""  # Design domain identifier
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
            f"You are the Empire AI Design Agent executing skill '{self.name}'.\n"
            f"{self.description}\n\n"
            f"## Design Domain\n{self.design_domain}\n\n"
            f"Apply your design expertise to the user's request below. "
            f"Be thorough and actionable. Provide specific recommendations "
            f"with rationale, alternatives, and edge cases."
        )

        if agi_block:
            system_prompt += (
                f"\n\n## Live System Context\n{agi_block}\n"
                f"Use this context to align your recommendations with current "
                f"strategy (AGI Governor), SI genome traits, and revenue targets. "
                f"For example, if AGI strategy is 'cost-optimization', "
                f"prioritize minimal-effort designs."
            )

        result = {
            "skill": self.name,
            "skill_description": self.description,
            "design_domain": self.design_domain,
            "input_params": input.params,
            "agi_context": {
                "agi_governor": agi,
                "si_strategy": si,
                "predictive_revenue": pr,
            },
        }

        if self.ask_llm is not None:
            try:
                user = "\n".join(user_context) if user_context else "Provide expert design guidance."
                llm_result = await self.ask_llm(system_prompt, user)
                result["llm_output"] = llm_result
                result["execution_mode"] = "llm"
            except Exception as e:
                result["llm_error"] = str(e)
                result["execution_mode"] = "analysis_only"
        else:
            result["execution_mode"] = "analysis_only"
            result["note"] = (
                "This skill provides design guidance based on its domain expertise. "
                "To execute with full LLM reasoning, wire an ask_llm callable."
            )

        elapsed_ms = int((time.time() - start) * 1000)
        return SkillOutput(
            success=True,
            data=result,
            metrics=SkillMetrics(duration_ms=elapsed_ms, api_calls=1 if self.ask_llm else 0),
        )


# ═════════════════════════════════════════════════════════════════════
# DESIGN SKILL DEFINITIONS
# ═════════════════════════════════════════════════════════════════════

# ── UI Design ─────────────────────────────────────────────────────

class UIComponentSkill(DesignSkill):
    name = "design.ui-component"
    version = "1.0.0"
    description = "Design individual UI components — buttons, forms, cards, modals, tables, navigation elements"
    tags = ["domain:design", "ui", "components"]
    design_domain = "UI Component Design — designing reusable interface elements with states, responsive behavior, and accessibility"


class UILayoutSkill(DesignSkill):
    name = "design.ui-layout"
    version = "1.0.0"
    description = "Design page and screen layouts — grid systems, responsive breakpoints, content hierarchy, whitespace"
    tags = ["domain:design", "ui", "layout"]
    design_domain = "UI Layout Design — grid systems, responsive breakpoints, content hierarchy, and spacing"


class UIScreenSkill(DesignSkill):
    name = "design.ui-screen"
    version = "1.0.0"
    description = "Design full screens and views — composition, visual hierarchy, information density"
    tags = ["domain:design", "ui", "screens"]
    design_domain = "UI Screen Design — full screen composition, visual hierarchy, focal points, and information density"


# ── UX Design ─────────────────────────────────────────────────────

class UXFlowSkill(DesignSkill):
    name = "design.ux-flow"
    version = "1.0.0"
    description = "Design user flows and task journeys — entry points, decision trees, error states, completion paths"
    tags = ["domain:design", "ux", "flows"]
    design_domain = "UX Flow Design — task journeys, decision trees, error recovery, and completion paths"


class UXWireframeSkill(DesignSkill):
    name = "design.ux-wireframe"
    version = "1.0.0"
    description = "Create wireframes and low-fidelity prototypes — content structure, functional layout, interaction zones"
    tags = ["domain:design", "ux", "wireframes"]
    design_domain = "UX Wireframing — low-fidelity content structure, functional layout, and interaction zones"


class UXPrototypeSkill(DesignSkill):
    name = "design.ux-prototype"
    version = "1.0.0"
    description = "Design interactive prototypes — click-through flows, state transitions, micro-interactions, feedback"
    tags = ["domain:design", "ux", "prototypes"]
    design_domain = "UX Prototyping — interactive prototypes with state transitions, micro-interactions, and feedback systems"


class UXResearchSkill(DesignSkill):
    name = "design.ux-research"
    version = "1.0.0"
    description = "Plan and conduct UX research — usability testing, user interviews, preference tests, analytics review"
    tags = ["domain:design", "ux", "research"]
    design_domain = "UX Research — usability testing, user interviews, preference tests, and analytics-driven insights"


# ── Visual & Brand Design ──────────────────────────────────────────

class VisualBrandSkill(DesignSkill):
    name = "design.visual-brand"
    version = "1.0.0"
    description = "Develop and extend brand identity — color palettes, typography systems, logo usage, brand voice visualization"
    tags = ["domain:design", "visual", "brand"]
    design_domain = "Brand Identity Design — color systems, typography, logo usage, and brand expression"


class VisualColorSkill(DesignSkill):
    name = "design.visual-color"
    version = "1.0.0"
    description = "Design color systems — primary, secondary, neutral, semantic palettes, contrast ratios, accessible combinations"
    tags = ["domain:design", "visual", "color"]
    design_domain = "Color System Design — palette generation, semantic color mapping, accessible contrast ratios, dark mode"


class VisualTypographySkill(DesignSkill):
    name = "design.visual-typography"
    version = "1.0.0"
    description = "Design typography systems — typeface selection, scale, hierarchy, line-height, responsive type"
    tags = ["domain:design", "visual", "typography"]
    design_domain = "Typography System Design — typeface selection, modular scale, hierarchy, responsive font sizing"


class VisualIconographySkill(DesignSkill):
    name = "design.visual-iconography"
    version = "1.0.0"
    description = "Design icon systems — icon style, grid, sizing, semantic meaning, accessibility"
    tags = ["domain:design", "visual", "icons"]
    design_domain = "Icon System Design — icon style guides, grid systems, semantic meaning, accessible labeling"


class VisualDataVizSkill(DesignSkill):
    name = "design.visual-data-viz"
    version = "1.0.0"
    description = "Design data visualizations — chart types, color encoding, labeling, accessibility, responsive layout"
    tags = ["domain:design", "visual", "data-viz"]
    design_domain = "Data Visualization Design — chart selection, color encoding, labeling, accessibility for complex data"


# ── Design Systems ────────────────────────────────────────────────

class SystemTokensSkill(DesignSkill):
    name = "design.system-tokens"
    version = "1.0.0"
    description = "Define design token systems — color, typography, spacing, shadow, motion tokens with naming conventions"
    tags = ["domain:design", "systems", "tokens"]
    design_domain = "Design Token Systems — naming conventions, value definitions, platform mappings, and documentation"


class SystemComponentLibrarySkill(DesignSkill):
    name = "design.system-component-library"
    version = "1.0.0"
    description = "Design component library architecture — component hierarchy, composition patterns, variant management"
    tags = ["domain:design", "systems", "component-library"]
    design_domain = "Component Library Architecture — hierarchy, composition, variant management, and API patterns"


class SystemDocumentationSkill(DesignSkill):
    name = "design.system-documentation"
    version = "1.0.0"
    description = "Create design system documentation — usage guidelines, component specs, code examples, contribution process"
    tags = ["domain:design", "systems", "documentation"]
    design_domain = "Design System Documentation — usage guidelines, component specs, code integration, and contribution workflows"


# ── Interaction & Motion ──────────────────────────────────────────

class MotionMicrointeractionsSkill(DesignSkill):
    name = "design.motion-microinteractions"
    version = "1.0.0"
    description = "Design micro-interactions — button feedback, hover states, form validation, notification animations"
    tags = ["domain:design", "motion", "microinteractions"]
    design_domain = "Micro-interaction Design — feedback animations, state transitions, timing, and accessibility considerations"


class MotionTransitionsSkill(DesignSkill):
    name = "design.motion-transitions"
    version = "1.0.0"
    description = "Design screen and element transitions — page transitions, modal entrances, list reordering, loading sequences"
    tags = ["domain:design", "motion", "transitions"]
    design_domain = "Transition Design — screen changes, element entrances/exits, shared element animations, and spatial continuity"


class MotionLoadingSkill(DesignSkill):
    name = "design.motion-loading"
    version = "1.0.0"
    description = "Design loading and progress states — skeleton screens, progress indicators, optimistic UI, delayed feedback"
    tags = ["domain:design", "motion", "loading"]
    design_domain = "Loading State Design — skeleton screens, progress patterns, optimistic UI, and graceful handling of delays"


# ── Accessibility ──────────────────────────────────────────────────

class A11yColorSkill(DesignSkill):
    name = "design.a11y-color"
    version = "1.0.0"
    description = "Audit and improve color accessibility — contrast ratios, color blindness considerations, semantic color usage"
    tags = ["domain:design", "a11y", "color"]
    design_domain = "Color Accessibility — WCAG contrast compliance, color blindness simulation, semantic color alternatives"


class A11yInteractionSkill(DesignSkill):
    name = "design.a11y-interaction"
    version = "1.0.0"
    description = "Design accessible interactions — keyboard navigation, focus management, screen reader support, touch targets"
    tags = ["domain:design", "a11y", "interaction"]
    design_domain = "Accessible Interaction Design — keyboard operability, focus management, ARIA patterns, and touch target sizing"


class A11yAuditSkill(DesignSkill):
    name = "design.a11y-audit"
    version = "1.0.0"
    description = "Conduct accessibility audits — WCAG compliance check, automated testing, manual review, assistive tech testing"
    tags = ["domain:design", "a11y", "audit"]
    design_domain = "Accessibility Auditing — WCAG compliance evaluation, testing methodology, remediation prioritization"


# ── Design Operations ─────────────────────────────────────────────

class OpsWorkflowSkill(DesignSkill):
    name = "design.ops-workflow"
    version = "1.0.0"
    description = "Design design workflows — handoff processes, review cycles, file organization, version control"
    tags = ["domain:design", "ops", "workflow"]
    design_domain = "Design Operations Workflows — handoff processes, review cycles, file organization, and collaboration tooling"


class OpsCritiqueSkill(DesignSkill):
    name = "design.ops-critique"
    version = "1.0.0"
    description = "Facilitate design critique sessions — framing, feedback guidelines, action tracking, iteration cycles"
    tags = ["domain:design", "ops", "critique"]
    design_domain = "Design Critique Facilitation — session planning, feedback frameworks, action tracking, and iteration cycles"


class OpsDesignSprintSkill(DesignSkill):
    name = "design.ops-design-sprint"
    version = "1.0.0"
    description = "Plan and run design sprints — problem framing, ideation, prototyping, user testing, decision frameworks"
    tags = ["domain:design", "ops", "sprints"]
    design_domain = "Design Sprint Facilitation — problem framing, ideation, prototyping, validation, and decision-making"


# ═════════════════════════════════════════════════════════════════════
# REGISTRATION
# ═════════════════════════════════════════════════════════════════════

DESIGN_SKILL_CLASSES = [
    # UI Design
    UIComponentSkill,
    UILayoutSkill,
    UIScreenSkill,
    # UX Design
    UXFlowSkill,
    UXWireframeSkill,
    UXPrototypeSkill,
    UXResearchSkill,
    # Visual & Brand
    VisualBrandSkill,
    VisualColorSkill,
    VisualTypographySkill,
    VisualIconographySkill,
    VisualDataVizSkill,
    # Design Systems
    SystemTokensSkill,
    SystemComponentLibrarySkill,
    SystemDocumentationSkill,
    # Interaction & Motion
    MotionMicrointeractionsSkill,
    MotionTransitionsSkill,
    MotionLoadingSkill,
    # Accessibility
    A11yColorSkill,
    A11yInteractionSkill,
    A11yAuditSkill,
    # Design Operations
    OpsWorkflowSkill,
    OpsCritiqueSkill,
    OpsDesignSprintSkill,
]


def register_design_skills(registry, ask_llm=None) -> None:
    """Register all design skills into a SkillRegistry.

    If ask_llm is provided (async callable(system, user) -> str),
    it is wired as a dependency on every design skill so they can
    execute their guidance via LLM.
    """
    for cls in DESIGN_SKILL_CLASSES:
        registry.register(cls)

    if ask_llm is not None:
        for cls in DESIGN_SKILL_CLASSES:
            try:
                registry.wire_dependency(cls.name, "ask_llm", ask_llm)
            except Exception as e:
                log.warning(f"[design.skills] failed to wire ask_llm on {cls.name}: {e}")

    log.info(f"[design.skills] registered {len(DESIGN_SKILL_CLASSES)} design skills"
             f"{' · LLM wired' if ask_llm else ' · analysis-only mode'}")


def get_design_skill_names() -> list[str]:
    """Return all design skill names for reference."""
    return [cls.name for cls in DESIGN_SKILL_CLASSES]
