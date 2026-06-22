---
type: skill
name: text.humanizer
version: 1.0.0
description: AI text humanizer — detects and strips AI-generated patterns (significance inflation, AI vocabulary, formulaic challenges) from writing
tags: [domain:text, writing, ai-detection, humanizer]
timeout_seconds: 30
max_retries: 2
execution_mode: llm
required_params:
  - text
dependencies: []
---

# Humanizer — AI Text Humanization Skill

Cloned from https://github.com/blader/humanizer.
Installed at `/root/humanizer/`.

## Overview

Humanizer detects patterns common in AI-generated writing and rewrites the input to sound more natural. It targets specific "AI tells" such as:

- **Significance Inflation**: Overuse of "crucial", "paramount", "landscape", "tapestry", "realm"
- **AI Vocabulary**: "Navigate the complexities", "foster innovation", "delve into", "a plethora of"
- **Formulaic Challenges**: "One of the most pressing challenges facing X today is..."
- **Hedge Words**: "It's worth noting that...", "It's important to consider...", "Let's explore..."

## Parameters

- `text`: The AI-generated text to humanize
- `aggressiveness`: How aggressively to strip AI patterns (1-5, default 3) — optional
- `preserve_length`: Whether to keep approximately the same length (boolean, default true) — optional

## Usage

The skill analyzes the input text for common AI writing patterns, removes or rewrites them, and returns more natural-sounding text that reads like human writing. It preserves the original meaning and factual content.

## Example

```
Input: "It's crucial to navigate the complex landscape of modern marketing strategies..."
→ Output: "Modern marketing strategies are complex, but here's what actually works..."
```
