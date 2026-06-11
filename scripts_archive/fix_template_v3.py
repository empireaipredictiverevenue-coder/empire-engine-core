"""
Fix the unclosed templates in empire_command_spa.py.
The Leads function's return html` template and inner templates are never closed,
causing the ActivityLog function's content to be misparsed as template content.
"""
import subprocess, re, sys

with open('empire_command_spa.py', 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
start = content.find(marker)
rest = content[start + len(marker):]
end = rest.rfind('"""')
js = rest[:end]

js_lines = js.split('\n')
print(f"Total JS lines: {len(js_lines)}")

# Count all backticks
bt_count = 0
for line in js_lines:
    bt_count += line.count('`')
print(f"Total backticks: {bt_count} (even: {bt_count % 2 == 0})")

# Find the Leads function's return html` template
# We need to find where the main return html` opens and the template that's unclosed
leads_start = None
leads_return_line = None
leads_map_line = None
for i, line in enumerate(js_lines):
    if 'function Leads(' in line:
        leads_start = i
        print(f"Leads function at JS line {i+1}")
    if leads_start is not None and leads_return_line is None and 'return html' in line and i > leads_start:
        leads_return_line = i
        print(f"Leads return html` at JS line {i+1}")
    if 'filtered.map(l =>' in line or 'leads.map(l =>' in line:
        leads_map_line = i
        print(f"Leads .map at JS line {i+1}")

# Find the ActivityLog function
al_start = None
for i, line in enumerate(js_lines):
    if 'function ActivityLog(' in line:
        al_start = i
        print(f"ActivityLog function at JS line {i+1}")
        break

if leads_start and al_start:
    # Count template depth between Leads return and ActivityLog
    template_depth = 0
    interp_depth = 0
    in_string = False
    str_char = None
    
    for idx in range(leads_start, al_start):
        line = js_lines[idx]
        i = 0
        while i < len(line):
            ch = line[i]
            nch = line[i+1] if i+1 < len(line) else ''
            
            if ch == '\\' and in_string:
                i += 2
                continue
            
            if not in_string:
                if ch in ("'", '"', '`'):
                    in_string = True
                    str_char = ch
                    if ch == '`':
                        template_depth += 1
                    i += 1
                    continue
            else:
                if ch == str_char:
                    in_string = False
                    if str_char == '`':
                        template_depth -= 1
                    str_char = None
                    i += 1
                    continue
                if str_char == '`' and ch == '$' and nch == '{':
                    interp_depth += 1
                    i += 2
                    continue
                i += 1
                continue
            
            if interp_depth > 0:
                if ch == '{':
                    interp_depth += 1
                elif ch == '}':
                    interp_depth -= 1
            
            i += 1
    
    print(f"\nTemplate depth at ActivityLog start: template={template_depth}, interp={interp_depth}")
    print(f"Need to close {template_depth} template(s) and {interp_depth} interpolation(s)")

# Now let me count backtick pairs more carefully
# Let me find ALL backtick lines in the Leads function (between leads_start and al_start)
print("\n=== All backtick lines in Leads function ===")
for i in range(leads_start, al_start):
    line = js_lines[i]
    count = line.count('`')
    if count > 0:
        print(f"JS {i+1}: {count} backtick(s): {line.strip()[:120]}")

# Check if there are backticks inside string literals that shouldn't be counted
# This could happen if there's a backtick inside a ' or " string
print("\n=== Looking for backticks inside single/double quoted strings ===")
for i in range(leads_start, al_start):
    line = js_lines[i]
    in_sq = False  # in single quote
    in_dq = False  # in double quote
    bt_in_string = False
    for j, ch in enumerate(line):
        if ch == "'" and not in_dq:
            in_sq = not in_sq
        elif ch == '"' and not in_sq:
            in_dq = not in_dq
        elif ch == '`' and (in_sq or in_dq):
            bt_in_string = True
            print(f"  JS {i+1}: backtick at col {j} inside string: {line.strip()[:100]}")

if not bt_in_string:
    print("  No backticks inside string literals")

# Now let me find the exact issue by looking at template literal positions
print("\n=== Template literal analysis ===")
# Track template depth properly, accounting for ${} interpolation
depth = 0
interp = 0
in_str = False
str_ch = None

for idx in range(leads_start, min(len(js_lines), al_start + 5)):
    line = js_lines[idx]
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
                if ch == '`':
                    depth += 1
                    if depth > 0 and interp == 0:
                        # Check if this is a tagged template (html`)
                        before = line[max(0, j-5):j]
                        if 'html' in before:
                            print(f"    html` OPEN at JS {idx+1} col {j} (depth={depth})")
                j += 1
                continue
        else:
            if ch == str_ch:
                in_str = False
                if str_ch == '`':
                    depth -= 1
                    if depth >= 0:
                        print(f"    ` CLOSE at JS {idx+1} col {j} (depth={depth})")
                str_ch = None
                j += 1
                continue
            if str_ch == '`' and ch == '$' and nch == '{':
                interp += 1
                j += 2
                continue
            j += 1
            continue
        
        if interp > 0:
            if ch == '{':
                interp += 1
            elif ch == '}':
                interp -= 1
                if interp == 0:
                    pass  # interpolation closed
        
        j += 1

print(f"\nFinal: depth={depth}, interp={interp}")
