"""
Fix the template bug by replacing the broken statusActions template lines
with proper closures for: statusActions, T_LEAD, callback body, .map(), 
outer parens, I1, T_MAIN, and function.
"""
import subprocess, re, sys

with open('empire_command_spa.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Find the broken area - the statusActions template line and the stray n line
# These are in the Python source, inside the _SPA_JS raw string

# The buggy lines (Python source):
#   line 1911: '              ${statusActions.length > 0 ? html`'
#   line 1912: 'n// ── ACTIVITY LOG ────────────────────────────────────────────'

# We need to replace these two lines with proper closings.
# The correct structure flows from the last ld-notes section through to
# before function ActivityLog():

# After this fix:
#   </div>               ← closes ld-notes (already exists, JS line 1395)
#   ${statusActions.length > 0 ? '' : ''}  ← closes ternary (replaces broken line)
# </div>                 ← closes ld-lead (already exists, JS line 1397)
# `                      ← closes T_LEAD (return html` from .map callback)
# })                     ← closes callback body + .map()
# )}                     ← closes outer ( + I1 (${!leads ...})
# </div>                 ← closes T_MAIN's main div
# `;                     ← closes T_MAIN + ;
# }                      ← closes Leads function
# function ActivityLog() {

# The old text to find and replace
old_span = '''              ${statusActions.length > 0 ? html`
n// ── ACTIVITY LOG ─────────────────────────────────────────────────────'''

new_span = '''              ${statusActions.length > 0 ? '' : ''}
            </div>
          `
        })
      )}
    </div>
  `;
}
'''

# Find the exact location
idx = content.find(old_span)
if idx < 0:
    print("ERROR: Could not find the buggy template lines!")
    sys.exit(1)

print(f"Found buggy lines at position {idx}")

# Verify context
before = content[idx-100:idx]
after = content[idx+len(old_span):idx+len(old_span)+60]
print(f"Before: {repr(before[-80:])}")
print(f"After: {repr(after[:60])}")

# Apply the fix
new_content = content[:idx] + new_span + content[idx+len(old_span):]

with open('empire_command_spa.py', 'w', encoding='utf-8') as f:
    f.write(new_content)

print("Fix applied. Testing...")

# Test: extract JS and check with node
marker = '_SPA_JS = r"""'
start = new_content.find(marker)
rest = new_content[start + len(marker):]
end = rest.rfind('"""')
js = rest[:end]

with open('/tmp/spa_fixed_v2.mjs', 'w') as f:
    f.write(js)

r = subprocess.run(['node', '--check', '/tmp/spa_fixed_v2.mjs'], capture_output=True, text=True, timeout=15)
if r.returncode == 0:
    print("SUCCESS: node --check PASSES on .mjs!")
else:
    print(f"FAILED: {r.stderr[:500]}")
    # Show error context
    m = re.search(r':(\d+):', r.stderr)
    if m:
        err_line = int(m.group(1))
        js_lines = js.split('\n')
        print(f"\nContext at error line {err_line}:")
        for i in range(max(0, err_line-3), min(len(js_lines), err_line+3)):
            marker_c = '>>>' if i == err_line-1 else '   '
            print(f'{marker_c} {i+1}: {js_lines[i][:200]}')
