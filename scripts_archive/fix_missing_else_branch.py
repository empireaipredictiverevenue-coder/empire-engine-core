#!/usr/bin/env python3
"""Fix: add ` : ''` to ternary expressions missing the else branch in template expressions."""
import sys

with open(sys.argv[1], 'rb') as f:
    content = f.read()

spa_start = content.find(b'SPA_JS = r' + b'"' * 3)
spa_end = content.rfind(b'"' * 3)
js_start = spa_start + len(b'SPA_JS = r' + b'"' * 3)
js = content[js_start:spa_end]

count = 0

# Pattern 1: html`...\n`}\n where } is the end of a ternary without : ''
# Find: backtick + backtick + } followed by newline
# The pattern: `} (backtick then closing brace) on its own line
# This should be ` : ''}

# Find occurrences where we have:
# a backtick on its own line (with just whitespace and `})
# This pattern: line with backtick followed by }

import re

# Pattern: whitespace + backtick + } + newline
# Where the backtick closes a tagged template and } closes a ${...} expression
# Fix: whitespace + backtick +  : '' + } + newline
old = b'`}\n'
new = b'` : \'\'}\n'

# Apply to JS content only, not entire file
idx = 0
fixes = []
while True:
    idx = js.find(old, idx)
    if idx < 0:
        break
    # Check that the backtick is preceded by whitespace (indentation line)
    # Look backwards to find the start of the line
    line_start = js.rfind(b'\n', 0, idx)
    if line_start < 0:
        line_start = 0
    else:
        line_start += 1
    
    # The line content should be just whitespace followed by `}
    line_content = js[line_start:idx+2]
    # Check if line_content is whitespace + `}
    stripped = line_content.lstrip()
    if stripped == b'`}':
        # This is a candidate for fixing
        js = js[:idx] + new + js[idx+3:]
        fixes.append(idx)
        idx += len(new)
        count += 1
    else:
        idx += 3

if count > 0:
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'wb') as f:
        f.write(content)
    print(f"FIXED: Added ` : ''}}` to {count} ternary expression(s)")
    for f_off in fixes:
        print(f"  Fixed at offset {f_off}")
else:
    print("No fixes needed")
