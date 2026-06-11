#!/usr/bin/env python3
"""Fix final leads closing: add missing ) for the (filtered.length === 0 paren."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

# Fix: Change "  })}\n\n// ── ACTIVITY LOG" to "  }))}\n\n// ── ACTIVITY LOG"
old = "  })}\n\n// ── ACTIVITY LOG"
new = "  }))}\n\n// ── ACTIVITY LOG"

if old in js:
    js = js.replace(old, new, 1)
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    print("FIXED: Added missing ) for (filtered.length paren")
else:
    print("Pattern not found!")
    # Debug
    idx = js.find("// ── ACTIVITY LOG")
    if idx >= 0:
        print(f"Context: {repr(js[idx-40:idx+10])}")
