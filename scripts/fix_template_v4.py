"""
Fix for the unclosed Leads function templates.
The Leads function has two return html` templates that are never closed.
"""
import subprocess, re

with open('empire_command_spa.py', 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
start = content.find(marker)
rest = content[start + len(marker):]
end = rest.rfind('"""')
js = rest[:end]
js_lines = js.split('\n')

print(f"Total JS lines: {len(js_lines)}")

# Find key line positions
line_1396 = None
line_1369 = None
line_1355 = None
line_1264 = None

for i, line in enumerate(js_lines):
    if '${statusActions.length > 0' in line:
        line_1396 = i
        print(f"Last interpolation at JS line {i+1}")
    if 'dollar-brace !leads' in line.lower() or '${!leads' in line:
        if 'filtered' in line and 'length === 0' not in line:
            pass  # not the right one
        if '!leads' in line:
            line_1351 = i
            print(f"!leads interpolation at JS line {i+1}")
    if 'filtered.map(l =>' in line:
        line_1355 = i
        print(f".map callback at JS line {i+1}")

# Find inner return html` at line 1369
line_1369 = None
for i in range(1365, 1375):
    if i < len(js_lines) and 'return html' in js_lines[i]:
        line_1369 = i
        print(f"Inner return html at JS line {i+1}")
        break

# Find main return html` at line 1264
line_1264 = None
for i in range(1260, 1280):
    if i < len(js_lines) and 'return html' in js_lines[i]:
        line_1264 = i
        print(f"Main return html at JS line {i+1}")
        break

# Print indentation
if line_1264:
    print(f"  Main return indent: {repr(js_lines[line_1264][:30])}")
if line_1355:
    print(f"  .map() indent:      {repr(js_lines[line_1355][:30])}")
if line_1369:
    print(f"  Inner return indent: {repr(js_lines[line_1369][:30])}")
if line_1396:
    print(f"  Last interp indent: {repr(js_lines[line_1396][:40])}")

if not all([line_1264, line_1355, line_1369, line_1396]):
    print("ERROR: Could not find all required lines!")
    exit(1)

# Build the closing lines
closing = [
    '            `;',            # close inner return html` template (12 spaces)
    '          })',              # close arrow body + .map()
    '        )',                 # close (filtered.length === 0 ? ...)
    '      }',                   # close ${!leads ? ... : ...}
    '      `;',                  # close main return html` template
    '    }',                     # close Leads function
    '',
    '// --- ACTIVITY LOG --------------------------------------------------------',
]

# Insert after line_1396
new_lines = js_lines[:line_1396 + 1] + closing + js_lines[line_1396 + 1:]

# Remove the old ActivityLog comment (which was at the original line_1396 + 2 or so)
for i in range(line_1396 + 1 + len(closing), len(new_lines)):
    stripped = new_lines[i].strip()
    seen_al = stripped.startswith('// --- ACTIVITY LOG')
    old_al = stripped.startswith('// ---- ACTIVITY LOG') or 'ACTIVITY LOG' in new_lines[i]
    if 'ACTIVITY LOG' in new_lines[i] and '---' in new_lines[i]:
        # This is the OLD comment, blank it
        new_lines[i] = ''

new_js = '\n'.join(new_lines)

# Test with node --check
with open('/tmp/spa_v4_fixed.mjs', 'w') as f:
    f.write(new_js)

r = subprocess.run(['node', '--check', '/tmp/spa_v4_fixed.mjs'], capture_output=True, text=True, timeout=15)
if r.returncode == 0:
    print("\nPASS: JS syntax is valid!")
    # Now update the original file
    # Replace the JS portion in the Python file
    new_content = content[:start + len(marker)] + new_js + content[end + 3 + start:]  # end + len('"""')
    # Actually, content[start + len(marker):] is rest
    # rest[:end] is the JS, rest[end:] is the closing '"""'
    # So: content = content[:start + len(marker)] + new_js + content[start + len(marker) + end:]
    # Wait, let me think more carefully
    # marker = '_SPA_JS = r"""'
    # start = content.find(marker)
    # rest = content[start + len(marker):]
    # end = rest.rfind('"""')
    # So content[start:] = marker + rest
    # rest[:end] = js, rest[end:end+3] = '"""', rest[end+3:] = rest of file
    
    new_content = content[:start + len(marker)] + new_js + content[start + len(marker) + end:]
    
    with open('empire_command_spa.py', 'w') as f:
        f.write(new_content)
    print("empire_command_spa.py updated successfully!")
    
    # Verify Python still compiles
    r2 = subprocess.run(['python3', '-c', 'import py_compile; py_compile.compile("empire_command_spa.py", doraise=True); print("Python OK")'],
                       capture_output=True, text=True, timeout=15)
    print(r2.stdout or r2.stderr[:500])
else:
    print(f"\nFAIL: {r.stderr[:500]}")
    m = re.search(r':(\d+):', r.stderr)
    if m:
        err_line = int(m.group(1))
        for i in range(max(0, err_line-2), min(len(new_lines), err_line+3)):
            marker_c = '>>>' if i == err_line-1 else '   '
            print(f'{marker_c} {i+1}: {new_lines[i][:200]}')
