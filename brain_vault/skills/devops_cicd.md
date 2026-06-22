---
type: skill
name: devops.cicd
version: "1.0"
description: CI/CD pipeline — configure and manage continuous integration and deployment
tags: [devops, cicd, automation]
timeout_seconds: 30
max_retries: 2
---

# devops.cicd

CI/CD pipeline — configure and manage continuous integration and deployment

## Overview

This skill provides capabilities for ci/cd pipeline — configure and manage continuous integration and deployment.
It integrates with the Empire AI agent system through the VaultSkillDiscoverer
and ImmutableSkillRegistry.

## Capabilities

- Configure GitHub Actions workflows
- Set up automated test runs on PRs
- Manage deployment pipelines for staging/prod
- Monitor pipeline run status and failure rates

## Usage

This skill is available to any agent in the Empire AI fleet with access to
the `devops.cicd` skill. Invoke it through the skills framework:

```python
from skills import ImmutableSkillRegistry, VaultSkillDiscoverer

registry = ImmutableSkillRegistry()
discoverer = VaultSkillDiscoverer(registry)
discoverer.scan_and_register()
result = registry.execute("devops.cicd", {"params": {}})
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| params | dict | Execution parameters specific to this skill |
| context | dict | Optional context from calling agent |

## Example

```python
# Execute the skill
result = registry.execute("devops.cicd", {
    "params": {},
    "context": {"source": "mission-control"}
})
print(result)
```
