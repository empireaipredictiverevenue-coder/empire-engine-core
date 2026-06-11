#!/usr/bin/env python3
"""Fix bug 4: remove stray n, close Leads template, keep ActivityLog standalone."""
import sys

with open(sys.argv[1], 'rb') as f:
    content = f.read()

# Find the SPA JS raw string
spa_start = content.find(b'SPA_JS = r' + b'"' * 3)
spa_end = content.rfind(b'"' * 3)
js_start = spa_start + len(b'SPA_JS = r' + b'"' * 3)
js = content[js_start:spa_end]

# Find the stray n character
idx = js.find(b'n//')
if idx < 0:
    print("ERROR: Could not find n// pattern")
    sys.exit(1)

# Show context before
line_start = js.rfind(b'\n', 0, idx)
before = js[line_start:idx+60]
print(f"Context: {before!r}")

# The line before n contains ${statusActions.length > 0 ? html`
# We need to close this with ` : ''} and then close the function structure

# Build the replacement:
# Close ternary: ` : ''}
# Close ld-lead div: </div>
# Close return template: `;
# Close function body + closures: }))}
# Newline + ActivityLog comment + function

close_template = (
    b'` : \'\'}\n'
    b'            </div>\n'
    b'          `;\n'
    b'        }))}\n'
    b'\n'
    b'// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG '
)

# Find the end of the n// line
eol = js.find(b'\n', idx)
if eol < 0:
    print("ERROR: Could not find end of line")
    sys.exit(1)
end_of_line = eol + 1  # include newline

# Replace from n to end of line
new_js = js[:idx] + close_template + js[end_of_line:]
content = content[:js_start] + new_js + content[spa_end:]

with open(sys.argv[1], 'wb') as f:
    f.write(content)

print("FIXED: stray n removed, Leads template properly closed, ActivityLog standalone")
