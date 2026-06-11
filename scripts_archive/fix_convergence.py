#!/usr/bin/env python3
"""Fix convergence chart: dynamic Y range from data, React state for legend highlight."""
with open('empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# Fix 1: Replace hardcoded tempMin/tempMax with dynamic computation
old_range = """        const tempMin = 0.04;  // slightly below the 0.05 floor
        const tempMax = 0.16;  // slightly above the 0.14 ceiling"""

new_range = """        const allTemps = history.flat();
        const dataMin = allTemps.length > 0 ? Math.min(...allTemps) : 0.05;
        const dataMax = allTemps.length > 0 ? Math.max(...allTemps) : 0.14;
        const tempMin = Math.max(0.03, dataMin - 0.015);
        const tempMax = Math.min(0.85, dataMax + 0.015);
        const tempSpan = tempMax - tempMin || 0.01;"""

if old_range in content:
    content = content.replace(old_range, new_range)
    changes += 1
    print("✓ Dynamic Y-axis range from data")
else:
    print("WARNING: Could not find tempMin/tempMax for fix")

# Fix 2: Update all references to (tempMax - tempMin) to use tempSpan
old_span = "(tempMax - tempMin)"
if old_span in content:
    content = content.replace(
        "const y = padT + plotH * (1 - (t - tempMin) / (tempMax - tempMin));",
        "const y = padT + plotH * (1 - (t - tempMin) / tempSpan);"
    )
    content = content.replace(
        "const y = padT + plotH * (1 - (history[c][ai] - tempMin) / (tempMax - tempMin));",
        "const y = padT + plotH * (1 - (history[c][ai] - tempMin) / tempSpan);"
    )
    changes += 1
    print("✓ Updated temp span references")

# Fix 3: Replace DOM manipulation legend click with React state approach
old_click = """onClick=${() => {
            const svg = document.querySelector('.pc-converge-svg');
            if (svg) {
              const lines = svg.querySelectorAll('.pc-converge-line');
              const thisLine = lines[ai];
              const isDimmed = thisLine && thisLine.style.opacity === '0.15';
              lines.forEach((l, i) => l.style.opacity = isDimmed ? '1' : (i === ai ? '1' : '0.15'));
              // Also toggle legend items
              document.querySelectorAll('.pc-converge-legend-item').forEach((el, i) => {
                el.classList.toggle('dimmed', !isDimmed && i !== ai);
              });
            }
          }}"""

new_click = """onClick=${() => setHighlighted(highlighted === ai ? null : ai)}"""

if old_click in content:
    content = content.replace(old_click, new_click)
    changes += 1
    print("✓ React state legend highlight replaces DOM manipulation")
else:
    print("WARNING: Could not find legend click handler for fix")

# Fix 3b: Add opacity based on React state to legend items
old_legend_item = """return html`<span key=${id} class="pc-converge-legend-item" ${new_click}"""
if "class=\"pc-converge-legend-item\" onClick=${() => setHighlighted" in content:
    # Already fixed, now add the dimmed class logic and line opacity
    old_legend_span = '<span key=${id} class="pc-converge-legend-item" onClick=${() => setHighlighted(highlighted === ai ? null : ai)}>'
    new_legend_span = '<span key=${id} class=${"pc-converge-legend-item" + (highlighted != null && highlighted !== ai ? " dimmed" : "")} onClick=${() => setHighlighted(highlighted === ai ? null : ai)}>'
    if old_legend_span in content:
        content = content.replace(old_legend_span, new_legend_span)
        changes += 1
        print("✓ Added dimmed class to legend items based on state")
else:
    print("WARNING: Legend click replacement not found")

# Fix 3c: Add opacity to SVG lines based on highlighted state
old_line_path = 'return html`<path key=${'
new_line_path = 'const lineOpacity = highlighted != null ? (highlighted === ai ? 1 : 0.15) : 1;\n          return html`<path key=${'
# Do this replacement in the context of where agentLines are defined
if 'return html`<path key=${' in content and 'class="pc-converge-line"' in content:
    # Find and replace the path rendering to include opacity
    old_path_render = """return html`<path key=${'line'+a.id} d="${d}" class="pc-converge-line" stroke="${color}" style=${{strokeDasharray:'1000',strokeDashoffset:'1000',animation:'pc-chart-draw 1.2s var(--ease-out-empire) '+(ai * 0.08)+'s forwards'}}/>`;"""
    new_path_render = """const lineOpacity = highlighted != null ? (highlighted === ai ? 1 : 0.15) : 1;
          return html`<path key=${'line'+a.id} d="${d}" class="pc-converge-line" stroke="${color}" opacity="${lineOpacity}" style=${{strokeDasharray:'1000',strokeDashoffset:'1000',animation:'pc-chart-draw 1.2s var(--ease-out-empire) '+(ai * 0.08)+'s forwards'}}/>`;"""
    if old_path_render in content:
        content = content.replace(old_path_render, new_path_render)
        changes += 1
        print("✓ Added opacity to SVG lines based on highlighted state")

# Fix 4: Add highlighted state to PanelCourtPanel component (useState)
old_panel_state = "const [expanded, setExpanded] = useState(null);"
new_panel_state = "const [expanded, setExpanded] = useState(null);\n  const [highlighted, setHighlighted] = useState(null);"
if old_panel_state in content:
    content = content.replace(old_panel_state, new_panel_state)
    changes += 1
    print("✓ Added highlighted state to PanelCourtPanel")
else:
    print("WARNING: Could not find expanded state for highlighted insertion")

with open('empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"\nTotal changes: {changes}")
