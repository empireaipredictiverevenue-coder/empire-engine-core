"""
Comprehensive fix for ALL template issues in empire_command_spa.py.
1. Close the leads.map template + .map() callback + ternaries
2. Remove orphaned code that leaked from the original broken template
3. Verify the JS passes syntax check
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
bt = sum(l.count('`') for l in js_lines)
print(f"Original backtick count: {bt} (even: {bt % 2 == 0})")

# === FIX 1: Close the Leads function templates ===
# Find the last interpolation line in Leads
line_for_insert = None
for i, line in enumerate(js_lines):
    if '${statusActions.length > 0' in line and "'' : ''" in line:
        line_for_insert = i
        print(f"FIX 1: Found last Leads interpolation at JS line {i+1}")
        break

if line_for_insert is None:
    print("ERROR: Could not find interpolation line!")
    exit(1)

# Insert closing sequence after the interpolation
closing = [
    "            `;",           # close inner return html` template
    "          })",             # close arrow body + .map()
    "        )",                # close (filtered.length === 0 ? ...)
    "      }",                  # close ${!leads ? ... : ...}
    "      `;",                  # close main return html` template
    "    }",                     # close Leads function
    "",
    "// --- ACTIVITY LOG ---",
]

new_lines = js_lines[:line_for_insert + 1] + closing + js_lines[line_for_insert + 1:]

# === FIX 2: Remove orphaned code between ActivityLog and MiniBarChart ===
# Find ActivityLog function end and MiniBarChart function start
al_end = None
mbc_start = None

for i, line in enumerate(new_lines):
    stripped = line.strip()
    if stripped == '}' and al_end is None:
        # Find the '}' that closes ActivityLog
        # Check if ActivityLog was defined before this point
        pass

# Find ActivityLog function start
al_func_idx = None
for i, line in enumerate(new_lines):
    if 'function ActivityLog' in line:
        al_func_idx = i
        break

# Find MiniBarChart function start
mbc_func_idx = None
for i, line in enumerate(new_lines):
    if 'function MiniBarChart' in line:
        mbc_func_idx = i
        break

if al_func_idx and mbc_func_idx:
    # Look for leaked/orphaned code between ActivityLog end and MiniBarChart
    # Find proper ActivityLog close (search for '}' after ActivityLog's return statement)
    # ActivityLog's template structure should end with `; }
    
    # The leaked code starts after ActivityLog's `; }` and before MiniBarChart
    print(f"\nActivityLog function at JS line {al_func_idx + 1}")
    print(f"MiniBarChart function at JS line {mbc_func_idx + 1}")
    
    # Find the activity log comment (our inserted one or the old one)
    print(f"\nLines around ActivityLog end:")
    for i in range(mbc_func_idx - 20, mbc_func_idx):
        if i >= 0 and i < len(new_lines):
            print(f"  {i+1}: {new_lines[i][:120]}")
    
    # Check if there are orphaned lines that need removal
    # The expected structure after ActivityLog closes should be:
    # ActivityLog function } → empty → separator → MiniBarChart function
    # But we might have: } → leaked code → } → separator → MiniBarChart
    
    # Find the first '}' that's followed by '// ---- ' and then MiniBarChart
    cleanup_lines = []
    for i in range(al_func_idx + 1, mbc_func_idx):
        stripped = new_lines[i].strip()
        # Check for leaked template content (ld-actions, statusActions, etc.)
        if 'ld-actions' in stripped or 'ld-action-btn' in stripped or 'statusActions.map' in stripped:
            cleanup_lines.append(i)
    
    # Also check for orphaned backtick lines without matching pairs
    # Remove orphaned function closes (single '}' lines that aren't legitimate)
    
    # Remove orphaned lines (in reverse order to preserve indices)
    if cleanup_lines:
        print(f"\nFIX 2: Removing {len(cleanup_lines)} orphaned lines")
        for idx in sorted(cleanup_lines, reverse=True):
            print(f"  Removing JS line {idx+1}: {new_lines[idx][:100]}")
            new_lines[idx] = ''  # blank instead of delete to preserve line numbers

# === Test ===
new_js = '\n'.join(new_lines)

with open('/tmp/spa_fixed_v5.mjs', 'w') as f:
    f.write(new_js)

r = subprocess.run(['node', '--check', '/tmp/spa_fixed_v5.mjs'], capture_output=True, text=True, timeout=15)
if r.returncode == 0:
    print("\nPASS: JS syntax is valid!")
    print(f"Backtick count: {sum(l.count('`') for l in new_lines)}")
    
    # Write back to Python file
    new_content = content[:start + len(marker)] + new_js + content[start + len(marker) + end:]
    with open('empire_command_spa.py', 'w') as f:
        f.write(new_content)
    print("empire_command_spa.py updated!")
    
    # Verify Python compiles
    r2 = subprocess.run(['python3', '-c', 'import py_compile; py_compile.compile("empire_command_spa.py", doraise=True); print("Python OK")'],
                       capture_output=True, text=True, timeout=15)
    print(r2.stdout or r2.stderr[:200])
else:
    print(f"\nFAIL: {r.stderr[:500]}")
    m = re.search(r':(\d+):', r.stderr)
    if m:
        err_line = int(m.group(1))
        for i in range(max(0, err_line-2), min(len(new_lines), err_line+3)):
            marker_c = '>>>' if i == err_line-1 else '   '
            print(f'{marker_c} {i+1}: {new_lines[i][:200]}')
