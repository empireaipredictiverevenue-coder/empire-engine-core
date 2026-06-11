#!/usr/bin/env python3
"""Fix bug 2: add missing } at Dispatch stats expression."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

fixes = []

# Fix: Add missing } after : '' in Dispatch stats expression
old = "</div>` : ''\n\n      ${rows.length > 0"
new = "</div>` : ''}\n\n      ${rows.length > 0"
if old in js:
    js = js.replace(old, new, 1)
    fixes.append("Bug2: Added } at Dispatch stats")
else:
    print("WARNING: Fix 1 not found")
    # Debug
    idx = js.find("` : ''\n\n      ")
    if idx >= 0:
        ctx = repr(js[idx:idx+60])
        print(f"  Found at {idx}: {ctx}")

if fixes:
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    for f in fixes:
        print(f"FIX: {f}")
else:
    print("No fixes applied")
