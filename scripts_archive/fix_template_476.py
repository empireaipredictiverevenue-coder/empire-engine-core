#!/usr/bin/env python3
"""Fix Dispatch section missing } and scan for all template expression bugs."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

fixes = []

# Fix: Dispatch stats expression missing }
old = "</div>` : ''\n\n      ${rows.length > 0"
new = "</div>` : ''}\n\n      ${rows.length > 0"
if old in js:
    js = js.replace(old, new, 1)
    fixes.append("Dispatch stats: added }")

# Also check Inbound section for orphaned `${(calls.length === 0)
old2 = "` : ''}\n\n      ${(calls.length === 0)\n\n      ${calls.length > 0"
new2 = "` : ''}\n\n      ${calls.length > 0"
if old2 in js:
    js = js.replace(old2, new2, 1)
    fixes.append("Inbound: removed orphaned ${(calls.length === 0)")

# Fix orphaned ? branch in Inbound
old3 = "      </div>` : ''}\n\n        ? html`<div class=\"tbl-empty\">"
new3 = "      </div>` : ''}\n\n      ${calls.length === 0 ? html`<div class=\"tbl-empty\">"
if old3 in js:
    js = js.replace(old3, new3, 1)
    fixes.append("Inbound: added ${calls.length === 0 before ? branch")

# Write back
if fixes:
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    for f in fixes:
        print(f"FIX: {f}")
else:
    print("No fixes applied")
