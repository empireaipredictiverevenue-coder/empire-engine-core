#!/usr/bin/env python3
"""Extract JS from command_spa.py and run node --check."""
import re, subprocess, sys

with open('empire_command_spa.py', 'r') as f:
    c = f.read()

spa_match = re.search(r'_SPA_JS = r"""', c)
closing = c.rfind('"""')
js_start = spa_match.end()
js = c[js_start:closing]

with open('/tmp/spa_final_check.js', 'w') as f:
    f.write(js)

print(f'JS: {len(js)} chars, {len(js.split(chr(10)))} lines')

result = subprocess.run(['node', '--check', '/tmp/spa_final_check.js'], capture_output=True, text=True)
if result.returncode == 0:
    print('node --check: PASSED')
else:
    print(f'node --check: FAILED')
    print(result.stderr[:500])
sys.exit(result.returncode)
