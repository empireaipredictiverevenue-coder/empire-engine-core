import sys

with open('/tmp/spa_check.js', 'r') as f:
    content = f.read()

lines = content.split('\n')
depth = 0  # template literal nesting
in_template = False
in_single = False
in_double = False
in_line_comment = False
in_block_comment = False

for i, line in enumerate(lines):
    j = 0
    in_line_comment = False
    while j < len(line):
        ch = line[j]
        next_ch = line[j+1] if j+1 < len(line) else ''
        
        # Handle comments
        if not in_template and not in_single and not in_double and not in_block_comment:
            if ch == '/' and next_ch == '/':
                in_line_comment = True
                break
            if ch == '/' and next_ch == '*':
                in_block_comment = True
                j += 2
                continue
        
        if in_block_comment:
            if ch == '*' and next_ch == '/':
                in_block_comment = False
                j += 2
                continue
            j += 1
            continue
        
        if in_line_comment:
            break
        
        # Handle strings
        if not in_template and not in_single and not in_double:
            if ch == "'":
                in_single = True
                j += 1
                continue
            if ch == '"':
                in_double = True
                j += 1
                continue
        
        if in_single:
            if ch == '\\':
                j += 2
                continue
            if ch == "'":
                in_single = False
            j += 1
            continue
        
        if in_double:
            if ch == '\\':
                j += 2
                continue
            if ch == '"':
                in_double = False
            j += 1
            continue
        
        # Handle template literals
        if not in_template:
            if ch == '`':
                in_template = True
                depth += 1
                print(f'Line {i+1} col {j}: OPEN template, depth={depth}')
        else:
            if ch == '`':
                # Check if it's escaped
                backslashes = 0
                k = j - 1
                while k >= 0 and line[k] == '\\':
                    backslashes += 1
                    k -= 1
                if backslashes % 2 == 0:
                    in_template = False
                    depth -= 1
                    print(f'Line {i+1} col {j}: CLOSE template, depth={depth}')
                else:
                    print(f'Line {i+1} col {j}: escaped backtick')
            elif ch == '$' and next_ch == '{':
                depth += 1
                j += 1
                print(f'Line {i+1} col {j}: OPEN expr, depth={depth}')
            elif ch == '}':
                # In a template literal, a } could close an expression or be literal
                # This is hard to track properly, but we can try
                print(f'Line {i+1} col {j}: "}}" in template, depth={depth}')
        
        j += 1
    
    if i >= 1427 and i <= 1430:
        print(f'  => Line {i+1} state: in_template={in_template} depth={depth}')
        print(f'  => {line[:100]}')

print(f'\nFinal state: in_template={in_template} depth={depth}')
print(f'Total backtick opens: {depth} unclosed')
