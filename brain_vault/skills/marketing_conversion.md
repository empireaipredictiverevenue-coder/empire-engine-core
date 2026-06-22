---
type: skill
name: marketing.conversion
version: 1.0.0
description: Conversion rate optimization — analyze pages, funnels, and flows to maximize conversion rates
tags:
  - domain:marketing
  - mode:llm
  - pipeline:cro
timeout_seconds: 60.0
max_retries: 2
execution_mode: llm
required_params:
  - goal
dependencies:
  - data.funnel
  - data.abtest
  - design.web-builder
  - content.landing
---

# marketing.conversion

Conversion rate optimization — analyze pages, funnels, forms, and user flows to identify drop-off points and recommend high-impact changes.

## Overview

Analyze marketing pages, signup flows, checkout funnels, and lead capture forms to improve conversion rates. Covers the full CRO lifecycle: page analysis, funnel auditing, CTA optimization, form design, trust signals, objection handling, and A/B test design. Outputs structured recommendations ranked by effort and impact.

Integrates with landing page builder, funnel analytics, A/B testing, and SEO skills for a complete optimization workflow.

## Capabilities

- **Page conversion analysis** — value proposition clarity, headline effectiveness, CTA placement and copy, visual hierarchy, trust signals, friction points
- **Funnel auditing** — stage-by-stage conversion, drop-off identification, leak plugging, recovery flows
- **CTA optimization** — button copy, placement, color, size, urgency triggers, primary vs secondary hierarchy
- **Form optimization** — field reduction, multi-step flows, inline validation, error handling, mobile-friendly inputs
- **Trust & social proof** — testimonial placement, review counts, security badges, case study snippets, logo walls
- **Objection handling** — FAQ design, guarantee placement, comparison tables, risk reversal, price anchoring
- **A/B test design** — hypothesis generation, variant specifications, sample size estimation, success metrics
- **Post-conversion flow** — thank-you pages, confirmation emails, upsell/downsell, onboarding activation

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `marketing.conversion` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("marketing.conversion", {"params": {}})
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| goal | string | ✅ | Primary conversion goal (e.g. "sign up", "request quote", "schedule call", "purchase") |
| page_type | string | — | Type of page: `landing`, `homepage`, `pricing`, `feature`, `checkout`, `form`. Default: `landing` |
| current_rate | string | — | Current conversion rate and target (e.g. "2.3% → goal of 5%") |
| traffic_source | string | — | Where visitors come from: `organic`, `paid`, `email`, `social`, `direct` |
| page_url | string | — | URL of the page to analyze |
| funnel_stages | list | — | List of funnel stage names for full-funnel analysis |
| audience | string | — | Target audience description |
| competitors | list | — | Competitor URLs for competitive CRO analysis |
| form_fields | list | — | Form field names if form optimization needed |

## Output

A structured CRO analysis with:

```json
{
  "cro_analysis": {
    "page": {
      "type": "landing|homepage|pricing|form",
      "goal": "...",
      "current_rate": "..."
    },
    "quick_wins": [
      {
        "issue": "CTA too far below fold",
        "fix": "Move primary CTA above fold with contrasting button",
        "effort": "low",
        "impact": "high",
        "confidence": "high"
      }
    ],
    "high_impact": [
      {
        "issue": "No social proof near form",
        "fix": "Add testimonial carousel and trust badges above submit button",
        "effort": "medium",
        "impact": "high",
        "confidence": "medium"
      }
    ],
    "a_b_test_ideas": [
      {
        "variant_a": "Current: 'Submit' button",
        "variant_b": "Proposed: 'Get Free Quote' button",
        "hypothesis": "Value-driven CTA copy increases click-through",
        "metric": "ctr",
        "min_sample": 1000
      }
    ],
    "funnel_audit": [
      {
        "stage": "Landing page → Form start",
        "drop_off": "65%",
        "issue": "Form not visible without scrolling on mobile",
        "fix": "Sticky CTA bar on mobile viewport"
      }
    ],
    "copy_alternatives": {
      "headline": ["Current: '...'", "Option A: '...'", "Option B: '...'"],
      "cta": ["Current: '...'", "Option A: '...'", "Option B: '...'"]
    }
  }
}
```

## Example

```python
# Execute the skill
result = registry.execute("marketing.conversion", {
    "params": {
        "goal": "Increase contractor lead form submissions",
        "page_type": "landing",
        "current_rate": "1.8% → target 4%",
        "traffic_source": "paid search (Google Ads)",
        "audience": "Homeowners with storm damage seeking restoration contractors",
        "form_fields": ["name", "phone", "email", "address", "damage_type", "insurance_provider"]
    },
    "context": {"source": "mission-control"}
})
print(result)
```
