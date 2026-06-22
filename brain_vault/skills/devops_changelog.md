---
type: skill
name: devops.changelog
version: "1.0"
description: Changelog generation — create release notes from git history
tags: [devops, changelog, release]
timeout_seconds: 30
max_retries: 2
---

# devops.changelog

Changelog generation — create release notes from git history

## Overview

This skill provides capabilities for changelog generation — create release notes from git history.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Generate changelog from git commit messages
- Categorize changes by type (feat, fix, chore)
- Group changes by release version
- Write human-readable release summaries

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `devops.changelog` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("devops.changelog", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("devops.changelog", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
