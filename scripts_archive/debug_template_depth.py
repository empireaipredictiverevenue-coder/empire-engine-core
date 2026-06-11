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
print(f"Total lines: {len(lines)}")

# Track template depth and interpolation
depth = 0
in_interp = False
interp_depth = 0
i = 0
line_num = 1

# Lines of interest
check_lines = {1396, 1398, 1400, 1402, 1420, 1422, 1424}

while i < len(js_bytes):
    b = js_bytes[i:i+1]
    
    # Count newlines to track line number
    if b == b'\n':
        line_num += 1
        if line_num in check_lines:
            print(f"Line {line_num}: depth={depth}, in_interp={in_interp}, interp_depth={interp_depth}")
        i += 1
        continue
    
    if b == b'`' and not in_interp:
        depth += 1
    elif b == b'`' and in_interp:
        pass  # Skip nested template tracking
    elif b == b'$' and i + 1 < len(js_bytes) and js_bytes[i+1:i+2] == b'{':
        if depth > 0 and depth % 2 == 1 and not in_interp:
            in_interp = True
            interp_depth = 1
        i += 2
        continue
    elif b == b'{' and in_interp:
        interp_depth += 1
    elif b == b'}' and in_interp:
        interp_depth -= 1
        if interp_depth == 0:
            in_interp = False
    elif b == b'\\' and i + 1 < len(js_bytes) and js_bytes[i+1:i+2] == b'"':
        if depth > 0 and depth % 2 == 1:
            pass  # Would replace
        i += 2
        continue
    
    i += 1

print(f"\nFinal: depth={depth}, in_interp={in_interp}")
