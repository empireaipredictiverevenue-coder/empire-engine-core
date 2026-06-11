"""Robust template literal depth tracker.

Tracks template depth properly:
- Backticks toggle template depth when NOT inside interpolation
- `${` enters interpolation mode  
- Inside interpolation, only matching `}` exits it
- Inside interpolation, backticks open/close INNER templates
- We don't track inner template depth (just the outer depth)
"""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else 'empire_command_spa.py'

with open(path, 'rb') as f:
    content = f.read()

marker = b'_SPA_JS = r' + b'"' * 3
close_marker = b'"' * 3
spa_start = content.find(marker)
spa_js_start = spa_start + len(marker)
spa_end = content.rfind(close_marker)
js_bytes = content[spa_js_start:spa_end]

lines = js_bytes.split(b'\n')
print(f"Total: {len(lines)} lines")

# Track depth with proper nesting
tmpl_depth = 0       # template nesting depth
interp_depth = 0     # interpolation brace depth (0 = not in interpolation)
inner_tmpl = False   # inside a nested template (inside interpolation)
inner_backticks = 0  # count of backticks inside interpolation

line_num = 1
unclosed = []

i = 0
while i < len(js_bytes):
    b = js_bytes[i:i+1]
    
    if b == b'\n':
        line_num += 1
        i += 1
        continue
    
    # Handle escape sequences: skip the next character
    if b == b'\\' and i + 1 < len(js_bytes):
        i += 2
        continue
    
    if b == b'`':
        if interp_depth > 0:
            # Inside interpolation, toggle inner template
            inner_tmpl = not inner_tmpl
            inner_backticks += 1
        else:
            # Toggle outer template depth
            if tmpl_depth % 2 == 0:
                tmpl_depth += 1  # opening
            else:
                tmpl_depth -= 1  # closing
        i += 1
        continue
    
    if b == b'$' and i + 1 < len(js_bytes) and js_bytes[i+1:i+2] == b'{':
        if tmpl_depth % 2 == 1 and interp_depth == 0 and not inner_tmpl:
            # Enter interpolation
            interp_depth = 1
            i += 2
            continue
    
    if b == b'{':
        if interp_depth > 0 and not inner_tmpl:
            interp_depth += 1
        i += 1
        continue
    
    if b == b'}':
        if interp_depth > 0 and not inner_tmpl:
            interp_depth -= 1
            if interp_depth == 0 and inner_tmpl:
                # Backticks seen inside interpolation, but inner_tmpl not reset
                pass
        i += 1
        continue
    
    i += 1

print(f"Final: tmpl_depth={tmpl_depth}, interp_depth={interp_depth}, inner_tmpl={inner_tmpl}")
print(f"Inner backticks seen: {inner_backticks}")

if tmpl_depth % 2 == 1:
    print(f"UNCLOSED TEMPLATE: depth={tmpl_depth} at end of file")
