#!/usr/bin/env python3
"""Find unclosed template literal by tracking template depth."""
import sys

with open('/tmp/spa_final_check.js', 'rb') as f:
    lines = f.read().split(b'\n')

depth = 0  # template depth
interp_depth = 0  # interpolation depth inside template
in_interp = False
open_lines = []  # lines where templates open

for i, line in enumerate(lines):
    chars = []
    prev = b''
    for j, ch in enumerate(line):
        c = bytes([ch])
        
        if c == b'`' and not in_interp:
            if depth == 0:
                depth = 1
                open_lines.append((i+1, 'OPEN', line[:80]))
            else:
                depth = 0
        elif c == b'$' and j+1 < len(line) and bytes([line[j+1]]) == b'{' and depth > 0:
            in_interp = True
            interp_depth = 1
        elif c == b'{' and in_interp:
            interp_depth += 1
        elif c == b'}' and in_interp:
            interp_depth -= 1
            if interp_depth == 0:
                in_interp = False
        elif c == b'`' and in_interp:
            # Nested template inside interpolation
            depth += 1
            in_interp = False
    
    if depth > 0:
        print(f"Line {i+1}: depth={depth}, interp={interp_depth}, in_interp={in_interp}")

if depth > 0:
    print(f"\nUNCLOSED TEMPLATE at end of file! depth={depth}")
    print(f"Open lines: {open_lines}")
else:
    print("\nAll templates properly closed")
