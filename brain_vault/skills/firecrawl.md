---
type: skill
name: scrape.firecrawl
version: 1.0.0
description: Open-source web scraping API optimized for LLMs and AI agents — scrape, search, and crawl at scale
tags: [domain:scraping, web, llm, data-extraction]
timeout_seconds: 120
max_retries: 2
execution_mode: llm
required_params:
  - action
  - url
dependencies: []
---

# Firecrawl — Web Scraping for LLMs Skill

Cloned from https://github.com/firecrawl/firecrawl.
Installed at `/root/firecrawl/`.

## Overview

Firecrawl is an open-source API designed to search, scrape, and interact with the web at scale, specifically optimized for LLMs and AI agents. It handles JavaScript rendering, IP blocking, CAPTCHAs, and extracts clean markdown/structured data.

## Key Features

- **Scrape**: Extract clean markdown/HTML from any URL (handles JS rendering)
- **Crawl**: Deep crawl entire domains with configurable depth and rate limits
- **Search**: Web search optimized for LLM consumption
- **Map**: Discover URLs on a domain via sitemaps and link analysis
- **Extract**: Structured data extraction with schema support

## Ecosystem

- `firecrawl-mcp-server` — MCP server for Claude Code, Cursor
- `firecrawl-cli` — Command-line interface
- `firecrawl-skills` — Agent skills for AI coding environments

## Self-Hosted Instance

Started via Docker:
```bash
cd /root/firecrawl && docker compose up -d
# Available at http://localhost:3002
```

## Parameters

- `action`: scrape, crawl, search, map, or extract
- `url`: Target URL (for scrape, crawl, map, extract)
- `query`: Search query (for search action)
- `max_pages`: Max pages to crawl (default 10) — for crawl action
- `formats`: Output formats (markdown, html, screenshot) — optional
- `include_tags`: CSS selectors to include — optional

## Usage

Self-hosted instances can use API without key:
```python
from firecrawl import Firecrawl
app = Firecrawl(api_key="fc-local")
result = app.scrape_url("https://example.com")
```

## Example

```
Input: action="scrape", url="https://example.com/products"
→ Output: Clean markdown content, metadata, and links from the page
```
