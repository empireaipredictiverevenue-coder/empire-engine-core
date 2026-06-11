#!/usr/bin/env python3
"""Test if wrapping the mjs in an IIFE fixes the parsing issue."""
import subprocess

with open('/tmp/spa_module.mjs') as f:
    content = f.read()

# Write the original as .mjs
with open('/tmp/test_orig.mjs', 'w') as f:
    f.write(content)

# Write a wrapped version as .mjs
wrapped = f'(async () => {{\n{content}\n}})();\n'
with open('/tmp/test_wrapped.mjs', 'w') as f:
    f.write(wrapped)

# Also write a version that removes the initial empty line + adds empty export
with_fix = content.lstrip('\n')
with_fix = 'export {};\n' + with_fix
with open('/tmp/test_fixed.mjs', 'w') as f:
    f.write(with_fix)

# Test each version
for name, path in [('original', '/tmp/test_orig.mjs'),
                   ('wrapped in async IIFE', '/tmp/test_wrapped.mjs'),
                   ('export + no leading newline', '/tmp/test_fixed.mjs')]:
    r = subprocess.run(['node', '--check', path], capture_output=True, text=True, timeout=10)
    if r.returncode == 0:
        print(f'{name}: PASS')
    else:
        err_line = ''
        import re
        m = re.search(r':(\d+):', r.stderr)
        if m:
            err_line = f' at line {m.group(1)}'
        print(f'{name}: FAIL{err_line}')
        print(f'  {r.stderr[:300]}')
