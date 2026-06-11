#!/usr/bin/env python3
"""Fix Leads section: close statusActions template and properly terminate all open expressions."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

fixes = []

# The problem: `${statusActions.length > 0 ? html` at the end of the Leads function
# is never closed, and the ActivityLog function is consumed as template content.
# 
# Fix: replace the orphaned opening with a proper closing sequence:
# Close the template, the ternary, the IIFE, the container divs, then the function
# Then add the ActivityLog function header.
#
# Pattern:
#   ${statusActions.length > 0 ? html`
#   // ── ACTIVITY LOG ──
#   function ActivityLog() {
#
# Should become:
#   ` : ''}
#         </div>
#       `;}
#   </div>
#   `;}
#
# // ── ACTIVITY LOG ──
# function ActivityLog() {

# Find the exact text to replace
old = (
    '${statusActions.length > 0 ? html`\n'
    '// ── ACTIVITY LOG ─────────────────────────────────────────────────────\n'
    'function ActivityLog() {'
)

# The closing sequence for the Leads function
new = (
    "` : ''}\n"
    "            </div>\n"
    "          `; }\n"
    "      </div>\n"
    "    </div>\n"
    "  `;\n"
    "}\n"
    "\n"
    "// ── ACTIVITY LOG ─────────────────────────────────────────────────────\n"
    "function ActivityLog() {"
)

if old in js:
    js = js.replace(old, new, 1)
    fixes.append("Closed statusActions template and Leads function")
else:
    print("WARNING: Fix 1 pattern not found")
    # Debug: find the area
    idx = js.find('statusActions.length > 0')
    if idx >= 0:
        end_idx = js.find('function ActivityLog()', idx)
        if end_idx >= 0:
            snippet = js[idx:end_idx + 50]
            print(f"Found area ({len(snippet)} chars)")
            print(f"First 80: {repr(snippet[:80])}")
            print(f"Last 80: {repr(snippet[-80:])}")
        else:
            print(f"Found at {idx}, no ActivityLog after")
            ctx = repr(js[idx:idx+100])
            print(f"Context: {ctx}")

# Write back
if fixes:
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    for f in fixes:
        print(f"FIX: {f}")
else:
    print("No fixes applied")
