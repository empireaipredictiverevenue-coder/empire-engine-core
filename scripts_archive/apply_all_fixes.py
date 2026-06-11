"""
Apply all template fixes to empire_command_spa.py:
1. Close Leads function templates
2. Fix ActivityLog missing }
3. Remove DonutChart duplicates
4. Fix HealthMonitor : ''} revert
5. Fix SniperFleet and Governor template issues
"""
import subprocess, re, sys

with open('empire_command_spa.py', 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
start = content.find(marker)
rest = content[start + len(marker):]
end = rest.rfind('"""')
js = rest[:end]
lines = js.split('\n')

print(f"Total lines: {len(lines)}")

# === FIX 1: Close Leads function templates ===
# Find the last interpolation line
fix1_line = None
for i, line in enumerate(lines):
    if '${statusActions.length > 0' in line and "'' : ''" in line:
        fix1_line = i
        break

if fix1_line is not None:
    print(f"\nFIX 1: Closing Leads templates at JS line {fix1_line+1}")
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
    lines = lines[:fix1_line + 1] + closing + lines[fix1_line + 1:]

# === FIX 2: Fix ActivityLog missing } on line 1491 ===
for i, line in enumerate(lines):
    if "` : ''" in line and not "` : ''}" in line and i > 1400 and i < 1500:
        lines[i] = line.replace("` : ''", "` : ''}", 1)
        print(f"\nFIX 2: ActivityLog missing }} at JS line {i+1}")
        break

# === FIX 3: Remove DonutChart duplicates ===
# Find DonutChart and HoloMap
dc_start = None
hm_start = None
for i, line in enumerate(lines):
    if 'function DonutChart' in line:
        dc_start = i
    if 'function HoloMap' in line:
        hm_start = i
        break

if dc_start and hm_start:
    # Track brace depth
    brace = 0
    paren = 0
    in_str = False
    str_ch = None
    proper_end = None
    
    for i in range(dc_start, hm_start):
        line = lines[i]
        j = 0
        while j < len(line):
            ch = line[j]
            nch = line[j+1] if j+1 < len(line) else ''
            if ch == '\\' and in_str:
                j += 2
                continue
            if not in_str:
                if ch in ("'", '"', '`'):
                    in_str = True
                    str_ch = ch
                elif ch == '{':
                    brace += 1
                elif ch == '}':
                    brace -= 1
                elif ch == '(':
                    paren += 1
                elif ch == ')':
                    paren -= 1
            else:
                if ch == str_ch:
                    in_str = False
                    str_ch = None
            j += 1
        
        if brace == 0 and paren == 0 and i > dc_start + 5:
            proper_end = i
            break
    
    if proper_end and proper_end < hm_start - 1:
        print(f"\nFIX 3: Removing {hm_start - proper_end - 1} duplicate DonutChart lines")
        for i in range(proper_end + 1, hm_start):
            lines[i] = ''
        
        # Also fix the } line (remove extra `)`)
        for i in range(proper_end - 5, proper_end + 5):
            if i < len(lines):
                stripped = lines[i].strip()
                if stripped == '}) {':
                    lines[i] = '}'
                    print(f"  Fixed line {i+1}: removed extra )")
                    break

# === FIX 4: Fix HealthMonitor : ''} ===
# Find HealthMonitor and SniperFleet
for i, line in enumerate(lines):
    if 'function HealthMonitor' in line:
        hm_func = i
    if 'function SniperFleet' in line:
        sf_func = i
        break

if hm_func and sf_func:
    # Look for ` : ''} that's part of a ternary with : html` else
    for i in range(hm_func, sf_func):
        stripped = lines[i].strip()
        if "` : ''}" in stripped:
            # Check if there's a ` : html` before this (meaning ternary already has else)
            # Search backwards for the matching ternary start
            prev_lines = lines[hm_func:i]
            has_html_else = any("` : html" in l for l in prev_lines[-20:])
            # Check if there's an EXACT pattern match
            if has_html_else:
                old = lines[i]
                lines[i] = stripped.replace("` : ''}", "`}", 1)
                if old != lines[i]:
                    print(f"\nFIX 4: HealthMonitor - removed `: ''` at JS line {i+1}")
                    print(f"  Before: {old.strip()}")
                    print(f"  After:  {lines[i].strip()}")

# === Test ===
new_js = '\n'.join(lines)

# Remove blanked lines (for cleaner output)
# Actually, keep them for line number preservation

with open('/tmp/spa_all_fixed.mjs', 'w') as f:
    f.write(new_js)

r = subprocess.run(['node', '--check', '/tmp/spa_all_fixed.mjs'], capture_output=True, text=True, timeout=15)
print(f"\nnode --check: {'PASS' if r.returncode == 0 else 'FAIL: ' + r.stderr[:500]}")

if r.returncode == 0:
    # Write back to Python file
    bt = sum(l.count('`') for l in lines)
    print(f"Backtick count: {bt} (even: {bt % 2 == 0})")
    
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
    import re
    m = re.search(r':(\d+):', r.stderr)
    if m:
        err_line = int(m.group(1))
        print(f"Error at JS line {err_line}")
        for i in range(max(0, err_line-2), min(len(lines), err_line+3)):
            marker_c = '>>>' if i == err_line-1 else '   '
            print(f'{marker_c} {i+1}: {lines[i][:200]}')
