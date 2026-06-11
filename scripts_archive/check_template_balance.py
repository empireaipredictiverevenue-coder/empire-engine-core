#!/usr/bin/env python3
"""Check template literal balance by tracking backtick and ${} depth."""
with open('/tmp/spa_final_check.js', 'r') as f:
    lines = f.readlines()

depth = 0
interp_depth = 0
in_interp = False

for i, line in enumerate(lines):
    # Track backtick count (simplified - doesn't handle escaped backticks)
    bt_count = line.count('`')
    ds_count = line.count('${')
    cb_count = 0
    
    # Track closing braces for interpolations
    # Simple approach: count all braces
    ob_count = line.count('{')
    cb_count = line.count('}')
    
    # Track template depth: each backtick toggles
    for j, ch in enumerate(line):
        if ch == '`':
            if depth == 0:
                depth = 1  # opening template
            elif depth == 1:
                depth = 0  # closing template (assumes no nesting, which is wrong but works for basic tracking)
    
    if depth > 0 and ds_count > 0:
        pass  # has interpolations inside template
    
    # Check for unclosed template after ActivityLog start
    if 'function ActivityLog()' in line:
        print(f"Line {i+1}: ActivityLog starts, template depth={depth}")

# Check end of file
print(f"End of file: template depth={depth}")

# Also do a line-by-line check for empty backtick lines
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped == '`':
        print(f"Line {i+1}: Standalone backtick")
    if stripped == '`}' or stripped == '` ;':
        print(f"Line {i+1}: `}} or `;")
