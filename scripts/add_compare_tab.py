"""
Add Compare Modes tab to the CplPricing component in empire_command_spa.py.
Shows PPL vs PPC pricing side-by-side for each lane.
"""
SPA = "/root/empire-v49/empire_command_spa.py"

with open(SPA, "r") as f:
    src = f.read()

changes = 0

# --- 1. ADD COMPARE TAB BUTTON ---
old_tabs = """          <button class="cpl-tab ${tab === 'roi' ? 'active' : ''}" onClick=${() => setTab('roi')}>ROI Calculator</button>
        </div>
      </div>

      ${tab === 'lanes' ? html`"""

new_tabs = """          <button class="cpl-tab ${tab === 'roi' ? 'active' : ''}" onClick=${() => setTab('roi')}>ROI Calculator</button>
          <button class="cpl-tab ${tab === 'compare' ? 'active' : ''}" onClick=${() => setTab('compare')}>Compare Modes</button>
        </div>
      </div>

      ${tab === 'lanes' ? html`"""

if old_tabs in src:
    src = src.replace(old_tabs, new_tabs)
    changes += 1
    print("[OK] Added Compare Modes tab button")
else:
    print("[WARN] Could not find tab buttons")

# --- 2. ADD CSS FOR COMPARE TABLE ---
old_css_marker = "/* -- AUTO-REFRESH TOGGLE ----------------------------------------- */"
new_css_marker = """/* -- COMPARE MODES TABLE ----------------------------------------- */
.cmp-intro{font-size:11px;color:var(--empire-mist);margin-bottom:16px;line-height:1.5}
.cmp-table{width:100%;border-collapse:collapse;font-size:11px;margin-bottom:20px}
.cmp-table th{text-align:left;padding:7px 9px;color:var(--empire-fog);font-weight:500;border-bottom:2px solid var(--empire-border);text-transform:uppercase;font-size:8px;letter-spacing:0.08em;background:var(--empire-elevated)}
.cmp-table td{padding:6px 9px;border-bottom:1px solid var(--empire-divider);color:var(--empire-white);vertical-align:middle}
.cmp-table tr:hover td{background:var(--empire-elevated)}
.cmp-table tr.seo-row td{opacity:0.4}
.cmp-model-cell{border-left:1px solid var(--empire-divider)}
.cmp-model-label{font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:0.08em;text-align:center;padding:3px 6px;border-radius:3px;display:inline-block}
.cmp-ppl{color:var(--signal-teal);border:1px solid rgba(0,200,200,0.2)}
.cmp-ppc{color:var(--signal-gold);border:1px solid rgba(255,183,0,0.2)}
.cmp-winner{background:rgba(68,229,184,0.04)}
.cmp-winner-tag{display:inline-block;font-size:8px;font-weight:600;letter-spacing:0.1em;text-transform:uppercase;padding:2px 6px;border-radius:3px;color:var(--signal-teal);border:1px solid rgba(68,229,184,0.2);background:rgba(68,229,184,0.06);margin-bottom:2px}
.cmp-value{font-family:var(--font-mono);font-size:10px}
.cmp-value.pos{color:var(--signal-teal)}
.cmp-value.neg{color:#e74c3c}
.cmp-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.cmp-card{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:8px;padding:14px 16px}
.cmp-card-label{font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:var(--empire-fog);margin-bottom:4px}
.cmp-card-value{font-size:18px;font-weight:600;color:var(--empire-white);font-family:var(--font-mono)}
.cmp-card-value.teal{color:var(--signal-teal)}
.cmp-card-value.gold{color:var(--signal-gold)}
.cmp-card-value.neutral{color:var(--empire-mist)}
.cmp-niche-filter{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:14px}
.cmp-niche-btn{padding:4px 12px;border:1px solid var(--empire-border);border-radius:5px;cursor:pointer;font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);background:transparent;transition:all 0.12s var(--ease-snap)}
.cmp-niche-btn:hover{border-color:var(--signal-teal);color:var(--signal-teal)}
.cmp-niche-btn.active{background:var(--signal-teal);color:var(--empire-black);border-color:var(--signal-teal);font-weight:600}
/* -- AUTO-REFRESH TOGGLE ----------------------------------------- */"""

if old_css_marker in src:
    src = src.replace(old_css_marker, new_css_marker)
    changes += 1
    print("[OK] Added Compare table CSS")
else:
    print("[WARN] Could not find CSS marker")

# --- 3. ADD THE COMPARE VIEW RENDERING ---
# Insert before the closing of the outer tab switch (before the last `})` )
old_switch_end = """        ` : ''}
      `}
    </div>
  `;
};"""

compare_view = """
      ${tab === 'compare' ? html`
        <div class="cmp-intro">Comparing <strong>PPL</strong> (Pay Per Lead) vs <strong>PPC</strong> (Pay Per Click) pricing models side-by-side per lane.</div>

        <div class="cmp-summary">
          <div class="cmp-card"><div class="cmp-card-label">Total Lanes</div><div class="cmp-card-value">${lanes.length}</div></div>
          <div class="cmp-card"><div class="cmp-card-label">Best PPL</div><div class="cmp-card-value teal">${(() => { const l = lanes.find(l => l.cpl_available && l.cpl && l.cpl.ppl && l.cpl.ppl.low); return l ? '$' + l.cpl.ppl.low : '-' })()}</div></div>
          <div class="cmp-card"><div class="cmp-card-label">Best PPC</div><div class="cmp-card-value gold">${(() => { const l = lanes.find(l => l.cpl_available && l.cpl && l.cpl.ppc && l.cpl.ppc.low); return l ? '$' + l.cpl.ppc.low : '-' })()}</div></div>
          <div class="cmp-card"><div class="cmp-card-label">Lanes with Both</div><div class="cmp-card-value neutral">${lanes.filter(l => l.cpl_available && l.cpl && l.cpl.ppl && l.cpl.ppc).length}</div></div>
        </div>

        <table class="cmp-table">
          <thead><tr>
            <th rowspan="2">Lane</th>
            <th rowspan="2">Niche</th>
            <th colspan="3" style="text-align:center;border-bottom:1px solid var(--signal-teal);color:var(--signal-teal)">PPL</th>
            <th colspan="3" style="text-align:center;border-bottom:1px solid var(--signal-gold);color:var(--signal-gold)">PPC</th>
            <th rowspan="2">Best</th>
          </tr><tr>
            <th style="color:var(--empire-fog)">CPL Range</th>
            <th style="color:var(--empire-fog)">Sell Price</th>
            <th style="color:var(--empire-fog)">Margin</th>
            <th style="color:var(--empire-fog)">CPL Range</th>
            <th style="color:var(--empire-fog)">Sell Price</th>
            <th style="color:var(--empire-fog)">Margin</th>
          </tr></thead>
          <tbody>
            ${lanes.map(l => {
              if (!l.cpl_available || !l.cpl) return html\`
                <tr class="seo-row">
                  <td style="font-family:var(--font-mono);font-size:10px;color:var(--empire-fog)">L\${String(l.lane_id).padStart(2,'0')}</td>
                  <td>\${l.niche}</td>
                  <td class="cmp-model-cell" colspan="3" style="text-align:center;color:var(--empire-fog);font-size:10px">Service lane — no CPL data</td>
                  <td class="cmp-model-cell" colspan="3" style="text-align:center;color:var(--empire-fog);font-size:10px">Service lane — no CPL data</td>
                  <td style="text-align:center"><span class="cpl-badge service">service</span></td>
                </tr>
              \`;
              const ppl = l.cpl.ppl; const ppc = l.cpl.ppc;
              const hasPpl = ppl && ppl.low != null; const hasPpc = ppc && ppc.low != null;
              const pplMid = hasPpl ? (ppl.low + ppl.high) / 2 : 0;
              const ppcMid = hasPpc ? (ppc.low + ppc.high) / 2 : 0;
              const pplPrice = hasPpl ? Math.round(pplMid * 2.5) : 0;
              const ppcPrice = hasPpc ? Math.round(ppcMid * 2.5) : 0;
              const pplMargin = hasPpl ? Math.round((pplPrice - pplMid) / pplPrice * 100) : 0;
              const ppcMargin = hasPpc ? Math.round((ppcPrice - ppcMid) / ppcPrice * 100) : 0;
              const best = hasPpl && hasPpc ? (pplMargin > ppcMargin ? 'ppl' : 'ppc') : hasPpl ? 'ppl' : hasPpc ? 'ppc' : 'none';
              return html\`
                <tr class="\${best === 'ppl' ? 'cmp-winner' : ''}">
                  <td style="font-family:var(--font-mono);font-size:10px;color:var(--empire-fog)">L\${String(l.lane_id).padStart(2,'0')}</td>
                  <td>\${l.niche}\${l.sub_niche !== l.niche ? html\` <span style="color:var(--empire-fog);font-size:9px">· \${l.sub_niche}</span>\` : ''}</td>
                  <td class="cmp-model-cell cmp-value">\${hasPpl ? '$\${ppl.low} — $\${ppl.high}' : '-'}</td>
                  <td class="cmp-model-cell cmp-value">\${hasPpl ? '$\${pplPrice}' : '-'}</td>
                  <td class="cmp-model-cell cmp-value \${pplMargin >= 30 ? 'pos' : pplMargin > 0 ? '' : 'neg'}">\${hasPpl ? pplMargin + '%' : '-'}</td>
                  <td class="cmp-model-cell cmp-value">\${hasPpc ? '$\${ppc.low} — $\${ppc.high}' : '-'}</td>
                  <td class="cmp-model-cell cmp-value">\${hasPpc ? '$\${ppcPrice}' : '-'}</td>
                  <td class="cmp-model-cell cmp-value \${ppcMargin >= 30 ? 'pos' : ppcMargin > 0 ? '' : 'neg'}">\${hasPpc ? ppcMargin + '%' : '-'}</td>
                  <td style="text-align:center">\${best !== 'none' ? html\`<span class="cmp-model-label cmp-\${best}">\${best.toUpperCase()}</span>\` : '-'}</td>
                </tr>
              \`;
            })}
          </tbody>
        </table>
      \` : ''}
"""

new_switch_end = compare_view + '\n' + old_switch_end

if old_switch_end in src:
    src = src.replace(old_switch_end, new_switch_end)
    changes += 1
    print("[OK] Added Compare view rendering")
else:
    print("[WARN] Could not find end of tab switch")

# --- WRITE ---
with open(SPA, "w") as f:
    f.write(src)

print(f"\nDone -- {changes} changes applied")
