#!/usr/bin/env python3
"""Fix ActivityLog function being commented out - add newline between comment and function."""
import sys

with open(sys.argv[1], 'rb') as f:
    content = f.read()

spa_start = content.find(b'SPA_JS = r' + b'"' * 3)
spa_end = content.rfind(b'"' * 3)
js_start = spa_start + len(b'SPA_JS = r' + b'"' * 3)
js = content[js_start:spa_end]

# The bug: // ── ACTIVITY LOG function ActivityLog() {
# fix: // ── ACTIVITY LOG \n function ActivityLog() {

old = b'// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG function ActivityLog() {'
new = b'// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG\nfunction ActivityLog() {'

if old in js:
    js = js.replace(old, new, 1)
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'wb') as f:
        f.write(content)
    print("FIXED: Added newline between ACTIVITY LOG comment and function declaration")
else:
    print("Pattern not found!")
    # Debug
    idx = js.find(b'function ActivityLog()')
    if idx >= 0:
        ctx = js[idx-30:idx+30]
        print(f"Context: {ctx!r}")
