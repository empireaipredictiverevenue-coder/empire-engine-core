#!/usr/bin/env python3
"""Fix the Pulse compliance section template bug.

The `${(() => {` at line 289 is missing its closing `}` after `; })()` at line 348.
The `}` ended up orphaned at line 380.
Fix: Add `}` after `; })()` at line 348 (making it `; })()}`) and remove the orphaned `}` at line 380.
"""
import sys
import re

with open(sys.argv[1], 'r') as f:
    c = f.read()

# Find the SPA_JS content
spa_start = c.find('_SPA_JS = r"""')
spa_end = c.rfind('"""')
if spa_start < 0 or spa_end < 0:
    print("ERROR: Could not find SPA_JS marker")
    sys.exit(1)

# Get the JS content
js_start = spa_start + len('_SPA_JS = r"""')
js = c[js_start:spa_end]

# Fix 1: Change `; })()` to `; })()}` at the compliance IIFE close
# The pattern is the compliance panel close followed by the IIFE end
old1 = '      </div>\n      `; })()\n\n      ${allPartners.length > 0'
new1 = '      </div>\n      `; })()}\n\n      ${allPartners.length > 0'

if old1 in js:
    js = js.replace(old1, new1, 1)
    print("Fix 1: Added missing } after ; })()")
else:
    print("ERROR: Fix 1 pattern not found!")
    sys.exit(1)

# Fix 2: Remove the orphaned } at line 380 that was the closing brace for the ${} from line 289
# It's now orphaned since we added the } in Fix 1
# The pattern is `: ''}\n\n    }\n\n      <div class="live-panel"`
# The `}` at the outer indent level (4 spaces) should be removed
old2 = "      </div>` : ''}\n    }\n\n      <div class=\"live-panel\">"
new2 = "      </div>` : ''}\n\n      <div class=\"live-panel\">"

if old2 in js:
    js = js.replace(old2, new2, 1)
    print("Fix 2: Removed orphaned } at line 380")
else:
    print("WARNING: Fix 2 pattern not found (might already be fixed)")
    # Try with single newline before <div
    old2b = "      </div>` : ''}\n    }\n\n      <div class=\"live-panel\">"
    new2b = "      </div>` : ''}\n\n      <div class=\"live-panel\">"
    if old2b in js:
        js = js.replace(old2b, new2b, 1)
        print("Fix 2b: Removed orphaned } at line 380")
    else:
        print("Fix 2 not needed - orphaned } not found")

# Write back
c = c[:js_start] + js + c[spa_end:]

with open(sys.argv[1], 'w') as f:
    f.write(c)

print("Done!")
