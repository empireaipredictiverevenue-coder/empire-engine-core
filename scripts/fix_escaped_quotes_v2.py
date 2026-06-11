#!/usr/bin/env python3
"""
Fix unnecessary backslash-escaped double quotes (\\") in JS template literals.

Python raw strings (r"""...""") preserve backslashes literally. When the JS code 
has `class=\"stub\"` inside backtick template literals, the Python raw string 
preserves the backslash, resulting in a literal `\"` in the served JS.

Inside Javascipt template literals (backticks), `\"` is an unnecessary escape
- it's valid but can cause issues in strict-mode ES module parsing.

Fix: Replace `\"` with just `"` everywhere inside the SPA JS, since all
instances are inside template literals where double quotes don't need escaping.
"""

with open("empire_command_spa.py", "r") as f:
    content = f.read()

# Find the SPA_JS region
marker = "_SPA_JS = r\"\"\""
start = content.find(marker)
if start == -1:
    print("ERROR: Could not find _SPA_JS marker")
    exit(1)

# Find the closing triple quotes
end_marker = "\"\"\""
# Search for the last occurrence of triple quotes after the opening
rest = content[start + len(marker):]
end = start + len(marker) + rest.rfind(end_marker)

# Extract the JS region
js_region = content[start + len(marker):end]

# Count before
before = js_region.count('\\"')

# Replace \" with " (only inside the JS region)
js_fixed = js_region.replace('\\"', '"')

after = js_fixed.count('\\"')

# Rebuild the file
fixed_content = (
    content[:start + len(marker)] +
    js_fixed +
    content[end:]
)

with open("empire_command_spa.py", "w") as f:
    f.write(fixed_content)

print(f"Fixed {before - after} occurrences of \\\" in the JS template")
print(f"Remaining: {after}")
print("Done.")
