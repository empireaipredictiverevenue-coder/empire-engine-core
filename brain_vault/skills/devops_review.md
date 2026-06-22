---
type: skill
name: devops.review
version: "1.0"
description: Code review — analyze pull requests for bugs, style issues, and improvements
tags: [devops, code-review, quality]
timeout_seconds: 30
max_retries: 2
---

# devops.review

Code review — analyze pull requests for bugs, style issues, and improvements

## Overview

This skill provides capabilities for code review — analyze pull requests for bugs, style issues, and improvements.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Review Python code for bugs and anti-patterns
- Check for security vulnerabilities
- Enforce code style and project conventions
- Suggest performance improvements

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `devops.review` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("devops.review", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("devops.review", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
