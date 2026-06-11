"""
Final comprehensive fix for all template issues in empire_command_spa.py.
1. Close Leads function templates
2. Remove ALL orphaned leaked code between ActivityLog and MiniBarChart
3. Fix any remaining template depth issues in ActivityLog
4. Verify with node --check and update Python file
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

# === FIX 1: Find and close the Leads function templates ===
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
    "            `;",
    "          })",
    "        )",
    "      }",
    "      `;",
    "    }",
    "",
    "// --- ACTIVITY LOG ---",
]

new_lines = js_lines[:line_for_insert + 1] + closing + js_lines[line_for_insert + 1:]

# === FIX 2: Find and remove ALL orphaned code between ActivityLog and MiniBarChart ===
# First, find ActivityLog function and MiniBarChart
al_func_start = None
mbc_func_start = None

for i, line in enumerate(new_lines):
    if 'function ActivityLog' in line:
        al_func_start = i
    if 'function MiniBarChart' in line:
        mbc_func_start = i
        break

if al_func_start and mbc_func_start:
    print(f"\nActivityLog at JS line {al_func_start + 1}")
    print(f"MiniBarChart at JS line {mbc_func_start + 1}")
    
    # Find where ActivityLog's `; }` is (the proper close of the function)
    # Search for the first `;` after the template close
    al_last_close = None
    
    # The ActivityLog function should end with:
    #     `;
    #   }
    # We need to find the first `}` after the ActivityLog function that could be its proper close
    
    # Search for ActivityLog's proper closing (return html` template closes with `; })
    # Find the lines:   `;  }   after the main template rendering
    found_close = False
    for i in range(al_func_start + 10, min(al_func_start + 150, len(new_lines))):
        stripped = new_lines[i].strip()
        # Look for `; - the closing of the return html template
        if stripped.startswith('`;') or stripped == '`;':
            found_close = True
            al_last_close = i + 1  # one more line for the function }
            print(f"  Template close at JS line {i+1}")
            continue
        if found_close and stripped == '}':
            al_last_close = i
            print(f"  Function close at JS line {i+1}")
            break
    
    # Now find orphaned lines between ActivityLog close and MiniBarChart
    orphaned_start = al_last_close + 1 if al_last_close else al_func_start + 1
    orphaned_end = mbc_func_start
    
    # Check what's in the orphaned range
    orphaned_lines = []
    for i in range(orphaned_start, orphaned_end):
        stripped = new_lines[i].strip()
        if stripped:  # non-empty
            orphaned_lines.append(i)
    
    if orphaned_lines:
        print(f"\nFIX 2: Removing {len(orphaned_lines)} orphaned lines ({orphaned_start + 1}-{orphaned_end})")
        for idx in orphaned_lines:
            print(f"  Removing JS line {idx+1}: {new_lines[idx][:100]}")
            new_lines[idx] = ''
    else:
        print("\nFIX 2: No orphaned lines found")
else:
    print("\nFIX 2: Could not find ActivityLog or MiniBarChart")

# === FIX 3: Check ActivityLog template depth ===
# Count backticks in ActivityLog
al_range = new_lines[al_func_start:mbc_func_start] if al_func_start and mbc_func_start else new_lines
al_bt = sum(l.count('`') for l in al_range)
print(f"\nActivityLog backtick count: {al_bt} (even: {al_bt % 2 == 0})")

# === Test with node --check ===
new_js = '\n'.join(new_lines)

with open('/tmp/spa_final_fixed.mjs', 'w') as f:
    f.write(new_js)

r = subprocess.run(['node', '--check', '/tmp/spa_final_fixed.mjs'], capture_output=True, text=True, timeout=15)
if r.returncode == 0:
    print(f"\n✓ PASS: JS syntax is valid!")
    bt_total = sum(l.count('`') for l in new_lines)
    print(f"Backtick count: {bt_total} (even: {bt_total % 2 == 0})")
    
    # Write back to Python file
    new_content = content[:start + len(marker)] + new_js + content[start + len(marker) + end:]
    with open('empire_command_spa.py', 'w') as f:
        f.write(new_content)
    print("✓ empire_command_spa.py updated!")
    
    # Verify Python compiles
    r2 = subprocess.run(['python3', '-c', 
        'import py_compile; py_compile.compile("empire_command_spa.py", doraise=True); print("Python OK")'],
        capture_output=True, text=True, timeout=15)
    print(r2.stdout or r2.stderr[:200])
else:
    print(f"\n✗ FAIL: {r.stderr[:500]}")
    m = re.search(r':(\d+):', r.stderr)
    if m:
        err_line = int(m.group(1))
        print(f"Error at JS line {err_line}")
        for i in range(max(0, err_line-2), min(len(new_lines), err_line+3)):
            marker_c = '>>>' if i == err_line-1 else '   '
            print(f'{marker_c} {i+1}: {new_lines[i][:200]}')
