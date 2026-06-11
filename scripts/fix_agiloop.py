#!/usr/bin/env python3
"""Fix the AgiLoop function: add missing closing brace and fix template structure"""

import subprocess
import re

# Read the committed JS
with open('/tmp/spa_committed.mjs', 'r') as f:
    js = f.read()

lines = js.split('\n')

# Find AgiLoop and Partners
agiloop_start = -1
partners_start = -1
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('function AgiLoop') and '{' in stripped:
        agiloop_start = i
    if agiloop_start >= 0 and partners_start < 0 and stripped.startswith('function Partners') and '{' in stripped:
        partners_start = i
        break

print(f'AgiLoop: line {agiloop_start+1} to {partners_start}')
print(f'Last line of AgiLoop ({partners_start}): {repr(lines[partners_start-1][:100])}')

# Check: is there a `}` on the last line of AgiLoop?
last_line = lines[partners_start - 1]
print(f'\nLast line ({partners_start}): {repr(last_line)}')
print(f'Last char: {repr(last_line[-1:]) if last_line else "N/A"}')

# The return ends with `;` but the function body needs `}` after
# Add `}` on a new line between AgiLoop's last line and Partners
if not last_line.rstrip().endswith('}'):
    print('\nAdding missing function close brace...')
    # Insert a new line with `}` before Partners
    lines.insert(partners_start, '}')
    print(f'Inserted }} before line {partners_start+1} (Partners)')
    print(f'Now AgiLoop ends at line {partners_start}')
    print(f'Partners is now at line {partners_start+1}')
else:
    print('\nLine already ends with } - no fix needed')

# Write fixed file
new_js = '\n'.join(lines)
with open('/tmp/spa_fixed_agiloop.mjs', 'w') as f:
    f.write(new_js)

# Test with node --check
r = subprocess.run(['node', '--check', '/tmp/spa_fixed_agiloop.mjs'], capture_output=True, text=True, timeout=15)
if r.returncode == 0:
    print('\nnode --check: PASS!')
else:
    print(f'\nnode --check: FAIL')
    # Check where error is now
    m = re.search(r':(\d+):', r.stderr)
    if m:
        err_line = int(m.group(1))
        print(f'  Error at line {err_line}: {r.stderr[:200]}')
        for i in range(max(0, err_line-2), min(len(lines), err_line+3)):
            marker = '>>>' if i == err_line-1 else '   '
            print(f'  {marker} {i+1}: {repr(lines[i][:120])}')
