---
type: skill
name: design.web-builder
version: 1.0.0
description: Landing page and website builder — design, structure, sections, CTAs, conversion optimization, and platform selection
tags:
  - domain:design
  - domain:marketing
  - mode:llm
  - pipeline:web
timeout_seconds: 60.0
max_retries: 2
execution_mode: llm
required_params:
  - goal
dependencies:
  - design.visual-color
  - design.visual-typography
  - content.seo
  - content.landing
---

# design.web-builder

Landing page and website builder — design conversion-optimized landing pages and multi-page websites with modern web standards.

## Overview

Design and build landing pages and websites tailored to the Empire AI contractor lead-gen ecosystem. Covers page architecture, section layout, conversion-focused design, platform/tech selection, responsive design, and SEO fundamentals. Outputs structured page blueprints, wireframe specifications, styling guidance, and implementation-ready copy and code snippets.

This skill bridges design strategy with practical web development — from low-fidelity wireframes through to production-ready HTML/CSS structure.

## Capabilities

- **Landing page architecture** — hero, value props, social proof, features, FAQ, footer — arranged in conversion-optimized order
- **Section design** — wireframe-level specs for each page section (headline, supporting copy, imagery, CTA placement, spacing)
- **Conversion Rate Optimization (CRO)** — CTA design, form placement, urgency triggers, trust signals, social proof layout, A/B testable variants
- **Multi-page site structure** — information architecture, navigation, internal linking, sitemap, content hierarchy
- **Platform selection** — static HTML/CSS, Tailwind, Bootstrap, Astro, Hugo, Next.js, or self-hosted tools (based on project constraints)
- **Responsive design** — mobile-first breakpoints, container widths, typography scaling, touch targets
- **Style system** — color palette assignment, typography scale, spacing rhythm, button/input/card styling tokens
- **SEO foundations** — semantic HTML structure, meta tags, heading hierarchy, alt text, structured data (JSON-LD), Core Web Vitals
- **Implementation scaffolding** — HTML boilerplate, CSS reset, component markup patterns, asset optimization

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `design.web-builder` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("design.web-builder", {"params": {}})
```

## Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| goal | string | ✅ | Primary goal (e.g. "capture contractor leads", "sell storm restoration services", "promote affiliate program") |
| audience | string | — | Target audience description (homeowners, contractors, carriers) |
| page_type | string | — | `landing` (single-page) or `website` (multi-page). Default: `landing` |
| sections | list | — | Specific sections needed. Defaults to standard landing page flow |
| brand_guidelines | string | — | Brand colors, fonts, voice for styling |
| platform | string | — | Target tech stack: `html-css`, `tailwind`, `bootstrap`, `astro`, `nextjs`, `hugo`. Default: `html-css` |
| cta_type | string | — | Primary CTA: `form`, `phone`, `chat`, `book`. Default: `form` |
| seo_keywords | list | — | Target keywords for SEO optimization |
| competitors | list | — | Competitor URLs or descriptions for differentiation |

## Output

A structured page blueprint with:

```json
{
  "page_blueprint": {
    "goal": "...",
    "page_type": "landing|website",
    "platform": "...",
    "sections": [
      {
        "type": "hero|features|social-proof|faq|cta|footer",
        "headline": "...",
        "supporting_copy": "...",
        "cta": { "text": "...", "type": "form|phone|book" },
        "imagery_spec": "...",
        "layout_hint": "left-text-right-image|centered|grid"
      }
    ],
    "style_tokens": {
      "colors": { "primary": "...", "secondary": "...", "accent": "...", "bg": "...", "text": "..." },
      "typography": { "headings": "...", "body": "...", "scale": "..." },
      "spacing": { "section_padding": "...", "container_max_width": "..." }
    },
    "seo": {
      "meta_title": "...",
      "meta_description": "...",
      "json_ld_type": "LocalBusiness|Product|Service",
      "heading_structure": ["h1", "h2", "h3", "..."]
    },
    "implementation": {
      "files": ["index.html", "style.css", "script.js"],
      "key_html_snippets": ["...hero section...", "...feature cards..."],
      "css_framework": "tailwind|bootstrap|vanilla"
    }
  },
  "cro_recommendations": [
    "Place primary CTA above the fold",
    "Add trust signals (BBB, Google Reviews) near form",
    "Use countdown timer for storm-response urgency"
  ],
  "a_b_testable_variants": [
    {"variant": "A", "headline": "...", "cta_text": "..."},
    {"variant": "B", "headline": "...", "cta_text": "..."}
  ]
}
```

## Example

```python
# Execute the skill
result = registry.execute("design.web-builder", {
    "params": {
        "goal": "Capture storm damage leads for roofing contractors in Dallas",
        "audience": "Homeowners with recent hail damage",
        "page_type": "landing",
        "platform": "tailwind",
        "cta_type": "phone",
        "seo_keywords": ["storm damage roof repair Dallas", "hail damage claim help"]
    },
    "context": {"source": "mission-control"}
})
print(result)
```
