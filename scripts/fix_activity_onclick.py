#!/usr/bin/env python3
"""Fix onClick using exact bytes match."""
with open('/root/empire-v49/empire_command_spa.py', 'rb') as f:
    content = f.read()

# The exact bytes from the file (Python repr shows \\` meaning literal backslash-backtick)
old = b'const el = document.querySelector(\\`.ld-lead[data-lead-id="${aLeadId}"\\]`);'
new = b"const el = document.querySelector('[data-lead-id=\"' + aLeadId + '\"]');"

if old in content:
    content = content.replace(old, new, 1)
    with open('/root/empire-v49/empire_command_spa.py', 'wb') as f:
        f.write(content)
    print("FIXED - onClick simplified")
else:
    # Try to find just the querySelector part and rebuild
    idx = content.find(b'querySelector')
    if idx >= 0:
        # Extract the full line
        line_start = content.rfind(b'\n', 0, idx) + 1
        line_end = content.find(b'\n', idx)
        old_line = content[line_start:line_end]
        new_line = b"                      const el = document.querySelector('[data-lead-id=\"' + aLeadId + '\"]');"
        print(f"Old line: {repr(old_line)}")
        print(f"Replacing with: {repr(new_line)}")
        content = content[:line_start] + new_line + content[line_end:]
        with open('/root/empire-v49/empire_command_spa.py', 'wb') as f:
            f.write(content)
        print("FIXED - line replaced")
