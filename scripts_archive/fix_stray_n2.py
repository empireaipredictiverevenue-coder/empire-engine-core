#!/usr/bin/env python3
"""Fix stray n character before // ACTIVITY LOG in Leads function."""
import sys

with open(sys.argv[1], 'rb') as f:
    content = f.read()

spa_start = content.find(b"SPA_JS = r" + b'"' * 3)
spa_end = content.rfind(b'"' * 3)
js_start = spa_start + len(b"SPA_JS = r" + b'"' * 3)
js = content[js_start:spa_end]

# Find n// ACTIVITY LOG
old_idx = None
for i in range(len(js) - 5):
    if js[i:i+3] == b'n//' and b'ACTIVITY' in js[i:i+40]:
        old_idx = i
        break

if old_idx is None:
    print("ERROR: Could not find stray n")
    sys.exit(1)

# Show context at the found position
ctx = js[old_idx:old_idx+50]
print(f"Found at offset {old_idx}: {ctx}")

# Find end of the current line after n// ── ... LOG ──...
eol = js.find(b'\n', old_idx)
if eol < 0:
    print("ERROR: Could not find end of line")
    sys.exit(1)
end_of_line = eol + 1  # include newline

# Build the replacement: proper template close + function close + comment
# We start from the current indentation context
# The template structure to close:
# ${statusActions.length > 0 ? html`
#   <div class="ld-actions">
#     ${statusActions.map(a => html`
#       <button ...>${a.label}</button>
#     `)}
#   </div>
# ` : ''}
# </div>
# `;
# })()}
#
# // ── ACTIVITY LOG

close_template = (
    b'` : \'\'}\n'
    b'            </div>\n'
    b'          `;\n'
    b'        }))}\n\n'
    b'// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG '
)

# Replace from old_idx to end_of_line with close_template
new_js = js[:old_idx] + close_template + js[end_of_line:]
content = content[:js_start] + new_js + content[spa_end:]
with open(sys.argv[1], 'wb') as f:
    f.write(content)
print(f"Fixed: removed stray n at offset {old_idx}, Leads template properly closed")
