---
type: skill
name: marketing.advertising
version: 1.0.0
description: Paid advertising strategy — plan, structure, and optimize ad campaigns across platforms for maximum ROAS
tags:
  - domain:marketing
  - mode:llm
  - pipeline:ads
timeout_seconds: 60.0
max_retries: 2
execution_mode: llm
required_params:
  - goal
dependencies:
  - data.abtest
  - design.web-builder
  - marketing.conversion
  - content.landing
---

# marketing.advertising

Paid advertising strategy — plan, structure, launch, and optimize paid ad campaigns across Google Ads, Meta, LinkedIn, and other platforms.

## Overview

End-to-end advertising strategy covering campaign architecture, platform selection, audience targeting, budget allocation, creative briefing, bid management, and performance optimization. Designed for performance marketers running lead-gen, e-commerce, and brand awareness campaigns.

Integrates with A/B testing, landing page builder, CRO, and landing page content skills for a complete conversion chain from ad click to conversion.

## Capabilities

- **Campaign architecture** — account structure design, campaign hierarchy (search, display, social, video, shopping), naming conventions, budget allocation across campaigns and ad sets
- **Platform selection** — Google Ads (search, display, YouTube, Performance Max), Meta (Facebook, Instagram, Audience Network), LinkedIn (Sponsored Content, InMail, Lead Gen Forms), Twitter/X, TikTok, programmatic display, native ads (Taboola, Outbrain)
- **Audience targeting** — keyword research and match types, audience segmentation (demographic, behavioral, custom, lookalike, retargeting), exclusions and suppression lists, audience layering
- **Budget strategy** — testing-phase vs scaling-phase budgets, allocation by platform, by campaign objective, by geo, daily vs lifetime budgets, budget pacing and velocity
- **Creative briefing** — ad format selection per platform, headline and description frameworks (PAS, BAB, AIDA), visual asset specifications, ad copy angles testing matrix, creative rotation rules
- **Bid strategy** — manual CPC, enhanced CPC, target CPA, target ROAS, maximize conversions, portfolio bid strategies, bid adjustments by device/location/time
- **Conversion tracking** — pixel installation, event setup, offline conversion import, call tracking integration, attribution window selection, view-through vs click-through attribution
- **Retargeting** — funnel-stage segmentation (visitors, engaged, leads, cart abandoners), retargeting windows and frequency caps, sequential retargeting, exclusion logic, RLSA (Remarketing Lists for Search Ads)
- **Landing page alignment** — message matching (ad copy → landing page headline), landing page load speed requirements, post-click conversion optimization, mobile responsiveness checks
- **Performance measurement** — ROAS, CPA, CTR, CPM, impression share, quality score, conversion rate, assisted conversions, incrementality testing
- **Optimization levers** — ad rotation and fatigue management, audience expansion, automated rules, schedule-based bid adjustments, geo-targeting refinements, negative keyword expansion, search query analysis

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `marketing.advertising` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("marketing.advertising", {"params": {}})
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| goal | string | ✅ | Advertising goal (e.g. "generate contractor leads", "drive demo signups", "retarget website visitors", "promote seasonal offer") |
| platform | string | — | Primary platform: `google`, `meta`, `linkedin`, `tiktok`, `twitter`, `programmatic`, `native`, `multi`. Default: `google` |
| budget | string | — | Monthly or total budget (e.g. "$5,000/month", "$15,000 total") |
| audience | string | — | Target audience description (ICP, demographics, job titles, interests, behaviors) |
| offer | string | — | What's being promoted (e.g. "free roof inspection", "storm damage claim assistance", "contractor partnership program") |
| landing_page_url | string | — | URL the ads will point to for pre-click to post-click alignment |
| tracking_setup | string | — | Current tracking status: `not_setup`, `pixel_only`, `full_tracking`, `offline_conversions` |
| current_campaigns | string | — | Description of currently running campaigns for optimization/iteration |
| competitors | list | — | Competitor URLs or brand names for competitive ad analysis |
| constraints | string | — | Brand guidelines, compliance requirements, excluded geos, banned terms |

## Output

A structured advertising strategy with:

```json
{
  "advertising_strategy": {
    "goal": "...",
    "platform": "google|meta|linkedin|multi",
    "budget": "...",
    "timeline": "test_phase|scale_phase|maintain",
    "overall_approach": "..."
  },
  "campaign_architecture": [
    {
      "campaign_name": "[Platform]_[Objective]_[Audience]_[Offer]",
      "objective": "leads|traffic|awareness|sales",
      "platform": "google_search|meta_newsfeed|linkedin_sponsored",
      "budget_pct": 40,
      "key_audience": "...",
      "ad_formats": ["responsive_search_ad", "image_ad", "video_ad"],
      "bidding_strategy": "target_cpa|maximize_conversions|target_roas",
      "target_cpa_or_roas": "$XX or XX%"
    }
  ],
  "audience_plan": {
    "prospecting": {
      "approach": "keyword_targeting|lookalike|interest_based|job_title",
      "segments": ["Segment A", "Segment B"],
      "estimated_size": "100K-500K",
      "exclusions": ["existing_customers", "recent_converters_30d"]
    },
    "retargeting": {
      "approach": "funnel_stage_based",
      "audiences": [
        {
          "name": "Site visitors (all)",
          "window": "30 days",
          "message": "General awareness / consideration",
          "budget_pct": 15
        },
        {
          "name": "Key page visitors",
          "window": "14 days",
          "message": "Case studies, demos, social proof",
          "budget_pct": 10
        },
        {
          "name": "Form starters / cart abandoners",
          "window": "7 days",
          "message": "Urgency, offer, objection handling",
          "budget_pct": 10
        }
      ],
      "frequency_cap": "3-5x/week",
      "exclusions": ["converted_last_14d"]
    }
  },
  "creative_brief": {
    "angles": [
      {
        "angle": "Pain Point",
        "headline_themes": ["...", "..."],
        "description_themes": ["...", "..."],
        "visual_suggestions": ["before/after", "face of frustrated person"]
      },
      {
        "angle": "Social Proof",
        "headline_themes": ["Join 500+ contractors", "Rated 4.9/5"],
        "description_themes": ["Testimonial-driven", "Stats and results"],
        "visual_suggestions": ["Logo wall", "Review screenshot", "Customer photo"]
      }
    ],
    "ad_format_specs": {
      "google_rsa": {"headlines": 15, "headline_max_chars": 30, "descriptions": 4, "description_max_chars": 90},
      "meta_single_image": {"primary_text_max": 125, "headline_max": 40}
    }
  },
  "budget_plan": {
    "test_phase_weeks": "2-4",
    "test_budget_pct": 30,
    "scale_budget_pct": 70,
    "by_campaign": [
      {"campaign": "Search - Brand", "budget_pct": 15, "notes": "Protect brand terms"},
      {"campaign": "Search - Non-Brand", "budget_pct": 35, "notes": "Primary lead driver"},
      {"campaign": "Display - Retargeting", "budget_pct": 20, "notes": "Warm audiences"},
      {"campaign": "Social - Prospecting", "budget_pct": 20, "notes": "Cold demand gen"},
      {"campaign": "Social - Retargeting", "budget_pct": 10, "notes": "Social warm audiences"}
    ],
    "budget_ramp": "Increase 20-30% every 3-5 days after 50+ conversions"
  },
  "tracking_plan": {
    "required_events": ["page_view", "lead", "form_submit", "phone_call"],
    "pixel_or_tag": "Google Ads tag + Meta pixel + GA4",
    "offline_conversions": "Import closed-won deals back to ad platforms",
    "attribution_window": "click: 30 days | view: 1 day",
    "utm_strategy": "All campaigns tagged with source, medium, campaign, term, content"
  },
  "optimization_plan": {
    "review_cadence": "Weekly (daily during first 7 days of new campaigns)",
    "key_checks": [
      "Spend pacing vs budget",
      "CPA/ROAS vs target",
      "Top/bottom performing ads and keywords",
      "Search query report (add negatives, expand keywords)",
      "Impression share (lost due to budget vs rank)",
      "Frequency metrics (audience fatigue)",
      "Landing page conversion rate",
      "Auction insights (competitor activity)"
    ],
    "optimization_levers": [
      {"issue": "CPA too high", "levers": ["Tighten audience", "Refresh creative", "Reduce bids", "Pause underperformers", "Check landing page conversion"]},
      {"issue": "CTR low", "levers": ["Test new headlines/hooks", "Refine audience match", "Test new visual creative", "Check ad relevance"]},
      {"issue": "CPM high", "levers": ["Expand audience", "Check placement exclusions", "Lower frequency cap", "Test different ad format"]},
      {"issue": "Low impression share", "levers": ["Increase budget (budget loss)", "Improve quality score (rank loss)", "Raise bids"]}
    ]
  }
}
```

## Example

```python
# Execute the skill
result = registry.execute("marketing.advertising", {
    "params": {
        "goal": "Generate qualified contractor signups for storm restoration network",
        "platform": "multi",
        "budget": "$10,000/month",
        "audience": "Roofing and restoration contractors in Texas, Florida, and Oklahoma seeking steady storm work",
        "offer": "Free contractor profile + first 3 leads free",
        "landing_page_url": "https://empire-ai.co.uk/contractors/signup",
        "tracking_setup": "pixel_only",
        "competitors": ["LeadHub", "StormForce", "ContractorNexus"],
        "constraints": "Must comply with contractor licensing regulations per state"
    },
    "context": {"source": "mission-control"}
})
print(result)
```
