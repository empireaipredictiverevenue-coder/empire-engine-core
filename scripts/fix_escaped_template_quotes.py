#!/usr/bin/env python3
"""
Fix unnecessary backslash-escaped double quotes (\\") inside JS template literals.

Inside JavaScript template literals (backtick strings), double quotes don't need
escaping. The \\" is an unnecessary escape sequence that modern browsers handle
but can cause "Unexpected token 'class'" errors in strict mode.

This script finds html`...` template literals and replaces \\" with " inside them.
"""
import re

with open("empire_command_spa.py", "r") as f:
    content = f.read()

# Find all html`...` template literal patterns and fix escaped quotes inside them
# We use a non-greedy match between backticks, but only when preceded by html
def fix_template_escapes(match):
    full = match.group(0)
    # Replace \" with " inside the template literal
    full = full.replace('\\"', '"')
    return full

# Pattern: html`...` (template literal starting with html`)
# We match from html` to the closing backtick, handling nested ${...}
# This is a simplified approach - we'll fix ALL \ " inside html`...` templates
count_before = content.count('\\"')

# Fix escaped quotes in html template literal sections
# Strategy: find html` then find the matching closing backtick
result = []
i = 0
in_template = False
template_start = 0

while i < len(content):
    if not in_template:
        if content[i:i+5] == 'html`':
            in_template = True
            template_start = i
            result.append(content[i])
            i += 1
        else:
            result.append(content[i])
            i += 1
    else:
        if content[i] == '`':
            # Check if this backtick is escaped (shouldn't be in well-formed JS)
            if i > 0 and content[i-1] == '\\':
                # Escaped backtick - part of template content
                result.append(content[i])
                i += 1
            else:
                # End of template literal
                in_template = False
                result.append(content[i])
                i += 1
        elif content[i] == '\\' and i+1 < len(content) and content[i+1] == '"':
            # Fix: replace \" with " inside template literal
            result.append('"')
            i += 2
        else:
            result.append(content[i])
            i += 1

fixed = ''.join(result)
count_after = fixed.count('\\"')

with open("empire_command_spa.py", "w") as f:
    f.write(fixed)

print(f"Fixed {count_before - count_after} unnecessary escaped quotes in template literals")
print(f"Remaining \\\" count: {count_after}")
print("Done.")
