---
type: skill
name: prompts.prompt-master
version: 1.0.0
description: Prompt engineering framework — converts vague requests into structured, high-quality prompts using 9-dimension intent extraction
tags: [domain:prompts, engineering, claude, llm]
timeout_seconds: 60
max_retries: 2
execution_mode: llm
required_params:
  - request
dependencies: []
---

# Prompt Master — Prompt Engineering Skill

Cloned from https://github.com/nidhinjs/prompt-master.
Installed at `/root/prompt-master/`.

## Overview

Prompt Master is an open-source framework that optimizes prompt engineering by converting vague, simple user requests into comprehensive, context-rich prompts suitable for any AI tool (ChatGPT, Gemini, Cursor, Midjourney, etc.).

## How It Works

Instead of making prompts longer, it uses a structured pipeline:

1. **Intent Extraction** — Analyzes the request across 9 dimensions: task, output, constraints, success criteria, audience, tone, format, examples, and edge cases
2. **Architecture Selection** — Automatically applies the optimal prompt architecture (chain-of-thought, few-shot, structured output, etc.)
3. **Tool Profiles** — Adapts output for 20+ AI tools (Claude, Cursor, ChatGPT, Gemini, Midjourney, etc.)

## Parameters

- `request`: The raw/ambiguous request to optimize
- `target_tool`: Which AI tool the prompt is for (e.g., "claude", "cursor", "chatgpt", "midjourney") — optional, defaults to "claude"
- `output_format`: Desired output format ("expanded", "structured", "concise") — defaults to "expanded"
- `context`: Additional context about the project or domain

## Usage

The skill reads the prompt-master profiles and applies them to the user's request. It returns an optimized prompt that can be used directly with the target AI tool.

## Example

```
Input: "Help me write a cold email"
→ Output: A fully structured prompt with target audience, tone constraints,
  success criteria, formatting requirements, and edge case handling
  tailored to the specified AI tool.
```
