---
type: skill
name: outreach.notify
version: "1.0"
description: Notification system — send alerts and updates via Telegram, email, and SMS
tags: [outreach, notifications, alerts]
timeout_seconds: 30
max_retries: 2
---

# outreach.notify

Notification system — send alerts and updates via Telegram, email, and SMS

## Overview

This skill provides capabilities for notification system — send alerts and updates via telegram, email, and sms.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Send Telegram messages with formatted content
- Send email notifications via Resend API
- Manage notification preferences per channel
- Batch notifications to prevent spam

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `outreach.notify` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("outreach.notify", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("outreach.notify", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
