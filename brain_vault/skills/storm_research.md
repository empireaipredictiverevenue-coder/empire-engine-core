---
type: skill
name: custom.storm.research
version: 1.0.0
description: Research storm damage claims for a specific city
tags:
  - domain:custom
  - mode:sync
timeout_seconds: 30
max_retries: 2
execution_mode: llm
required_params:
  - city
dependencies:
  - brain.vault.search
---

Research storm damage claims in the specified city. Use the brain.vault.search
skill to find relevant storm history in the vault, then synthesize a summary
of recent storm events, common damage types, and average claim values.

Return a structured report with:
- city: the target city
- recent_storms: list of storm events found
- damage_types: common types of damage (hail, wind, flood)
- claim_estimate: estimated claim value range
- recommendations: actionable next steps
