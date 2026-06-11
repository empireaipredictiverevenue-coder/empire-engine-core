#!/usr/bin/env python3
"""Fix bug 1: close outer ${} after IIFE in Pulse section."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

fixes = []

# Fix: Add } after ; })() to close the outer ${} from line 288
# Pattern: `; })()\n\n      ${allPartners.length > 0
# Should become: `; })()}\n\n      ${allPartners.length > 0
old1 = "`; })()\n\n      ${allPartners.length > 0"
new1 = "`; })()}\n\n      ${allPartners.length > 0"
if old1 in js:
    js = js.replace(old1, new1, 1)
    fixes.append("Bug1: Added } after ; })()")
else:
    print(f"WARNING: Fix 1 not found")

# Fix: Remove the orphaned } at line 380 (4 spaces indent, alone on line after amdTotal)
# Pattern: ` : ''}\n    }\n\n      <div class="live-panel">
old2 = "` : ''}\n    }\n\n      <div class=\"live-panel\">"
new2 = "` : ''}\n\n      <div class=\"live-panel\">"
if old2 in js:
    js = js.replace(old2, new2, 1)
    fixes.append("Bug1: Removed orphaned } at line 380")
else:
    print(f"WARNING: Fix 2 not found")

# Write back
if fixes:
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    for f in fixes:
        print(f"FIX: {f}")
else:
    print("No fixes applied")
