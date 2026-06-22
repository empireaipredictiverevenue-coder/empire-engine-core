---
type: skill
name: skills.claude-skills
version: 1.0.0
description: Hundreds of production-ready skills for Claude Code, Cursor, Aider, Gemini CLI — engineering, marketing, C-level advisory, compliance
tags: [domain:skills, claude, cursor, production, multi-agent]
timeout_seconds: 60
max_retries: 2
execution_mode: llm
required_params:
  - domain
dependencies: []
---

# Claude Skills — Production-Ready Agent Skills

Cloned from https://github.com/alirezarezvani/claude-skills.
Installed at `/root/claude-skills/`.

## Overview

A comprehensive open-source library featuring hundreds of production-ready skills, agent plugins, and CLI scripts designed to extend AI coding agents. Supports Claude Code, OpenAI Codex, Gemini CLI, Cursor, Aider, Windsurf, and more.

## Skill Categories

The repo contains modular skills consisting of:
- **Structured Instructions** (`SKILL.md`) — Domain-specific prompt templates
- **CLI Tools** — Python standard library-based command-line utilities
- **Reference Templates** — For engineering, marketing, C-level advisory, compliance, and more

## Parameters

- `domain`: The domain to search for skills (e.g., "engineering", "marketing", "compliance", "c-level", "devops", "security")
- `query`: Specific question or task within the domain
- `tool`: Target AI coding tool (e.g., "claude", "cursor", "aider", "codex") — optional

## Usage

Search the claude-skills repository for the most relevant skill definition for the given domain and task. Return the skill instructions, CLI tool usage (if applicable), and how to apply it.

## Example

```
Input: domain="engineering", query="code review best practices"
→ Output: Relevant SKILL.md content, CLI tools for automated review,
  and integration instructions for Claude Code
```
