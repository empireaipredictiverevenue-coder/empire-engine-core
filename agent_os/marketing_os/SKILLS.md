# MARKETING OS · Skills Registry

## Overview
45 registered marketing skills sourced from the [marketingskills](https://github.com/coreyhaines31/marketingskills) repository. Each skill wraps a `SKILL.md` prompt template and is executable via the Skills Framework's `HarnessManager.run()`.

All skills are registered in `skills/marketing_skills.py` and wired into the hub's `empire_skills_init.py`. They are callable directly via `HarnessManager.run("marketing.<skill>", params)` or indirectly through the mesh task queue via `mesh.marketing.execute`.

### Execution modes
- **LLM mode** — If `ask_llm` is wired, the skill executes its SKILL.md prompt template against the LLM.
- **Analysis-only mode** — Without LLM, the skill returns the parsed instructions for manual execution.

---

### Product & Strategy

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.product` | `product-marketing` | Product marketing strategy — positioning, messaging, pricing, GTM, competitive differentiation |
| `marketing.marketing-plan` | `marketing-plan` | Marketing plan creation — channel mix, budget allocation, quarterly roadmaps |
| `marketing.pricing` | `pricing` | Pricing strategy — value-based pricing, tiering, packaging, discount psychology |
| `marketing.launch` | `launch` | Product launch strategy — pre-launch, launch day, post-launch campaigns and timing |
| `marketing.marketing-psychology` | `marketing-psychology` | Marketing psychology — persuasion triggers, cognitive biases, behavioral economics |

### Email & Outreach

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.emails` | `emails` | Email sequence design — drip campaigns, welcome series, lifecycle emails, behavior-triggered flows |
| `marketing.cold-email` | `cold-email` | Cold email outreach — copy templates, sequencing, deliverability, personalization |
| `marketing.sms` | `sms` | SMS marketing — campaign strategy, compliance (TCPA), automation, segmentation |
| `marketing.prospecting` | `prospecting` | B2B prospecting — ICP definition, lead sourcing, enrichment, sequencing |

### Paid Advertising

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.ads` | `ads` | Paid advertising campaigns — strategy, bidding, platform selection, optimization |
| `marketing.ad-creative` | `ad-creative` | Ad creative strategy — visual concepts, copy angles, creative testing frameworks |
| `marketing.offers` | `offers` | Offer strategy — discount design, bundling, pricing promotions, urgency tactics |

### Copy & Content

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.copywriting` | `copywriting` | Copywriting for landing pages, emails, ads, social, and web copy |
| `marketing.copy-editing` | `copy-editing` | Copy editing — clarity, concision, tone, grammar, brand voice consistency |
| `marketing.content-strategy` | `content-strategy` | Content strategy — editorial planning, topic clusters, content lifecycle |
| `marketing.video` | `video` | Video marketing strategy — content types, distribution, optimization, platforms |
| `marketing.image` | `image` | Visual content strategy — infographics, data visualization, branded imagery |
| `marketing.ideas` | `marketing-ideas` | Marketing idea generation — channel brainstorming, creative concepts, growth experiments |

### SEO & Search

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.programmatic-seo` | `programmatic-seo` | Programmatic SEO — template-based landing pages, structured data, scalable content |
| `marketing.schema` | `schema` | Schema markup strategy — structured data, rich snippets, knowledge graph |
| `marketing.ai-seo` | `ai-seo` | AI-powered SEO — LLM content optimization, AI search readiness, generative engine optimization |
| `marketing.seo-audit` | `seo-audit` | SEO audit — technical SEO review, content gap analysis, competitor benchmarking |
| `marketing.site-architecture` | `site-architecture` | Site architecture for SEO — information architecture, internal linking, URL structure |
| `marketing.aso` | `aso` | App Store Optimization — keyword strategy, conversion rate, creative optimization |
| `marketing.directory-submissions` | `directory-submissions` | Directory submission strategy — citation building, local SEO, niche directories |

### Conversion Rate Optimization (CRO)

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.cro` | `cro` | Conversion rate optimization — funnel analysis, UX testing, landing page optimization |
| `marketing.ab-testing` | `ab-testing` | A/B testing design — hypothesis formulation, test design, statistical significance, analysis |
| `marketing.signup` | `signup` | Signup flow optimization — form design, friction reduction, conversion rate |
| `marketing.onboarding` | `onboarding` | User onboarding design — activation flows, time-to-value, retention mechanics |
| `marketing.popups` | `popups` | Popup and overlay strategy — timing, targeting, design, conversion optimization |
| `marketing.paywalls` | `paywalls` | Paywall strategy — metering, hard walls, dynamic paywalls, subscriber conversion |

### Social & Community

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.social` | `social` | Social media marketing — platform strategy, content calendar, community management |
| `marketing.community` | `community-marketing` | Community marketing — building, engaging, and monetizing online communities |
| `marketing.co-marketing` | `co-marketing` | Co-marketing partnerships — partner selection, joint campaigns, co-branded content |

### Analytics & Operations

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.analytics` | `analytics` | Marketing analytics — metrics frameworks, dashboard design, attribution, KPI tracking |
| `marketing.revops` | `revops` | Revenue operations — funnel metrics, attribution, pipeline management, tooling stack |
| `marketing.sales-enablement` | `sales-enablement` | Sales enablement — battle cards, collateral, objection handling, playbooks |
| `marketing.churn-prevention` | `churn-prevention` | Churn prevention — retention strategies, win-back campaigns, at-risk detection |

### Growth & Lead Gen

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.referrals` | `referrals` | Referral program design — customer referrals, affiliate schemes, ambassador programs, viral loops |
| `marketing.lead-magnets` | `lead-magnets` | Lead magnet design — content upgrades, gated assets, value exchange optimization |
| `marketing.free-tools` | `free-tools` | Free tools as marketing — interactive tools, calculators, generators for lead gen |

### Research & Intelligence

| Skill | Directory | Description |
|-------|-----------|-------------|
| `marketing.customer-research` | `customer-research` | Customer research — surveys, interviews, persona development, jobs-to-be-done |
| `marketing.competitor-profiling` | `competitor-profiling` | Competitor profiling — intelligence gathering, positioning analysis, SWOT |
| `marketing.competitors` | `competitors` | Competitive analysis — feature comparison, pricing parity, differentiation |
| `marketing.pr` | `public-relations` | Public relations — press outreach, media kits, announcement strategy, crisis comms |

---

## Total: 45 registered skills

### Skills on disk without registration (4)
These `skills/marketingskills/skills/` directories have SKILL.md files but no corresponding `BaseSkill` class:
- `keyword-research` — keyword research & discovery
- `link-building` — backlink acquisition strategy
- `local-seo` — local business SEO optimization
- `technical-seo` — technical SEO audit & implementation

### Registration
All 45 skills are registered in `skills/marketing_skills.py` via `register_marketing_skills(registry, ask_llm=None)`. When `ask_llm` is wired, skills execute their SKILL.md prompt template against the LLM. AGI/SI/PR context is injected automatically by the HarnessManager's `SkillHarness._build_context()`.

### Mesh routing
Marketing skills are dispatched through the `agent_task_queue` via `marketing.*` task types. The `mesh.marketing` worker polls for these tasks and calls `/api/hermes/execute-skill` on the hub, which routes through `AgentMesh.execute_marketing_skill()` → `HarnessManager.run()`.
