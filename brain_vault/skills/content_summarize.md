---
type: skill
name: content.summarize
version: "1.0"
description: Summarization — condense long documents into concise summaries
tags: [content, summarization, analysis]
timeout_seconds: 30
max_retries: 2
---

# content.summarize

Summarization — condense long documents into concise summaries

## Overview

This skill provides capabilities for summarization — condense long documents into concise summaries.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Summarize articles and reports at configurable lengths
- Extract key points from meeting transcripts
- Generate executive summaries from detailed documents
- Bullet-point summaries of research findings

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `content.summarize` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("content.summarize", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("content.summarize", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
