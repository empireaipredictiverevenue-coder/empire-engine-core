"""
Fix the template bug in empire_command_spa.py by:
1. Removing the stray `n` line
2. Replacing the unclosed template with proper closing structure
"""
import subprocess
import re

with open('empire_command_spa.py', 'r', encoding='utf-8') as f:
    content = f.read()
    lines = content.split('\n')

# Find the exact JS boundaries
marker = '_SPA_JS = r"""'
start = content.find(marker)
rest = content[start + len(marker):]
end = rest.rfind('"""')
js = rest[:end]
js_lines = js.split('\n')

# Find the problematic lines in Python source
# Look for the line with "n// ── ACTIVITY LOG" in PYTHON source (CSS section)
py_stray_line = None
for i, line in enumerate(lines):
    if 'n// ── ACTIVITY LOG' in line:
        py_stray_line = i
        print(f"Found stray line at Python line {i+1}: {repr(line)}")
        break

# Find the statusActions template in PYTHON source
py_status_line = None
for i, line in enumerate(lines):
    if 'statusActions.length > 0' in line and '?' in line and 'html`' in line:
        py_status_line = i
        print(f"Found statusActions template at Python line {i+1}: {repr(line)[:100]}")
        break

if py_stray_line is None and py_status_line is None:
    print("No stray line or statusActions template found - checking current state")
    # Check if the file already has the fix but with wrong closing order
    for i, line in enumerate(lines):
        if 'statusActions.length > 0' in line:
            print(f"Found at Python line {i+1}: {repr(line)[:120]}")

# The current state should have:
# Python lines ~1911-1912 already fixed to:
#   1911:               ${statusActions.length > 0 ? '' : ''}
#   1912:             </div>
#   1913:           `)}
#   1914:         `;
#   1915:       }
#   1916: function ActivityLog() {

# The issue is that `)} closes the template, then ) closes .map(, then } closes I1
# But the order should be: ` (close T_LEAD), ; (end return), } (close callback), ) (close .map), } (close I1)

# Let me find the exact current state around the fix
print("\n=== Current state around fix area ===")
for i in range(1908, min(len(lines), 1920)):
    print(f"  {i+1}: {repr(lines[i])}")

# Now let me look at what the correct JS should look like
# The template opened at `return html` on line 1369 (JS) needs to be closed
# Then .map() needs to close
# Then I1 needs to close
# Then T_MAIN needs to close
# Then the function needs to close

# Find the JS line that corresponds to Python line 1913 (`)})
# By looking at the JS context
print(f"\nJS lines around the transition:")
for i in range(1393, min(len(js_lines), 1402)):
    print(f"  JS {i+1}: {repr(js_lines[i])}")

# Now let me determine the correct fix:
# After `</div>` (JS line 1397, ld-lead close):
# We need:
# ```
#           `          ← close T_LEAD (10 spaces + backtick)
#         })           ← }) closes callback body + .map( (8 spaces)
#       }              ← } closes I1 (6 spaces)
#     </div>           ← close T_MAIN's outer div (4 spaces)
#   `;                 ← close T_MAIN (2 spaces + `;)
# }                    ← close function (0 spaces)
# function ActivityLog() { ...

# But we need to verify this by checking what's inside T_MAIN between the I1 close and T_MAIN close

# Actually, let me look at what T_MAIN's structure looks like
# T_MAIN opens at line 1264: return html`
# T_MAIN contains: <div> ... stuff ... ${!leads ? ... : ...} </div>
# So between I1 close (}) and T_MAIN close (`), there's </div>

# Let me check if </div> is already there or if it was inside the original unclosed template
print(f"\nT_MAIN content around the end:")
# Find what comes after ${!leads ...} in the main template
for i in range(1390, min(len(js_lines), 1402)):
    print(f"  JS {i+1}: {repr(js_lines[i])}")

# Looking at the data, the fix should be:
# Replace JS lines 1398-1400 with:
# Line 1398: `          ` (close T_LEAD)
# Line 1399: `        })` (close callback + .map())
# Line 1400: `      }` (close I1)
# (Lines 1401- onward shift down)

# WAIT - I need to check: is there an outer `(` from "(filtered.length === 0"?
# Looking at line 1353: `: (filtered.length === 0`
# So the closing order is:
# ) closes .map(
# ) closes the outer ( from (filtered.length === 0
# } closes I1

# So: ` closes T_LEAD, } closes callback, ) closes .map(, ) closes outer (, } closes I1

# The correct structure (in JS) at lines 1398-1401:
# 1398: `          ` ← close T_LEAD
# 1399: `        })` ← close callback (.map's {}), close .map(
# Wait no. `.map(l => { ... })` — callback body closes with }, then ) closes .map(
# And `(filtered.length === 0 ? ...)` — the outer ( closes with )
# And I1 ${...} closes with }

# So: first } closes callback body
# first ) closes .map(
# second ) closes outer ( from (filtered.length === 0 
# second } closes I1 (${)

# Line by line:
# 1398: `          ` ← close T_LEAD (still inside callback body)
# 1399: `        }` ← close callback body
# 1400: `      })` ← close .map(, close outer (
# Wait, }) would close callback body + .map(, but callback body was already closed on line 1399

# Hmm, let me reconsider. `filtered.map(l => { ... })` — the { opens the body, the } closes it, the ) closes .map(.

# And `(filtered.length === 0 ? ...)` — the ( opens, the ) closes it.

# And `${!leads ? ...}` — the { of ${ opens interpolation, the } closes it.

# So the closing structure after T_LEAD:
# }   ← close callback body (l => { ... })
# )   ← close .map(
# )   ← close outer ( from (filtered.length === 0
# }   ← close I1 (${)

# Total: }}})

# But that's too many. Let me re-check.

# Looking at the actual code:
# : filtered.map(l => {
#     ...code...
#     return html`
#       </div>
#     `
#   })
# }
# </div>
# `;

# Wait, I don't have the structure right. Let me look at the ACTUAL code format around lines 1350-1360:

print("\n=== Lines 1350-1360 of JS ===")
for i in range(1349, min(len(js_lines), 1361)):
    print(f"  {i+1}: {repr(js_lines[i])}")
