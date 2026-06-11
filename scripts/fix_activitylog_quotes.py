"""Targeted fix: replace `\"` with `"` on specific ActivityLog template lines."""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else 'empire_command_spa.py'

with open(path, 'rb') as f:
    content = f.read()

marker = b'_SPA_JS = r' + b'"' * 3
close_marker = b'"' * 3

spa_start = content.find(marker)
spa_js_start = spa_start + len(marker)
spa_end = content.rfind(close_marker)
js_bytes = content[spa_js_start:spa_end]

replaced = 0

# Fix specific patterns in ActivityLog
targets = [
    b'html`<div class=\\"stub\\"><div class=\\"stub-title\\">Could not load Activity Log</div><div class=\\"stub-body\\">',
    b'html`<div class=\\"stub\\"><div class=\\"stub-body\\">Loading activity log',
    b'html`<div class=\\"act-empty\\">',
    b'html`<div class=\\"act-feed\\">',
]

for target in targets:
    replacement = target.replace(b'\\"', b'"')
    count = js_bytes.count(target)
    if count > 0:
        js_bytes = js_bytes.replace(target, replacement)
        replaced += count

# Fix any remaining \" in ActivityLog section
dash = bytes([0xe2, 0x94, 0x80, 0xe2, 0x94, 0x80])
activity_marker = b'// ' + dash + b' ACTIVITY LOG'
act_idx = js_bytes.find(activity_marker)
if act_idx >= 0:
    next_section = js_bytes.find(b'\nfunction ', act_idx + 50)
    if next_section < 0:
        next_section = js_bytes.find(b'\n// ' + dash + b' ', act_idx + 50)
    if next_section < 0:
        next_section = len(js_bytes)
    
    act_section = js_bytes[act_idx:next_section]
    act_fixed = act_section.replace(b'\\"', b'"')
    extra = act_section.count(b'\\"') - act_fixed.count(b'\\"')
    replaced += extra
    js_bytes = js_bytes[:act_idx] + act_fixed + js_bytes[next_section:]

new_content = content[:spa_js_start] + js_bytes + content[spa_end:]
with open(path, 'wb') as f:
    f.write(new_content)

print(f"Total: {replaced} replacements")
