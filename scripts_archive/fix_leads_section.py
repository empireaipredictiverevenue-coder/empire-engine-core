#!/usr/bin/env python3
"""Fix Leads section bugs: missing : '' in ternary, stray n character."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

fixes = []

# Fix: Add : '' before the closing } in the note button ternary
# Pattern: button>\\n                `}\\n              </div>\\n              ${statusActions.length
# Should be: button>\\n                ` : ''}\\n              </div>\\n              ${statusActions.length
old1 = "                  </button>\n                `}\n              </div>\n              ${statusActions.length > 0"
new1 = "                  </button>\n                ` : ''}\n              </div>\n              ${statusActions.length > 0"
if old1 in js:
    js = js.replace(old1, new1, 1)
    fixes.append("Added : '' in note button ternary")
else:
    print("WARNING: Fix 1 not found")
    # Debug
    idx = js.find("ld-note-save")
    if idx >= 0:
        ctx = repr(js[idx:idx+200])
        print(f"  Found at {idx}: {ctx}")

# Fix: Remove stray 'n' before Activity Log comment
# Pattern: n// ── ACTIVITY LOG ──
old2 = "\nn// ── ACTIVITY LOG ─────────────────────────────────────────────────────"
new2 = "\n// ── ACTIVITY LOG ─────────────────────────────────────────────────────"
if old2 in js:
    js = js.replace(old2, new2, 1)
    fixes.append("Removed stray n before Activity Log")
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
