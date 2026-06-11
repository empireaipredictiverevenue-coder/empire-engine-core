#!/usr/bin/env python3
"""Find which function/section in the JS triggers the ES module parse failure."""
import re, subprocess, tempfile, os

with open('empire_command_spa.py') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
start = content.find(marker)
rest = content[start + len(marker):]
end = rest.rfind('"""')
js = rest[:end]

# Check if the JS, when wrapped as a proper module, parses correctly
# Try adding an import and export to make it a valid module
# Then remove sections one by one

# First: what if we just wrap the entire file in an async function?
wrapped = f'export default async function(){{\n{js}\n}};\n'

with tempfile.NamedTemporaryFile(suffix='.mjs', mode='w', delete=False) as f:
    fname = f.name
    f.write(wrapped)

r = subprocess.run(['node', '--check', fname], capture_output=True, text=True, timeout=10)
os.unlink(fname)

if r.returncode == 0:
    print("Wrapped in function: PASS - the issue is at MODULE TOP LEVEL")
else:
    print(f"Wrapped in function: FAIL")
    # Extract line
    m = re.search(r':(\d+):', r.stderr)
    if m:
        err_line = int(m.group(1))
        lines = wrapped.split('\n')
        # Adjust for the wrapper line
        adj_line = err_line - 2  # account for wrapper
        if 0 <= adj_line < len(lines):
            print(f"  At adjusted JS line {adj_line}: {lines[adj_line][:150]}")

# Second: check if the issue is with import statements at the top
# Remove imports and see if it parses
without_imports = re.sub(r'^import .+?\n', '', js, flags=re.MULTILINE)
# Also remove the \n at the start if present
without_imports = without_imports.lstrip('\n')

with tempfile.NamedTemporaryFile(suffix='.mjs', mode='w', delete=False) as f:
    fname = f.name
    f.write(without_imports)

r = subprocess.run(['node', '--check', fname], capture_output=True, text=True, timeout=10)
os.unlink(fname)

if r.returncode == 0:
    print("Without imports: PASS - the issue is with HOW imports interact with the rest of the code")
else:
    print("Without imports: FAIL - the issue is in the non-import code")
    m = re.search(r':(\d+):', r.stderr)
    if m:
        print(f"  Error at line {m.group(1)}")
