---
type: skill
name: marketing.seo-expert
version: 1.0.0
description: Full-spectrum SEO strategy — technical audits, competitive intelligence, link building, local SEO, Core Web Vitals, site architecture, and AI search readiness
tags:
  - domain:marketing
  - mode:llm
  - pipeline:seo
timeout_seconds: 120.0
max_retries: 2
execution_mode: llm
required_params:
  - goal
dependencies:
  - content.seo
  - content.meta
  - data.metrics
---

# marketing.seo-expert

Full-spectrum SEO strategy — technical audits, competitive intelligence, link building strategy, local SEO optimization, Core Web Vitals improvement, site architecture planning, and AI search (GEO/LLMO) readiness. Covers the strategic layer above content-level optimization, producing actionable roadmaps and prioritized audit findings.

## Overview

Strategic SEO management for the Empire AI ecosystem — storm restoration contractors, lead generation domains, and service-area businesses. Covers technical SEO audits, competitive landscape analysis, link acquisition strategy, local SEO optimization for multi-location contractors, Core Web Vitals performance tuning, site architecture information architecture, E-E-A-T signals, AI search readiness (Google SGE / Bard / ChatGPT optimization), and international/multi-region SEO. Outputs prioritized action plans, audit reports with effort × impact scoring, and measurable KPI targets.

Integrates with content optimization (`content.seo`, `content.meta`), and data analytics (`data.metrics`, `data.trends`) for a complete SEO strategy and execution workflow.

## Capabilities

- **Technical SEO audits** — crawlability analysis (robots.txt, sitemap.xml, noindex/nofollow audit), indexation status (Google Index coverage report simulation), canonical URL audit, pagination and faceted navigation handling, JavaScript SEO (hydration, CSR vs SSR, dynamic rendering), broken link detection (internal, external, image), redirect chain analysis (301 → 302 → 404 loops), orphan page detection, HTTPS/SSL validation, mixed content scanning, hreflang tag audit
- **Core Web Vitals optimization** — LCP (Largest Contentful Paint) analysis and fixes (image optimization, CDN, lazy loading, critical CSS), FID/INP (Interaction to Next Paint) reduction (event handler optimization, long task splitting, web worker offloading), CLS (Cumulative Layout Shift) elimination (dimension attributes, font swap strategies, dynamic content containers), TTFB improvement (server response time, edge caching, CDN selection, database query optimization), mobile vs desktop performance comparison
- **Competitive SEO intelligence** — competitor domain authority comparison (DR/DA), backlink gap analysis (competitor links we don't have), content gap analysis (topics competitors rank for that we don't), keyword cannibalization detection across multiple domains, SERP feature ownership analysis (featured snippets, People Also Ask, video carousels, local packs), share of voice tracking, ranking velocity comparison
- **Link building strategy** — prospect identification (relevance score, domain authority, traffic estimates), outreach strategy (email templates, value proposition, relationship-based approaches), content-based link acquisition (skyscraper technique, guest posting, resource page targeting, broken link building), digital PR (newsworthy data, expert roundups, HARO/Connectively), unlinked brand mention conversion, internal link equity distribution, toxic link disavowal strategy
- **Local SEO** — Google Business Profile optimization (categories, attributes, posts, Q&A management, review generation strategy), local citation audit and building (consistency across Yelp, BBB, Angi, HomeAdvisor, Nextdoor), local pack ranking factors analysis (proximity, prominence, relevance), NAP (Name, Address, Phone) consistency audit, local link building (local sponsorships, chamber of commerce, community organizations), multi-location SEO strategy (service area pages, location landing pages, localized content), local review signal analysis (volume, velocity, diversity, response rate)
- **E-E-A-T signals** — Experience signals (real-world expertise, case studies, before/after portfolios, video demonstrations), Expertise signals (author bios, credentials, certifications, industry awards, publications), Authoritativeness signals (external mentions, media coverage, industry partnerships, speaking engagements), Trustworthiness signals (secure checkout, privacy policy, clear contact info, business license display, refund/guarantee policy), YMYL (Your Money or Your Life) content compliance for restoration services
- **AI search readiness (GEO/LLMO)** — Generative Engine Optimization (GEO) — content structure for AI answer extraction, verbatim quote formatting for LLM citation, FAQ schema optimization for AI answer boxes, conversational keyword targeting (natural language queries, question-based searches), training data signals (Reddit mentions, Wikipedia citations, authoritative source inclusion), ChatGPT/Bard entity recognition setup, source credibility optimization for AI citations
- **Site architecture & information architecture** — silo structure design (topic clusters, pillar pages, supporting content), URL structure optimization (short, descriptive, keyword-rich, consistent hierarchy), breadcrumb schema implementation, category/tag taxonomy optimization, flat vs deep architecture trade-offs, pagination best practices (rel=next/prev, view-all options), site search and internal search optimization
- **International & multi-region SEO** — hreflang tag implementation (language + region targeting), geo-targeted content strategy, ccTLD vs subdomain vs subdirectory strategy, localized keyword research (regional language variations, dialect differences), multi-currency and multi-language UX considerations
- **SEO monitoring & KPI framework** — organic traffic trend analysis, keyword rank tracking setup, conversion by organic traffic channel, crawl budget optimization, index coverage monitoring, Core Web Vitals real-user monitoring (RUM), backlink growth velocity, local rank tracking, market share measurement

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `marketing.seo-expert` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("marketing.seo-expert", {"params": {}})
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| goal | string | ✅ | SEO strategy goal (e.g. "full technical audit for empire-ai.co.uk", "competitive backlink analysis for DFW storm restoration niche", "local SEO strategy for 5 new metro expansions") |
| seo_type | string | — | Type of engagement: `full_audit`, `technical_audit`, `competitive_analysis`, `link_building_plan`, `local_seo_strategy`, `core_web_vitals`, `site_architecture`, `ai_search_readiness`, `strategy_roadmap`. Default: `full_audit` |
| url | string | — | Primary domain or URL to audit/optimize |
| niche | string | — | Industry or market vertical (e.g. "storm restoration", "roofing", "water damage restoration", "general contracting") |
| target_keywords | list | — | Priority keyword list for the engagement |
| competitors | list | — | Competitor domains for competitive analysis |
| locations | list | — | Service locations for local SEO: `[{"city": "Dallas", "state": "TX"}, ...]` |
| current_metrics | string | — | Current performance snapshot (traffic, rankings, domain authority, Core Web Vitals scores) |
| target_markets | list | — | Target countries or regions for international SEO: `["US", "GB", "CA"]` |
| link_budget | string | — | Estimated link building budget: `none`, `low`, `medium`, `high`. Default: `medium` |
| timeframe | string | — | Strategy timeframe: `30_days`, `90_days`, `6_months`, `12_months`. Default: `90_days` |
| include_implementation | boolean | — | Generate implementation-ready code snippets (schema, redirects, robots.txt, .htaccess). Default: `false` |
| priority_filter | string | — | Filter recommendations by minimum priority: `critical`, `high`, `medium`, `low`. Default: `medium` |

## Output

A structured SEO strategy report with:

```json
{
  "seo_strategy": {
    "goal": "...",
    "seo_type": "full_audit|technical_audit|...",
    "url": "...",
    "timeframe": "90_days",
    "generated_at": "2026-06-21T12:00:00Z"
  },
  "executive_summary": {
    "current_state": "Summary of current SEO health with key findings",
    "opportunity_score": 72,
    "estimated_traffic_impact": "+35-60% in 6 months",
    "critical_issues": 3,
    "high_priority": 12,
    "medium_priority": 18,
    "quick_wins": 8
  },
  "technical_audit": {
    "crawlability": {
      "score": 65,
      "issues": [
        {"severity": "critical", "finding": "37 orphan pages with no internal links", "impact": "Pages not indexed", "fix": "Add contextual internal links from related content", "effort": "medium", "priority": "critical"},
        {"severity": "high", "finding": "robots.txt blocks /guides/ directory", "impact": "12 guide pages excluded from index", "fix": "Remove Disallow: /guides/ from robots.txt", "effort": "low", "priority": "high"},
        {"severity": "medium", "finding": "XML sitemap last modified 90 days ago", "impact": "Crawl budget inefficiency", "fix": "Implement dynamic sitemap generation", "effort": "medium", "priority": "medium"}
      ]
    },
    "indexation": {
      "indexed_pages": 145,
      "not_indexed": 23,
      "errors": ["5 pages with noindex tag", "3 pages blocked by robots.txt", "15 canonical issues"],
      "recommendations": ["Remove noindex from /service-area/dallas page", "..."]
    },
    "core_web_vitals": {
      "overall_pass_rate": 58,
      "lcp": {
        "current": "3.2s",
        "target": "< 2.5s",
        "pass_rate": 45,
        "issues": ["Hero image not compressed (1.2MB)", "No critical CSS inlined", "Server TTFB 800ms"]
      },
      "inp": {
        "current": "180ms",
        "target": "< 200ms",
        "pass_rate": 82,
        "issues": ["Third-party analytics scripts blocking main thread"]
      },
      "cls": {
        "current": "0.15",
        "target": "< 0.1",
        "pass_rate": 67,
        "issues": ["No width/height on 15 images", "Web font swap strategy not implemented"]
      },
      "recommendations": [
        {"priority": "critical", "task": "Compress and WebP-convert hero image", "effort": "low", "estimated_improvement": "LCP -0.6s"},
        {"priority": "high", "task": "Inline critical CSS above fold", "effort": "medium", "estimated_improvement": "LCP -0.4s"},
        {"priority": "medium", "task": "Add explicit width/height to all images", "effort": "medium", "estimated_improvement": "CLS 0.15 → 0.05"}
      ]
    },
    "redirects_and_broken": {
      "broken_links": {"internal": 4, "external": 12},
      "redirect_chains": [
        {"url": "/storm-damage", "chain": ["301 → /storm-damage-repair", "302 → /services/storm-damage", "200"], "fix": "Update to direct 301", "effort": "low"}
      ],
      "orphan_pages": 37
    },
    "schema_markup": {
      "implemented_types": ["LocalBusiness", "Product"],
      "missing_recommended": ["FAQPage", "HowTo", "Review", "Service", "BreadcrumbList"],
      "errors": ["LocalBusiness missing openingHours", "Product missing price"]
    }
  },
  "competitive_analysis": {
    "domain_comparison": [
      {"domain": "empire-ai.co.uk", "dr": 32, "organic_traffic": 4500, "ranking_keywords": 820},
      {"domain": "competitor1.com", "dr": 48, "organic_traffic": 12000, "ranking_keywords": 2100},
      {"domain": "competitor2.com", "dr": 38, "organic_traffic": 7800, "ranking_keywords": 1450}
    ],
    "content_gaps": [
      {"topic": "How to choose a storm restoration contractor", "avg_monthly_searches": 3200, "top_ranking_domain": "competitor1.com", "our_ranking": "not in top 100", "opportunity": "high"}
    ],
    "backlink_gaps": [
      {"referring_domain": "homeadvisor.com", "linking_to": ["competitor1.com", "competitor2.com"], "not_linking_to": ["empire-ai.co.uk"], "opportunity": "Create contractor profile page on HomeAdvisor"}
    ],
    "keyword_cannibalization": [
      {"keyword": "roof repair Dallas", "ranking_pages": ["/dallas-roof-repair", "/services/roofing/dallas", "/locations/dallas-roofing"], "best_page": "/dallas-roof-repair", "action": "Consolidate 302 redirects to best page"}
    ]
  },
  "link_building_plan": {
    "strategy": "content-based + local partnerships",
    "phases": [
      {"phase": 1, "weeks": "1-4", "tactics": ["Convert 8 unlinked brand mentions", "Fix 12 broken external links → suggest replacement content", "Submit to 5 niche directories (Angi, HomeAdvisor, BBB, Nextdoor, Yelp)"]},
      {"phase": 2, "weeks": "5-12", "tactics": ["Skyscraper: Upgrade competitor's top content piece + outreach", "Guest post on 5 contractor industry blogs", "Create data study: '2026 Storm Damage Statistics by Metro' for digital PR"]}
    ],
    "prospects": [
      {"domain": "stormdamage.org", "dr": 45, "relevance": 0.95, "approach": "Resource page link request", "priority": "high", "estimated_difficulty": "medium"}
    ]
  },
  "local_seo": {
    "locations_audited": [
      {
        "city": "Dallas",
        "google_business_profile": {
          "verified": true,
          "completeness": 85,
          "missing_fields": ["service_area", "hours_holiday", "attributes:wheelchair_accessible"],
          "categories": ["Roofing contractor", "Storm restoration service"],
          "suggested_categories": ["Water damage restoration service", "General contractor"],
          "review_count": 37,
          "avg_rating": 4.5,
          "review_response_rate": 62,
          "response_rate_target": "> 90%"
        },
        "citation_consistency": {
          "score": 78,
          "inconsistencies": ["Phone number differs on Yelp (214-555-0101 vs 214-555-0102)", "Address missing suite number on BBB"],
          "action": "Standardize NAP across all 12 citation sources"
        },
        "local_pack_position": {
          "current": "5th",
          "target": "top 3",
          "gap_analysis": "Competitors have 2.5x more reviews and respond to 98% of reviews"
        }
      }
    ],
    "local_link_opportunities": [
      {"source": "Dallas Chamber of Commerce", "type": "membership directory", "effort": "low", "value": "high"},
      {"source": "Local news coverage of storm season prep", "type": "digital PR", "effort": "medium", "value": "high"}
    ]
  },
  "ai_search_readiness": {
    "geo_score": 45,
    "recommendations": [
      {"priority": "high", "task": "Add FAQ schema with question-answer pairs for 20 common storm damage questions", "effort": "medium", "impact": "AI answer extraction readiness"},
      {"priority": "high", "task": "Create definitive guide: 'Complete Guide to Storm Damage Claims in Texas' with structured data", "effort": "high", "impact": "ChatGPT/Bard citation target"},
      {"priority": "medium", "task": "Build authority signals: get Wikipedia mention for 'storm restoration' category", "effort": "high", "impact": "Training data inclusion"},
      {"priority": "medium", "task": "Optimize for conversational queries: 'how long does it take to file a storm damage claim in Texas'", "effort": "low", "impact": "AI answer box targeting"}
    ]
  },
  "site_architecture": {
    "current_structure": "Flat — all pages one level from root",
    "recommended_structure": "Hub-and-spoke by metro + service type",
    "recommendations": [
      {"priority": "high", "task": "Create metro landing pages: /dallas/storm-damage, /fort-worth/storm-damage, etc.", "effort": "high"},
      {"priority": "high", "task": "Implement breadcrumb schema on all service pages", "effort": "low"},
      {"priority": "medium", "task": "Build topic cluster around 'storm damage claim process' with pillar page + 8 subtopics", "effort": "medium"}
    ]
  },
  "roadmap": {
    "phase_1_quick_wins_week_1_2": [
      {"task": "Fix robots.txt blocking /guides/", "effort": "5 min", "impact": "12 pages indexed"},
      {"task": "Compress and WebP hero images", "effort": "30 min", "impact": "LCP -0.6s"},
      {"task": "Add width/height to top 10 images", "effort": "15 min", "impact": "CLS fix"}
    ],
    "phase_2_foundation_week_3_6": [
      {"task": "Implement FAQ schema on 5 service pages", "effort": "2 hours", "impact": "Featured snippet + AI answer eligibility"},
      {"task": "NAP cleanup across 12 citation sources", "effort": "3 hours", "impact": "Local pack improvement"},
      {"task": "Create metro landing page template", "effort": "4 hours", "impact": "Site architecture foundation"}
    ],
    "phase_3_growth_week_7_12": [
      {"task": "Link outreach campaign — 20 prospects", "effort": "10 hours", "impact": "Domain authority +2-3"},
      {"task": "Create data study for digital PR", "effort": "8 hours", "impact": "Earned media + backlinks"},
      {"task": "Launch expanded local citation strategy for 5 metros", "effort": "6 hours", "impact": "Local visibility in new markets"}
    ],
    "kpi_targets": {
      "3_months": {"organic_traffic": "+20%", "keyword_top_10": "+15", "domain_authority": "+2", "core_web_vitals_pass": "70%"},
      "6_months": {"organic_traffic": "+50%", "keyword_top_10": "+40", "domain_authority": "+5", "core_web_vitals_pass": "90%"},
      "12_months": {"organic_traffic": "+100%", "keyword_top_10": "+100", "domain_authority": "+10", "core_web_vitals_pass": "95%"}
    }
  }
}
```

## Example

```python
# Execute the skill — full technical SEO audit
result = registry.execute("marketing.seo-expert", {
    "params": {
        "goal": "Full technical SEO audit and 90-day strategy for empire-ai.co.uk in the storm restoration niche",
        "seo_type": "full_audit",
        "url": "https://empire-ai.co.uk",
        "niche": "storm restoration",
        "target_keywords": ["storm damage restoration", "hail damage claim help", "roof repair financing"],
        "competitors": ["https://competitor1.com", "https://competitor2.com"],
        "locations": [{"city": "Dallas", "state": "TX"}, {"city": "Houston", "state": "TX"}, {"city": "Oklahoma City", "state": "OK"}],
        "current_metrics": "DR 32, 4500 monthly organic visits, 820 ranking keywords, 58% Core Web Vitals pass rate",
        "timeframe": "90_days",
        "include_implementation": true,
        "priority_filter": "high"
    },
    "context": {"source": "mission-control"}
})
print(result)

# Execute the skill — local SEO strategy for metro expansion
result = registry.execute("marketing.seo-expert", {
    "params": {
        "goal": "Local SEO rollout plan for 5 new metro locations in Texas and Oklahoma",
        "seo_type": "local_seo_strategy",
        "url": "https://empire-ai.co.uk",
        "niche": "storm restoration",
        "locations": [{"city": "San Antonio", "state": "TX"}, {"city": "Austin", "state": "TX"}, {"city": "Tulsa", "state": "OK"}],
        "timeframe": "30_days",
        "priority_filter": "high"
    },
    "context": {"source": "mission-control"}
})
print(result)

# Execute the skill — competitive analysis
result = registry.execute("marketing.seo-expert", {
    "params": {
        "goal": "Competitive backlink and content gap analysis for DFW metro storm restoration",
        "seo_type": "competitive_analysis",
        "url": "https://empire-ai.co.uk",
        "competitors": ["https://competitor1.com", "https://competitor2.com", "https://competitor3.com"],
        "niche": "storm restoration",
        "target_keywords": ["storm damage repair Dallas", "hail damage roofing Fort Worth", "emergency roof repair"],
        "timeframe": "30_days"
    },
    "context": {"source": "mission-control"}
})
print(result)
```
