#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Replace CplPricing component with tabbed version + ROI Calculator.
Adds CSS for the ROI calculator form/results.
"""
import sys

SPA_PATH = "/root/empire-v49/empire_command_spa.py"

with open(SPA_PATH, "r", encoding="utf-8") as f:
    content = f.read()

changes = []

# ── 1. Replace CplPricing component ─────────────────────────────
old_component_start = "function CplPricing() {"
old_component_end = "function App()"
idx_start = content.find(old_component_start)
idx_end = content.find(old_component_end, idx_start)

if idx_start < 0 or idx_end < 0:
    print("ERROR: Could not find CplPricing component bounds")
    sys.exit(1)

# Build the new component with ASCII-safe characters
arrow_left = "<-"
arrow_right = "->"
em_dash = "--"
en_dash = "-"
times = "x"
bullet = "."

new_component = r"""function CplPricing() {
  const [tab, setTab] = React.useState('pricing');
  // Pricing tab state
  const [lanes, setLanes] = React.useState([]);
  const [summary, setSummary] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [page, setPage] = React.useState(0);
  const [modelFilter, setModelFilter] = React.useState('all');
  const PER_PAGE = 12;
  // ROI Calculator state
  const [niches, setNiches] = React.useState([]);
  const [subNiches, setSubNiches] = React.useState([]);
  const [selectedNiche, setSelectedNiche] = React.useState('');
  const [selectedSubNiche, setSelectedSubNiche] = React.useState('');
  const [sellPrice, setSellPrice] = React.useState(500);
  const [monthlyVolume, setMonthlyVolume] = React.useState(100);
  const [calcModel, setCalcModel] = React.useState('ppl');
  const [calcResult, setCalcResult] = React.useState(null);
  const [calcLoading, setCalcLoading] = React.useState(false);

  React.useEffect(() => {
    apiFetch('/api/v1/cpl/lanes?model=ppl&monthly_volume=100')
      .then(data => {
        if (data && data.lanes) {
          setLanes(data.lanes);
          const total = data.lanes.length;
          const priced = data.lanes.filter(l => l.cpl_available !== false);
          const avgCplLow = priced.reduce((s, l) => s + (l.cpl_low || 0), 0) / (priced.length || 1);
          const avgCplHigh = priced.reduce((s, l) => s + (l.cpl_high || 0), 0) / (priced.length || 1);
          const avgMargin = priced.reduce((s, l) => s + (l.margin_pct || 0), 0) / (priced.length || 1);
          const totalAnnRev = priced.reduce((s, l) => s + ((l.annual_revenue_projected || 0)), 0);
          setSummary({ total, priced: priced.length, avgCplLow, avgCplHigh, avgMargin, totalAnnualRevenue: totalAnnRev });
        }
        setLoading(false);
      })
      .catch(err => {
        setError(err.message || 'Failed to load CPL data');
        setLoading(false);
      });
    apiFetch('/api/v1/cpl/niches')
      .then(data => {
        if (data && data.niches) setNiches(data.niches);
      })
      .catch(() => {});
  }, []);

  React.useEffect(() => {
    if (!selectedNiche) { setSubNiches([]); setSelectedSubNiche(''); return; }
    apiFetch('/api/v1/cpl/niche/' + encodeURIComponent(selectedNiche))
      .then(data => {
        if (data && data.sub_niches) {
          const sn = Object.keys(data.sub_niches);
          setSubNiches(sn);
          setSelectedSubNiche(sn[0] || '');
        }
      })
      .catch(() => { setSubNiches([]); setSelectedSubNiche(''); });
  }, [selectedNiche]);

  function runCalculation() {
    if (!selectedNiche) return;
    setCalcLoading(true);
    setCalcResult(null);
    const params = 'niche=' + encodeURIComponent(selectedNiche)
      + '&sub_niche=' + encodeURIComponent(selectedSubNiche || selectedNiche)
      + '&sell_price=' + sellPrice
      + '&monthly_volume=' + monthlyVolume
      + '&model=' + calcModel;
    Promise.all([
      apiFetch('/api/v1/cpl/margin?' + params),
      apiFetch('/api/v1/cpl/roi/' + encodeURIComponent(selectedNiche)
        + '?sub_niche=' + encodeURIComponent(selectedSubNiche || selectedNiche)
        + '&monthly_volume=' + monthlyVolume
        + '&sell_price=' + sellPrice
        + '&model=' + calcModel),
    ])
      .then(([margin, roi]) => {
        setCalcResult({ margin, roi });
        setCalcLoading(false);
      })
      .catch(err => {
        setCalcResult({ error: err.message || 'Calculation failed' });
        setCalcLoading(false);
      });
  }

  if (loading) return html`<div class="cpl-loading">Loading CPL benchmarks...</div>`;
  if (error) return html`<div class="cpl-error">${error}</div>`;
  if (!summary && tab === 'pricing') return html`<div class="cpl-loading">Loading...</div>`;

  const filtered = modelFilter === 'all' ? lanes : lanes.filter(l => (l.recommended_model || '').toLowerCase() === modelFilter);
  const totalPages = Math.ceil(filtered.length / PER_PAGE);
  const pageLanes = filtered.slice(page * PER_PAGE, (page + 1) * PER_PAGE);
  const marginClass = (pct) => {
    if (pct >= 50) return 'hi';
    if (pct >= 25) return 'mid';
    return 'lo';
  };

  const pricingTab = html`
    <div class="cpl-summary">
      <div class="cpl-summary-card">
        <div class="cpl-summary-val teal">${summary.total}</div>
        <div class="cpl-summary-lbl">Total Lanes</div>
      </div>
      <div class="cpl-summary-card">
        <div class="cpl-summary-val teal">$${summary.avgCplLow.toFixed(0)}-$${summary.avgCplHigh.toFixed(0)}</div>
        <div class="cpl-summary-lbl">Avg CPL Range</div>
      </div>
      <div class="cpl-summary-card">
        <div class="cpl-summary-val teal">${summary.avgMargin.toFixed(1)}%</div>
        <div class="cpl-summary-lbl">Avg Margin</div>
      </div>
      <div class="cpl-summary-card">
        <div class="cpl-summary-val dim">$${(summary.totalAnnualRevenue / 1000).toFixed(0)}K</div>
        <div class="cpl-summary-lbl">Projected Annual</div>
      </div>
    </div>

    <div class="cpl-nav">
      <button class="cpl-nav-btn ${modelFilter === 'all' ? 'active' : ''}" onClick=${() => { setModelFilter('all'); setPage(0); }}>All Models</button>
      <button class="cpl-nav-btn ${modelFilter === 'ppl' ? 'active' : ''}" onClick=${() => { setModelFilter('ppl'); setPage(0); }}>PPL Only</button>
      <button class="cpl-nav-btn ${modelFilter === 'ppc' ? 'active' : ''}" onClick=${() => { setModelFilter('ppc'); setPage(0); }}>PPC Only</button>
      <button class="cpl-nav-btn ${modelFilter === 'service' ? 'active' : ''}" onClick=${() => { setModelFilter('service'); setPage(0); }}>Service</button>
      <span style=${{marginLeft:'auto',fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-fog)',letterSpacing:'0.08em'}}>${filtered.length} of ${lanes.length} lanes shown</span>
    </div>

    <div class="cpl-table-wrap">
      <table class="cpl-table">
        <thead>
          <tr>
            <th>Lane</th>
            <th>Niche</th>
            <th>Sub-Niche</th>
            <th>CPL Low</th>
            <th>CPL High</th>
            <th>Model</th>
            <th>Sell Price</th>
            <th>Margin</th>
            <th>Annual Rev</th>
          </tr>
        </thead>
        <tbody>
          ${pageLanes.map(l => html\`
            <tr class="${l.cpl_available === false ? 'cpl-seo' : ''}">
              <td><strong style="color:var(--empire-white)">${l.lane_id}</strong></td>
              <td>${l.niche}</td>
              <td class="cpl-niche-tag">${l.sub_niche || '--'}</td>
              <td class="cpl-num">${l.cpl_low != null ? '$' + l.cpl_low.toFixed(0) : '--'}</td>
              <td class="cpl-num">${l.cpl_high != null ? '$' + l.cpl_high.toFixed(0) : '--'}</td>
              <td>${l.recommended_model ? html\`<span class="cpl-bdg ${l.recommended_model.toLowerCase()}">${l.recommended_model}</span>\` : html\`<span class="cpl-bdg both">--</span>\`}</td>
              <td class="cpl-num cpl-pos">${l.suggested_sell_price_low != null ? '$' + l.suggested_sell_price_low.toFixed(0) + '-' + l.suggested_sell_price_high.toFixed(0) : '--'}</td>
              <td class="cpl-num">
                ${l.margin_pct != null ? html\`
                  <span class="cpl-margin-bar ${marginClass(l.margin_pct)}" style="width:${Math.min(l.margin_pct, 80)}px"></span>
                  ${l.margin_pct.toFixed(0)}%
                \` : '--'}
              </td>
              <td class="cpl-num cpl-pos">${l.annual_revenue_projected ? '$' + (l.annual_revenue_projected / 1000).toFixed(0) + 'K' : '--'}</td>
            </tr>
          \`).join('')}
        </tbody>
      </table>
      ${!pageLanes.length ? html\`<div class="tbl-empty">No lanes match this filter</div>\` : ''}
    </div>

    ${totalPages > 1 ? html\`
      <div class="cpl-pagination">
        <button class="cpl-pg-btn" disabled=${page === 0} onClick=${() => setPage(p => Math.max(0, p - 1))}>Prev</button>
        <span class="cpl-pg-info">Page ${page + 1} of ${totalPages}</span>
        <button class="cpl-pg-btn" disabled=${page >= totalPages - 1} onClick=${() => setPage(p => Math.min(totalPages - 1, p + 1))}>Next</button>
      </div>
    \` : ''}
  `;

  const roiTab = html\`
    <div class="cpl-roi-grid">
      <div class="cpl-roi-form">
        <div class="cpl-roi-form-title">Parameters</div>

        <div class="cpl-fld">
          <label class="cpl-fld-lbl">Niche</label>
          <select class="cpl-fld-sel" value=${selectedNiche} onChange=${(e) => setSelectedNiche(e.target.value)}>
            <option value="">Select niche...</option>
            ${niches.map(n => html\`<option value="${n}">${n}</option>\`)}
          </select>
        </div>

        <div class="cpl-fld">
          <label class="cpl-fld-lbl">Sub-Niche</label>
          <select class="cpl-fld-sel" value=${selectedSubNiche} onChange=${(e) => setSelectedSubNiche(e.target.value)} disabled=${!subNiches.length}>
            ${subNiches.map(sn => html\`<option value="${sn}">${sn}</option>\`)}
            ${!subNiches.length ? html\`<option value="">No sub-niches available</option>\` : ''}
          </select>
        </div>

        <div class="cpl-fld-row">
          <div class="cpl-fld">
            <label class="cpl-fld-lbl">Sell Price ($)</label>
            <input class="cpl-fld-in" type="number" min="1" step="10" value=${sellPrice} onChange=${(e) => setSellPrice(parseFloat(e.target.value) || 0)} />
          </div>
          <div class="cpl-fld">
            <label class="cpl-fld-lbl">Monthly Vol.</label>
            <input class="cpl-fld-in" type="number" min="1" step="10" value=${monthlyVolume} onChange=${(e) => setMonthlyVolume(parseInt(e.target.value) || 0)} />
          </div>
        </div>

        <div class="cpl-fld">
          <label class="cpl-fld-lbl">Model</label>
          <div class="cpl-model-tog">
            <button class="cpl-model-btn ${calcModel === 'ppl' ? 'active' : ''}" onClick=${() => setCalcModel('ppl')}>PPL</button>
            <button class="cpl-model-btn ${calcModel === 'ppc' ? 'active' : ''}" onClick=${() => setCalcModel('ppc')}>PPC</button>
          </div>
        </div>

        <button class="cpl-calc-btn" onClick=${runCalculation} disabled=${calcLoading || !selectedNiche}>
          ${calcLoading ? 'Calculating...' : 'Calculate ROI'}
        </button>
      </div>

      <div class="cpl-roi-results">
        ${calcResult && calcResult.error ? html\`
          <div class="cpl-error">${calcResult.error}</div>
        \` : calcResult && calcResult.margin ? html\`
          <div class="cpl-roi-results-title">P&L Statement -- ${selectedNiche} / ${selectedSubNiche}</div>

          <div class="cpl-roi-metrics">
            <div class="cpl-roi-card">
              <div class="cpl-roi-val teal">$${(calcResult.margin.cpl_low || 0).toFixed(0)}-$${(calcResult.margin.cpl_high || 0).toFixed(0)}</div>
              <div class="cpl-roi-lbl">CPL Range</div>
            </div>
            <div class="cpl-roi-card">
              <div class="cpl-roi-val dim">$${(calcResult.margin.monthly_acquisition_cost || 0).toLocaleString()}</div>
              <div class="cpl-roi-lbl">Acq Cost /mo</div>
            </div>
            <div class="cpl-roi-card">
              <div class="cpl-roi-val teal">$${(calcResult.margin.monthly_revenue || 0).toLocaleString()}</div>
              <div class="cpl-roi-lbl">Revenue /mo</div>
            </div>
            <div class="cpl-roi-card">
              <div class="cpl-roi-val ${(calcResult.margin.gross_margin_usd || 0) >= 0 ? 'teal' : 'cpl-neg'}">$${(calcResult.margin.gross_margin_usd || 0).toLocaleString()}</div>
              <div class="cpl-roi-lbl">Gross Profit /mo</div>
            </div>
            <div class="cpl-roi-card">
              <div class="cpl-roi-val teal">${(calcResult.margin.gross_margin_pct || 0).toFixed(1)}%</div>
              <div class="cpl-roi-lbl">Margin</div>
            </div>
            <div class="cpl-roi-card">
              <div class="cpl-roi-val teal">${calcResult.margin.breakeven_volume || 0}</div>
              <div class="cpl-roi-lbl">Breakeven /mo</div>
            </div>
            <div class="cpl-roi-card">
              <div class="cpl-roi-val teal">$${((calcResult.margin.annual_revenue || 0) / 1000).toFixed(0)}K</div>
              <div class="cpl-roi-lbl">Annual Revenue</div>
            </div>
            <div class="cpl-roi-card">
              <div class="cpl-roi-val teal">$${((calcResult.margin.annual_profit || 0) / 1000).toFixed(0)}K</div>
              <div class="cpl-roi-lbl">Annual Profit</div>
            </div>
          </div>

          <div class="cpl-roi-rev-breakdown">
            <div class="cpl-roi-bd-title">Monthly Breakdown</div>
            <div class="cpl-roi-bd-row">
              <span class="cpl-roi-bd-lbl">Acquisition (${monthlyVolume} leads x avg CPL $${((calcResult.margin.cpl_low + calcResult.margin.cpl_high) / 2).toFixed(0)})</span>
              <span class="cpl-roi-bd-val dim">- $${calcResult.margin.monthly_acquisition_cost.toLocaleString()}</span>
            </div>
            <div class="cpl-roi-bd-row">
              <span class="cpl-roi-bd-lbl">Revenue (${monthlyVolume} leads x $${sellPrice.toFixed(0)})</span>
              <span class="cpl-roi-bd-val teal">+ $${calcResult.margin.monthly_revenue.toLocaleString()}</span>
            </div>
            <div class="cpl-roi-bd-row cpl-roi-bd-total">
              <span class="cpl-roi-bd-lbl">Net Profit / Month</span>
              <span class="cpl-roi-bd-val ${(calcResult.margin.gross_margin_usd || 0) >= 0 ? 'teal' : 'cpl-neg'}">
                ${(calcResult.margin.gross_margin_usd || 0) >= 0 ? '+' : ''}$${calcResult.margin.gross_margin_usd.toLocaleString()}
              </span>
            </div>
          </div>

          ${calcResult.roi ? html\`
          <div class="cpl-roi-roi-section">
            <div class="cpl-roi-bd-title">ROI Analysis</div>
            <div class="cpl-roi-roi-grid">
              <div class="cpl-roi-roi-stat">
                <span class="cpl-roi-roi-val ${(calcResult.roi.roi_percentage || 0) >= 0 ? 'teal' : 'cpl-neg'}">${(calcResult.roi.roi_percentage || 0) >= 0 ? '+' : ''}${calcResult.roi.roi_percentage.toFixed(1)}%</span>
                <span class="cpl-roi-roi-lbl">ROI</span>
              </div>
              <div class="cpl-roi-roi-stat">
                <span class="cpl-roi-roi-val teal">${calcResult.roi.markup_multiple || 0}x</span>
                <span class="cpl-roi-roi-lbl">Markup</span>
              </div>
              <div class="cpl-roi-roi-stat">
                <span class="cpl-roi-roi-val teal">${calcResult.roi.breakeven_volume || 0}</span>
                <span class="cpl-roi-roi-lbl">Breakeven /mo</span>
              </div>
            </div>
          </div>
          \` : ''}

          <div class="cpl-roi-tip">
            <strong>Tip:</strong> Adjust the sell price to target 60%+ margin. The breakeven volume tells you how many leads you need to cover costs at this price.
          </div>
        \` : html\`
          <div class="cpl-roi-placeholder">
            <div class="cpl-roi-placeholder-icon">📊</div>
            <div class="cpl-roi-placeholder-title">ROI Calculator</div>
            <div class="cpl-roi-placeholder-body">Select a niche, set your sell price and volume, then click <strong>Calculate ROI</strong> to see the full P&L statement for any lane vertical.</div>
          </div>
        \`}
      </div>
    </div>
  `;

  return html\`
    <div class="section-h">
      <div>
        <div class="section-title">CPL <em>Pricing</em> & Lane Margins</div>
        <div class="section-sub">Per-lane benchmarks / sell prices / margin analysis</div>
      </div>
    </div>

    <div class="cpl-tabs">
      <button class="cpl-tab ${tab === 'pricing' ? 'active' : ''}" onClick=${() => setTab('pricing')}>Lane Pricing</button>
      <button class="cpl-tab ${tab === 'roi' ? 'active' : ''}" onClick=${() => setTab('roi')}>ROI Calculator</button>
    </div>

    ${tab === 'pricing' ? pricingTab : roiTab}
  `;
}
"""

new_component = new_component.strip()

# Replace old component with new one
content = content[:idx_start] + new_component + "\n\n" + content[idx_end:]
changes.append("Replaced CplPricing component with tabbed version + ROI Calculator")

# ── 2. Add ROI Calculator CSS ──────────────────────────────────
roi_css = """
/* -- CPL TABS -- */
.cpl-tabs{display:flex;gap:0;margin-bottom:24px;border-bottom:1px solid var(--empire-divider)}
.cpl-tab{padding:10px 22px;font-family:var(--font-mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:var(--empire-mist);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s var(--ease-snap);background:none;border-top:none;border-left:none;border-right:none}
.cpl-tab:hover{color:var(--empire-white)}
.cpl-tab.active{color:var(--signal-teal);border-bottom-color:var(--signal-teal)}
/* -- ROI CALCULATOR -- */
.cpl-roi-grid{display:grid;grid-template-columns:320px 1fr;gap:20px;align-items:start}
.cpl-roi-form{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px}
.cpl-roi-form-title{font-weight:500;font-size:13px;color:var(--empire-white);margin-bottom:18px;letter-spacing:.02em}
.cpl-fld{display:flex;flex-direction:column;gap:5px;margin-bottom:14px}
.cpl-fld-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.cpl-fld-lbl{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase}
.cpl-fld-in{background:var(--empire-elevated);border:1px solid var(--empire-border);padding:9px 12px;color:var(--empire-white);font-family:var(--font-mono);font-size:13px;outline:none}
.cpl-fld-in:focus{border-color:var(--signal-teal)}
.cpl-fld-sel{background:var(--empire-elevated);border:1px solid var(--empire-border);padding:9px 12px;color:var(--empire-white);font-family:var(--font-mono);font-size:12px;outline:none;cursor:pointer;appearance:none;-webkit-appearance:none;background-image:url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%2394a3b8'/%3E%3C/svg%3E");background-repeat:no-repeat;background-position:right 12px center;padding-right:32px}
.cpl-fld-sel:focus{border-color:var(--signal-teal)}
.cpl-fld-sel:disabled{opacity:.4;cursor:default}
.cpl-model-tog{display:flex;gap:0;border:1px solid var(--empire-border);overflow:hidden}
.cpl-model-btn{padding:8px 20px;font-family:var(--font-mono);font-size:10px;letter-spacing:.12em;text-transform:uppercase;background:transparent;color:var(--empire-mist);cursor:pointer;border:none;border-right:1px solid var(--empire-divider);transition:all .15s var(--ease-snap)}
.cpl-model-btn:last-child{border-right:none}
.cpl-model-btn:hover{color:var(--empire-white);background:var(--empire-elevated)}
.cpl-model-btn.active{color:var(--signal-teal);background:rgba(68,229,184,0.06)}
.cpl-calc-btn{width:100%;padding:12px 0;background:var(--signal-teal);color:#000;font-family:var(--font-mono);font-size:11px;letter-spacing:.14em;text-transform:uppercase;border:none;cursor:pointer;font-weight:700;margin-top:6px;transition:background .15s var(--ease-snap)}
.cpl-calc-btn:hover{background:var(--strike-cyan)}
.cpl-calc-btn:disabled{opacity:.5;cursor:default}
/* -- ROI Results -- */
.cpl-roi-results{min-height:300px}
.cpl-roi-results-title{font-weight:500;font-size:14px;color:var(--empire-white);margin-bottom:16px;letter-spacing:.02em}
.cpl-roi-metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.cpl-roi-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:14px 16px;text-align:center}
.cpl-roi-val{font-family:var(--font-display);font-weight:200;font-size:24px;color:var(--empire-white);line-height:1;margin-bottom:4px}
.cpl-roi-val.teal{color:var(--signal-teal)}
.cpl-roi-val.dim{color:var(--empire-mist)}
.cpl-roi-val.cpl-neg{color:var(--status-red)}
.cpl-roi-lbl{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.12em;text-transform:uppercase}
.cpl-roi-rev-breakdown{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;margin-bottom:16px}
.cpl-roi-bd-title{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;margin-bottom:12px}
.cpl-roi-bd-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--empire-divider);font-family:var(--font-mono);font-size:11px}
.cpl-roi-bd-row:last-child{border-bottom:none}
.cpl-roi-bd-total{padding-top:12px;margin-top:4px;border-top:2px solid var(--empire-border)}
.cpl-roi-bd-lbl{color:var(--empire-silver)}
.cpl-roi-bd-val{font-weight:500;text-align:right}
.cpl-roi-bd-val.teal{color:var(--signal-teal)}
.cpl-roi-bd-val.dim{color:var(--empire-mist)}
.cpl-roi-bd-val.cpl-neg{color:var(--status-red)}
.cpl-roi-roi-section{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;margin-bottom:16px}
.cpl-roi-roi-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
.cpl-roi-roi-stat{text-align:center;padding:12px 0}
.cpl-roi-roi-val{font-family:var(--font-display);font-weight:200;font-size:28px;line-height:1;display:block;margin-bottom:4px}
.cpl-roi-roi-val.teal{color:var(--signal-teal)}
.cpl-roi-roi-val.cpl-neg{color:var(--status-red)}
.cpl-roi-roi-lbl{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.12em;text-transform:uppercase}
.cpl-roi-tip{font-size:11px;color:var(--empire-mist);line-height:1.6;padding:12px 14px;background:var(--empire-elevated);border-left:3px solid var(--strike-cyan);margin-top:16px}
.cpl-roi-tip strong{color:var(--empire-white)}
.cpl-roi-placeholder{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:80px 32px;text-align:center;background:var(--empire-surface);border:1px dashed var(--empire-border)}
.cpl-roi-placeholder-icon{font-size:48px;margin-bottom:16px;opacity:.5}
.cpl-roi-placeholder-title{font-weight:200;font-size:22px;color:var(--empire-white);letter-spacing:-.02em;margin-bottom:10px}
.cpl-roi-placeholder-body{color:var(--empire-mist);font-size:12px;max-width:400px;line-height:1.7}
.cpl-roi-placeholder-body strong{color:var(--signal-teal)}
"""

# Insert CSS after the cpl-error rule
idx2 = content.find(".cpl-error{padding:32px;")
if idx2 > 0:
    end_idx = content.find("}", idx2) + 1
    content = content[:end_idx] + "\n" + roi_css + content[end_idx:]
    changes.append("Added ROI Calculator CSS")
else:
    changes.append("WARN: CSS insertion point not found")

with open(SPA_PATH, "w", encoding="utf-8") as f:
    f.write(content)

print("=== Changes ===")
for c in changes:
    print(f"  {c}")
print("=== DONE ===")
