---
type: skill
name: agentic.superpowers
version: 1.0.0
description: Agentic skills framework — Socratic brainstorming, TDD enforcement, implementation planning, subagent-driven dev, automated code review
tags: [domain:agentic, development, tdd, code-review, planning]
timeout_seconds: 120
max_retries: 2
execution_mode: llm
required_params:
  - capability
dependencies: []
---

# Superpowers — Agentic Skills Framework Skill

Cloned from https://github.com/obra/superpowers.
Installed at `/root/superpowers/`.

## Overview

Superpowers is an agentic skills framework and software development methodology designed to extend AI coding agents (Claude Code, Cursor, Gemini CLI, GitHub Copilot CLI, OpenCode, and others).

## Key Capabilities

- **Socratic Brainstorming**: Structured exploration of problems and solutions
- **TDD Enforcement**: Test-driven development workflow enforcement
- **Implementation Planning**: Detailed step-by-step implementation plans
- **Subagent-Driven Development**: Delegate tasks to sub-agents
- **Automated Code Review**: Systematic code review with quality gates
- **Skill Design**: Framework for creating and testing new agent skills

## OpenCode Installation

```json
{
  "plugin": ["superpowers@git+https://github.com/obra/superpowers.git"]
}
```

## Parameters

- `capability`: The superpower to invoke (brainstorm, tdd, plan, delegate, review, design-skill)
- `task`: The task or problem description
- `context`: Additional context files or references — optional
- `constraints`: Any constraints or requirements — optional

## Usage

The skill applies the Superpowers methodology to the given task. It follows the structured workflows defined in the repo's test harnesses and skill templates.

## Example

```
Input: capability="plan", task="implement a REST API for contractor dispatch"
→ Output: Detailed implementation plan with file structure, data flow,
  test strategy, and deployment considerations
```
