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

### 6. `mesh.marketing.execute`
Execute a marketing skill from the Skills Framework. Loads the SKILL.md prompt template and runs it via LLM.
- Input: skill_name (e.g. marketing.emails), params (audience, goal, tone, etc.)
- Output: skill result with LLM output, instructions loaded, execution mode (llm or analysis_only)
- **Task routing:** `social.scraper` → `mesh.marketing` (SLA: 60 min, Priority: Medium) · `marketing.publishing` → `mesh.marketing` (SLA: 1440 min, Priority: Medium) · `marketing.advertising` → `mesh.marketing` (SLA: 720 min, Priority: High) · `content.seo` → `mesh.marketing` (SLA: 60 min, Priority: Medium) · `marketing.seo-expert` → `mesh.marketing` (SLA: 120 min, Priority: High)
- **AGI/SI/PR aware: System context (AGI Governor strategy, SI genome traits, Predictive Revenue forecast) is injected into the LLM system prompt. Skills can adapt recommendations based on current close rate, revenue targets, and strategic priorities.

### 7. `mesh.email.execute`
Execute an email marketing skill from the Skills Framework. Covers strategy, deliverability, compliance, sequences, copywriting, analytics, and provider integrations.
- Input: skill_name (e.g. email.sequence, email.deliverability, email.compliance-can-spam), params (campaign goal, audience, provider, compliance requirements, etc.)
- Output: email marketing guidance with specific recommendations, compliance checks, and implementation steps
- **Task routing:** `email.execute` → `mesh.email` (SLA: 30 min, Priority: High)
- **AGI/SI/PR aware: Injects live AGI Governor strategy, SI best-per-niche, and Predictive Revenue metrics (24h revenue, MRR, close rate) into the skill's system prompt for context-aware recommendations.

### 8. `mesh.design.execute`
Execute a design skill from the Skills Framework. Each design skill provides expert guidance across UI, UX, visual, motion, accessibility, and design ops disciplines.
- Input: skill_name (e.g. design.ui-screen, design.visual-color, design.a11y-audit), params (goal, audience, constraints, brand_guidelines, etc.)
- Output: design guidance with recommendations, rationale, alternatives
- **Task routing:** `design.execute` → `mesh.design` (SLA: 30 min, Priority: High)
- **AGI/SI/PR aware: Design recommendations are aligned with current AGI strategy (e.g. cost-optimization → minimal-effort designs), SI genome traits, and revenue targets

### 9. `mesh.autoresearch.run`

Execute an autoresearch experiment on a target. This is the recursive self-healing loop skill.
- Input: target (e.g. "contractor_sms", "storm_strike", "trading", "sniper", "weather", "email_subject", "buyer")
- Output: experiment result with score comparison

### 10. `mesh.autoresearch.scratchpad`
Read the unified measurement program (scratchpad.md) for current system status across all targets.
- Input: none
- Output: scratchpad contents with per-target metrics

### 11. `mesh.autoresearch.browser`
Execute browser-based research using the dev-browser harness (wraps dev-browser for scraping, form filling, and automation).
- Input: action (scrape_page, submit_form, run_script), target_url, params
- Output: browser interaction results

### 12. `mesh.autoresearch.orchestrate`
Run the full recursive meta-loop — executes all autoresearch targets in sequence and aggregates results.
- Input: dry_run (optional boolean)
- Output: complete run report with per-target outcomes

### 13. `browser.dev-browser`
Browser automation via dev-browser — sandboxed Playwright API for AI agents.
- Input: action (scrape, form_fill, screenshot, automate), url, params
- Output: browser interaction results (text, screenshots, page data)

### 14. `prompts.prompt-master`
Prompt engineering framework — converts vague requests into structured, high-quality prompts.
- Input: request, target_tool (optional), output_format (optional), context (optional)
- Output: optimized prompt ready for target AI tool

### 15. `skills.claude-skills`
Hundreds of production-ready skills for Claude Code, Cursor, Aider, Gemini CLI.
- Input: domain, query, tool (optional)
- Output: matching skill instructions, CLI tool usage, integration guide

### 16. `text.humanizer`
AI text humanizer — detects and strips AI-generated patterns from writing.
- Input: text, aggressiveness (optional), preserve_length (optional)
- Output: humanized text with AI tells removed

### 17. `memory.supermemory`
RAG memory engine — persistent user profiles, auto-syncing, conversation memory extraction.
- Input: action (store, retrieve, search, sync, extract), query, source, limit
- Output: memory operation result

### 18. `scientific.scientific-agent-skills`
140+ scientific domain skills — bioinformatics, genomics, drug discovery, physics, materials science.
- Input: domain, task, query, databases (optional)
- Output: scientific skill instructions, database access, analysis workflows

### 19. `scrape.firecrawl`
Open-source web scraping optimized for LLMs — scrape, crawl, search, map, extract.
- Input: action, url, query, max_pages, formats
- Output: clean markdown/structured data from web pages

### 20. `agentic.superpowers`
Agentic skills framework — Socratic brainstorming, TDD, planning, subagent dev, code review.
- Input: capability (brainstorm, tdd, plan, delegate, review, design-skill), task, context
- Output: structured workflow result

## Mesh Agents Managed
- mesh.scout — Finds targets in storm zones
- mesh.outreach — Sends messages
- mesh.dispatcher — Dispatches contractors
- mesh.studio_copy — Writes copy
- mesh.studio_render — Renders videos
- mesh.quality — Scores calls
- mesh.marketing — Executes the 45 marketing skills (email, ads, SEO, referrals, CRO, etc.) via Skills Framework
- mesh.design — Executes the 24 design skills (UI, UX, visual, motion, accessibility, design ops) via Skills Framework
- mesh.email — Executes the 25 email marketing skills (strategy, deliverability, compliance, sequences, copy, analytics, provider config) via Skills Framework
- mesh.autoresearch — Runs the recursive self-healing loop (SMS, storm, email, buyer, trading, sniper, weather optimization)
- mesh.browser — Browser automation harness for autonomous web research via dev-browser
- mesh.orchestrator — Meta-loop orchestrator, runs the complete 5-hour nightly cycle
- mesh.scraper — Web scraping via firecrawl for LLM-optimized data extraction
