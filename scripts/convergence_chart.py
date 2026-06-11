#!/usr/bin/env python3
"""Add temperature convergence line chart CSS and component to Panel Court SPA."""
with open('empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# ── 1. Add convergence chart CSS after the orbital layout CSS block ──
old_marker = ".pc-orbital-agent-won{font-family:var(--font-mono);font-size:6px;letter-spacing:.08em;text-transform:uppercase;color:var(--signal-teal);position:absolute;top:-8px;left:50%;transform:translateX(-50%);background:var(--empire-surface);padding:1px 5px;border-radius:3px;border:1px solid rgba(68,229,184,0.2);white-space:nowrap}"

new_css_chart = """.pc-orbital-agent-won{font-family:var(--font-mono);font-size:6px;letter-spacing:.08em;text-transform:uppercase;color:var(--signal-teal);position:absolute;top:-8px;left:50%;transform:translateX(-50%);background:var(--empire-surface);padding:1px 5px;border-radius:3px;border:1px solid rgba(68,229,184,0.2);white-space:nowrap}
/* ── Convergence Chart ───────────────────────────────────── */
.pc-converge-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-top:20px}
.pc-converge-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.pc-converge-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.pc-converge-count{font-family:var(--font-mono);font-size:10px;color:var(--signal-teal)}
.pc-converge-chart{position:relative;width:100%;height:220px;padding:0 8px}
.pc-converge-svg{width:100%;height:100%}
.pc-converge-grid{stroke:var(--empire-divider);stroke-width:0.5px;stroke-dasharray:3 4}
.pc-converge-line{fill:none;stroke-width:2px;stroke-linecap:round;transition:opacity .2s var(--ease-snap)}
.pc-converge-line:hover{stroke-width:3px;opacity:1 !important}
.pc-converge-label{font-family:var(--font-mono);font-size:7px;fill:var(--empire-fog)}
.pc-converge-y-label{font-family:var(--font-mono);font-size:6px;fill:var(--empire-fog);letter-spacing:.08em}
.pc-converge-legend{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px;padding-top:12px;border-top:1px solid var(--empire-divider);justify-content:center}
.pc-converge-legend-item{display:flex;align-items:center;gap:4px;font-family:var(--font-mono);font-size:7px;color:var(--empire-mist);cursor:pointer;transition:opacity .2s var(--ease-snap)}
.pc-converge-legend-item.dimmed{opacity:.35}
.pc-converge-legend-swatch{width:10px;height:2px;border-radius:1px;flex-shrink:0}
@keyframes pc-chart-draw{0%{stroke-dashoffset:1000}100%{stroke-dashoffset:0}}"""

if old_marker in content:
    content = content.replace(old_marker, new_css_chart)
    changes += 1
    print("✓ Added convergence chart CSS")
else:
    print("WARNING: Could not find CSS marker for chart CSS insertion")

# ── 2. Add convergence chart JSX after the orbital wrapper closing div ──
old_pool_end = """    </div>
      ` : ''}

      <!-- ── Decision List ── -->"""

new_pool_end = """    </div>
      ` : ''}

      <!-- ── Temperature Convergence Chart ── -->
      ${(() => {
        const history = pool && pool.temperature_history ? pool.temperature_history : [];
        const agents = pool && pool.agents ? pool.agents : [];
        if (history.length < 2) return '';
        
        const chartW = 640;
        const chartH = 200;
        const padL = 32, padR = 16, padT = 10, padB = 28;
        const plotW = chartW - padL - padR;
        const plotH = chartH - padT - padB;
        const maxCycles = history.length;
        const tempMin = 0.04;  // slightly below the 0.05 floor
        const tempMax = 0.16;  // slightly above the 0.14 ceiling
        
        // Y-axis labels
        const yTicks = [0.05, 0.08, 0.11, 0.14];
        const yLines = yTicks.map(t => {
          const y = padT + plotH * (1 - (t - tempMin) / (tempMax - tempMin));
          return html`<line key=${'yg'+t} x1="${padL}" y1="${y.toFixed(1)}" x2="${padL+plotW}" y2="${y.toFixed(1)}" class="pc-converge-grid"/>`;
        });
        
        // X-axis labels (cycle numbers)
        const xLabelStep = Math.max(1, Math.floor(maxCycles / 8));
        const xLabels = [];
        for (let c = 0; c < maxCycles; c += xLabelStep) {
          const x = padL + (c / (maxCycles - 1 || 1)) * plotW;
          xLabels.push(html`<text key=${'xl'+c} x="${x.toFixed(1)}" y="${chartH - 6}" class="pc-converge-label" text-anchor="middle">${c}</text>`);
        }
        
        // Y-axis labels
        const yLabelEls = yTicks.map(t => {
          const y = padT + plotH * (1 - (t - tempMin) / (tempMax - tempMin));
          return html`<text key=${'yl'+t} x="${padL - 4}" y="${y.toFixed(1)+3}" class="pc-converge-y-label" text-anchor="end">${t.toFixed(2)}</text>`;
        });
        
        // Agent color palette
        const agentColors = ['#44E5B8','#FFB800','#FF6444','#5AC8FA','#C8A2C8','#FF8C42',
                              '#7B68EE','#FF69B4','#20B2AA','#F0E68C'];
        
        // Line paths for each agent
        const agentLines = agents.map((a, ai) => {
          const color = agentColors[ai % agentColors.length];
          const pts = [];
          for (let c = 0; c < maxCycles; c++) {
            if (history[c] && history[c][ai] != null) {
              const x = padL + (c / (maxCycles - 1 || 1)) * plotW;
              const y = padT + plotH * (1 - (history[c][ai] - tempMin) / (tempMax - tempMin));
              pts.push(x.toFixed(1) + ',' + y.toFixed(1));
            }
          }
          if (pts.length < 2) return '';
          const d = 'M' + pts.join(' L');
          return html`<path key=${'line'+a.id} d="${d}" class="pc-converge-line" stroke="${color}" style=${{strokeDasharray:'1000',strokeDashoffset:'1000',animation:'pc-chart-draw 1.2s var(--ease-out-empire) '+(ai * 0.08)+'s forwards'}}/>`;
        });
        
        // Legend
        const legendItems = agents.map((a, ai) => {
          const color = agentColors[ai % agentColors.length];
          const id = 'conv_legend_' + a.id;
          return html`<span key=${id} class="pc-converge-legend-item" onClick=${() => {
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
          }}>
            <span class="pc-converge-legend-swatch" style=${{background: color}}></span>
            #${a.id}
          </span>`;
        });
        
        return html`
        <div class="pc-converge-panel">
          <div class="pc-converge-head">
            <span class="pc-converge-title">Temperature Convergence</span>
            <span class="pc-converge-count">${maxCycles} cycles · ${agents.length} agents</span>
          </div>
          <div class="pc-converge-chart">
            <svg class="pc-converge-svg" viewBox="0 0 ${chartW} ${chartH}" preserveAspectRatio="xMidYMid meet">
              ${yLines}
              ${yLabelEls}
              ${xLabels}
              ${agentLines}
            </svg>
          </div>
          <div class="pc-converge-legend">
            ${legendItems}
          </div>
        </div>
        `;
      })()}

      <!-- ── Decision List ── -->"""

if old_pool_end in content:
    content = content.replace(old_pool_end, new_pool_end)
    changes += 1
    print("✓ Added convergence chart component after orbital ring")
else:
    print("WARNING: Could not find pool end marker for chart insertion")

with open('empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"\nTotal changes: {changes}")
