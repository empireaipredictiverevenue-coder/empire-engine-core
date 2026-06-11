#!/usr/bin/env python3
"""Fix ALL missing closing } in template expressions that end with ` : ''"""
import re, sys

with open(sys.argv[1], 'r') as f:
    c = f.read()

# Find the SPA_JS content
marker = '_SPA_JS = r"""'
spa_start = c.find(marker)
spa_end = c.rfind('"""')
if spa_start < 0 or spa_end < 0:
    print("ERROR: Could not find SPA_JS marker")
    sys.exit(1)

js_start = spa_start + len(marker)
js = c[js_start:spa_end]

fixes = []

# Fix 1: The Pulse compliance IIFE - add } after ; })()
old1 = '      </div>\n      `; })()\n\n      ${allPartners.length > 0'
new1 = '      </div>\n      `; })()}\n\n      ${allPartners.length > 0'
if old1 in js:
    js = js.replace(old1, new1, 1)
    fixes.append("Fix 1: Added } after ; })() in Pulse compliance section")

# Fix 2: The Dispatch section stats expression - add } at end of line
# Pattern: ...</div>` : '' (no } at end)
# Need to find lines ending with ` : '' but not followed by }
old2 = "</div>` : ''\n\n      ${rows.length > 0"
new2 = "</div>` : ''}\n\n      ${rows.length > 0"
if old2 in js:
    js = js.replace(old2, new2, 1)
    fixes.append("Fix 2: Added } after Dispatch stats expression")

# Fix 3: Look for ALL lines ending with ` : '' (without }) and add }
# This is a broader fix
count = 0
lines = js.split('\n')
for i, line in enumerate(lines):
    stripped = line.strip()
    # Check if line ends with template close + ternary else
    # Pattern: ...` : '' — where ` is a backtick closing a template
    if "` : ''" in stripped:
        # Find the backtick position
        bt_pos = stripped.find("` : ''")
        if bt_pos >= 0:
            # Check if there's a } after '' on this line
            after = stripped[bt_pos + 6:]  # after "` : ''"
            # Also check line continuation - if next line starts with } it might already be closed
            if not after.strip().startswith('}') and not stripped.endswith('}'):
                # Check if this is truly the end of a template expression
                # The pattern is: ...html`...` : ''
                # The ` : '' is the backtick close, ternary else, and empty string
                # If there's no } after, it's a bug
                if stripped.endswith("''"):
                    # Add } at the end
                    lines[i] = line + '}'
                    count += 1
                    print(f"  Fixed line {i+1}: {stripped[:60]}...")

if count > 0:
    fixes.append(f"Fix 3: Added missing }} at {count} line(s)")
    js = '\n'.join(lines)

# Write back
c = c[:js_start] + js + c[spa_end:]

with open(sys.argv[1], 'w') as f:
    f.write(c)

if fixes:
    for f in fixes:
        print(f)
else:
    print("No fixes applied")
