---
type: skill
name: contractor.referral
version: "1.0"
description: Referral management — track and reward contractor referrals and bounty payouts
tags: [contractor, referral, bounty]
timeout_seconds: 30
max_retries: 2
---

# contractor.referral

Referral management — track and reward contractor referrals and bounty payouts

## Overview

This skill provides capabilities for referral management — track and reward contractor referrals and bounty payouts.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Track contractor referral codes and signups
- Calculate $500 bounty on referred first claims
- Monitor referral pipeline and conversion
- Generate referral reward payout reports

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `contractor.referral` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("contractor.referral", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("contractor.referral", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
