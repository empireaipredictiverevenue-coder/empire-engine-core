"""
Refactor Pulse function: extract 6 template sections into const variables.
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

# Find main template containing 'pulse-grid'
search_start = 0
main_return_start = -1
main_template = ""
main_bt_end = -1

while True:
    pos = pulse_code.find('return html`', search_start)
    if pos < 0:
        break
    bt_end = find_template_end(pulse_code, pos + len('return html`'))
    if bt_end > 0:
        t = pulse_code[pos + len('return html`'):bt_end]
        if 'pulse-grid' in t:
            main_return_start = pos
            main_template = t
            main_bt_end = bt_end
            break
    search_start = pos + 1

assert main_return_start >= 0, "Could not find main return template"
print(f"Main template: {len(main_template)} chars")

# Find ALL marker positions
pg = '<div class="pulse-grid">'
pm = '${activePartnersList.length > 0 ? html`'
cm = '${(() => {'
ptm = '${allPartners.length > 0 ? html`'
am = '${amdTotal > 0 ? html`'
lm = '<div class="live-panel">'

pg_start = main_template.find(pg)
p_start = main_template.find(pm, pg_start)
c_start = main_template.find(cm, p_start)
pt_start = main_template.find(ptm, c_start)
# AMD: find SECOND occurrence (first is mini-bar in pulse-grid)
a_first = main_template.find(am)
a_start = main_template.find(am, a_first + 1)  # second occurrence
l_start = main_template.find(lm, a_start)

assert pg_start >= 0
assert p_start >= 0
assert c_start >= 0
assert pt_start >= 0
assert a_start >= 0
assert l_start >= 0

last_div = main_template.rfind('</div>')

print(f"pg  = {pg_start}")
print(f"p   = {p_start}")
print(f"c   = {c_start}")
print(f"pt  = {pt_start}")
print(f"a   = {a_start}")
print(f"l   = {l_start}")
print(f"end = {last_div}")

# Extract sections: each goes from its start to the NEXT section's start
section_header = main_template[:pg_start]
pulse_grid_raw = main_template[pg_start:p_start]
pipeline_raw = main_template[p_start:c_start]
compliance_raw = main_template[c_start:pt_start]
partner_raw = main_template[pt_start:a_start]
amd_raw = main_template[a_start:l_start]
live_raw = main_template[l_start:last_div]
wrapper_close = main_template[last_div:]

total = (len(section_header) + len(pulse_grid_raw) + len(pipeline_raw) +
         len(compliance_raw) + len(partner_raw) + len(amd_raw) +
         len(live_raw) + len(wrapper_close))
print(f"Sum: {total} vs template: {len(main_template)}")
assert total == len(main_template), f"Sum mismatch: {total} != {len(main_template)}"

print(f"section_header: {len(section_header)}")
print(f"pulse_grid: {len(pulse_grid_raw)}")
print(f"pipeline: {len(pipeline_raw)}")
print(f"compliance: {len(compliance_raw)}")
print(f"partner: {len(partner_raw)}")
print(f"amd: {len(amd_raw)}")
print(f"live: {len(live_raw)}")
print(f"wrapper_close: {len(wrapper_close)}")

def unwrap(text):
    """Strip outer ${ } wrappers."""
    t = text.strip()
    if t.startswith('${'):
        t = t[2:]
    if t.endswith('}'):
        t = t[:-1].rstrip(' \n')
    return t

pre_return = pulse_code[:main_return_start]

# Build variables
stats_grid_var = f"  const statsGrid = html`{section_header}{pulse_grid_raw}`;"
pipeline_var = f"  const pipelineSection = {unwrap(pipeline_raw)};"
compliance_var = f"  const complianceSection = {unwrap(compliance_raw)};"

# Partner chart
pt_unwrapped = unwrap(partner_raw)
while pt_unwrapped.endswith('}'):
    s = pt_unwrapped.rstrip(' \n')
    if s.endswith('}'):
        pt_unwrapped = s[:-1].rstrip(' \n')
    else:
        break
partner_var = f"  const partnerChart = {pt_unwrapped};"

# AMD chart
amd_unwrapped = unwrap(amd_raw)
while amd_unwrapped.endswith('}'):
    s = amd_unwrapped.rstrip(' \n')
    if s.endswith('}'):
        amd_unwrapped = s[:-1].rstrip(' \n')
    else:
        break
amd_var = f"  const amdChart = {amd_unwrapped};"

live_var = f"  const liveEvents = html`{live_raw}`;"

# Return template (flat, no wrapper div - statsGrid opens the wrapper)
return_template = f"""  return html`
      ${{statsGrid}}
      ${{pipelineSection}}
      ${{complianceSection}}
      ${{partnerChart}}
      ${{amdChart}}
      ${{liveEvents}}
{wrapper_close}
  `;"""

# Build refactored Pulse function
refactored_pulse = (pre_return + "\n" +
    stats_grid_var + "\n" +
    pipeline_var + "\n" +
    compliance_var + "\n" +
    partner_var + "\n" +
    amd_var + "\n" +
    live_var + "\n" +
    return_template + "\n" +
    pulse_code[main_bt_end + 1:].lstrip(';\n'))

# Verify key elements
checks = {
    'pulse-grid': 'pulse-grid' in refactored_pulse,
    'activePartnersList.length': 'activePartnersList.length' in refactored_pulse,
    'compliance-panel': 'compliance-panel' in refactored_pulse,
    'DonutChart': 'DonutChart' in refactored_pulse,
    'partnerChart': 'partnerChart' in refactored_pulse,
    'live-panel': 'live-panel' in refactored_pulse,
    'useEffect': 'useEffect' in refactored_pulse,
}
all_pass = True
for name, result in checks.items():
    status = 'OK' if result else 'MISSING'
    if not result:
        all_pass = False
    print(f"  {status}: {name}")
assert all_pass, "Some elements missing!"

# Check return template nesting
ret_in_ref = refactored_pulse.rfind('return html`')
ret_bt = find_template_end(refactored_pulse, ret_in_ref + len('return html`'))
ret_content = refactored_pulse[ret_in_ref + len('return html`'):ret_bt]
backtick_count = ret_content.count('`')
print(f"Backticks in return template: {backtick_count} (should be 0)")
assert backtick_count == 0, "Return template still has backticks!"

# Reconstruct full file
new_js = js_content[:pulse_start] + refactored_pulse + js_content[pulse_end:]
new_content = content[:js_start] + new_js + content[closing:]
print(f"Original: {len(content)} chars -> New: {len(new_content)} chars")

with open('empire_command_spa.py', 'w') as f:
    f.write(new_content)
print("File written successfully!")
