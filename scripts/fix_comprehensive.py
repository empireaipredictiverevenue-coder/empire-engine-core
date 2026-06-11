#!/usr/bin/env python3
"""
Comprehensive fix for all template literal issues in empire_command_spa.py

Known issues:
1. AgiLoop function - missing closing `}` (line ~947)
2. Leads function - unclosed template `${statusActions.length > 0 ? html` (line ~1396)
3. HealthMonitor, SniperFleet, Governor - `: ''}` creates triple-branch ternary
4. Orphaned lines from template absorption
"""

import subprocess
import re
import sys

def fix_all():
    # Read the committed JS
    r = subprocess.run(['git', 'show', 'HEAD:empire_command_spa.py'], capture_output=True, text=True)
    content = r.stdout
    
    marker = '_SPA_JS = r"""'
    start = content.find(marker)
    rest = content[start + len(marker):]
    end = rest.rfind('"""')
    js = rest[:end]
    lines = js.split('\n')
    
    print(f"Starting: {len(lines)} lines, {len(js)} bytes")
    print(f"Backticks: {js.count(chr(96))}")
    
    # === FIX 1: AgiLoop missing closing brace ===
    # Find AgiLoop and next function
    agi_start = -1
    next_func = -1
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith('function AgiLoop') and '{' in stripped:
            agi_start = i
        elif agi_start >= 0 and next_func < 0 and stripped.startswith('function ') and '{' in stripped:
            next_func = i
            break
    
    if agi_start >= 0 and next_func >= 0:
        last_line = lines[next_func - 1]
        if not last_line.strip().endswith('}'):
            print(f"\nFix 1: Adding missing }} after AgiLoop (after line {next_func})")
            lines.insert(next_func, '}')
            print(f"  Inserted }} before line {next_func+1}")
    
    # === FIX 2: Close unclosed template in Leads ===
    for i, line in enumerate(lines):
        if "statusActions.length > 0 ? html`" in line:
            print(f"\nFix 2: Closing unclosed template at line {i+1}")
            print(f"  Before: {repr(line[:80])}")
            lines[i] = line.replace("statusActions.length > 0 ? html`", "statusActions.length > 0 ? '' : ''")
            print(f"  After:  {repr(lines[i][:80])}")
            break
    
    # === FIX 3: Remove orphaned ActivityLog artifact ===
    # The line after the fix might start weird artifacts
    for i, line in enumerate(lines):
        if line.strip().startswith('n//') and 'ACTIVITY LOG' in line:
            print(f"\nFix 3: Removing orphaned line {i+1}")
            lines[i] = ''
    
    # === FIX 4: Fix `: ''}` in HealthMonitor that creates triple-branch ternary ===
    # Find HealthMonitor and next function
    hm_start = -1
    for i, line in enumerate(lines):
        if 'function HealthMonitor' in line:
            hm_start = i
            break
    
    if hm_start >= 0:
        # Find the end of HealthMonitor (next function)
        hm_end = len(lines)
        for i in range(hm_start + 1, len(lines)):
            stripped = line.strip()
            if i > hm_start and stripped.startswith('function ') and '{' in stripped:
                hm_end = i
                break
        
        # Find `: ''}` patterns in HealthMonitor that are after a ternary with : html`
        print(f"\nFix 4: Fixing HealthMonitor template issues")
        fixed_count = 0
        for i in range(hm_start, hm_end):
            line = lines[i]
            stripped = line.strip()
            # Pattern: line has ` : ''}` and the backtick starts the line
            # AND there's already a : html` before it (creating triple ternary)
            if "` : ''}" in stripped and stripped.strip().startswith('`'):
                # Check if there's an outer ternary with : html` before this
                # Simple check: if the line only has the backtick close and extra else
                indent = line[:len(line) - len(stripped)]
                lines[i] = indent + '`}'
                fixed_count += 1
                print(f"  Fixed line {i+1}: {repr(line[:80])} -> {repr(lines[i][:80])}")
        
        if fixed_count == 0:
            print(f"  No fixes needed in HealthMonitor")
    
    # === FIX 5: Fix SniperFleet `: ''}` issues ===
    for func_name in ['SniperFleet', 'Governor']:
        func_start = -1
        func_end = len(lines)
        for i, line in enumerate(lines):
            stripped = line.strip()
            if f'function {func_name}' in stripped and '{' in stripped:
                func_start = i
            elif func_start >= 0 and func_end == len(lines) and stripped.startswith('function ') and '{' in stripped:
                func_end = i
                break
        
        if func_start < 0:
            continue
        
        print(f"\nFix 5: Fixing {func_name} template issues")
        fixed_count = 0
        for i in range(func_start, func_end):
            line = lines[i]
            stripped = line.strip()
            if "` : ''}" in stripped:
                # Only fix if the backtick starts the stripped content
                # (meaning it's a template close, not template content)
                # AND there's already : html` in the same ternary
                # We check by looking at the pattern: ` : ''} after a ` : html`` ` : ''}`
                # Actually we need to be more careful - some ` : ''} are correct
                
                # Check if there's a : before the backtick
                bt_idx = stripped.index('`')
                after_bt = stripped[bt_idx+1:]
                if ': ' in after_bt and "'" in after_bt:
                    # Check if : html` appears somewhere before this in the same function
                    # For now, check if the line has both ` : and also another ` : earlier
                    # This isn't perfect but catches the common case
                    pass
                
                # Simple heuristic: if line starts with backtick and has ` : ''}
                # (template close followed by extra else)
                if stripped.startswith('`') and "` : ''}" == stripped[-7:]:
                    indent = line[:len(line) - len(stripped)]
                    lines[i] = indent + '`}'
                    fixed_count += 1
                    print(f"  Fixed line {i+1}: {repr(line[:80])} -> {repr(lines[i][:80])}")
        
        if fixed_count == 0:
            print(f"  No fixes applied to {func_name}")
    
    # Save intermediate file
    new_js = '\n'.join(lines)
    with open('/tmp/spa_comprehensive_fix.mjs', 'w') as f:
        f.write(new_js)
    
    print(f"\n=== Testing with node --check ===")
    r = subprocess.run(['node', '--check', '/tmp/spa_comprehensive_fix.mjs'], capture_output=True, text=True, timeout=15)
    if r.returncode == 0:
        print("PASS!")
        return True, new_js
    else:
        print(f"FAIL: {r.stderr[:300]}")
        m = re.search(r':(\d+):', r.stderr)
        if m:
            err_line = int(m.group(1))
            print(f"  Error at line {err_line}")
            lns = new_js.split('\n')
            for i in range(max(0, err_line-2), min(len(lns), err_line+3)):
                marker = '>>>' if i == err_line-1 else '   '
                print(f"  {marker} {i+1}: {repr(lns[i][:120])}")
        return False, new_js

if __name__ == '__main__':
    success, js = fix_all()
    sys.exit(0 if success else 1)
