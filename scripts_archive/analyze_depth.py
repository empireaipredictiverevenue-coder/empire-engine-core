#!/usr/bin/env python3
"""Track ${} depth inside template literals to find mismatch."""
import re, sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

lines = content.split('\n')

# Track state. We enter/exit template literals with backticks.
# Inside a template, we track ${...} depth as a stack.
# When a } arrives, we check if the stack has a matching ${.

depth = 0        # template expression depth (${...})
bt_depth = 0     # template literal nesting (0 = outside, 1+ = inside)
bt_stack = []    # for each template, track the ${ depth when it opened
errors = []

for i, line in enumerate(lines):
    linenum = i + 1
    j = 0
    while j < len(line):
        ch = line[j]
        
        # Backtick (unescaped) toggles template literal
        if ch == '`' and (j == 0 or line[j-1] != '\\'):
            if bt_depth > 0:
                # Exiting a template
                exit_depth = bt_stack.pop()
                if depth > exit_depth:
                    unclosed = depth - exit_depth
            errors.append(f"Line {linenum}:{j}: Exiting template with {unclosed} unclosed ${{}} expressions (depth was {depth}, exit at {exit_depth})")
                bt_depth -= 1
            else:
                # Entering a template
                bt_stack.append(depth)
                bt_depth += 1
            j += 1
            continue
        
        if bt_depth > 0:
            # Inside a template literal
            if ch == '$' and j + 1 < len(line) and line[j+1] == '{':
                depth += 1
                j += 2
                continue
            elif ch == '}' and depth > 0:
                # Check if this } closes the innermost ${}
                # Simple heuristic: assume every } when depth > 0 closes a template expression
                depth -= 1
                j += 1
                continue
            # Also track JS brace depth inside expressions? That's too complex.
        
        j += 1

print(f"End state: bt_depth={bt_depth}, depth={depth}")
print(f"Template stack: {bt_stack}")

if errors:
    print(f"\n{len(errors)} error(s) found:")
    for e in errors:
        print(f"  {e}")
else:
    print("\nNo errors found by simple depth analysis.")

# Now try to detect the specific error location by comparing behavior
# between the original (passes as .js) and modified (fails)
# The key insight is that Node ESM parser may handle } differently
# in template expressions when parsing CJS vs ESM
print(f"\nTotal backticks: {content.count('`')}")
