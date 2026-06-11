#!/usr/bin/env python3
"""
Accurately find 'class' keywords in the served JS that appear OUTSIDE of 
template literals, strings, or comments.

This uses a proper character-level state machine rather than line-based heuristics.
"""
import re
import sys

from empire_command_spa import command_spa_page

html = command_spa_page()
m = re.search(r'<script type="module">(.*?)</script>', html, re.DOTALL)
if not m:
    print("ERROR: Could not extract module script")
    sys.exit(1)

js = m.group(1)

# State machine
# States: NORMAL, TEMPLATE_LITERAL, SINGLE_QUOTE_STRING, DOUBLE_QUOTE_STRING,
#         LINE_COMMENT, BLOCK_COMMENT, REGEX
state = "NORMAL"
depth = 0  # for nested template literals

# Find every occurrence of 'class' and check its context
class_matches = []
for m2 in re.finditer(r'\bclass\b', js):
    pos = m2.start()
    
    # Walk backwards from this position to the start of the file,
    # tracking string/template/comment state
    state = "NORMAL"
    template_depth = 0
    i = 0
    while i < pos:
        ch = js[i]
        
        if state == "NORMAL":
            if ch == '`':
                state = "TEMPLATE_LITERAL"
                template_depth = 1
            elif ch == "'":
                state = "SINGLE_QUOTE_STRING"
            elif ch == '"':
                state = "DOUBLE_QUOTE_STRING"
            elif ch == '/' and i + 1 < pos:
                if js[i+1] == '/':
                    state = "LINE_COMMENT"
                    i += 1
                elif js[i+1] == '*':
                    state = "BLOCK_COMMENT"
                    i += 1
                    
        elif state == "TEMPLATE_LITERAL":
            if ch == '`' and (i == 0 or js[i-1] != '\\'):
                template_depth -= 1
                if template_depth == 0:
                    state = "NORMAL"
            elif ch == '$' and i + 1 < pos and js[i+1] == '{':
                template_depth += 1  # nesting
                
        elif state == "SINGLE_QUOTE_STRING":
            if ch == "'" and (i == 0 or js[i-1] != '\\'):
                state = "NORMAL"
                
        elif state == "DOUBLE_QUOTE_STRING":
            if ch == '"' and (i == 0 or js[i-1] != '\\'):
                state = "NORMAL"
                
        elif state == "LINE_COMMENT":
            if ch == '\n':
                state = "NORMAL"
                
        elif state == "BLOCK_COMMENT":
            if ch == '*' and i + 1 < pos and js[i+1] == '/':
                state = "NORMAL"
                i += 1
                
        i += 1
    
    if state != "NORMAL" and state != "LINE_COMMENT":
        # 'class' is inside a string/template/comment — fine
        continue
    
    if state == "NORMAL":
        # Check the character before 'class' to make sure it's not part of
        # a longer identifier or a string we missed
        before = js[pos - 1] if pos > 0 else ' '
        after_char = js[pos + 5] if pos + 5 < len(js) else ' '
        
        # 'class' as a keyword is followed by whitespace, {, (, or similar
        # If it's preceded by a dot/property access, it's fine
        if before == '.':
            continue
            
        # Find the line number
        line_num = js[:pos].count('\n') + 1
        line_start = js.rfind('\n', 0, pos) + 1
        line_end = js.find('\n', pos)
        if line_end == -1:
            line_end = len(js)
        col = pos - line_start + 1
        
        context = js[max(0, pos - 20):pos + 20]
        
        print(f"FOUND 'class' outside string/template at JS line {line_num}, col {col}")
        print(f"  Context: ...{repr(context)}...")
        print(f"  Line content: {js[line_start:line_end][:200]}")
        print()

# Summary
print(f"Search complete.")
