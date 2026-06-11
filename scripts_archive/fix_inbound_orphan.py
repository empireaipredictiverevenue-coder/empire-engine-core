#!/usr/bin/env python3
"""Fix all remaining template bugs in empire_command_spa.py."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

fixes = []

# Fix: Remove orphaned ${(calls.length === 0) and blank line
old = ": ''}\n      " + "${(calls.length === 0)\n\n      " + "${calls.length > 0"
new = ": ''}\n\n      " + "${calls.length > 0"
if old in js:
    js = js.replace(old, new, 1)
    fixes.append("Inbound: removed orphaned ${(calls.length === 0)")
else:
    print("WARNING: Fix 1 not found")
    # Check what's actually there
    idx = js.find("calls.length === 0")
    if idx >= 0:
        ctx = repr(js[idx-20:idx+40])
        print(f"  Found at {idx}: {ctx}")

# Write back
if fixes:
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    for f in fixes:
        print(f"FIX: {f}")
else:
    print("No fixes applied")
