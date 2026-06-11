"""Replace `\"` with `"` inside template literals in the SPA JS.

Inside JS template literals (backticks), double quotes don't need escaping.
But Node.js v24 ESM mode treats `\"` differently in some cases, causing
`Unexpected token 'class'` errors. The fix is to simply use `"` instead.

This script tracks template literal depth and only replaces `\"` when
inside a template literal, leaving string literals unchanged.
"""
import sys
import re

path = sys.argv[1] if len(sys.argv) > 1 else 'empire_command_spa.py'

with open(path, 'rb') as f:
    content = f.read()

# Find the JS content within the _SPA_JS = r"""...""" block
marker = b'_SPA_JS = r' + b'"' * 3
close_marker = b'"' * 3

spa_start = content.find(marker)
if spa_start < 0:
    print("ERROR: _SPA_JS marker not found")
    sys.exit(1)

spa_js_start = spa_start + len(marker)
# Find the closing """ - need to be smart about it
# The last """ in the file is the closing one
spa_end = content.rfind(close_marker)
if spa_end <= spa_js_start:
    print("ERROR: closing marker not found")
    sys.exit(1)

js_bytes = content[spa_js_start:spa_end]

# Now track template depth and replace `\"` with `"` inside templates
# Also handle the `\\\"` pattern (double backslash + quote)
result = []
depth = 0
in_interp = False
interp_depth = 0
i = 0

while i < len(js_bytes):
    b = js_bytes[i:i+1]
    
    if b == b'`' and not in_interp:
        depth += 1
        result.append(b'`')
        i += 1
    elif b == b'`' and in_interp:
        # Backtick inside interpolation closes the inner template only
        # But we don't track inner template depth here since we're in interp
        result.append(b'`')
        i += 1
    elif b == b'$' and i + 1 < len(js_bytes) and js_bytes[i+1:i+2] == b'{':
        if depth > 0 and depth % 2 == 1 and not in_interp:
            in_interp = True
            interp_depth = 1
        result.append(b'${')
        i += 2
    elif b == b'{' and in_interp:
        interp_depth += 1
        result.append(b'{')
        i += 1
    elif b == b'}' and in_interp:
        interp_depth -= 1
        if interp_depth == 0:
            in_interp = False
        result.append(b'}')
        i += 1
    elif b == b'\\' and i + 1 < len(js_bytes) and js_bytes[i+1:i+2] == b'"':
        if depth > 0 and depth % 2 == 1:
            # Inside a template! Replace `\"` with `"`
            result.append(b'"')
            i += 2
        else:
            # Outside template, keep as-is
            result.append(b'\\"')
            i += 2
    else:
        result.append(b)
        i += 1

fixed_js = b''.join(result)

# Write back to the Python file
new_content = content[:spa_js_start] + fixed_js + content[spa_end:]
with open(path, 'wb') as f:
    f.write(new_content)

old_count = js_bytes.count(b'\\"')
new_count = fixed_js.count(b'\\"')
replaced = old_count - new_count
print(f"Replaced {replaced} occurrences of `\\\"` with `\"` inside template literals")
print(f"Remaining `\\\"` outside templates: {new_count}")
