#!/usr/bin/env python3
"""
Fix unnecessary backslash-quotes (\\") in the Python source file's _SPA_JS raw string.

Inside Python raw strings (r\"\"\"...\"\"\"), \\" is stored as literal backslash + double quote.
When served as JS inside template literals, \\" is an unnecessary escape that may confuse
ES module parsers (like <script type="module"> in browsers, or .mjs files in Node.js).

Fix: Replace \\" with " everywhere inside the _SPA_JS string.
"""
import re

with open('empire_command_spa.py', 'r') as f:
    content = f.read()

# Find the _SPA_JS region
marker = '_SPA_JS = r"""'
start = content.find(marker)
if start == -1:
    print("ERROR: Could not find _SPA_JS marker")
    exit(1)

# Find the closing triple quotes
# Search for the last occurrence of triple quotes after the opening
rest = content[start + len(marker):]
end_marker = '"""'
end = start + len(marker) + rest.rfind(end_marker)

# Extract the JS region (inside the raw string)
js_region = content[start + len(marker):end]

# Count \\" patterns (literal backslash + double quote)
# In the raw string, \\" appears as \ followed by "
# In Python regex, we need to match literal \"
count_before = len(re.findall(r'\\"', js_region))
print(f"Found {count_before} backslash-quote patterns in JS region")

# Replace \\" with " (just the double quote)
js_fixed = re.sub(r'\\"', '"', js_region)

count_after = len(re.findall(r'\\"', js_fixed))
print(f"After fix: {count_after} remaining")

# Rebuild the file
fixed_content = (
    content[:start + len(marker)] +
    js_fixed +
    content[end:]
)

with open('empire_command_spa.py', 'w') as f:
    f.write(fixed_content)

print(f"Fixed! Removed {count_before - count_after} backslash-quote patterns")
print("Done.")
