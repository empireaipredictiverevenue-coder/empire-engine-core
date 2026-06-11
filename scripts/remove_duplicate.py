#!/usr/bin/env python3
"""Remove duplicate ActivityLog function declaration created by the fix_stray_n_final.py."""
import sys

with open(sys.argv[1], 'rb') as f:
    content = f.read()

spa_start = content.find(b'SPA_JS = r' + b'"' * 3)
spa_end = content.rfind(b'"' * 3)
js_start = spa_start + len(b'SPA_JS = r' + b'"' * 3)
js = content[js_start:spa_end]

# The duplicate pattern:
# function ActivityLog() {n// ── ACTIVITY LOG ────
# function ActivityLog() {
# Fix: function ActivityLog() {

old = b'function ActivityLog() {n//'
new = b'function ActivityLog() {'
# But we need to also remove the second function ActivityLog() {
# Looking at the actual content, we need to find:
# function ActivityLog() { + n// ── ACTIVITY LOG ── + \n + function ActivityLog() {

# Find the pattern
idx = js.find(b'function ActivityLog() {n//')
if idx >= 0:
    # Find where the second function ActivityLog() { starts
    eol = js.find(b'\n', idx)
    if eol >= 0:
        # Find the second occurrence of function ActivityLog()
        second = js.find(b'function ActivityLog() {', eol)
        if second >= 0:
            # Remove everything from idx to the second function
            # Keep the first function, remove the n// and second function
            after_second = js.find(b'\n', second)
            if after_second >= 0:
                # Remove from function ActivityLog() {n// to after the second function's opening brace
                new_js = js[:idx] + b'function ActivityLog() {' + js[after_second+1:]
                content = content[:js_start] + new_js + content[spa_end:]
                with open(sys.argv[1], 'wb') as f:
                    f.write(content)
                print(f"FIXED: Removed duplicate from {idx} to {after_second}")
            else:
                print("ERROR: no newline after second function")
        else:
            print("ERROR: no second function found")
            ctx = js[eol:eol+80]
            print(f"Context: {ctx!r}")
    else:
        print("ERROR: no newline after first function")
else:
    print("Pattern not found")
    # Debug: show what's around the Activities section
    act_idx = js.find(b'function ActivityLog()')
    if act_idx >= 0:
        ctx = js[act_idx:act_idx+120]
        print(f"Context: {ctx!r}")
