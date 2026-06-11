"""
Comprehensive template fix for empire_command_spa.py.
Fixes multiple template literal bugs across the entire file.
"""
import subprocess, re, sys

with open('empire_command_spa.py', 'r', encoding='utf-8') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
start = content.find(marker)
prefix = content[:start + len(marker)]
rest = content[start + len(marker):]
end = rest.rfind('"""')
suffix = rest[end:]
old_js = rest[:end]

lines = old_js.split('\n')

# Fix 1: Already applied - Leads function statusActions template

# Fix 2-6: Find all `} patterns (template close followed by interpolation close)
# that should be ` : ''} (proper ternary false branch)

# Pattern: lines ending with `} where the previous context suggests a ternary
fixes_applied = []
for i, line in enumerate(lines):
    stripped = line.rstrip()
    
    # Check if line ends with `}
    if stripped.endswith('`}'):
        # Check if this is inside a ${... ? ...} interpolation
        # The fix: change `} to ` : ''}
        fixed = stripped[:-2] + '` : \'\'}'
        lines[i] = fixed.replace(stripped.rstrip(), fixed)
        fixes_applied.append((i+1, line, fixed))
        print(f"FIX: Line {i+1}: {line[:60]} -> {fixed[:60]}")

print(f"\nApplied {len(fixes_applied)} template backtick-close fixes")

# Test the fixed JS
new_js = '\n'.join(lines)
with open('/tmp/spa_all_fixed.mjs', 'w') as f:
    f.write(new_js)

r = subprocess.run(['node', '--check', '/tmp/spa_all_fixed.mjs'], capture_output=True, text=True, timeout=15)
if r.returncode == 0:
    print("\nSUCCESS: node --check PASSES!")
    # Write back to the file
    with open('empire_command_spa.py', 'w', encoding='utf-8') as f:
        f.write(prefix + new_js + suffix)
    print("Written to empire_command_spa.py")
else:
    print(f"\nFAILED: {r.stderr[:500]}")
    m = re.search(r':(\d+):', r.stderr)
    if m:
        err_line = int(m.group(1))
        js_lines = new_js.split('\n')
        print(f"\nError at line {err_line}:")
        for j in range(max(0, err_line-2), min(len(js_lines), err_line+3)):
            marker_c = '>>>' if j == err_line-1 else '   '
            print(f'{marker_c} {j+1}: {js_lines[j][:200]}')
