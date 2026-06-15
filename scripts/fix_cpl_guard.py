#!/usr/bin/env python3
"""Fix null summary guard in CplPricing component."""
SPA_PATH = "/root/empire-v49/empire_command_spa.py"

with open(SPA_PATH, "r") as f:
    content = f.read()

old = '  if (error) return html`<div class="cpl-error">${error}</div>`;\n\n  const filtered'
new = '  if (error) return html`<div class="cpl-error">${error}</div>`;\n  if (!summary) return html`<div class="cpl-error">No lane pricing data available</div>`;\n\n  const filtered'

if old in content:
    content = content.replace(old, new)
    with open(SPA_PATH, "w") as f:
        f.write(content)
    print("OK: Added null summary guard")
else:
    print("WARN: Pattern not found")
