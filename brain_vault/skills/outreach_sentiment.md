---
type: skill
name: outreach.sentiment
version: "1.0"
description: Sentiment analysis — measure emotional tone in replies and conversations
tags: [outreach, sentiment, analysis]
timeout_seconds: 30
max_retries: 2
---

# outreach.sentiment

Sentiment analysis — measure emotional tone in replies and conversations

## Overview

This skill provides capabilities for sentiment analysis — measure emotional tone in replies and conversations.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Score sentiment (positive, neutral, negative) in messages
- Track sentiment trends over time per contact
- Alert on strongly negative interactions
- Correlate sentiment with conversion outcomes

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.sentiment` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.sentiment", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.sentiment", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
