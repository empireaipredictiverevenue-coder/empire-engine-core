"""
Find gaps between detected section boundaries.
"""
import re

with open('empire_command_spa.py', 'r') as f:
    content = f.read()

spa_match = re.search(r'_SPA_JS = r"""', content)
closing = content.rfind('"""')
js_start = spa_match.end()
js_content = content[js_start:closing]

pulse_start = js_content.find('function Pulse(')
pulse_end = js_content.find('function stripMeta')
pulse_code = js_content[pulse_start:pulse_end]

def find_template_end(text, start_pos):
    i = start_pos
    stack = []
    while i < len(text):
        ch = text[i]
        if ch == '`':
            if not stack:
                return i
            elif stack[-1] == 'template':
                stack.pop()
            else:
                stack.append('template')
        elif ch == '$' and i + 1 < len(text) and text[i + 1] == '{':
            stack.append('expression')
            i += 1
        elif ch == '}':
            if stack and stack[-1] == 'expression':
                stack.pop()
        i += 1
    return -1

# Find main template
search_start = 0
while True:
    pos = pulse_code.find('return html`', search_start)
    if pos < 0:
        break
    bt_end = find_template_end(pulse_code, pos + len('return html`'))
    if bt_end > 0:
        t = pulse_code[pos + len('return html`'):bt_end]
        if 'pulse-grid' in t:
            # Check gaps
            print(f"Template: {len(t)} chars")
            
            # Example sections from the script
            end = ft = 0
            sections = [
                ('section_header', lambda: (0, t.find('<div class="pulse-grid">'))),
                ('pulse_grid', lambda: (t.find('<div class="pulse-grid">'), t.find('${activePartnersList.length > 0 ? html`'))),
                ('pipeline', lambda: (t.find('${activePartnersList.length > 0 ? html`'), t.find('${(() => {'))),
            ]
            
            comp_start = t.find('${(() => {')
            # Find compliance end: })()} + then find ` : ''}`
            comp_end_marker = t.find('})()}', comp_start)
            rest = t[comp_end_marker + len('})()}'):]
            
            END_MARKER = "` : ''}"
            end_of_expr = rest.find(END_MARKER)
            full_comp_end = comp_end_marker + len('})()}') + end_of_expr + len(END_MARKER)
            
            print(f"\nTemplate offset {full_comp_end} after compliance:")
            print(repr(t[full_comp_end:full_comp_end+50]))
            
            # Find AMD chart after compliance
            amd_marker = '${amdTotal > 0 ? html`'
            amd_start = t.find(amd_marker, full_comp_end)
            print(f"\nAMD chart at offset {amd_start}")
            print(f"Gap: {amd_start - full_comp_end} chars")
            if amd_start - full_comp_end > 0:
                print(f"Gap content: {repr(t[full_comp_end:amd_start])}")
            
            # Find end of AMD
            amd_expr = t[amd_start:]
            close_idx_a = amd_expr.find(END_MARKER)
            amd_end = amd_start + close_idx_a + len(END_MARKER)
            print(f"\nAMD ends at offset {amd_end}")
            
            # Find live panel
            live_marker = '<div class="live-panel">'
            live_start = t.find(live_marker, amd_end)
            print(f"Live panel at offset {live_start}")
            print(f"Gap: {live_start - amd_end} chars")
            if live_start - amd_end > 0:
                print(f"Gap content: {repr(t[amd_end:live_start])}")
            
            # Last </div>
            last_div = t.rfind('</div>')
            print(f"Last </div> at offset {last_div}")
            print(f"Live to last div: {last_div} - {live_start} = {last_div - live_start}")
            
            break
    search_start = pos + 1
