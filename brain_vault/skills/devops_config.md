---
type: skill
name: devops.config
version: "1.0"
description: Configuration validation — validate YAML, JSON, TOML, and INI configs
tags: [devops, config, validation]
timeout_seconds: 30
max_retries: 2
---

# devops.config

Configuration validation — validate YAML, JSON, TOML, and INI configs

## Overview

This skill provides capabilities for configuration validation — validate yaml, json, toml, and ini configs.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Validate YAML syntax and schema
- Check JSON config against expected structure
- Validate environment variable requirements
- Detect misconfigured or conflicting settings

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `devops.config` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("devops.config", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("devops.config", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
