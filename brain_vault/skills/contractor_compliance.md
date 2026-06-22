---
type: skill
name: contractor.compliance
version: "1.0"
description: Compliance checks — verify regulatory and legal compliance for contractors
tags: [contractor, compliance, legal]
timeout_seconds: 30
max_retries: 2
---

# contractor.compliance

Compliance checks — verify regulatory and legal compliance for contractors

## Overview

This skill provides capabilities for compliance checks — verify regulatory and legal compliance for contractors.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Check contractor licensing across states
- Verify insurance coverage expiry dates
- Track DNC compliance and opt-out lists
- Generate compliance audit reports

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.compliance` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.compliance", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.compliance", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
