---
type: skill
name: memory.supermemory
version: 1.0.0
description: RAG memory engine for AI agents — persistent user profiles, auto-syncing external data, memory extraction from conversations
tags: [domain:memory, rag, context, agents, retrieval]
timeout_seconds: 60
max_retries: 2
execution_mode: llm
required_params:
  - action
dependencies: []
---

# Supermemory — RAG Memory Engine Skill

Cloned from https://github.com/supermemoryai/supermemory.
Installed at `/root/supermemory/`.

## Overview

Supermemory is a comprehensive memory and context engine for AI agents and applications. It provides RAG (Retrieval-Augmented Generation), persistent user profiles, auto-syncing of external data (Notion, Gmail, GitHub), and memory extraction from conversations.

## Key Features

- **Persistent Memory**: Store and retrieve agent memories across sessions
- **RAG Engine**: Semantic search over stored memories and documents
- **Auto-Sync**: Pull data from Notion, Gmail, GitHub, and other sources
- **Conversation Memory**: Extract and store important context from agent interactions
- **Plugin Ecosystem**: Plugins for OpenCode, Claude Code, and OpenClaw

## Plugin Ecosystem

The organization also maintains:
- `opencode-supermemory` — Plugin for OpenCode AI environment
- `claude-supermemory` — Plugin for Claude Code
- `openclaw-supermemory` — Plugin for OpenClaw agent

## Parameters

- `action`: Memory operation (store, retrieve, search, sync, extract)
- `query`: Search query or content to store (for retrieve/search/store actions)
- `source`: Data source to sync (notion, gmail, github) — for sync action
- `conversation`: Conversation text to extract memories from — for extract action
- `limit`: Max results to return (default 10) — for retrieve/search actions

## Usage

Supermemory can be used as a hosted API service or run locally. The skill interfaces with Supermemory to give agents persistent memory across sessions and conversations.

## Example

```
Input: action="retrieve", query="what did we discuss about pricing?"
→ Output: Relevant memories from previous conversations about pricing strategy
```
