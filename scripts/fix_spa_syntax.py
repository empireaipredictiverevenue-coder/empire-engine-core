#!/usr/bin/env python3
"""
Diagnose and fix JS syntax errors in the SPA by:
1. Extracting rendered JS from command_spa_page()
2. Running Node.js syntax check
3. Finding the error context in the source file
4. Suggesting/carrying out the fix
"""
import sys, os, re, subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from empire_command_spa import command_spa_page

html = command_spa_page()

# Extract the module script block
blocks = re.findall(r'<script type="module">(.*?)</script>', html, re.DOTALL)
if not blocks:
    # Fallback: get the second script block
    all_scripts = re.findall(r'<script[^>]*>(.*?)</script>', html, re.DOTALL)
    if len(all_scripts) >= 2:
        js = all_scripts[1]
    else:
        js = ""
else:
    js = blocks[0]

print(f"Rendered JS length: {len(js)} chars")

# Write to temp file
tmpfile = "/tmp/spa_check.mjs"
with open(tmpfile, "w") as f:
    f.write(js)

# Run Node.js syntax check
result = subprocess.run(
    ["node", "--check", tmpfile],
    capture_output=True, text=True, timeout=15
)

if result.returncode == 0:
    print("✅ Node.js syntax check: PASSED")
    sys.exit(0)

# Parse the error
err_text = result.stderr.strip()
print(f"❌ Node.js syntax error:\n{err_text}")

# Extract line number from error
line_match = re.search(r':(\d+):(\d+)', err_text.split('\n')[0])
if line_match:
    err_line = int(line_match.group(1))
    err_col = int(line_match.group(2))
    print(f"\nError at line {err_line}, column {err_col}")
    
    # Show context in rendered JS
    rendered_lines = js.split('\n')
    for i in range(max(0, err_line-5), min(len(rendered_lines), err_line+3)):
        marker = "  ← ERROR HERE" if i == err_line - 1 else ""
        print(f"  {i+1:5d}: {rendered_lines[i][:120]}{marker}")
    
    # Now find this text in the source file
    with open(os.path.join(os.path.dirname(__file__), '..', 'empire_command_spa.py'), 'r') as f:
        source = f.read()
    
    # Search for the error line's content in the source
    error_content = rendered_lines[err_line - 1].strip()
    print(f"\nSearching for: {repr(error_content[:80])}")
    
    idx = source.find(error_content[:60])
    if idx >= 0:
        src_line = source[:idx].count('\n') + 1
        print(f"Found in source at line {src_line}")
        # Show source context
        src_lines = source.split('\n')
        for i in range(max(0, src_line-3), min(len(src_lines), src_line+2)):
            print(f"  SRC {i+1}: {src_lines[i]}")
    else:
        print("Could not find exact match in source (may be in _SPA_JS raw string)")
        # Try searching within _SPA_JS
        js_start = source.find('_SPA_JS = r"""')
        js_section_start = js_start + len('_SPA_JS = r"""')
        js_section_end = source.find('"""', js_section_start)
        js_source = source[js_section_start:js_section_end]
        js_lines = js_source.split('\n')
        
        if err_line <= len(js_lines):
            print(f"\n_SPA_JS line {err_line}: {repr(js_lines[err_line-1])}")
        
        # Show context around the error in _SPA_JS source
        for i in range(max(0, err_line-6), min(len(js_lines), err_line+3)):
            marker = "  ← ERROR HERE" if i == err_line - 1 else ""
            print(f"  JS {i+1:5d}: {repr(js_lines[i])[:150]}{marker}")

# Clean up
if os.path.exists(tmpfile):
    os.unlink(tmpfile)
