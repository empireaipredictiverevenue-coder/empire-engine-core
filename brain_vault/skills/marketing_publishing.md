---
type: skill
name: marketing.publishing
version: 1.0.0
description: Content publishing and distribution — publish, syndicate, and promote content across channels for maximum reach and engagement
tags:
  - domain:marketing
  - mode:llm
  - pipeline:publishing
timeout_seconds: 60.0
max_retries: 2
execution_mode: llm
required_params:
  - goal
dependencies:
  - content.seo
  - content.landing
  - data.funnel
---

# marketing.publishing

Content publishing and distribution — publish, syndicate, and promote content across blog, social, email, directories, syndication networks, and partner channels.

## Overview

End-to-end content publishing strategy covering channel selection, publication scheduling, cross-platform syndication, distribution optimization, and performance measurement. Designed for teams that need to get content in front of the right audience through the right channels at the right time.

Integrates with SEO, landing page content, and funnel analytics skills for a complete publishing and measurement workflow.

## Capabilities

- **Channel strategy** — select optimal distribution channels based on audience, content type, and business goals (blog, LinkedIn, Medium, industry pubs, email, social, syndication networks, directories)
- **Publication scheduling** — timing optimization per channel, frequency recommendations, content calendar alignment, seasonal publishing cadence
- **Cross-platform syndication** — republishing strategy with canonical URLs, excerpt vs full-content syndication, platform-specific formatting, duplicate content SEO considerations
- **Distribution optimization** — paid promotion for organic content, influencer amplification, community sharing (Reddit, Hacker News, Slack communities, newsletters)
- **Email distribution** — newsletter integration, subscriber segment targeting, send-time optimization, forward-to-friend mechanics
- **Directory & aggregator submissions** — industry directories, podcast directories, event calendars, startup directories, Capterra/G2 for product content
- **RSS/feed strategy** — full vs partial feed, category-specific feeds, podcast RSS, YouTube RSS, newsletter RSS-to-email bridges
- **Social cross-posting** — platform-native reformatting, hashtag strategy per platform, visual sizing per channel, engagement hooks
- **Repurposing workflow** — turn blog posts into LinkedIn carousels, Twitter threads, newsletter dispatches, video scripts, podcast episodes, infographics
- **Performance measurement** — per-channel reach, engagement rate, referral traffic, conversion attribution, share of voice, amplification rate

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `marketing.publishing` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("marketing.publishing", {"params": {}})
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| goal | string | ✅ | Publishing goal (e.g. "drive traffic to landing page", "build backlinks", "establish thought leadership", "promote new feature") |
| content_type | string | — | Type of content: `blog_post`, `case_study`, `white_paper`, `press_release`, `video`, `podcast`, `infographic`, `newsletter`. Default: `blog_post` |
| audience | string | — | Target audience description for channel selection |
| channels | list | — | Specific channels to publish on. If omitted, skill recommends best channels based on content and audience |
| publish_cadence | string | — | Publishing frequency: `daily`, `weekly`, `biweekly`, `monthly`. Default: `weekly` |
| existing_content | string | — | Existing content URL or summary to repurpose/distribute |
| syndication_type | string | — | `full_reprint`, `excerpt_with_link`, `canonical_tag`, `no_syndication`. Default: `canonical_tag` |
| competitors | list | — | Competitor content URLs to benchmark against |
| seo_keywords | list | — | Target keywords for content optimization before publishing |

## Output

A structured publishing and distribution plan with:

```json
{
  "publishing_plan": {
    "goal": "...",
    "content_type": "blog_post|case_study|...",
    "primary_channel": "...",
    "schedule": {
      "publish_date": "YYYY-MM-DD",
      "time": "HH:MM (timezone)",
      "cadence": "weekly",
      "best_days": ["Tuesday", "Thursday"],
      "best_times": ["08:00 EST", "12:00 EST"]
    }
  },
  "channel_breakdown": [
    {
      "channel": "Blog (self-hosted)",
      "action": "Publish full post with featured image",
      "format": "Markdown → HTML with meta tags",
      "seo_checks": ["meta title", "meta description", "open graph tags", "schema markup", "internal links"],
      "distribution_hooks": ["RSS feed update", "ping search engines", "internal slack announcement"]
    },
    {
      "channel": "LinkedIn",
      "action": "Publish article or native post with link",
      "format": "1,300-2,000 character post with 3-5 images",
      "hashtags": ["#storms", "#roofing", "#restoration"],
      "best_time": "Tue-Thu 08:00-10:00 local"
    },
    {
      "channel": "Email newsletter",
      "action": "Include in weekly digest with preview + CTA",
      "format": "Subject line, preview text, 2-3 sentence intro with link to full post",
      "segment": "All subscribers + industry-specific tag"
    }
  ],
  "syndication_plan": {
    "approach": "canonical_tag|excerpt_with_link|full_reprint",
    "targets": [
      {
        "platform": "Medium",
        "format": "Republish with canonical URL to original",
        "audience_match": "high",
        "effort": "low"
      },
      {
        "platform": "Industry publication (e.g. Roofing Contractor mag)",
        "format": "Pitch exclusive adapted version",
        "audience_match": "very high",
        "effort": "high"
      }
    ]
  },
  "repurposing_opportunities": [
    {
      "format": "Twitter thread",
      "effort": "low",
      "reach_potential": "medium",
      "key_takeaways": ["Statistic X", "Insight Y", "Quote Z"]
    },
    {
      "format": "LinkedIn carousel",
      "effort": "medium",
      "reach_potential": "high",
      "slides": ["Hook", "Problem", "Data point", "Solution", "CTA"]
    },
    {
      "format": "YouTube short / TikTok",
      "effort": "high",
      "reach_potential": "very high",
      "script_hook": "..."
    }
  ],
  "performance_metrics": {
    "primary_kpi": "referral_traffic",
    "secondary_kpis": ["engagement_rate", "share_ratio", "conversion_rate", "backlinks_generated"],
    "lookback_window": "14 days",
    "benchmarks": {
      "blog_ctr": "2-5%",
      "email_open_rate": "20-35%",
      "social_engagement": "1-3%",
      "syndication_reach": "varies by platform"
    }
  }
}
```

## Example

```python
# Execute the skill
result = registry.execute("marketing.publishing", {
    "params": {
        "goal": "Drive traffic to storm restoration contractor landing page",
        "content_type": "blog_post",
        "audience": "Homeowners in storm-affected areas seeking restoration services",
        "channels": ["blog", "linkedin", "email_newsletter", "industry_directory"],
        "publish_cadence": "weekly",
        "syndication_type": "canonical_tag",
        "seo_keywords": ["storm damage restoration", "hail claim help", "roof repair financing"]
    },
    "context": {"source": "mission-control"}
})
print(result)
```
