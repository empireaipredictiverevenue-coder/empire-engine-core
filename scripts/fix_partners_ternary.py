#!/usr/bin/env python3
"""Fix: remove extra ` : ''}` in Partners section ternary where the else branch is already provided."""
import sys

with open(sys.argv[1], 'rb') as f:
    content = f.read()

spa_start = content.find(b'SPA_JS = r' + b'"' * 3)
spa_end = content.rfind(b'"' * 3)
js_start = spa_start + len(b'SPA_JS = r' + b'"' * 3)
js = content[js_start:spa_end]

# The pattern: backtick + space + colon + space + '' + }
# But the \` : ''} at position where the template from : html\` needs to close
# with the ternary already completed by : html\`
# Fix: change ` : ''} to `}

# Pattern: whitespace + backtick + : ''} followed by newline (where : '' is extra)
# We need to find the specific instance at the Partners section

# Search for specific context
old = b'              ` : \'\'}'
new = b'              `}'

count = js.count(old)
if count > 0:
    js = js.replace(old, new, 1)
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'wb') as f:
        f.write(content)
    print(f"FIXED: Removed extra `: ''}}` in Partners section")
else:
    print("Pattern not found")
    # Debug: find nearby context
    idx = js.find(b'pending_review')
    if idx >= 0:
        ctx = js[idx:idx+500]
        print(f"Context around 'pending_review':")
        print(ctx.decode('utf-8', errors='replace'))
