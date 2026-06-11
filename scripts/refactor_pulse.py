import re

with open('empire_command_spa.py', 'r') as f:
    content = f.read()

spa_start = content.find('_SPA_JS = r"""')
closing = content.rfind('"""')
js_start = spa_start + len('_SPA_JS = r"""')
js_content = content[js_start:closing]

pulse_start = js_content.find('function Pulse(')
pulse_end = js_content.find('function stripMeta')

pulse_code = js_content[pulse_start:pulse_end]

ret_start = pulse_code.find('return html`')
template_body_start = ret_start + len('return html`')
last_bt = pulse_code.rfind('`')

template_content = pulse_code[template_body_start:last_bt]

# Find section boundaries
pulse_grid_start = template_content.find('<div class="pulse-grid">')
pipeline_marker = '${activePartnersList.length > 0 ? html`'
pipeline_start = template_content.find(pipeline_marker)
compliance_marker = '${(() => {'
compliance_start = template_content.find(compliance_marker, pipeline_start)
partner_marker = '${allPartners.length > 0 ? html`'
partner_start = template_content.find(partner_marker, compliance_start)

amd_marker = '${amdTotal > 0 ? html`'
first_amd = template_content.find(amd_marker)
second_amd = template_content.find(amd_marker, first_amd + 50)
live_panel_marker = '<div class="live-panel">'
live_panel_start = template_content.find(live_panel_marker, second_amd)

# Validate all markers found
assert pulse_grid_start >= 0, "pulse_grid_start not found"
assert pipeline_start >= 0, "pipeline_start not found"
assert compliance_start >= 0, "compliance_start not found"
assert partner_start >= 0, "partner_start not found"
assert second_amd >= 0, "second_amd not found"
assert live_panel_start >= 0, "live_panel_start not found"

print(f"Boundaries found:")
print(f"  pulse_grid: {pulse_grid_start}")
print(f"  pipeline: {pipeline_start}")
print(f"  compliance: {compliance_start}")
print(f"  partner: {partner_start}")
print(f"  second_amd: {second_amd}")
print(f"  live_panel: {live_panel_start}")
print(f"  template_end: {len(template_content)}")

# Extract sections
section_header = template_content[:pulse_grid_start]
stats_grid = template_content[pulse_grid_start:pipeline_start]
pipeline_expr = template_content[pipeline_start:compliance_start]
compliance_expr = template_content[compliance_start:partner_start]
partner_expr = template_content[partner_start:second_amd]
amd_expr = template_content[second_amd:live_panel_start]
live_events_raw = template_content[live_panel_start:]

def strip_expr(s):
    """Strip outer ${ and trailing } from a template expression."""
    s = s.strip()
    if s.startswith('${'):
        s = s[2:]
        if s.endswith('}'):
            s = s[:-1]
    return s

pipeline_section = strip_expr(pipeline_expr)
compliance_section = strip_expr(compliance_expr)
partner_chart = strip_expr(partner_expr)
amd_chart = strip_expr(amd_expr)

# Remove stray trailing '}' from amd_chart (it was a literal } in the template)
while amd_chart.endswith('}'):
    stripped = amd_chart.rstrip(' \n')
    if stripped.endswith('}'):
        amd_chart = stripped[:-1].rstrip(' \n')
    else:
        break

# Live events: content from <div class="live-panel"> through its closing </div>
# The last </div> in the template closes the main wrapper, not the live panel
last_div_close = live_events_raw.rfind('</div>')
if last_div_close >= 0:
    live_events = live_events_raw[:last_div_close].rstrip('\n ')
    remaining_wrapper_close = live_events_raw[last_div_close:]
else:
    live_events = live_events_raw
    remaining_wrapper_close = ''

# Print section info
sections = {
    'section_header': section_header,
    'stats_grid': stats_grid,
    'pipeline_section': pipeline_section,
    'compliance_section': compliance_section,
    'partner_chart': partner_chart,
    'amd_chart': amd_chart,
    'live_events': live_events,
}
for name, val in sections.items():
    print(f"  {name}: {len(val)} chars")

print(f"  remaining_wrapper_close: {repr(remaining_wrapper_close)}")
print()

# Verify no ${} at start of extracted expressions
for name, val in sections.items():
    stripped = val.strip()
    if stripped.startswith('${'):
        print(f"ERROR: {name} still starts with ${{!")
        raise AssertionError(f"{name} not stripped")

# Find setup code (before return)
last_brace = pulse_code.rfind('}', 0, ret_start)
setup_code = pulse_code[:last_brace] + '\n'

# Code after the template
remainder = pulse_code[last_bt+1:]  # ';\n}'

# Build the refactored Pulse function
parts = [
    setup_code,
    '  // -- Extracted template sections --\n',
    '  const statsGrid = html`',
    stats_grid.strip(),
    '`;\n\n',
    '  const pipelineSection = ',
    pipeline_section,
    '\n\n',
    '  const complianceSection = ',
    compliance_section,
    '\n\n',
    '  const partnerChart = ',
    partner_chart,
    '\n\n',
    '  const amdChart = ',
    amd_chart,
    '\n\n',
    '  const liveEvents = html`',
    live_events.strip(),
    '`;\n\n',
    '  return html`\n    <div>',
    section_header,
    '\n      ${statsGrid}\n      ${pipelineSection}\n      ${complianceSection}\n      ${partnerChart}\n      ${amdChart}\n      ${liveEvents}\n    </div>\n',
    remaining_wrapper_close.strip(),
    '\n  `;',
    remainder
]

new_pulse = ''.join(parts)

# Verify
assert 'const statsGrid = html`' in new_pulse, "Missing statsGrid"
assert 'const pipelineSection = ' in new_pulse, "Missing pipelineSection"
assert 'const complianceSection = ' in new_pulse, "Missing complianceSection"
assert 'const partnerChart = ' in new_pulse, "Missing partnerChart"
assert 'const amdChart = ' in new_pulse, "Missing amdChart"
assert 'const liveEvents = html`' in new_pulse, "Missing liveEvents"
assert 'return html`' in new_pulse, "Missing return"
assert 'function Pulse(' in new_pulse, "Missing function declaration"

print("=== VERIFICATION ===")
print("All checks passed!")
print(f"Old pulse length: {len(pulse_code)}")
print(f"New pulse length: {len(new_pulse)}")
print()

# Write the new content
new_js_content = js_content[:pulse_start] + new_pulse + js_content[pulse_end:]
new_content = content[:js_start] + new_js_content + content[closing:]

with open('empire_command_spa.py', 'w') as f:
    f.write(new_content)

print("File written successfully!")

# Double-check written file
with open('empire_command_spa.py', 'r') as f:
    check = f.read()
assert '_SPA_JS = r"""' in check, "Lost _SPA_JS"
assert 'const statsGrid' in check, "Missing statsGrid in written file"
assert 'const pipelineSection' in check, "Missing pipelineSection in written file"
assert 'const complianceSection' in check, "Missing complianceSection in written file"
assert 'const partnerChart' in check, "Missing partnerChart in written file"
assert 'const amdChart' in check, "Missing amdChart in written file"
assert 'const liveEvents' in check, "Missing liveEvents in written file"
print("Written file verified!")
