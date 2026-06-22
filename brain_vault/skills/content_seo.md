---
type: skill
name: content.seo
version: 1.0.0
description: SEO content optimization — optimize content, structure, metadata, and keywords for maximum search engine visibility and organic traffic
tags:
  - domain:content
  - mode:llm
  - pipeline:seo
timeout_seconds: 60.0
max_retries: 2
execution_mode: llm
required_params:
  - goal
dependencies:
  - content.meta
  - data.trends
---

# content.seo

SEO content optimization — optimize page-level content, copy, structure, and metadata to rank higher in search engines and drive organic traffic.

## Overview

Optimize content for search engines with a focus on on-page SEO, keyword strategy, content structure, and metadata generation. Covers the full content optimization lifecycle: keyword research integration, title and heading optimization, content structure and readability, internal linking strategy, semantic relevance, and search intent alignment. Outputs actionable content improvements ranked by SEO impact.

**Scope:** This skill focuses on page-level content and copy optimization. For technical SEO audits, competitive analysis, site architecture, link building, Core Web Vitals, or AI search readiness, use the `marketing.seo-expert` skill.

Integrates with metadata generation (`content.meta`), keyword trends (`data.trends`), and content authoring tools for a complete SEO content workflow.

## Capabilities

- **Keyword integration** — primary and secondary keyword placement, LSI/natural language keyword variation, keyword density analysis, TF-IDF relevance scoring, keyword stuffing detection
- **Title & meta optimization** — title tag crafting (length, keyword position, click-through hooks), meta description optimization (160-char target, CTA inclusion, keyword inclusion), social share preview (OG tags, Twitter Cards)
- **Content structure** — heading hierarchy (H1-H6), topic cluster modeling, pillar page structure, subheading keyword alignment, paragraph length and readability optimization
- **Search intent alignment** — informational vs transactional vs navigational intent matching, content format selection (blog post, landing page, product page, guide, listicle, video), SERP feature targeting (featured snippets, People Also Ask, knowledge panels)
- **Readability & UX** — Flesch-Kincaid grade level, sentence length optimization, transition words, passive voice reduction, scannability (bullets, bold, short paragraphs), mobile-friendly formatting
- **Internal linking** — link opportunity identification, anchor text optimization, link equity distribution, topic cluster linking structure, orphan content detection
- **Semantic SEO** — entity recognition and inclusion, topical authority signals, co-occurrence optimization, schema vocabulary alignment (NewsArticle, BlogPosting, FAQPage, HowTo)
- **Image SEO** — alt text optimization (with keyword context), file naming conventions, image compression recommendations
- **Content freshness signals** — update recommendations based on ranking drift, content decay detection, new information integration, date stamping, recency signals

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.seo` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.seo", {"params": {}})
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| goal | string | ✅ | Optimization goal (e.g. "improve ranking for 'storm damage roofing Dallas'", "optimize new contractor landing page content", "audit existing blog for keyword gaps") |
| content | string | — | Raw content text or markdown to optimize. If omitted, generates optimization framework based on goal and keywords |
| target_keywords | list | — | Primary and secondary keywords. Format: `["primary keyword", "secondary keyword"]` |
| seo_type | string | — | Type of optimization: `onpage`, `keyword_research`, `content_structure`, `full_audit`, `meta_only`. Default: `onpage` |
| page_type | string | — | Type of page: `blog_post`, `landing_page`, `service_page`, `product_page`, `article`, `guide`, `about_page`. Default: `blog_post` |
| audience | string | — | Target audience description for tone and language alignment (e.g. "homeowners seeking storm restoration") |
| competitors | list | — | Competitor URLs for gap analysis and benchmarking |
| current_ranking | string | — | Current search position and target (e.g. "position 12 → goal: top 3") |
| search_intent | string | — | Intent: `informational`, `transactional`, `navigational`, `commercial_investigation`. Default: `informational` |
| target_length | integer | — | Target word count for the optimized content |
| include_schema | boolean | — | Generate JSON-LD structured data recommendations. Default: `true` |
| include_links | boolean | — | Generate internal linking recommendations. Default: `true` |
| readability_target | string | — | Target readability level: `general_audience`, `professional`, `expert`. Default: `general_audience` |
| locale | string | — | Target locale for local SEO nuances. Default: `en_US` |

## Output

A structured SEO content optimization report with:

```json
{
  "seo_optimization": {
    "goal": "...",
    "page_type": "blog_post|landing_page|...",
    "target_keywords": ["primary keyword", "secondary keyword"],
    "search_intent": "informational|transactional|...",
    "current_ranking": "..."
  },
  "keyword_analysis": {
    "primary_keyword": {
      "keyword": "...",
      "current_density": "1.2%",
      "recommended_density": "1.5-2.0%",
      "placement_ok": true,
      "suggested_additions": [
        {"option": "Include in H2 subheading", "priority": "high"},
        {"option": "Add to image alt text", "priority": "medium"}
      ]
    },
    "secondary_keywords": [
      {
        "keyword": "...",
        "found": true,
        "recommendation": "Increase mentions from 2 to 4-5 instances"
      }
    ],
    "keyword_gaps": [
      {"keyword": "hail damage claim timeline", "searched_per_month": 2400, "difficulty": "medium", "opportunity": "high"}
    ],
    "lsqi_variations": [
      {"phrase": "how to file storm damage claim", "intent_match": "informational", "priority": "high"}
    ]
  },
  "meta_optimization": {
    "title_tag": {
      "current": "...",
      "recommended": "...",
      "length_current": 52,
      "length_recommended": 55,
      "keyword_position": "front|middle|end",
      "issues": []
    },
    "meta_description": {
      "current": "...",
      "recommended": "...",
      "length_current": 145,
      "length_recommended": 155,
      "cta_included": true,
      "issues": []
    },
    "og_tags": {
      "og_title": "...",
      "og_description": "...",
      "og_image_recommendation": "1200x630px with keyword visual context"
    }
  },
  "content_structure": {
    "heading_audit": [
      {"heading": "H1: Current title", "issue": "Missing primary keyword", "fix": "...", "priority": "high"},
      {"heading": "H2: Section name", "issue": "Too long (75 chars)", "fix": "...", "priority": "medium"}
    ],
    "readability": {
      "flesch_kincaid_grade": 8.5,
      "recommended_grade": "7-9 for general audience",
      "avg_sentence_length": 18.2,
      "recommended_sentence_length": "15-20 words",
      "passive_sentences_pct": 12,
      "passive_recommended": "< 10%",
      "transition_word_density": "good"
    },
    "topic_cluster": {
      "pillar_topic": "...",
      "cluster_content": ["...", "..."],
      "internal_link_targets": ["...", "..."],
      "gap_opportunities": ["..."]
    }
  },
  "technical_recommendations": [
    {
      "issue": "No FAQ schema on page",
      "impact": "medium",
      "effort": "low",
      "fix": "Add FAQPage JSON-LD for the 6 common questions in the content",
      "implementation": "{\"@context\": \"https://schema.org\", \"@type\": \"FAQPage\", ...}"
    }
  ],
  "internal_links": [
    {
      "anchor_text": "how to file an insurance claim",
      "target_url": "/guides/insurance-claim-process",
      "relevance": 0.92,
      "priority": "high",
      "link_equity": "follow"
    }
  ],
  "featured_snippet_opportunities": [
    {
      "query": "how long does storm damage claim take",
      "current_snippet_type": "list",
      "our_content_format": "numbered steps",
      "optimization_advice": "Format the claim timeline as an ordered list in H3 section",
      "likelihood": "high"
    }
  ],
  "action_items": [
    {"priority": "critical", "task": "Add primary keyword to H1 title tag", "effort": "low", "impact": "high"},
    {"priority": "high", "task": "Write 300-word section on 'types of storm damage covered' targeting featured snippet", "effort": "medium", "impact": "high"},
    {"priority": "medium", "task": "Add internal links to 3 related pillar pages", "effort": "low", "impact": "medium"},
    {"priority": "low", "task": "Optimize 4 images with keyword-rich alt text", "effort": "low", "impact": "low"}
  ]
}
```

## Example

```python
# Execute the skill
result = registry.execute("content.seo", {
    "params": {
        "goal": "Optimize contractor landing page for 'storm damage roof repair Dallas'",
        "content": "# Storm Damage Roof Repair Dallas\n\nWhen storms hit Dallas, your roof is the first line of defense...\n\n## Why Act Fast\n\n...",
        "target_keywords": ["storm damage roof repair Dallas", "hail damage roof repair", "emergency roof repair Dallas"],
        "seo_type": "full_audit",
        "page_type": "landing_page",
        "audience": "Homeowners in Dallas-Fort Worth metro area who experienced recent storm damage",
        "competitors": ["https://competitor1.com/storm-damage-repair", "https://competitor2.com/dallas-roof-repair"],
        "search_intent": "commercial_investigation",
        "include_schema": true,
        "readability_target": "general_audience"
    },
    "context": {"source": "mission-control"}
})
print(result)
```
