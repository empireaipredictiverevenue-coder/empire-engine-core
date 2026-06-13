#!/usr/bin/env python3
"""Fix the unterminated string literal in tests/test_brain_personality_e2e.py."""
import re

with open('tests/test_brain_personality_e2e.py', 'r') as f:
    content = f.read()

# The issue: Line 1375 is just `        print(f"` and line 1376 continues the string
# We need to join them into one line
old = (
    '        print(f"'
    '\n'
    '    Generating 10 {persona.upper()} drafts (temp={draft_temp:.2f})...)'
)
new = '        print(f"\\n    Generating 10 {persona.upper()} drafts (temp={draft_temp:.2f})...")'

if old in content:
    content = content.replace(old, new)
    with open('tests/test_brain_personality_e2e.py', 'w') as f:
        f.write(content)
    print("Fixed successfully!")
else:
    print("Pattern not found. Checking exact content...")
    idx = content.find('print(f"')
    while idx >= 0:
        end = content.find('\n', idx)
        line = content[idx:end]
        if 'Generating' in line or 'Generating' in content[idx:idx+60]:
            print(f"Found at {idx}: {repr(line)}")
            # Check next 2 lines
            for j in range(2):
                nl_start = end + 1
                nl_end = content.find('\n', nl_start)
                print(f"  +1: {repr(content[nl_start:nl_end])}")
                end = nl_end
            break
        idx = content.find('print(f"', idx + 1)
    else:
        print("Could not find the 'Generating' print statement at all")
