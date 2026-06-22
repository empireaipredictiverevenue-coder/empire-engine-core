---
type: skill
name: browser.dev-browser
version: 1.0.0
description: Browser automation via dev-browser — sandboxed Playwright API for AI agents to control browsers
tags: [domain:automation, browser, playwright, sandboxed]
timeout_seconds: 120
max_retries: 2
execution_mode: llm
required_params:
  - action
dependencies: []
---

# dev-browser — Browser Automation Skill

Cloned from https://github.com/SawyerHood/dev-browser (6.2k⭐).
Installed at `/root/dev-browser/`.

## Overview

dev-browser is a browser automation tool that lets AI agents control browsers using sandboxed JavaScript scripts. Scripts run in a QuickJS WASM environment with no host-system access.

## Capabilities

- **Navigate**: Go to URLs, wait for network idle, wait for selectors
- **Interact**: Click, fill forms, select options, hover, scroll
- **Extract**: Get text content, attributes, screenshots, HTML
- **Automate**: Form submission, multi-step workflows, login flows
- **Computer Use**: Pixel/vision-based interactions (`page.cua`) and DOM-element interactions (`page.domCua`)

## Usage

```bash
# Run a browser script
npx dev-browser run /path/to/script.js

# Script format:
const { page } = await browser.newPage();
await page.goto('https://example.com');
const title = await page.title();
const text = await page.evaluate(() => document.body.innerText);
await page.screenshot({ path: 'screenshot.png' });
await browser.close();
return { title, text };
```

## Parameters

- `action`: The browser action to perform (scrape, form_fill, screenshot, automate)
- `url`: Target URL (required for scrape/screenshot)
- `script`: Path to a .js script file (for automate action)
- `form_data`: JSON object of {selector: value} pairs (for form_fill)
- `wait_selector`: CSS selector to wait for before extracting
- `headless`: Boolean, whether to run headless (default: true)

## Example

```python
from skills.browser_harness import scrape_page, submit_form

# Scrape a page
result = scrape_page("https://example.com", wait_selector=".content")
print(result["title"], result["text_content"][:500])

# Fill and submit a form
result = submit_form("https://example.com/signup", {
    "#email": "user@example.com",
    "#name": "Test User"
})
```
