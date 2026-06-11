#!/usr/bin/env python3
"""Fix Pulse section: close outer ${} after IIFE, remove orphaned } at line 380."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

fixes = []

# Fix 1: Close the ${} after IIFE: `; })() -> `; })()}
old1 = "      </div>\n      `; })()\n\n      ${allPartners.length > 0"
new1 = "      </div>\n      `; })()}\n\n      ${allPartners.length > 0"
if old1 in js:
    js = js.replace(old1, new1, 1)
    fixes.append("Added } after ; })()")
else:
    print("WARNING: Fix 1 not found")
    idx = js.find('; })()')
    if idx >= 0:
        ctx = js[idx-30:idx+30]
        print(f"  Found at {idx}: {repr(ctx)}")

# Fix 2: Remove orphaned } at line 380
old2 = "      </div>` : ''}\n    }\n\n      <div class=\"live-panel\">"
new2 = "      </div>` : ''}\n\n      <div class=\"live-panel\">"
if old2 in js:
    js = js.replace(old2, new2, 1)
    fixes.append("Removed orphaned } at line 380")
else:
    print("WARNING: Fix 2 not found")

# Write back
if fixes:
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    for f in fixes:
        print(f"FIX: {f}")
else:
    print("No fixes applied")
