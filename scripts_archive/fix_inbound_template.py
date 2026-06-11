#!/usr/bin/env python3
"""Fix the Inbound section template bugs in empire_command_spa.py."""
import re, sys

with open(sys.argv[1], 'r') as f:
    c = f.read()

# Find the SPA_JS content
marker = '_SPA_JS = r"""'
spa_start = c.find(marker)
spa_end = c.rfind('"""')
if spa_start < 0 or spa_end < 0:
    print("ERROR: Could not find SPA_JS marker")
    sys.exit(1)

js_start = spa_start + len(marker)
js = c[js_start:spa_end]

fixes = 0

# Fix: Remove orphaned `${(calls.length === 0)` and connect ternary branches
# The pattern is: `} : ''}\n      ${(calls.length === 0)\n\n      ${calls.length > 0`
# Should become: `} : ''}\n      ${calls.length > 0`
old = "` : ''}\n\n      ${(calls.length === 0)\n\n      ${calls.length > 0"
new = "` : ''}\n\n      ${calls.length > 0"
if old in js:
    js = js.replace(old, new, 1)
    fixes += 1
    print("Fix 1: Removed orphaned ${(calls.length === 0)")
else:
    print("WARNING: Fix 1 pattern not found! Trying alternate...")
    # Try without \n\n
    old2 = "` : ''}\n      ${(calls.length === 0)\n\n      ${calls.length > 0"
    if old2 in js:
        js = js.replace(old2, new, 1)
        fixes += 1
        print("Fix 1a: Removed orphaned ${(calls.length === 0)")

# Fix: Add `${calls.length === 0` before the orphaned ? branch
# Pattern: `</div>` : ''}\n\n        ? html`<div class="tbl-empty">`
# Should become: `</div>` : ''}\n\n      ${calls.length === 0 ? html`<div class="tbl-empty">`
old3 = "      </div>` : ''}\n\n        ? html`<div class=\\\"tbl-empty\\\">"
new3 = "      </div>` : ''}\n\n      ${calls.length === 0 ? html`<div class=\\\"tbl-empty\\\">"
if old3 in js:
    js = js.replace(old3, new3, 1)
    fixes += 1
    print("Fix 2: Added ${calls.length === 0 before ? branch")
else:
    print("WARNING: Fix 2 pattern not found!")

if fixes > 0:
    c = c[:js_start] + js + c[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(c)
    print(f"Applied {fixes} fix(es)")
else:
    print("No fixes applied")
