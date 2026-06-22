---
type: skill
name: contractor.payout
version: "1.0"
description: Payout processing — manage contractor payouts via USDC/Solana
tags: [contractor, payouts, payments]
timeout_seconds: 30
max_retries: 2
---

# contractor.payout

Payout processing — manage contractor payouts via USDC/Solana

## Overview

This skill provides capabilities for payout processing — manage contractor payouts via usdc/solana.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Process Solana USDC payouts to contractors
- Track payout history and status
- Handle payout retries and failure recovery
- Generate payout reports for accounting

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.payout` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.payout", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.payout", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
