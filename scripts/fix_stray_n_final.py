#!/usr/bin/env python3
"""Fix stray n: close the leaked template, close Leads function, fix ActivityLog boundary."""
import sys

with open(sys.argv[1], 'rb') as f:
    content = f.read()

# Find JS content
spa_start = content.find(b'SPA_JS = r' + b'"' * 3)
spa_end = content.rfind(b'"' * 3)
js_start = spa_start + len(b'SPA_JS = r' + b'"' * 3)
js = content[js_start:spa_end]

# The stray n is at: ${statusActions.length > 0 ? html`
#                     n// ── ACTIVITY LOG ──
#                     function ActivityLog() {
# Fix: Replace from `${statusActions.length > 0 ? html`
#       n// ── ACTIVITY LOG ──` to the end of that line with:
#       `${statusActions.length > 0 ? html`` : ''}
#       </div>
#       `;
#       })()}
#
#       // ── ACTIVITY LOG
#       function ActivityLog() {

# Find the pattern
old_pattern = b'${statusActions.length > 0 ? html`\nn// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG'

idx = js.find(old_pattern)
if idx < 0:
    print("ERROR: Could not find pattern")
    # Try without unicode
    old_pattern2 = b'${statusActions.length > 0 ? html`\nn// \xe2\x94\x80'
    idx2 = js.find(old_pattern2)
    if idx2 >= 0:
        print(f"Found partial match at {idx2}")
        ctx = js[idx2:idx2+80]
        print(f"Context: {ctx!r}")
    sys.exit(1)

print(f"Found pattern at offset {idx}")

# Find the end of the line containing n//
eol = js.find(b'\n', idx)
if eol < 0:
    print("ERROR: no newline after n//")
    sys.exit(1)
end_of_line = eol + 1

# The replacement: properly close template, function closures, and start ActivityLog
new_content = (
    b'${statusActions.length > 0 ? html`` : \'\'}\n'
    b'            </div>\n'
    b'          `;\n'
    b'        }))}\n'
    b'\n'
    b'// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\n'
    b'function ActivityLog() {'
)

# Replace from the start of the pattern to end_of_line
new_js = js[:idx] + new_content + js[end_of_line:]
content = content[:js_start] + new_js + content[spa_end:]

with open(sys.argv[1], 'wb') as f:
    f.write(content)

print("FIXED: stray n removed, template closed, ActivityLog boundary fixed")
