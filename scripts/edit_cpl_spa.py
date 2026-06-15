#!/usr/bin/env python3
"""
Edit empire_command_spa.py to wire CPL lane pricing into the SPA dashboard.
"""
import re

SPA_PATH = "/root/empire-v49/empire_command_spa.py"
MC_PATH = "/root/empire-v49/empire_mission_control.py"

with open(SPA_PATH, "r") as f:
    content = f.read()

changes_made = []

# ── 1. Add CPL pricing CSS to _SPA_CSS ─────────────────────────
cpl_css = """/* ── CPL PRICING ───────────────────────────────────────────── */
.cpl-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:24px}
.cpl-summary-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;text-align:center;position:relative;overflow:hidden}
.cpl-summary-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.cpl-summary-val{font-family:var(--font-display);font-weight:200;font-size:32px;color:var(--empire-white);line-height:1}
.cpl-summary-val.teal{color:var(--signal-teal)}
.cpl-summary-val.dim{color:var(--empire-mist)}
.cpl-summary-lbl{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:6px}
.cpl-nav{display:flex;gap:8px;margin-bottom:20px;flex-wrap:wrap}
.cpl-nav-btn{padding:6px 14px;font-family:var(--font-mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase;border:1px solid var(--empire-border);background:transparent;color:var(--empire-mist);cursor:pointer;border-radius:4px}
.cpl-nav-btn:hover{color:var(--empire-white);border-color:var(--empire-border-hi)}
.cpl-nav-btn.active{color:var(--signal-teal);border-color:var(--signal-teal-soft)}
.cpl-table-wrap{background:var(--empire-surface);border:1px solid var(--empire-border);overflow-x:auto;margin-bottom:20px}
.cpl-table{width:100%;border-collapse:collapse;font-size:11px;min-width:900px}
.cpl-table thead th{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;text-align:left;padding:10px 12px;border-bottom:1px solid var(--empire-divider);background:var(--empire-elevated);font-weight:500;white-space:nowrap}
.cpl-table tbody td{padding:9px 12px;border-bottom:1px solid var(--empire-divider);color:var(--empire-silver);vertical-align:middle}
.cpl-table tbody tr:hover{background:var(--empire-elevated)}
.cpl-table tbody tr:last-child td{border-bottom:none}
.cpl-table tbody tr.cpl-seo{opacity:0.5}
.cpl-table tbody tr.cpl-seo:hover{opacity:0.7}
.cpl-num{font-family:var(--font-mono);text-align:right}
.cpl-pos{color:var(--signal-teal);font-weight:500}
.cpl-bdg{display:inline-block;padding:2px 7px;font-family:var(--font-mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;border-radius:3px;border:1px solid}
.cpl-bdg.ppl{color:var(--signal-teal);border-color:rgba(68,229,184,0.2)}
.cpl-bdg.ppc{color:var(--strike-cyan);border-color:rgba(90,200,250,0.2)}
.cpl-bdg.service{color:var(--status-amber);border-color:rgba(255,184,0,0.2)}
.cpl-bdg.both{color:var(--empire-mist);border-color:var(--empire-divider)}
.cpl-margin-bar{display:inline-block;height:8px;border-radius:4px;min-width:12px;margin-right:8px;vertical-align:middle}
.cpl-margin-bar.hi{background:var(--signal-teal)}
.cpl-margin-bar.mid{background:var(--status-amber)}
.cpl-margin-bar.lo{background:var(--status-red)}
.cpl-pagination{display:flex;gap:10px;align-items:center;justify-content:center;margin-top:16px;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist)}
.cpl-pg-btn{padding:4px 12px;border:1px solid var(--empire-border);background:transparent;color:var(--empire-mist);cursor:pointer;border-radius:4px;font-family:var(--font-mono);font-size:9px;letter-spacing:.12em;text-transform:uppercase}
.cpl-pg-btn:hover{color:var(--empire-white);border-color:var(--empire-border-hi)}
.cpl-pg-btn:disabled{opacity:.4;cursor:default}
.cpl-pg-info{font-size:9px;color:var(--empire-fog)}
.cpl-niche-tag{font-size:9px;color:var(--empire-fog);letter-spacing:.04em}
.cpl-loading{padding:48px 0;text-align:center;font-family:var(--font-ui);font-size:12px;color:var(--empire-mist);font-style:italic}
.cpl-error{padding:32px;text-align:center;font-family:var(--font-mono);font-size:11px;color:var(--status-red);background:var(--empire-surface);border:1px solid rgba(255,68,68,0.2)}
"""

# Insert CPL CSS after the CCP/CSS section
idx = content.find("ccp-summary-car")
if idx > 0:
    css_close = content.find('"""', idx + 20)
    if css_close > 0:
        content = content[:css_close] + cpl_css + content[css_close:]
        changes_made.append("Added CPL pricing CSS")
    else:
        changes_made.append("WARN: CSS close not found")
else:
    changes_made.append("WARN: CSS insertion marker not found")

# ── 2. Add CplPricing React component ─────────────────────────
cpl_component = """
function CplPricing() {
  const [lanes, setLanes] = React.useState([]);
  const [summary, setSummary] = React.useState(null);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState(null);
  const [page, setPage] = React.useState(0);
  const [modelFilter, setModelFilter] = React.useState('all');
  const PER_PAGE = 12;

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
  }, []);

  if (loading) return html`<div class="cpl-loading">Loading CPL benchmarks...</div>`;
  if (error) return html`<div class="cpl-error">${error}</div>`;

  const filtered = modelFilter === 'all' ? lanes : lanes.filter(l => (l.recommended_model || '').toLowerCase() === modelFilter);
  const totalPages = Math.ceil(filtered.length / PER_PAGE);
  const pageLanes = filtered.slice(page * PER_PAGE, (page + 1) * PER_PAGE);

  const marginClass = (pct) => {
    if (pct >= 50) return 'hi';
    if (pct >= 25) return 'mid';
    return 'lo';
  };

  return html`
    <div class="section-h">
      <div>
        <div class="section-title">CPL <em>Pricing</em> & Lane Margins</div>
        <div class="section-sub">Per-lane benchmarks \u00b7 sell prices \u00b7 margin analysis</div>
      </div>
    </div>

    <div class="cpl-summary">
      <div class="cpl-summary-card">
        <div class="cpl-summary-val teal">${summary.total}</div>
        <div class="cpl-summary-lbl">Total Lanes</div>
      </div>
      <div class="cpl-summary-card">
        <div class="cpl-summary-val teal">$${summary.avgCplLow.toFixed(0)}\u2013$${summary.avgCplHigh.toFixed(0)}</div>
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
              <td class="cpl-niche-tag">${l.sub_niche || '\u2014'}</td>
              <td class="cpl-num">${l.cpl_low != null ? '$' + l.cpl_low.toFixed(0) : '\u2014'}</td>
              <td class="cpl-num">${l.cpl_high != null ? '$' + l.cpl_high.toFixed(0) : '\u2014'}</td>
              <td>${l.recommended_model ? html\`<span class="cpl-bdg ${l.recommended_model.toLowerCase()}">${l.recommended_model}</span>\` : html\`<span class="cpl-bdg both">\u2014</span>\`}</td>
              <td class="cpl-num cpl-pos">${l.suggested_sell_price_low != null ? '$' + l.suggested_sell_price_low.toFixed(0) + '\u2013' + l.suggested_sell_price_high.toFixed(0) : '\u2014'}</td>
              <td class="cpl-num">
                ${l.margin_pct != null ? html\`
                  <span class="cpl-margin-bar ${marginClass(l.margin_pct)}" style="width:${Math.min(l.margin_pct, 80)}px"></span>
                  ${l.margin_pct.toFixed(0)}%
                \` : '\u2014'}
              </td>
              <td class="cpl-num cpl-pos">${l.annual_revenue_projected ? '$' + (l.annual_revenue_projected / 1000).toFixed(0) + 'K' : '\u2014'}</td>
            </tr>
          \`).join('')}
        </tbody>
      </table>
      ${!pageLanes.length ? html\`<div class="tbl-empty">No lanes match this filter</div>\` : ''}
    </div>

    ${totalPages > 1 ? html\`
      <div class="cpl-pagination">
        <button class="cpl-pg-btn" disabled=${page === 0} onClick=${() => setPage(p => Math.max(0, p - 1))}>\u2190 Prev</button>
        <span class="cpl-pg-info">Page ${page + 1} of ${totalPages}</span>
        <button class="cpl-pg-btn" disabled=${page >= totalPages - 1} onClick=${() => setPage(p => Math.min(totalPages - 1, p + 1))}>Next \u2192</button>
      </div>
    \` : ''}
  \`;
}
"""

# Insert before function App()
app_match = re.search(r'\nfunction App\(\)', content)
if app_match:
    content = content[:app_match.start()] + "\n" + cpl_component + content[app_match.start():]
    changes_made.append("Added CplPricing React component")
else:
    changes_made.append("WARN: function App() not found")

# ── 3. Add CPL nav entry in NAV_GROUPS ─────────────────────────
old_nav = "      { id: 'affiliates',   label: 'Affiliates',    sub: 'Manage \u00b7 referral links \u00b7 stats' },\n"
new_nav = old_nav + "      { id: 'cpl-pricing',  label: 'CPL Pricing',    sub: 'Per-lane margins \u00b7 sell prices \u00b7 benchmarks' },\n"
if old_nav in content:
    content = content.replace(old_nav, new_nav)
    changes_made.append("Added CPL nav entry")
else:
    changes_made.append("WARN: affiliates nav entry not found")

# ── 4. Wire CPL in rendering switch ─────────────────────────────
old_stub = "            html`<${Stub} section=${active} />`\n"
new_stub = "            active.id === 'cpl-pricing' ? html`<${CplPricing} />` :\n" + old_stub
if old_stub in content:
    content = content.replace(old_stub, new_stub)
    changes_made.append("Wired CPL in render switch")
else:
    changes_made.append("WARN: Stub fallback not found")

# Write back
with open(SPA_PATH, "w") as f:
    f.write(content)

print("=== Changes to empire_command_spa.py ===")
for c in changes_made:
    print(f"  {c}")

# ── 5. Mission Control ──────────────────────────────────────────
mc_changes = []
with open(MC_PATH, "r") as f:
    mc_content = f.read()

cpl_fn = """
def _aggregate_cpl() -> dict:
    out = {
        "lanes_total": 0,
        "lanes_priced": 0,
        "avg_cpl_low": 0.0,
        "avg_cpl_high": 0.0,
        "avg_margin": 0.0,
    }
    try:
        from empire_pricing import cpl_engine
        lp = cpl_engine.lane_pricing()
        lanes = lp.get("lanes", [])
        priced = [l for l in lanes if l.get("cpl_available") is not False]
        out["lanes_total"] = len(lanes)
        out["lanes_priced"] = len(priced)
        if priced:
            out["avg_cpl_low"] = round(sum(l.get("cpl_low", 0) or 0 for l in priced) / len(priced), 2)
            out["avg_cpl_high"] = round(sum(l.get("cpl_high", 0) or 0 for l in priced) / len(priced), 2)
            margins = [l.get("margin_pct", 0) or 0 for l in priced if l.get("margin_pct") is not None]
            if margins:
                out["avg_margin"] = round(sum(margins) / len(margins), 2)
    except Exception:
        pass
    return out


"""

match_fn = re.search(r'\ndef _aggregate_network\(', mc_content)
if match_fn:
    mc_content = mc_content[:match_fn.start()] + cpl_fn + mc_content[match_fn.start():]
    mc_changes.append("Added _aggregate_cpl()")

# Wire into snapshot
old_payload = '''    payload = {
        "ts":         datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "agi":        _aggregate_agi(),
        "si":         _aggregate_si(),
        "brain":      _aggregate_brain(get_db),
        "revenue":    _aggregate_revenue(),
        "compliance": _aggregate_compliance(get_db),
        "network":    _aggregate_network(broadcaster),
    }'''
new_payload = old_payload.replace(
    '"network":    _aggregate_network(broadcaster),',
    '"network":    _aggregate_network(broadcaster),\n        "cpl":        _aggregate_cpl(),'
)
if old_payload in mc_content:
    mc_content = mc_content.replace(old_payload, new_payload)
    mc_changes.append("Wired _aggregate_cpl() into snapshot")
else:
    mc_changes.append("WARN: snapshot payload not found")

with open(MC_PATH, "w") as f:
    f.write(mc_content)

print()
print("=== Changes to empire_mission_control.py ===")
for c in mc_changes:
    print(f"  {c}")

print()
print("=== DONE ===")
