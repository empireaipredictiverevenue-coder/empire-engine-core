#!/usr/bin/env python3
"""Fix stray n character before // ── ACTIVITY LOG in Leads function."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

# Bug: stray 'n' character before Activity Log corrupts the template
# Replace: n// ── ACTIVITY LOG ────
# With: proper template close + Activity Log comment
old = 'n// ── ACTIVITY LOG \xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80\xe2\x94\x80'

# The template structure to close:
# ${statusActions.length > 0 ? html`
#   ...action buttons...
# ` : ''}
# </div>
# `;     (close the outer template from filtered.map callback)
# }))}   (close function body, map(), filter, outer ${})
new = (
    '` : \'\'}\n'   # close the statusActions ternary template
    '            </div>\n'  # close ld-lead div
    '          `;\n'  # close the outer return template
    '        }))}\n\n'  # close function body, map(), filter, outer ${}
    '// \xe2\x94\x80\xe2\x94\x80 ACTIVITY LOG'
)

if old in js:
    js = js.replace(old, new, 1)
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    print('FIXED: Stray n removed, Leads template properly closed')
else:
    print('Pattern not found!')
    idx = js.find('// \xe2\x94\x80\xe2\x94\x80 ACTIVITY')
    if idx >= 0:
        ctx = repr(js[idx-40:idx+20])
        print(f'Found comment at {idx}: {ctx}')
    else:
        idx2 = js.find('n//')
        if idx2 >= 0:
            ctx = repr(js[idx2-20:idx2+20])
            print(f'Found n// at {idx2}: {ctx}')
