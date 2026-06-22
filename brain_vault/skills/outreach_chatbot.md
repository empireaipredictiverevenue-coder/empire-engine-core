---
type: skill
name: outreach.chatbot
version: "1.0"
description: Chatbot configuration — build and configure conversational AI bots
tags: [outreach, chatbot, automation]
timeout_seconds: 30
max_retries: 2
---

# outreach.chatbot

Chatbot configuration — build and configure conversational AI bots

## Overview

This skill provides capabilities for chatbot configuration — build and configure conversational ai bots.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Configure chatbot flows and triggers
- Set up lead qualification questions
- Integrate with website and messaging platforms
- Review chatbot interaction transcripts

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.chatbot` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.chatbot", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.chatbot", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
