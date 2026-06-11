#!/usr/bin/env python3
"""Comprehensive fix: restore, apply UMD, fix all template bugs, validate."""
import subprocess, sys, os

# Step 1: Restore from git
subprocess.run(['git', 'checkout', 'empire_command_spa.py'], cwd=os.path.dirname(os.path.abspath(__file__)) + '/..')
print("RESTORED")

# Step 2: Read file
with open('empire_command_spa.py', 'rb') as f:
    content = f.read()

# Step 3: Apply UMD switch
# HTML: import map → CDN scripts
old_html = b'  <script type="importmap">\n  {{\n    "imports": {{\n      "react":           "https://esm.sh/react@18.3.1",\n      "react-dom/client":"https://esm.sh/react-dom@18.3.1/client",\n      "htm":             "https://esm.sh/htm@3.1.1"\n    }}\n  }}\n  </script>\n  <script type="module">{_SPA_JS}</script>'
new_html = b'  <script crossorigin src="https://unpkg.com/react@18.3.1/umd/react.production.min.js"></script>\n  <script crossorigin src="https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js"></script>\n  <script crossorigin src="https://unpkg.com/htm@3.1.1/dist/htm.umd.js"></script>\n  <script>{_SPA_JS}</script>'
content = content.replace(old_html, new_html, 1)

# JS: import → const
old_imports = b'import { createElement as h, useState, useEffect, useRef, useCallback } from \'react\';\nimport { createRoot } from \'react-dom/client\';\nimport htm from \'htm\';'
new_imports = b'const { createElement: h, useState, useEffect, useRef, useCallback } = React;\nconst { createRoot } = ReactDOM;'
content = content.replace(old_imports, new_imports, 1)

print("UMD switch applied")

# Find JS content
spa_start = content.find(b'SPA_JS = r' + b'"' * 3)
spa_end = content.rfind(b'"' * 3)
js_start = spa_start + len(b'SPA_JS = r' + b'"' * 3)
js = content[js_start:spa_end]

fixes = []

# Fix 1: Pulse IIFE - close outer ${} after ; })()
idx1 = js.find(b'`; })()\n\n      ${allPartners.length > 0')
if idx1 >= 0:
    js = js[:idx1] + b'`; })()}\n\n      ${allPartners.length > 0' + js[idx1 + len(b'`; })()\n\n      ${allPartners.length > 0'):]
    fixes.append("Pulse IIFE closed")

# Fix 2: Dispatch stats - close missing }
idx2 = js.find(b'</div>` : \'\'\n\n      ${rows.length > 0')
if idx2 >= 0:
    js = js[:idx2] + b'</div>` : \'\'}\n\n      ${rows.length > 0' + js[idx2 + len(b'</div>` : \'\'\n\n      ${rows.length > 0'):]
    fixes.append("Dispatch stats missing } closed")

# Fix 3: Inbound section - remove orphaned ${(calls.length === 0)
idx3 = js.find(b'\'\'}\n      ${(calls.length === 0)\n\n      ${calls.length > 0')
if idx3 >= 0:
    js = js[:idx3] + b'\'}\n\n      ${calls.length > 0' + js[idx3 + len(b'\'\n      ${(calls.length === 0)\n\n      ${calls.length > 0'):]
    fixes.append("Inbound orphaned ${ removed")

# Fix 3b: Inbound - add ${calls.length === 0 before ? branch
idx3b = js.find(b'\'}\n\n        ? html`<div class="tbl-empty">')
if idx3b >= 0:
    js = js[:idx3b] + b'\'}\n\n      ${calls.length === 0 ? html`<div class="tbl-empty">' + js[idx3b + len(b'\'}\n\n        ? html`<div class="tbl-empty">'):]
    fixes.append("Inbound ternary branch fixed")

# Fix 4: Missing else branches (ternary without : '')
# Pattern: backtick + } on its own line → backtick + : '' + }
count_else = 0
idx4 = 0
while True:
    idx4 = js.find(b'`}\n', idx4)
    if idx4 < 0:
        break
    line_start = js.rfind(b'\n', 0, idx4)
    if line_start < 0:
        line_start = 0
    else:
        line_start += 1
    line_content = js[line_start:idx4+2]
    stripped = line_content.lstrip()
    if stripped == b'`}':
        js = js[:idx4] + b'` : \'\'}' + js[idx4+3:]
        idx4 += 6
        count_else += 1
    else:
        idx4 += 3
if count_else > 0:
    fixes.append(f"{count_else} missing else branch(es) added")

# Fix 5: Partners section - extra ` : ''} should be `}
idx5 = js.find(b'              ` : \'\'}')
if idx5 >= 0:
    js = js[:idx5] + b'              `}' + js[idx5+len(b'              ` : \'\'}'):]
    fixes.append("Partners extra `: ''` removed")

# Fix 6: COMMENTED OUT ActivityLog function
idx6 = js.find(b'// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG function ActivityLog() {')
if idx6 >= 0:
    js = js[:idx6] + b'// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG\nfunction ActivityLog() {' + js[idx6+len(b'// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG function ActivityLog() {'):]
    fixes.append("ActivityLog comment/newline fixed")

# Write back
if fixes:
    content = content[:js_start] + js + content[spa_end:]
    with open('empire_command_spa.py', 'wb') as f:
        f.write(content)
    print(f"Applied {len(fixes)} fixes:")
    for f in fixes:
        print(f"  ✓ {f}")
else:
    print("No fixes needed")

# Validate
import re
with open('empire_command_spa.py', 'r') as f:
    c = f.read()
spa_match = re.search(r'_SPA_JS = r"""', c)
closing = c.rfind('"""')
js_str = c[spa_match.end():closing]
with open('/tmp/spa_final_check.js', 'w') as f:
    f.write(js_str)
print(f'\nJS: {len(js_str)} chars, {len(js_str.split(chr(10)))} lines')

result = subprocess.run(['node', '--check', '/tmp/spa_final_check.js'], capture_output=True, text=True)
if result.returncode == 0:
    print('✅ node --check: PASSED')
    return 0
else:
    print(f'❌ node --check: FAILED')
    print(result.stderr[:500])
    return 1
