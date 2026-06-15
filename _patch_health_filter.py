import sys

# Read file as bytes
with open('empire_command_spa.py', 'rb') as f:
    data = bytearray(f.read())

# Define old and new spans as byte strings  
# Old spans for green, amber, red
old_spans = [
    b'cpl-health-green" style="flex:${g}" title="${g} healthy">${g}</span>',
    b'cpl-health-amber" style="flex:${a}" title="${a} at-risk">${a}</span>',
    b'cpl-health-red" style="flex:${r}" title="${r} critical">${r}</span>',
]

# New spans with click handlers (keep same structure, just add onClick + classes)
new_spans = [
    b'cpl-health-green${healthFilter===\'green\'?\' cpl-health-active\':healthFilter?\' cpl-health-dim\':\'\'}" style="flex:${g};cursor:pointer" title="${g} healthy - click to filter" onclick=${()=>setHealthFilter(healthFilter===\'green\'?null:\'green\')}>${g}</span>',
    b'cpl-health-amber${healthFilter===\'amber\'?\' cpl-health-active\':healthFilter?\' cpl-health-dim\':\'\'}" style="flex:${a};cursor:pointer" title="${a} at-risk - click to filter" onclick=${()=>setHealthFilter(healthFilter===\'amber\'?null:\'amber\')}>${a}</span>',
    b'cpl-health-red${healthFilter===\'red\'?\' cpl-health-active\':healthFilter?\' cpl-health-dim\':\'\'}" style="flex:${r};cursor:pointer" title="${r} critical - click to filter" onclick=${()=>setHealthFilter(healthFilter===\'red\'?null:\'red\')}>${r}</span>',
]

# Apply replacements (from last to first to preserve byte positions)
replacements = []
for old_s, new_s in zip(old_spans, new_spans):
    # Find SECOND occurrence (first is in CSS)
    first = data.find(old_s)
    second = data.find(old_s, first + 1)
    if second >= 0:
        replacements.append((second, second + len(old_s), new_s))
        print(f"Found at byte {second}: {old_s[:30]}...")
    else:
        print(f"NOT FOUND: {old_s[:30]}...")
        # Fall back: find first occurrence after a large offset
        # The JS template is after the CSS section (~115KB into file)
        late = data.find(old_s, 120000)
        if late >= 0:
            replacements.append((late, late + len(old_s), new_s))
            print(f"  Found late at byte {late}")
        else:
            print(f"  Not found anywhere!")

# Apply from last to first
replacements.sort(key=lambda x: x[0], reverse=True)
for start, end, new_s in replacements:
    data[start:end] = new_s

# Add CSS classes for active/dim states
# Find .cpl-health-meta and insert after it
meta_css = b'.cpl-health-meta'
meta_idx = data.find(meta_css)
if meta_idx >= 0:
    line_end = data.find(b'\n', meta_idx)
    new_css = b'\n.cpl-health-active{opacity:1!important;filter:brightness(1.3);box-shadow:0 0 8px currentColor}\n.cpl-health-dim{opacity:0.35;filter:saturate(0.3)}\n'
    data[line_end:line_end] = new_css
    print("Added CSS for active/dim states")

with open('empire_command_spa.py', 'wb') as f:
    f.write(data)

print("\nAll edits applied!")
