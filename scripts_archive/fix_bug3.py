#!/usr/bin/env python3
"""Fix bug 3: orphaned ${(calls.length === 0) and missing ${ before ? branch."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

fixes = []

# Fix 1: Remove orphaned ${(calls.length === 0) and blank line
old1 = ": ''}\n      ${(calls.length === 0)\n\n      ${calls.length > 0"
new1 = ": ''}\n\n      ${calls.length > 0"
if old1 in js:
    js = js.replace(old1, new1, 1)
    fixes.append("Bug3: Removed orphaned ${(calls.length === 0)")
else:
    print("WARNING: Fix 1 not found")

# Fix 2: Add ${calls.length === 0 before ? branch in Inbound table section
old2 = "` : ''}\n\n        ? html`<div class=\"tbl-empty\">"
new2 = "` : ''}\n\n      ${calls.length === 0 ? html`<div class=\"tbl-empty\">"
if old2 in js:
    js = js.replace(old2, new2, 1)
    fixes.append("Bug3: Added ${calls.length === 0 before ? branch")
else:
    print("WARNING: Fix 2 not found")
    # Debug
    idx = js.find('tbl-empty')
    if idx >= 0:
        ctx = repr(js[idx-40:idx+20])
        print(f"  Found tbl-empty at {idx}: {ctx}")

if fixes:
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    for f in fixes:
        print(f"FIX: {f}")
else:
    print("No fixes applied")
