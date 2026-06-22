---
type: skill
name: contractor.dispute
version: "1.0"
description: Dispute resolution — manage and resolve fee disputes with contractors
tags: [contractor, dispute, resolution]
timeout_seconds: 30
max_retries: 2
---

# contractor.dispute

Dispute resolution — manage and resolve fee disputes with contractors

## Overview

This skill provides capabilities for dispute resolution — manage and resolve fee disputes with contractors.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Log and categorize dispute cases
- Track dispute resolution timeline
- Suggest resolution options based on precedent
- Escalate unresolved disputes to human operators

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.dispute` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.dispute", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.dispute", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
