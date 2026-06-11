#!/usr/bin/env python3
"""Add critique visualization to Panel Court SPA."""
with open('empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# ── 1. Add critique arrow CSS after pc-orbit-line CSS ──
old_css = """.pc-orbit-line.winner{stroke:rgba(68,229,184,0.25);stroke-width:1.5px}"""
new_css = """.pc-orbit-line.winner{stroke:rgba(68,229,184,0.25);stroke-width:1.5px}
/* ── Critique arrows ── */
.pc-critique-arrow{fill:none;stroke:rgba(255,184,0,0.25);stroke-width:1.2px;stroke-dasharray:5 4;stroke-linecap:round;pointer-events:none}
.pc-critique-arrow.severe{stroke:rgba(255,68,68,0.35);stroke-width:1.8px}
.pc-critique-arrow.mild{stroke:rgba(68,229,184,0.18);stroke-width:1px;stroke-dasharray:2 6}
.pc-critique-arrowhead{fill:rgba(255,184,0,0.3)}
.pc-critique-arrowhead.severe{fill:rgba(255,68,68,0.4)}
.pc-critique-arrowhead.mild{fill:rgba(68,229,184,0.2)}
/* ── Critique detail ── */
.pc-critique-detail{margin-top:14px;padding-top:14px;border-top:1px solid var(--empire-divider)}
.pc-critique-title{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;margin-bottom:10px}
.pc-critique-card{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:10px 12px;margin-bottom:8px;border-radius:4px;border-left:3px solid rgba(255,184,0,0.3)}
.pc-critique-card.severe{border-left-color:rgba(255,68,68,0.4)}
.pc-critique-card.mild{border-left-color:rgba(68,229,184,0.3)}
.pc-critique-head{display:flex;gap:10px;align-items:center;margin-bottom:6px;font-family:var(--font-mono);font-size:8px}
.pc-critique-flow{color:var(--status-amber)}
.pc-critique-sev{color:var(--empire-mist);letter-spacing:.08em}
.pc-critique-sev.high{color:var(--status-red)}
.pc-critique-sev.low{color:var(--signal-teal)}
.pc-critique-adj{color:var(--strike-cyan);margin-left:auto}
.pc-critique-text{font-size:10px;color:var(--empire-silver);line-height:1.5}"""

if old_css in content:
    content = content.replace(old_css, new_css)
    changes += 1
    print("✓ Added critique CSS")
else:
    print("WARNING: Could not find pc-orbit-line.winner CSS")

# ── 2. Add critique arrows to orbital SVG ──
old_svg_lines = """                <!-- Connection lines from center -->
                ${svgLines}"""

new_svg_lines = """                <!-- Connection lines from center -->
                ${svgLines}
                <!-- Critique arrows between agents -->
                ${(() => {
                  const d0 = poolData || data;
                  const crits = (d0 && d0.length > 0 && d0[0].agent_critiques) 
                    ? (typeof d0[0].agent_critiques === 'string' 
                        ? JSON.parse(d0[0].agent_critiques) 
                        : d0[0].agent_critiques) 
                    : [];
                  return crits.map((cr, ci) => {
                    const cidx = (cr.critic_id || 1) - 1;
                    const tidx = (cr.target_id || 1) - 1;
                    const cAngle = (cidx * 360 / 10 - 90) * Math.PI / 180;
                    const tAngle = (tidx * 360 / 10 - 90) * Math.PI / 180;
                    const cr = 160; // slightly inside the orbit ring
                    const cx = Math.cos(cAngle) * cr;
                    const cy = Math.sin(cAngle) * cr;
                    const tx = Math.cos(tAngle) * cr;
                    const ty = Math.sin(tAngle) * cr;
                    // Arrowhead
                    const dx = tx - cx, dy = ty - cy;
                    const len = Math.sqrt(dx*dx+dy*dy) || 1;
                    const ux = dx/len, uy = dy/len;
                    const sevCls = (cr.severity || 0) >= 7 ? 'severe' : (cr.severity || 0) <= 3 ? 'mild' : '';
                    const tipX = tx - ux * 8;
                    const tipY = ty - uy * 8;
                    const wing = 4;
                    const px = -uy * wing, py = ux * wing;
                    const pts = `${tx.toFixed(1)},${ty.toFixed(1)} ${(tipX+px).toFixed(1)},${(tipY+py).toFixed(1)} ${(tipX-px).toFixed(1)},${(tipY-py).toFixed(1)}`;
                    return html`
                      <line key=${'crline'+ci} x1="${cx.toFixed(1)}" y1="${cy.toFixed(1)}" x2="${tx.toFixed(1)}" y2="${ty.toFixed(1)}" class=${'pc-critique-arrow' + (sevCls ? ' ' + sevCls : '')}/>
                      <polygon key=${'crhead'+ci} points="${pts}" class=${'pc-critique-arrowhead' + (sevCls ? ' ' + sevCls : '')}/>
                    `;
                  });
                })()}"""

if old_svg_lines in content:
    content = content.replace(old_svg_lines, new_svg_lines)
    changes += 1
    print("✓ Added critique arrows to orbital SVG")
else:
    print("WARNING: Could not find SVG lines marker")

# ── 3. Add critique detail section after per-agent scores in decision detail ──
old_detail = """                  ${d.judge_reasoning ? html`
                    <div class="pc-judge-block">"""

new_detail = """                  ${(() => {
                    const crits = d.agent_critiques 
                      ? (typeof d.agent_critiques === 'string' ? JSON.parse(d.agent_critiques) : d.agent_critiques) 
                      : [];
                    if (!crits || crits.length === 0) return '';
                    return html`
                    <div class="pc-critique-detail">
                      <div class="pc-critique-title">Agent Critique Rounds</div>
                      ${crits.map((cr, ci) => {
                        const sev = cr.severity || 0;
                        const sevCls = sev >= 7 ? 'severe' : sev <= 3 ? 'mild' : '';
                        const sevLabel = sev >= 7 ? 'high' : sev <= 3 ? 'low' : '';
                        return html`
                        <div key=${'crit'+ci} class=${'pc-critique-card' + (sevCls ? ' ' + sevCls : '')}>
                          <div class="pc-critique-head">
                            <span class="pc-critique-flow">Agent #${cr.critic_id} → #${cr.target_id}</span>
                            <span class=${'pc-critique-sev' + (sevLabel ? ' ' + sevLabel : '')}>sev ${sev}/10</span>
                            ${cr.suggested_adjustment != null ? html`<span class="pc-critique-adj">${cr.suggested_adjustment > 0 ? '+' : ''}${cr.suggested_adjustment.toFixed(1)}</span>` : ''}
                          </div>
                          <div class="pc-critique-text">${cr.critique_text || '—'}</div>
                        </div>
                        `;
                      })}
                    </div>
                    `;
                  })()}
                  ${d.judge_reasoning ? html`
                    <div class="pc-judge-block">"""

if old_detail in content:
    content = content.replace(old_detail, new_detail)
    changes += 1
    print("✓ Added critique detail to decision view")
else:
    print("WARNING: Could not find judge_reasoning detail marker")

with open('empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"\nTotal changes: {changes}")
