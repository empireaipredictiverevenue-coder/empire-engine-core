---
type: skill
name: empire.lead_scorer
version: 1.0.0
description: Score the quality of a storm damage lead based on property data, urgency
  signals, and historical conversion patterns
tags:
- domain:custom
- mode:sync
- pipeline:scoring
timeout_seconds: 45.0
max_retries: 2
execution_mode: llm
required_params:
- lead
- niche
---

Analyze the storm damage lead and return a quality score (0-100).

Consider:
1. Urgency score (higher = better)
2. Property type (commercial > residential)
3. Damage severity (severe > moderate > minor)
4. Niche fit (roofing/hvac/restoration)
5. Phone/email presence (confirmed contact > missing)

Return a JSON object with: score (0-100), tier (hot/warm/cold), reasoning, recommended_action
