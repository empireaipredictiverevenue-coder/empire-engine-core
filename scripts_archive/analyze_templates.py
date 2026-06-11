#!/usr/bin/env python3
"""Analyze template literal nesting to find the 'Missing } in template expression' bug."""

import re, sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

lines = content.split('\n')

# Strategy: track template literal depth
# Every `(backtick) toggles being inside/outside a template literal
# Inside a template, ${ opens an expression and } closes it
# Outside a template, ${ is $ followed by { (not a template expression)

in_template = False
template_depth = 0
brace_depth = 0  # tracks ${...} depth inside templates

for i, line in enumerate(lines):
    linenum = i + 1
    col = 0
    while col < len(line):
        ch = line[col]
        if ch == '`' and (col == 0 or line[col-1] != '\\'):
            # Unescaped backtick toggles template literal
            in_template = not in_template
            if not in_template:
                # Exiting template - check if all expressions closed
                if brace_depth > 0:
                    print(f"Line {linenum} col {col}: LEFT TEMPLATE with {brace_depth} unclosed expression(s)!")
                    print(f"  Context: {line[max(0,col-20):col+30]}")
                    brace_depth = 0
            template_depth += 1 if in_template else -1
            col += 1
            continue
        
        if in_template:
            if ch == '$' and col + 1 < len(line) and line[col+1] == '{':
                brace_depth += 1
                col += 2
                continue
            elif ch == '}' and brace_depth > 0:
                # Check that this } closes a template expression, not a nested block
                # We need to track JS brace depth inside expressions
                brace_depth -= 1
                col += 1
                continue
        
        col += 1
    
    # Check for lines with issues
    if in_template and brace_depth > 0 and '}' not in line:
        # warn about lines inside unclosed expression
        pass

if in_template:
    print(f"\nERROR: File ends while still inside a template literal (depth={template_depth})")
elif brace_depth > 0:
    print(f"\nERROR: File ends with {brace_depth} unclosed template expression(s)")
elif not in_template and brace_depth == 0:
    print("\nOK: All template literals and expressions are balanced")
else:
    print(f"\nState: in_template={in_template}, template_depth={template_depth}, brace_depth={brace_depth}")

# Also count total backticks
backtick_count = content.count('`')
print(f"\nTotal backticks: {backtick_count} (should be even)")

# Find all backtick positions
bt_positions = []
for i, line in enumerate(lines):
    for col, ch in enumerate(line):
        if ch == '`':
            bt_positions.append((i+1, col))

# Show backtick around the error area (lines 270-340)
print("\nBacktick positions around error area:")
for ln, col in bt_positions:
    if 270 <= ln <= 340:
        ctx = lines[ln-1][max(0,col-5):col+10].strip()
        print(f"  Line {ln}:{col} ...{ctx}...")
