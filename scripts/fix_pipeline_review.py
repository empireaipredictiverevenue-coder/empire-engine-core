#!/usr/bin/env python3
"""Fix pipeline orbital: add keys, label conversion estimate, fix arrow positioning."""
with open('empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# Fix 1: Label conversion as "(est.)" - change the count display
old_conv = "const totalConverted = Math.round(totalReplied * 0.28); // rough: ~28% of replies convert"
new_conv = "const totalConverted = Math.round(totalReplied * 0.28); // rough estimate"
if old_conv in content:
    content = content.replace(old_conv, new_conv)
    changes += 1
    print("✓ Labeled conversion as estimate")

# Fix 2: Change Converted stage label to show "(est.)" in orbital node
old_stage_conv = "{ id: 'converted',icon: '★', label: 'Converted',count: totalConverted,   cls: 'converted' }"
new_stage_conv = "{ id: 'converted',icon: '★', label: 'Conv (est)',count: totalConverted,   cls: 'converted' }"
if old_stage_conv in content:
    content = content.replace(old_stage_conv, new_stage_conv)
    changes += 1
    print("✓ Added (est) to converted stage label")

# Fix 3a: Add key=${s.id} to SVG lines
old_line = """return html`<line 
              x1="0" y1="0" 
              x2="${ax.toFixed(1)}" y2="${ay.toFixed(1)}" 
              class=${'pipe-orbit-line' + (isActive ? ' active' : '')}
              style=${{animationDelay: (i * 0.12) + 's'}}
            />`;"""
if old_line in content:
    new_line = """return html`<line 
              key=${s.id}
              x1="0" y1="0" 
              x2="${ax.toFixed(1)}" y2="${ay.toFixed(1)}" 
              class=${'pipe-orbit-line' + (isActive ? ' active' : '')}
              style=${{animationDelay: (i * 0.12) + 's'}}
            />`;"""
    content = content.replace(old_line, new_line)
    changes += 1
    print("✓ Added keys to SVG lines")
else:
    print("WARNING: Could not find SVG line template for key fix")

# Fix 3b: Add key=${s.id} to arrow polygons
old_arrow = """return html`<polygon class="pipe-orbit-arrow" points="${points}" style=${{animationDelay: (i * 0.2) + 's'}} />`;"""
if old_arrow in content:
    new_arrow = """return html`<polygon key=${s.id} class="pipe-orbit-arrow" points="${points}" style=${{animationDelay: (i * 0.2) + 's'}} />`;"""
    content = content.replace(old_arrow, new_arrow)
    changes += 1
    print("✓ Added keys to arrow polygons")
else:
    print("WARNING: Could not find arrow polygon for key fix")

# Fix 3c: Add key=${s.id} to stage nodes
old_stage = """return html`
                <div class=${'pipe-stage-node' + (s.cls ? ' ' + s.cls : '')}
                     style=${{transform: 'translate(-50%,-50%) translate(' + ax.toFixed(1) + 'px,' + ay.toFixed(1) + 'px)', animationDelay: (i * 0.08) + 's'}}>
                  <span class="pipe-stage-icon">${s.icon}</span>
                  <span class="pipe-stage-count">${s.count}</span>
                  <span class="pipe-stage-label">${s.label}</span>
                </div>
              `;"""
if old_stage in content:
    new_stage = """return html`
                <div key=${s.id} class=${'pipe-stage-node' + (s.cls ? ' ' + s.cls : '')}
                     style=${{transform: 'translate(-50%,-50%) translate(' + ax.toFixed(1) + 'px,' + ay.toFixed(1) + 'px)', animationDelay: (i * 0.08) + 's'}}>
                  <span class="pipe-stage-icon">${s.icon}</span>
                  <span class="pipe-stage-count">${s.count}</span>
                  <span class="pipe-stage-label">${s.label}</span>
                </div>
              `;"""
    content = content.replace(old_stage, new_stage)
    changes += 1
    print("✓ Added keys to stage nodes")
else:
    print("WARNING: Could not find stage node template for key fix")

# Fix 4: Arrow positioning - move from 0.82*midR to 0.78*midR so arrows sit between orbit ring and nodes
old_arr_calc = """const midR = orbitR;
            const x1 = Math.cos(a1) * midR * 0.82;
            const y1 = Math.sin(a1) * midR * 0.82;
            const x2 = Math.cos(a2) * midR * 0.82;
            const y2 = Math.sin(a2) * midR * 0.82;"""
new_arr_calc = """const midR = orbitR;
            const x1 = Math.cos(a1) * midR * 0.78;
            const y1 = Math.sin(a1) * midR * 0.78;
            const x2 = Math.cos(a2) * midR * 0.78;
            const y2 = Math.sin(a2) * midR * 0.78;"""
if old_arr_calc in content:
    content = content.replace(old_arr_calc, new_arr_calc)
    changes += 1
    print("✓ Moved arrow positions to 0.78*orbitR for better visibility")
else:
    print("WARNING: Could not find arrow position calc for fix")

with open('empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"\nTotal changes: {changes}")
