"""Trace template literal open/close structure to find unclosed templates."""
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

lines = js_bytes.split(b'\n')

# Find function Leads and its return html`
leads_start = None
return_html_line = None
for i, line in enumerate(lines):
    if b'function Leads' in line:
        leads_start = i
    if leads_start and i > leads_start and i < leads_start + 100 and b'return html' in line:
        if return_html_line is None:
            return_html_line = i

print(f"Leads function starts at line {leads_start + 1}")
print(f"return html at line {return_html_line + 1}")

# From return_html_line to line 1410, count all backtick chars with indentation
print("\n=== Template backtick analysis ===")
templates = []
for i in range(return_html_line, min(return_html_line + 300, len(lines))):
    l = lines[i]
    bt = sum(1 for c in l if c == 0x60)
    if bt > 0:
        templates.append((i, bt, l))

for idx, bt, l in templates:
    print(f"  Line {idx+1}: bt={bt} | {l[:120]!r}")

if templates:
    print(f"\nTotal template backtick lines: {len(templates)}")
    total_bt = sum(t[1] for t in templates)
    print(f"Total backticks in range: {total_bt}")
    print(f"Net open templates (odd=unclosed): {total_bt % 2}")
