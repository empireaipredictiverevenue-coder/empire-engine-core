#!/usr/bin/env python3
"""Fix the Leads section closing: } -> })})"""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

# Find the pattern before ActivityLog
activ_idx = js.find('function ActivityLog()')
if activ_idx < 0:
    print("ERROR: Could not find ActivityLog")
    sys.exit(1)

# Look backwards for the lone }
before = js[activ_idx-50:activ_idx]
print("Before ActivityLog:")
print(repr(before))

# The fix: change `;\n        }\n\n// ──` to `;\n        })}\n\n// ──`
old = "`;\n        }\n\n// ── ACTIVITY LOG"
new = "`;\n        })}\n\n// ── ACTIVITY LOG"

if old in js:
    js = js.replace(old, new, 1)
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    print("FIXED: Changed } to })} before ActivityLog")
else:
    print("Pattern not found, trying alternate...")
    old2 = "`;\n        }\n// ── ACTIVITY LOG"
    if old2 in js:
        js = js.replace(old2, new, 1)
        content = content[:js_start] + js + content[spa_end:]
        with open(sys.argv[1], 'w') as f:
            f.write(content)
        print("FIXED (2): Changed } to })} before ActivityLog")
    else:
        # Check what's actually there
        idx = js.find("// ── ACTIVITY LOG")
        if idx >= 0:
            ctx = repr(js[idx-50:idx])
            print(f"Context at // ── ACTIVITY LOG: {ctx}")
