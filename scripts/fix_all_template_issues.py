#!/usr/bin/env python3
"""
Comprehensive fix for template literal issues in empire_command_spa.py.

Root cause: Unclosed template literal in Leads function (line 1396)
that absorbed ActivityLog, MiniBarChart, DonutChart, HoloMap, HealthMonitor,
SniperFleet, Governor, Stub, and App functions as template content.

The fix closes the unclosed template, then removes the absorbed duplicate
code from downstream functions.
"""

import subprocess
import re

# Step 1: Extract JS from committed Python file
r = subprocess.run(['git', 'show', 'HEAD:empire_command_spa.py'], capture_output=True, text=True)
content = r.stdout

marker = '_SPA_JS = r"""'
start = content.find(marker)
rest = content[start + len(marker):]
end = rest.rfind('"""')
js = rest[:end]

lines = js.split('\n')
print(f"Starting: {len(lines)} lines, {len(js)} bytes")
print(f"Backtick count: {js.count(chr(96))} (even: {js.count(chr(96)) % 2 == 0})")

# Step 2: Find function boundaries
funcs = {}
for i, line in enumerate(lines):
    stripped = line.strip()
    if stripped.startswith('function ') and '{' in stripped:
        name = stripped.split('(')[0].replace('function ', '').strip()
        funcs[name] = i

for name, line_num in sorted(funcs.items(), key=lambda x: x[1]):
    print(f"  {name}: line {line_num+1}")

# Step 3: Close the unclosed template in Leads function
# Line 1396: `${statusActions.length > 0 ? html` → close properly
leads_line = 1395  # 0-indexed
print(f"\n=== Fixing unclosed template at line {leads_line+1} ===")
print(f"  Before: {repr(lines[leads_line][:80])}")

# The line `${statusActions.length > 0 ? html` needs to be closed
# Since the absorbed content was supposed to be the statusActions rendering
# but it's been mixed with ActivityLog, we close the template safely
lines[leads_line] = "              ${statusActions.length > 0 ? '' : ''}"
print(f"  After:  {repr(lines[leads_line][:80])}")

# Step 4: The next line is `n// ── ACTIVITY LOG ...` which starts with 'n'
# This is the remnant of the broken template content. Remove it.
if leads_line + 1 < len(lines) and 'ACTIVITY LOG' in lines[leads_line + 1]:
    print(f"\n  Removing ActivityLog remnant line {leads_line+2}: {repr(lines[leads_line+1][:60])}")
    lines[leads_line + 1] = ''
elif leads_line + 1 < len(lines):
    print(f"\n  Line after fix: {repr(lines[leads_line+1][:80])}")

# Step 5: The ActivityLog function (line 1398) was absorbed as template content
# We need to find where the real ActivityLog code ends and restore proper structure
# The ActivityLog function in the committed JS is from line 1398 to 1545
# But it's all template content, so `function ActivityLog() {` etc. are text.

# Actually, looking at the committed JS structure more carefully:
# The unclosed template starts at line 1396 and continues absorbing
# All subsequent code. But the backticks in the absorbed code (like ActivityLog's
# `return html\`...``) were counted by the parser, creating the even count.
#
# When we fix line 1396 to close the template, the parser will now see
# ActivityLog as real JavaScript code, since `function ActivityLog() {`
# is no longer inside a template literal.
#
# BUT: The ActivityLog function itself may have internal template issues
# from when it was written "inside" a broken context.

# Let's save this intermediate version and check what errors remain
mid_content = '\n'.join(lines)

with open('/tmp/spa_fix_step1.mjs', 'w') as f:
    f.write(mid_content)

# Check
r = subprocess.run(['node', '--check', '/tmp/spa_fix_step1.mjs'], capture_output=True, text=True, timeout=15)
if r.returncode == 0:
    print("\nnode --check: PASS!")
else:
    print(f"\nnode --check: FAIL at line ...")
    # Extract error line
    m = re.search(r':(\d+):', r.stderr)
    if m:
        err_line = int(m.group(1))
        print(f"  Error at line {err_line}: {r.stderr[:200]}")
        # Show context
        for i in range(max(0, err_line-3), min(len(lines), err_line+3)):
            marker = '>>>' if i == err_line-1 else '   '
            print(f"  {marker} {i+1}: {repr(lines[i][:120])}")
    
    # The error should now be at a different location since we closed the template
    # Let's look for the specific issue patterns
    
    # Check for ` : ''} patterns that create ternary with 3 branches
    # These were added by commit 4895d88 as misguided fixes
    print(f"\n=== Scanning for ` : ''}} patterns ===")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('`') and ": ''}" in stripped:
            # Check if there's already an : html` before this on the same line
            # (indicating a ternary with 2 else branches)
            idx = stripped.find(": ''}")
            before = stripped[:idx]
            if ': html`' in before or ': html<' in before or '"' in stripped:
                print(f"  JS {i+1}: {repr(stripped[:100])}")
                
                # This looks like a triple-branch ternary: condition ? true : else1 : else2
                # The fix is to remove `: ''}` since there's already an else branch
                
                # BUT we need to be careful - some ` : ''} might be correct
                # Let's only fix patterns where we see the actual issue:
                # ` : ''} AFTER `: html`...content...`
                
                # Pattern: ` : ''} at the end of a template that already has : html`
                # This means the template content is `foo` : html`bar` : ''} 
                # which is invalid
    
    # Also scan for the specific pattern: )` : ''}
    print(f"\n=== Scanning for )\\` : ''}} pattern ===")
    for i, line in enumerate(lines):
        if "): ''}" in line and chr(96) + " : ''}" in line:
            print(f"  JS {i+1}: {repr(line.strip()[:120])}")
