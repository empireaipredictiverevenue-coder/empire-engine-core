---
type: skill
name: contractor.onboard
version: "1.0"
description: Contractor onboarding — verify, approve, and activate new contractors
tags: [contractor, onboarding, verification]
timeout_seconds: 30
max_retries: 2
---

# contractor.onboard

Contractor onboarding — verify, approve, and activate new contractors

## Overview

This skill provides capabilities for contractor onboarding — verify, approve, and activate new contractors.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Verify contractor credentials and licenses
- Run background and compliance checks
- Guide contractors through onboarding flow
- Track onboarding completion status

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.onboard` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.onboard", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.onboard", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
