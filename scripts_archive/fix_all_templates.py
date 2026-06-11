"""
Apply ALL template fixes to empire_command_spa.py at once.

Known bugs from git diff:
1. `}` → ` : ''}` (template + closing interpolation incorrectly ordered)
2. Various template mismatch patterns
"""
import subprocess, re, sys

with open('empire_command_spa.py', 'r', encoding='utf-8') as f:
    original = f.read()

content = original

# Fix 1: The main Leads function issue - replace the unclosed template
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

print("=== Fix 1: Leads function unclosed template ===")
idx = content.find(old_span)
if idx >= 0:
    content = content[:idx] + new_span + content[idx+len(old_span):]
    print("Applied ✓")
else:
    print("Pattern not found ✗")
    # Debug: find partial matches
    for snippet in ['statusActions.length > 0 ? html`', 'n// ── ACTIVITY LOG']:
        idx2 = content.find(snippet)
        if idx2 >= 0:
            print(f"  Partial match '{snippet}' at position {idx2}")
            context = content[idx2-50:idx2+50]
            print(f"  Context: {repr(context)}")
        else:
            print(f"  No match for '{snippet}'")

# Fix 2: ActivityLog function - `${filteredEntries.length > 0 ? html` 
# This is a template interpolation that needs proper opening
# The issue is that in the ActivityLog function, `return html`` opens a template
# Content inside the template needs proper `:` and interpolation close patterns
# But we need to find these in the extracted JS...

# Let me instead extract the JS, fix it, and re-embed it
print("\n=== Fix 2: Extract JS and fix remaining issues ===")

marker = '_SPA_JS = r"""'
start = content.find(marker)
rest = content[start + len(marker):]
end = rest.rfind('"""')
old_js = rest[:end]

# Find the JS boundary in the Python source
_js_start = start + len(marker)
_js_end = _js_start + end

# Now apply fixes to the JS

# The ActivityLog function template has `}` patterns that should be ` : ''}`
# But first, let's check the template structure by counting backticks
bt_count = 0
for ch in old_js:
    if ch == '`':
        bt_count += 1
print(f"Backtick count in JS: {bt_count} ({'even' if bt_count % 2 == 0 else 'ODD - unbalanced!'})")

# The fix: in the ActivityLog function's return template, there are `}` patterns
# that need to be ` : ''}` 
# Pattern: at end of lines like `</div>` which should be followed by interpolation close

# Actually, let me use a smarter approach.
# Let me check the ActivityLog function's structure
lines = old_js.split('\n')
found_al = False
for i, line in enumerate(lines):
    if 'function ActivityLog' in line:
        found_al = True
    if found_al and i < 120:
        print(f"  JS line {i+1}: {line[:150]}")

# The real fix for the ActivityLog template is likely:
# The return html` template's content includes `${...}` interpolations
# that use html` sub-templates. Some of these sub-templates are closed
# with `` `} `` instead of `` ` : ''} ``.

# Let me find ALL instances of `}` in the JS that need fixing
# Pattern: inside a template interpolation, a `}` right after a backtick
# means the template closes and then the interpolation closes, but there's
# no false branch for a ternary

# Look for lines that end with `} or contain the pattern
print("\n=== Finding `} patterns that might need fixing ===")
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped == '`}' or stripped.endswith('`}'):
        # Show context
        print(f"Line {i+1}: {line[:120]}")
        for j in range(max(0, i-2), min(len(lines), i+3)):
            marker_c = '>> ' if j == i else '   '
            prev_line = lines[j]
            print(f"  {marker_c} {j+1}: {prev_line[:100]}")

# Let me check if the main template in ActivityLog is properly structured
# by looking at the template opening and closing
print("\n=== ActivityLog template open/close ===")
in_al = False
for i, line in enumerate(lines):
    if 'function ActivityLog' in line:
        in_al = True
    if in_al:
        if 'return html' in line:
            print(f"  return html` at line {i+1}: {line}")
        if i > 1400 and i < 1450 and 'return html' in line:
            break
