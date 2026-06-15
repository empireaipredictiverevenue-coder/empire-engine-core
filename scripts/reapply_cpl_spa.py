"""
Re-apply CPL pricing feature + ROI calculator tab to empire_command_spa.py.
Inserts at known string positions using the restored git file.
"""
SPA = "/root/empire-v49/empire_command_spa.py"

with open(SPA, "r") as f:
    src = f.read()

changes = 0

# --- 1. ADD CPL/ROI CSS ----------------------------------------------------
old_css_end = "ccp-summary-car"
new_css = """
/* -- CPL PRICING ------------------------------------------------- */
.cpl-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:20px;flex-wrap:wrap;gap:12px}
.cpl-tabs{display:flex;gap:4px;background:var(--empire-elevated);padding:3px;border-radius:8px}
.cpl-tab{padding:7px 18px;border:none;border-radius:6px;cursor:pointer;font-family:var(--font-mono);font-size:11px;color:var(--empire-mist);background:transparent;transition:all 0.15s var(--ease-snap)}
.cpl-tab:hover{color:var(--empire-white);background:var(--empire-raised)}
.cpl-tab.active{color:var(--empire-black);background:var(--signal-teal);font-weight:600}
.cpl-summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px;margin-bottom:20px}
.cpl-card{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:8px;padding:14px 16px}
.cpl-card-label{font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:var(--empire-fog);margin-bottom:4px}
.cpl-card-value{font-size:20px;font-weight:600;color:var(--empire-white);font-family:var(--font-mono)}
.cpl-card-value.positive{color:var(--signal-teal)}
.cpl-card-value.warning{color:var(--signal-gold)}
.cpl-nav{display:flex;gap:4px;flex-wrap:wrap;margin-bottom:14px}
.cpl-nav-btn{padding:5px 12px;border:1px solid var(--empire-border);border-radius:5px;cursor:pointer;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);background:transparent;transition:all 0.15s var(--ease-snap)}
.cpl-nav-btn:hover{border-color:var(--signal-teal);color:var(--signal-teal)}
.cpl-nav-btn.active{background:var(--signal-teal);color:var(--empire-black);border-color:var(--signal-teal);font-weight:600}
.cpl-table{width:100%;border-collapse:collapse;font-size:11px}
.cpl-table th{text-align:left;padding:8px 10px;color:var(--empire-fog);font-weight:500;border-bottom:1px solid var(--empire-border);text-transform:uppercase;font-size:9px;letter-spacing:0.08em}
.cpl-table td{padding:7px 10px;border-bottom:1px solid var(--empire-border);color:var(--empire-white);vertical-align:middle}
.cpl-table tr:hover td{background:var(--empire-elevated)}
.cpl-table tr.seo-row td{opacity:0.5}
.cpl-badge{display:inline-block;padding:2px 7px;border-radius:4px;font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:0.06em}
.cpl-badge.ppl{background:rgba(0,200,200,0.15);color:var(--signal-teal)}
.cpl-badge.ppc{background:rgba(255,183,0,0.15);color:var(--signal-gold)}
.cpl-badge.service{background:rgba(130,100,255,0.15);color:#8264ff}
.cpl-margin-bar{display:inline-block;height:6px;border-radius:3px;min-width:2px;vertical-align:middle;margin-right:6px}
.cpl-margin-bar.high{background:var(--signal-teal)}
.cpl-margin-bar.mid{background:var(--signal-gold)}
.cpl-margin-bar.low{background:#e74c3c}
.cpl-pagination{display:flex;align-items:center;justify-content:center;gap:8px;margin-top:16px;font-size:11px;color:var(--empire-mist)}
.cpl-pagination button{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:4px;padding:4px 10px;cursor:pointer;color:var(--empire-white);font-family:var(--font-mono);font-size:10px;transition:all 0.12s var(--ease-snap)}
.cpl-pagination button:hover{background:var(--signal-teal);color:var(--empire-black);border-color:var(--signal-teal)}
.cpl-pagination button:disabled{opacity:0.3;cursor:default}
.cpl-loading{text-align:center;padding:60px 0;color:var(--empire-fog);font-family:var(--font-mono);font-size:12px}
.cpl-error{background:rgba(231,76,60,0.1);border:1px solid #e74c3c;border-radius:8px;padding:16px 20px;color:#e74c3c;font-size:12px;margin-bottom:20px}
/* -- ROI CALCULATOR ---------------------------------------------- */
.roi-form{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:8px;padding:20px;margin-bottom:20px}
.roi-form-row{display:flex;gap:16px;flex-wrap:wrap;align-items:end}
.roi-form-group{display:flex;flex-direction:column;gap:4px;min-width:160px}
.roi-form-group label{font-size:9px;text-transform:uppercase;letter-spacing:0.1em;color:var(--empire-fog)}
.roi-form-group input,.roi-form-group select{background:var(--empire-raised);border:1px solid var(--empire-border);border-radius:5px;padding:8px 12px;color:var(--empire-white);font-family:var(--font-mono);font-size:12px;outline:none;transition:border-color 0.15s var(--ease-snap)}
.roi-form-group input:focus,.roi-form-group select:focus{border-color:var(--signal-teal)}
.roi-form-group input::placeholder{color:var(--empire-fog);opacity:0.5}
.roi-form-apply{padding:8px 24px;background:var(--signal-teal);border:none;border-radius:5px;color:var(--empire-black);font-family:var(--font-mono);font-size:11px;font-weight:600;cursor:pointer;transition:all 0.15s var(--ease-snap)}
.roi-form-apply:hover{box-shadow:var(--glow-signal);transform:translateY(-1px)}
.roi-form-apply:disabled{opacity:0.4;cursor:default;transform:none;box-shadow:none}
.roi-results{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:12px}
.roi-card{background:var(--empire-elevated);border:1px solid var(--empire-border);border-radius:8px;padding:14px 16px}
.roi-card-label{font-size:9px;text-transform:uppercase;letter-spacing:0.12em;color:var(--empire-fog);margin-bottom:4px}
.roi-card-value{font-size:18px;font-weight:600;color:var(--empire-white);font-family:var(--font-mono)}
.roi-card-value.profit{color:var(--signal-teal)}
.roi-card-value.loss{color:#e74c3c}
.roi-card-value.neutral{color:var(--signal-gold)}
.roi-table-wrap{overflow-x:auto;margin-top:8px}
.roi-table{width:100%;border-collapse:collapse;font-size:11px}
.roi-table th{text-align:left;padding:7px 10px;color:var(--empire-fog);font-weight:500;border-bottom:1px solid var(--empire-border);text-transform:uppercase;font-size:9px;letter-spacing:0.08em}
.roi-table td{padding:6px 10px;border-bottom:1px solid var(--empire-border);color:var(--empire-white);vertical-align:middle}
.roi-table tr:hover td{background:var(--empire-raised)}
.roi-table .pos{color:var(--signal-teal)}
.roi-table .neg{color:#e74c3c}
"""

if old_css_end in src:
    idx = src.find(old_css_end)
    closing_idx = src.find('"""', idx)
    if closing_idx > 0:
        # Insert BEFORE the closing """ so the CSS is inside _SPA_CSS
        insert_pos = closing_idx
        src = src[:insert_pos] + new_css + src[insert_pos:]
        changes += 1
        print("[OK] Inserted CPL/ROI CSS")
    else:
        print("[WARN] Could not find closing triple-quote after CSS")
else:
    print(f"[WARN] Could not find '{old_css_end}' in file")

# --- 2. ADD CplPricing COMPONENT BEFORE App() ----------------------------
# Note: In Python triple-quoted strings, backticks are NOT special characters.
# So we write `html` directly (no backslash before backtick).
cpl_component = """

// -- CPL PRICING + ROI CALCULATOR --------------------------------------------
const CplPricing = () => {
  const [lanes, setLanes] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [modelFilter, setModelFilter] = React.useState('all');
  const [page, setPage] = React.useState(1);
  const [tab, setTab] = React.useState('lanes');
  const perPage = 12;
  // ROI calculator state
  const [roiNiche, setRoiNiche] = React.useState('Roofing Restoration');
  const [roiVolume, setRoiVolume] = React.useState(100);
  const [roiSellPrice, setRoiSellPrice] = React.useState('');
  const [roiResult, setRoiResult] = React.useState(null);
  const [roiLoading, setRoiLoading] = React.useState(false);

  React.useEffect(() => {
    apiFetch('/api/v1/cpl/lanes?model=both&monthly_volume=100')
      .then(data => { setLanes(data.lanes || data); setLoading(false); })
      .catch(e => { setError(e.message || 'Failed to load CPL data'); setLoading(false); });
  }, []);

  if (loading) return html`<div class="cpl-loading">Loading CPL pricing...</div>`;
  if (error) return html`<div class="cpl-error">${error}</div>`;
  if (!lanes) return html`<div class="cpl-loading">No data</div>`;

  const filtered = lanes.filter(l => {
    if (modelFilter === 'all') return true;
    if (modelFilter === 'service') return !l.cpl_available;
    return l.best_model === modelFilter;
  });
  const totalPages = Math.ceil(filtered.length / perPage);
  const pg = Math.min(page, Math.max(1, totalPages));
  const pageLanes = filtered.slice((pg - 1) * perPage, pg * perPage);

  const summary = (() => {
    const priced = lanes.filter(l => l.cpl_available);
    if (!priced.length) return { total: lanes.length, priced: 0, avgLow: 0, avgHigh: 0, avgMargin: 0 };
    return {
      total: lanes.length,
      priced: priced.length,
      avgLow: Math.round(priced.reduce((s, l) => s + l.cpl_low, 0) / priced.length),
      avgHigh: Math.round(priced.reduce((s, l) => s + l.cpl_high, 0) / priced.length),
      avgMargin: Math.round(priced.reduce((s, l) => s + (l.margin_pct || 0), 0) / priced.length * 10) / 10,
    };
  })();

  const marginClass = (pct) => pct >= 50 ? 'high' : pct >= 25 ? 'mid' : 'low';
  const modelClass = (m) => m === 'ppl' ? 'ppl' : m === 'ppc' ? 'ppc' : 'service';

  const runRoi = () => {
    setRoiLoading(true);
    setRoiResult(null);
    const sp = roiSellPrice ? parseFloat(roiSellPrice) : null;
    const params = new URLSearchParams({ niche: roiNiche, monthly_volume: String(roiVolume) });
    if (sp) params.set('sell_price', String(sp));
    apiFetch('/api/v1/cpl/roi/' + encodeURIComponent(roiNiche) + '?' + params.toString())
      .then(data => { setRoiResult(data); setRoiLoading(false); })
      .catch(e => { setError(e.message); setRoiLoading(false); });
  };

  const roiClass = (v) => v > 0 ? 'profit' : v < 0 ? 'loss' : 'neutral';

  return html`
    <div class="section-h">
      <div class="cpl-header">
        <h2 style="margin:0;font-size:16px;font-weight:600">CPL Pricing</h2>
        <div class="cpl-tabs">
          <button class="cpl-tab ${tab === 'lanes' ? 'active' : ''}" onClick=${() => setTab('lanes')}>Lane Pricing</button>
          <button class="cpl-tab ${tab === 'roi' ? 'active' : ''}" onClick=${() => setTab('roi')}>ROI Calculator</button>
        </div>
      </div>

      ${tab === 'lanes' ? html`
        <div class="cpl-summary">
          <div class="cpl-card"><div class="cpl-card-label">Total Lanes</div><div class="cpl-card-value">${summary.total}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Priced Lanes</div><div class="cpl-card-value">${summary.priced} / ${summary.total}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Avg CPL Range</div><div class="cpl-card-value">$${summary.avgLow} - $${summary.avgHigh}</div></div>
          <div class="cpl-card"><div class="cpl-card-label">Avg Margin</div><div class="cpl-card-value ${summary.avgMargin >= 50 ? 'positive' : 'warning'}">${summary.avgMargin}%</div></div>
        </div>

        <div class="cpl-nav">
          <button class="cpl-nav-btn ${modelFilter === 'all' ? 'active' : ''}" onClick=${() => { setModelFilter('all'); setPage(1); }}>All</button>
          <button class="cpl-nav-btn ${modelFilter === 'ppl' ? 'active' : ''}" onClick=${() => { setModelFilter('ppl'); setPage(1); }}>PPL</button>
          <button class="cpl-nav-btn ${modelFilter === 'ppc' ? 'active' : ''}" onClick=${() => { setModelFilter('ppc'); setPage(1); }}>PPC</button>
          <button class="cpl-nav-btn ${modelFilter === 'service' ? 'active' : ''}" onClick=${() => { setModelFilter('service'); setPage(1); }}>Service</button>
          <span style="flex:1;text-align:right;font-size:10px;color:var(--empire-fog);padding:5px 0">${filtered.length} lanes</span>
        </div>

        <table class="cpl-table">
          <thead><tr>
            <th>Lane</th><th>Niche</th><th>Sub-Niche</th><th>CPL Lo</th><th>CPL Hi</th>
            <th>Model</th><th>Sell Price</th><th>Margin</th><th>Annual Rev</th>
          </tr></thead>
          <tbody>
            ${pageLanes.map(l => html`
              <tr class="${l.cpl_available ? '' : 'seo-row'}">
                <td style="color:var(--empire-fog);font-family:var(--font-mono);font-size:10px">L${String(l.lane_id).padStart(2,'0')}</td>
                <td>${l.niche}</td>
                <td>${l.sub_niche}</td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available ? '$' + l.cpl_low : '-'}</td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available ? '$' + l.cpl_high : '-'}</td>
                <td><span class="cpl-badge ${modelClass(l.best_model)}">${l.best_model || 'n/a'}</span></td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available ? '$' + l.sell_price_low + ' - $' + l.sell_price_high : '-'}</td>
                <td>
                  ${l.cpl_available ? html`
                    <span class="cpl-margin-bar ${marginClass(l.margin_pct)}" style="width:${Math.min(l.margin_pct, 100)}%"></span>
                    ${l.margin_pct}%
                  ` : '-'}
                </td>
                <td style="font-family:var(--font-mono);font-size:10px">${l.cpl_available ? '$' + (l.annual_revenue || 0).toLocaleString() : '-'}</td>
              </tr>
            `)}
          </tbody>
        </table>

        ${totalPages > 1 ? html`
          <div class="cpl-pagination">
            <button disabled=${pg <= 1} onClick=${() => setPage(pg - 1)}>Prev</button>
            <span>Page ${pg} of ${totalPages}</span>
            <button disabled=${pg >= totalPages} onClick=${() => setPage(pg + 1)}>Next</button>
          </div>
        ` : ''}
      ` : html`
        <div class="roi-form">
          <div class="roi-form-row">
            <div class="roi-form-group">
              <label>Niche</label>
              <select value=${roiNiche} onChange=${e => setRoiNiche(e.target.value)}>
                ${[...new Set(lanes.map(l => l.niche))].sort().map(n => html`<option value="${n}">${n}</option>`)}
              </select>
            </div>
            <div class="roi-form-group">
              <label>Monthly Volume (leads)</label>
              <input type="number" min="1" max="10000" value=${roiVolume} onChange=${e => setRoiVolume(parseInt(e.target.value) || 100)} />
            </div>
            <div class="roi-form-group">
              <label>Sell Price / Lead (optional - blank uses default 2.5x CPL)</label>
              <input type="number" min="1" step="10" placeholder="Auto (2.5x CPL)" value=${roiSellPrice} onChange=${e => setRoiSellPrice(e.target.value)} />
            </div>
            <button class="roi-form-apply" disabled=${roiLoading} onClick=${runRoi}>
              ${roiLoading ? 'Calculating...' : 'Calculate ROI'}
            </button>
          </div>
        </div>

        ${roiResult ? html`
          <div class="roi-results">
            <div class="roi-card">
              <div class="roi-card-label">Monthly Revenue</div>
              <div class="roi-card-value ${roiClass(roiResult.monthly_revenue - roiResult.monthly_acquisition_cost)}">
                $${(roiResult.monthly_revenue || 0).toLocaleString()}
              </div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">Acquisition Cost</div>
              <div class="roi-card-value">$${(roiResult.monthly_acquisition_cost || 0).toLocaleString()}</div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">Gross Profit</div>
              <div class="roi-card-value ${roiClass(roiResult.monthly_revenue - roiResult.monthly_acquisition_cost)}">
                $${((roiResult.monthly_revenue || 0) - (roiResult.monthly_acquisition_cost || 0)).toLocaleString()}
              </div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">Margin</div>
              <div class="roi-card-value ${roiClass(roiResult.margin_pct)}">${roiResult.margin_pct}%</div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">ROI</div>
              <div class="roi-card-value ${roiClass(roiResult.roi_percentage)}">${roiResult.roi_percentage}%</div>
            </div>
            <div class="roi-card">
              <div class="roi-card-label">Breakeven Volume</div>
              <div class="roi-card-value">${roiResult.breakeven_volume || 'N/A'}</div>
            </div>
          </div>
        ` : ''}

        ${roiResult ? html`
          <h3 style="font-size:12px;font-weight:600;margin:20px 0 12px;color:var(--empire-white)">Per-Lane Projection (at ${roiVolume} leads/mo)</h3>
          <div class="roi-table-wrap">
            <table class="roi-table">
              <thead><tr>
                <th>Lane</th><th>Niche</th><th>Model</th><th>CPL</th><th>Acquisition</th><th>Revenue</th><th>Profit</th><th>Margin</th>
              </tr></thead>
              <tbody>
                ${lanes.filter(l => l.cpl_available && l.niche === roiNiche).map(l => {
                  const midCpl = (l.cpl_low + l.cpl_high) / 2;
                  const acq = Math.round(midCpl * roiVolume);
                  const nicheLanes = lanes.filter(x => x.cpl_available && x.niche === roiNiche);
                  const rev = nicheLanes.length ? Math.round((roiResult.monthly_revenue || 0) / nicheLanes.length) : 0;
                  const profit = rev - acq;
                  const margin = rev > 0 ? Math.round((profit / rev) * 100) : 0;
                  return html`
                    <tr>
                      <td style="font-family:var(--font-mono);font-size:10px;color:var(--empire-fog)">L${String(l.lane_id).padStart(2,'0')}</td>
                      <td>${l.sub_niche}</td>
                      <td><span class="cpl-badge ${modelClass(l.best_model)}">${l.best_model || 'n/a'}</span></td>
                      <td style="font-family:var(--font-mono)">$${l.cpl_low}-$${l.cpl_high}</td>
                      <td style="font-family:var(--font-mono)">$${acq.toLocaleString()}</td>
                      <td style="font-family:var(--font-mono)" class="pos">$${rev.toLocaleString()}</td>
                      <td style="font-family:var(--font-mono)" class="${profit >= 0 ? 'pos' : 'neg'}">$${profit.toLocaleString()}</td>
                      <td class="${margin >= 30 ? 'pos' : 'neg'}">${margin}%</td>
                    </tr>
                  `;
                })}
              </tbody>
            </table>
          </div>
        ` : ''}
      `}
    </div>
  `;
};
"""

app_marker = "function App()"
idx = src.find(app_marker)
if idx > 0:
    insert_pos = src.rfind('\n', 0, idx) + 1
    src = src[:insert_pos] + cpl_component + src[insert_pos:]
    changes += 1
    print("[OK] Inserted CplPricing component before function App()")
else:
    print("[WARN] Could not find 'function App()'")

# --- 3. ADD NAV ENTRY ----------------------------------------------------
old_nav = "{ id: 'affiliates',   label: 'Affiliates',    sub: 'Manage · referral links · stats' },"
new_nav = """{ id: 'affiliates',   label: 'Affiliates',    sub: 'Manage · referral links · stats' },
      { id: 'cpl-pricing',  label: 'CPL Pricing',   sub: 'Per-lane margins \u00b7 sell prices \u00b7 benchmarks' },"""

if old_nav in src:
    src = src.replace(old_nav, new_nav)
    changes += 1
    print("[OK] Added CPL Pricing nav entry")
else:
    print("[WARN] Could not find affiliates nav entry")

# --- 4. WIRE IN RENDERING SWITCH -----------------------------------------
old_switch = "active.id === 'affiliates'    ? html`<${Affiliates} />` :"
new_switch = """active.id === 'affiliates'    ? html`<${Affiliates} />` :
            active.id === 'cpl-pricing'   ? html`<${CplPricing} />` :"""

if old_switch in src:
    src = src.replace(old_switch, new_switch)
    changes += 1
    print("[OK] Wired CplPricing in rendering switch")
else:
    print("[WARN] Could not find affiliates rendering switch entry")

# --- WRITE ----------------------------------------------------------------
with open(SPA, "w") as f:
    f.write(src)

print(f"\nDone -- {changes} changes applied")
