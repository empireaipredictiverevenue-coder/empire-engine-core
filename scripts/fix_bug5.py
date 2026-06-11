#!/usr/bin/env python3
"""Fix bug 5: close statusActions template leak and remove stray n."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

fixes = []

# Find the exact broken area
old = (
    '${statusActions.length > 0 ? html`\n'
    'n// ── ACTIVITY LOG ─────────────────────────────────────────────────────\n'
    'function ActivityLog() {'
)

new = (
    '${statusActions.length > 0 ? html`\n'
    '                <div class="ld-actions">\n'
    '                  ${statusActions.map(a => html`\n'
    '                    <button class="ld-action-btn ${a.cls}" onClick=${() => doUpdate(l.id, a.status)} disabled=${busy === (l.id + \':\' + a.status)}>\n'
    '                      ${a.label}\n'
    '                    </button>\n'
    '                  `)}\n'
    '                </div>\n'
    '              ` : \'\'}\n'
    '            </div>\n'
    '          `;\n'
    '        })()}\n'
    '\n'
    '// ── ACTIVITY LOG ─────────────────────────────────────────────────────\n'
    'function ActivityLog() {'
)

if old in js:
    js = js.replace(old, new, 1)
    fixes.append("Bug5: Closed statusActions template, removed stray n, added proper closing")
else:
    print("WARNING: Fix not found!")
    idx = js.find('statusActions.length > 0')
    if idx >= 0:
        ctx = repr(js[idx:idx+200])
        print(f"  Found at {idx}:")
        print(f"  {ctx}")

if fixes:
    content = content[:js_start] + js + content[spa_end:]
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    for f in fixes:
        print(f"FIX: {f}")
else:
    print("No fixes applied")
