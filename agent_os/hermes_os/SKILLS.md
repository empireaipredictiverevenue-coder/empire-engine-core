# HERMES MESH · Skills Registry

## Registered Skills

### 1. `mesh.task.create`
Create a new task ticket in the agent_task_queue.
- Input: task_type, payload, assigned_agent (optional), priority
- Output: ticket_id

### 2. `mesh.task.claim`
Atomically claim the next available task for an agent.
- Input: agent_name, task_types (optional filter)
- Output: task dict or null

### 3. `mesh.task.update`
Update a task's status (Done, Failed, Blocked, etc.).
- Input: ticket_id, status, result (optional), error (optional)
- Output: ok

### 4. `mesh.agent.heartbeat`
Register/ping an agent in the registry.
- Input: agent_name, status
- Output: ok

### 5. `mesh.status.report`
Full mesh snapshot — agents, queue stats, recent tasks.
- Input: none
- Output: structured mesh status

### 6. `scout.find_roofs`
Prospect roofs in storm zones via satellite imagery and risk data.
- Input: metro, niche, min_risk_score, max_results
- Output: list of roof targets with coordinates, risk score, priority
- **Task routing:** `scout.find_roofs` → `mesh.scout` (SLA: 30 min, Priority: High)
- **AGI/SI/PR aware:** Injects AGI Governor targeting strategy for ROI-weighted territory scoring

### 7. `outreach.draft_email`
Draft and send outreach messages to storm chaser prospects.
- Input: prospect_name, niche, message_tone, channel (email, sms), follow_up_count
- Output: drafted message, delivery status, reply tracking
- **Task routing:** `outreach.draft_email` → `mesh.outreach` (SLA: 5 min, Priority: Critical)
- **AGI/SI/PR aware:** Injects SI best-per-niche insights, Predictive Revenue close rate for personalized messaging

### 8. `studio.write_script`
Write a video script for a target audience and niche.
- Input: niche, audience, call_to_action, duration_seconds, hook_style
- Output: full video script with hook, body, CTA, and visual notes
- **Task routing:** `studio.write_script` → `mesh.studio_copy` (SLA: 60 min, Priority: Medium)
- **AGI/SI/PR aware:** Injects Predictive Revenue conversion metrics to tune CTA effectiveness

### 9. `studio.render_reel`
Render a video reel from a script using FFmpeg and TTS.
- Input: script_text, voice_profile, background_asset, duration, format
- Output: rendered video file path or URL, render metadata
- **Task routing:** `studio.render_reel` → `mesh.studio_render` (SLA: 10 min, Priority: High)
- **AGI/SI/PR aware:** Injects close-rate data to prioritize high-conversion niches in rendering queue

### 10. `revenue.connect_buyer`
Connect a qualified lead with a buyer/contractor for claim dispatch.
- Input: lead_id, contractor_id, niche, estimated_claim_value, metadata
- Output: dispatch record with status, buyer confirmation, tracking ID
- **Task routing:** `revenue.connect_buyer` → `mesh.dispatcher` (SLA: 5 min, Priority: Critical)
- **AGI/SI/PR aware:** Injects Predictive Revenue fee forecast, AGI Governor prioritization for dispatch routing

### 11. `revenue.score_call`
Score a sales call recording for quality and conversion probability.
- Input: call_recording_url_or_text, transcript, lead_id, agent_id
- Output: quality score (0–100), conversion probability (%), improvement recommendations
- **Task routing:** `revenue.score_call` → `mesh.quality` (SLA: 15 min, Priority: Medium)
- **AGI/SI/PR aware:** Injects Predictive Revenue data for scoring calibration, AGI strategy for quality thresholds

### 12. `swarm.fire`
Execute a swarm fire — simultaneous TTS calls to target list via Kokoro/Ollama.
- Input: target_list, script, voice_params, max_concurrent, tts_model
- Output: swarm dispatch results, call outcomes per target, aggregate stats
- **Task routing:** `swarm.fire` → `mesh.swarm_worker` (SLA: 5 min, Priority: High) · `swarm.strike_video` → `mesh.swarm_worker` (SLA: 10 min, Priority: Medium)
- **AGI/SI/PR aware:** Injects real-time AGI Governor resource budget, Predictive Revenue SLA constraints for swarm throughput

### 13. `scrape.web`
Extract structured data from web pages using firecrawl or Playwright.
- Input: url, data_schema, max_pages, format (markdown, json, structured)
- Output: extracted data in requested format, fetch metadata
- **Task routing:** `scrape.web` → `mesh.scraper` (SLA: 30 min, Priority: High) · `scrape.crawl` → `mesh.scraper` (SLA: 120 min, Priority: Medium)
- **AGI/SI/PR aware:** Injects AGI Governor efficiency targets for crawl depth and breadth balancing

### 14. `agentic.plan`
Create an execution plan for a complex multi-step task.
- Input: objective, context, constraints, available_agents, deadline
- Output: structured plan with steps, agent assignments, dependencies, timeline
- **Task routing:** `agentic.plan` → `mesh.orchestrator` (SLA: 30 min, Priority: High) · `agentic.review` → `mesh.orchestrator` (SLA: 30 min, Priority: High) · `autoresearch.orchestrate` → `mesh.orchestrator` (SLA: 360 min, Priority: Low)
- **AGI/SI/PR aware:** Injects full AGI Governor strategy, SI genome traits for optimal agent selection and task prioritization

### 15. `mesh.marketing.execute`
Execute a marketing skill from the Skills Framework. Loads the SKILL.md prompt template and runs it via LLM.
- Input: skill_name (e.g. marketing.emails), params (audience, goal, tone, etc.)
- Output: skill result with LLM output, instructions loaded, execution mode (llm or analysis_only)
- **Task routing:** `marketing.execute` → `mesh.marketing` (SLA: 30 min, Priority: High) · `marketing.emails` → `mesh.marketing` (SLA: 120 min, Priority: High) · `marketing.cold-email` → `mesh.marketing` (SLA: 240 min, Priority: High) · `marketing.sms` → `mesh.marketing` (SLA: 120 min, Priority: Critical) · `marketing.ads` → `mesh.marketing` (SLA: 720 min, Priority: High) · `marketing.copywriting` → `mesh.marketing` (SLA: 240 min, Priority: High) · `marketing.social` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.analytics` → `mesh.marketing` (SLA: 240 min, Priority: Low) · `marketing.video` → `mesh.marketing` (SLA: 240 min, Priority: Medium) · `marketing.cro` → `mesh.marketing` (SLA: 120 min, Priority: High) · `marketing.content-strategy` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.referrals` → `mesh.marketing` (SLA: 240 min, Priority: Medium) · `marketing.revops` → `mesh.marketing` (SLA: 240 min, Priority: Medium) · `marketing.product` → `mesh.marketing` (SLA: 1440 min, Priority: Low) · `marketing.seo-audit` → `mesh.marketing` (SLA: 120 min, Priority: High) · `marketing.lead-magnets` → `mesh.marketing` (SLA: 240 min, Priority: High) · `marketing.prospecting` → `mesh.marketing` (SLA: 480 min, Priority: Medium) · `marketing.ad-creative` → `mesh.marketing` (SLA: 480 min, Priority: Medium) · `marketing.ab-testing` → `mesh.marketing` (SLA: 180 min, Priority: Medium) · `marketing.onboarding` → `mesh.marketing` (SLA: 240 min, Priority: Medium) · `marketing.signup` → `mesh.marketing` (SLA: 120 min, Priority: High) · `marketing.offers` → `mesh.marketing` (SLA: 240 min, Priority: Medium) · `marketing.launch` → `mesh.marketing` (SLA: 1440 min, Priority: Low) · `marketing.customer-research` → `mesh.marketing` (SLA: 1440 min, Priority: Low) · `marketing.ideas` → `mesh.marketing` (SLA: 240 min, Priority: Medium) · `marketing.pr` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.co-marketing` → `mesh.marketing` (SLA: 2880 min, Priority: Low) · `marketing.community` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.image` → `mesh.marketing` (SLA: 480 min, Priority: Medium) · `marketing.copy-editing` → `mesh.marketing` (SLA: 240 min, Priority: High) · `marketing.programmatic-seo` → `mesh.marketing` (SLA: 10080 min, Priority: Low) · `marketing.schema` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.ai-seo` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.aso` → `mesh.marketing` (SLA: 720 min, Priority: Medium) · `marketing.free-tools` → `mesh.marketing` (SLA: 480 min, Priority: Medium) · `marketing.directory-submissions` → `mesh.marketing` (SLA: 1440 min, Priority: Low) · `marketing.churn-prevention` → `mesh.marketing` (SLA: 720 min, Priority: High) · `marketing.competitor-profiling` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.competitors` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.marketing-plan` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.marketing-psychology` → `mesh.marketing` (SLA: 480 min, Priority: Medium) · `marketing.pricing` → `mesh.marketing` (SLA: 480 min, Priority: Medium) · `marketing.sales-enablement` → `mesh.marketing` (SLA: 480 min, Priority: Medium) · `marketing.site-architecture` → `mesh.marketing` (SLA: 1440 min, Priority: Low) · `marketing.keyword-research` → `mesh.marketing` (SLA: 240 min, Priority: High) · `marketing.link-building` → `mesh.marketing` (SLA: 2880 min, Priority: Medium) · `marketing.local-seo` → `mesh.marketing` (SLA: 240 min, Priority: High) · `marketing.technical-seo` → `mesh.marketing` (SLA: 480 min, Priority: High) · `marketing.popups` → `mesh.marketing` (SLA: 240 min, Priority: Medium) · `marketing.paywalls` → `mesh.marketing` (SLA: 480 min, Priority: Medium) · `content.seo` → `mesh.marketing` (SLA: 60 min, Priority: Medium) · `social.scraper` → `mesh.marketing` (SLA: 60 min, Priority: Medium) · `social.facebook-bot` → `mesh.marketing` (SLA: 15 min, Priority: High) · `prompts.optimize` → `mesh.marketing` (SLA: 15 min, Priority: High) · `scientific.research` → `mesh.marketing` (SLA: 60 min, Priority: Low)
- **AGI/SI/PR aware: System context (AGI Governor strategy, SI genome traits, Predictive Revenue forecast) is injected into the LLM system prompt. Skills can adapt recommendations based on current close rate, revenue targets, and strategic priorities.

### 16. `mesh.email.execute`
Execute an email marketing skill from the Skills Framework. Covers strategy, deliverability, compliance, sequences, copywriting, analytics, and provider integrations.
- Input: skill_name (e.g. email.sequence, email.deliverability, email.compliance-can-spam), params (campaign goal, audience, provider, compliance requirements, etc.)
- Output: email marketing guidance with specific recommendations, compliance checks, and implementation steps
- **Task routing:** `email.execute` → `mesh.email` (SLA: 30 min, Priority: High)
- **AGI/SI/PR aware: Injects live AGI Governor strategy, SI best-per-niche, and Predictive Revenue metrics (24h revenue, MRR, close rate) into the skill's system prompt for context-aware recommendations.

### 17. `mesh.design.execute`
Execute a design skill from the Skills Framework. Each design skill provides expert guidance across UI, UX, visual, motion, accessibility, and design ops disciplines.
- Input: skill_name (e.g. design.ui-screen, design.visual-color, design.a11y-audit), params (goal, audience, constraints, brand_guidelines, etc.)
- Output: design guidance with recommendations, rationale, alternatives
- **Task routing:** `design.execute` → `mesh.design` (SLA: 30 min, Priority: High) · `design.ui-component` → `mesh.design` (SLA: 60 min, Priority: Medium) · `design.ui-layout` → `mesh.design` (SLA: 120 min, Priority: Medium) · `design.ui-screen` → `mesh.design` (SLA: 120 min, Priority: High) · `design.ux-flow` → `mesh.design` (SLA: 60 min, Priority: High) · `design.ux-wireframe` → `mesh.design` (SLA: 120 min, Priority: Medium) · `design.ux-prototype` → `mesh.design` (SLA: 240 min, Priority: High) · `design.ux-research` → `mesh.design` (SLA: 480 min, Priority: Medium) · `design.visual-brand` → `mesh.design` (SLA: 1440 min, Priority: Medium) · `design.visual-color` → `mesh.design` (SLA: 120 min, Priority: High) · `design.visual-typography` → `mesh.design` (SLA: 120 min, Priority: Medium) · `design.visual-iconography` → `mesh.design` (SLA: 180 min, Priority: Low) · `design.visual-data-viz` → `mesh.design` (SLA: 240 min, Priority: Medium) · `design.system-tokens` → `mesh.design` (SLA: 240 min, Priority: Low) · `design.system-component-library` → `mesh.design` (SLA: 480 min, Priority: Medium) · `design.system-documentation` → `mesh.design` (SLA: 240 min, Priority: Low) · `design.motion-microinteractions` → `mesh.design` (SLA: 60 min, Priority: Medium) · `design.motion-transitions` → `mesh.design` (SLA: 120 min, Priority: Medium) · `design.motion-loading` → `mesh.design` (SLA: 60 min, Priority: Low) · `design.a11y-color` → `mesh.design` (SLA: 120 min, Priority: High) · `design.a11y-interaction` → `mesh.design` (SLA: 180 min, Priority: Critical) · `design.a11y-audit` → `mesh.design` (SLA: 240 min, Priority: High) · `design.ops-workflow` → `mesh.design` (SLA: 240 min, Priority: Medium) · `design.ops-critique` → `mesh.design` (SLA: 120 min, Priority: Medium) · `design.ops-design-sprint` → `mesh.design` (SLA: 480 min, Priority: High) · `design.web-builder` → `mesh.design` (SLA: 120 min, Priority: High)
- **AGI/SI/PR aware: Design recommendations are aligned with current AGI strategy (e.g. cost-optimization → minimal-effort designs), SI genome traits, and revenue targets

### 18. `mesh.autoresearch.run`

Execute an autoresearch experiment on a target. This is the recursive self-healing loop skill.
- Input: target (e.g. "contractor_sms", "storm_strike", "trading", "sniper", "weather", "email_subject", "buyer")
- Output: experiment result with score comparison

### 19. `mesh.autoresearch.scratchpad`
Read the unified measurement program (scratchpad.md) for current system status across all targets.
- Input: none
- Output: scratchpad contents with per-target metrics

### 20. `mesh.autoresearch.browser`
Execute browser-based research using the dev-browser harness (wraps dev-browser for scraping, form filling, and automation).
- Input: action (scrape_page, submit_form, run_script), target_url, params
- Output: browser interaction results

### 21. `mesh.autoresearch.orchestrate`
Run the full recursive meta-loop — executes all autoresearch targets in sequence and aggregates results.
- Input: dry_run (optional boolean)
- Output: complete run report with per-target outcomes

### 22. `browser.dev-browser`
Browser automation via dev-browser — sandboxed Playwright API for AI agents.
- Input: action (scrape, form_fill, screenshot, automate), url, params
- Output: browser interaction results (text, screenshots, page data)

### 23. `prompts.prompt-master`
Prompt engineering framework — converts vague requests into structured, high-quality prompts.
- Input: request, target_tool (optional), output_format (optional), context (optional)
- Output: optimized prompt ready for target AI tool

### 24. `skills.claude-skills`
Hundreds of production-ready skills for Claude Code, Cursor, Aider, Gemini CLI.
- Input: domain, query, tool (optional)
- Output: matching skill instructions, CLI tool usage, integration guide

### 25. `text.humanizer`
AI text humanizer — detects and strips AI-generated patterns from writing.
- Input: text, aggressiveness (optional), preserve_length (optional)
- Output: humanized text with AI tells removed

### 26. `memory.supermemory`
RAG memory engine — persistent user profiles, auto-syncing, conversation memory extraction.
- Input: action (store, retrieve, search, sync, extract), query, source, limit
- Output: memory operation result

### 27. `scientific.scientific-agent-skills`
140+ scientific domain skills — bioinformatics, genomics, drug discovery, physics, materials science.
- Input: domain, task, query, databases (optional)
- Output: scientific skill instructions, database access, analysis workflows

### 28. `scrape.firecrawl`
Open-source web scraping optimized for LLMs — scrape, crawl, search, map, extract.
- Input: action, url, query, max_pages, formats
- Output: clean markdown/structured data from web pages

### 29. `agentic.superpowers`
Agentic skills framework — Socratic brainstorming, TDD, planning, subagent dev, code review.
- Input: capability (brainstorm, tdd, plan, delegate, review, design-skill), task, context
- Output: structured workflow result

### 30. `consulting.strategy`
Strategic business consulting — market analysis, growth strategy, pricing optimization, competitive positioning.
- Input: goal, business_context, constraints (optional), audience (optional), depth (optional: strategic/tactical/operational)
- Output: strategic analysis with domain coverage, structured input for LLM, recommendations pending flag
- **Task routing:** `consulting.strategy` → `mesh.orchestrator` (SLA: 30 min, Priority: High)
- **AGI/SI/PR aware:** Injects full AGI Governor strategy, SI genome traits for context-aware business recommendations

### 31. `mesh.delegate`
Task delegation engine — breaks down complex objectives into subtasks, maps to most capable agents via keyword matching, creates task tickets in agent_task_queue.
- Input: objective, context (optional), deadline (optional), auto_create_tasks (optional boolean)
- Output: execution plan with subtask breakdown, agent assignments, priorities, ticket IDs (if auto_create_tasks=true)
- **Task routing:** `mesh.delegate` → `mesh.orchestrator` (SLA: 5 min, Priority: High)
- **AGI/SI/PR aware:** Maps to 14 available agents via keyword matching. Agent capability registry includes scout, outreach, dispatcher, studio, quality, swarm, marketing, design, email, scraper, orchestrator, autoresearch, browser

## Mesh Agents Managed
- mesh.scout — Finds targets in storm zones
- mesh.outreach — Sends messages
- mesh.dispatcher — Dispatches contractors
- mesh.studio_copy — Writes copy
- mesh.studio_render — Renders videos
- mesh.quality — Scores calls
- mesh.swarm_worker — Executes swarm TTS calls and strike video generation via Kokoro/Ollama/FFmpeg pipeline
- mesh.marketing — Executes the 45 marketing skills (email, ads, SEO, referrals, CRO, etc.) via Skills Framework
- mesh.design — Executes the 24 design skills (UI, UX, visual, motion, accessibility, design ops) via Skills Framework
- mesh.email — Executes the 25 email marketing skills (strategy, deliverability, compliance, sequences, copy, analytics, provider config) via Skills Framework
- mesh.autoresearch — Runs the recursive self-healing loop (SMS, storm, email, buyer, trading, sniper, weather optimization)
- mesh.browser — Browser automation harness for autonomous web research via dev-browser
- mesh.orchestrator — Meta-loop orchestrator, runs the complete 5-hour nightly cycle
- mesh.scraper — Web scraping via firecrawl for LLM-optimized data extraction
