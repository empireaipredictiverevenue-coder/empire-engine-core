#!/usr/bin/env python3
"""Patch empire_command_spa.py with SEO performance monitoring tab."""
with open('empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# 1. SECTIONS entry after freebuff
old_sec = "  { id: 'freebuff',      label: 'FreeBuff',       sub: '5-Panel consensus · CFO · Purist · Judge' },"
new_sec = """  { id: 'freebuff',      label: 'FreeBuff',       sub: '5-Panel consensus · CFO · Purist · Judge' },
  { id: 'seo',           label: 'SEO',            sub: 'Audits · keywords · content · genome' },"""

if old_sec in content:
    content = content.replace(old_sec, new_sec)
    changes += 1
    print("1. SECTIONS entry: added")
else:
    print("1. SECTIONS: NOT FOUND")

# 2. Component routing
old_route = "            active.id === 'freebuff'     ? html`<${FreeBuffPanel} />` :"
new_route = """            active.id === 'freebuff'     ? html`<${FreeBuffPanel} />` :
            active.id === 'seo'          ? html`<${SEOPanel} />` :"""

if old_route in content:
    content = content.replace(old_route, new_route)
    changes += 1
    print("2. Routing: added")
else:
    print("2. Routing: NOT FOUND")

# 3. SEO Panel component
seo_component = r"""// ── SEO PERFORMANCE ───────────────────────────────────────────────────
function SEOPanel() {
  const [data, setData] = useState(null);
  const [err, setErr] = useState(null);
  useEffect(() => {
    apiFetch('/api/seo/performance').then(r => r.json())
      .then(d => { setData(d); setErr(null); })
      .catch(e => setErr(e.message));
  }, []);

  if (err) return html`<div class="stub"><div class="stub-title">Could not load SEO data</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const s = data.stats || {};
  const genome = data.genome || {};
  const audits = data.audits || [];
  const keywords = data.keywords || [];
  const content = data.content || [];
  const topKeywords = keywords.filter(k => (k.conversion_rate || 0) > 0).slice(0, 10);

  const traitColors = {
    keyword_competitiveness: '#FF4444',
    local_intent:            '#5AC8FA',
    content_depth:           '#44E5B8',
    technical_rigor:         '#FFB800',
    link_authority:          '#C8A2C8',
  };
  const traitLabels = {
    keyword_competitiveness: 'Competition',
    local_intent:            'Local Intent',
    content_depth:           'Depth',
    technical_rigor:         'Technical',
    link_authority:          'Authority',
  };

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">SEO <em>Optimization</em></div>
          <div class="section-sub">Audits · keyword tracking · content generation · genome evolution</div>
        </div>
        <div class="rv-narrative-badge">Gen ${data.evolution_runs || 0} · ${s.leads_attributed || 0} leads attributed</div>
      </div>

      <div class="pulse-grid">
        <div class="stat-card">
          <div class="stat-label">Audits Run</div>
          <div class="stat-value dim">${s.audits_run || 0}</div>
          <div class="stat-meta">website health checks</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Keywords Tracked</div>
          <div class="stat-value cyan">${s.keywords_tracked || 0}</div>
          <div class="stat-meta">with intent & competition data</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Content Generated</div>
          <div class="stat-value teal">${s.content_generated || 0}</div>
          <div class="stat-meta">LLM-optimized pages</div>
        </div>
        <div class="stat-card">
          <div class="stat-label">Total Revenue</div>
          <div class="stat-value teal">$${(s.total_revenue || 0).toLocaleString()}</div>
          <div class="stat-meta">${s.total_conversions || 0} conversions · ${(s.avg_conversion_rate || 0).toFixed(1)}% avg rate</div>
        </div>
      </div>

      <div class="split">
        <div class="panel">
          <div class="panel-head">SEO Genome (Gen ${data.evolution_runs || 0})</div>
          ${Object.entries(genome).length === 0 ? html`<div class="kb-empty">No genome data yet.</div>` :
            Object.entries(genome).map(([trait, val]) => {
              const pct = Math.round((val || 0) * 100);
              const color = traitColors[trait] || '#64748B';
              const label = traitLabels[trait] || trait;
              return html`
            <div class="si-trait" key=${trait}>
              <div class="si-trait-head">
                <span class="si-trait-name">${label}</span>
                <span class="si-trait-pct" style=${{color}}>${pct}%</span>
              </div>
              <div class="si-trait-track">
                <div class="si-trait-fill" style=${{width: pct + '%', background: color}}></div>
              </div>
            </div>
            `;
            })}
          ${data.last_evolution ? html`
          <div class="si-evo-footer" style=${{marginTop: '12px', paddingTop: '10px'}}>
            <span>Last evolution: ${data.last_evolution.slice(0,19).replace('T',' ')}</span>
          </div>` : ''}
        </div>

        <div class="panel">
          <div class="panel-head">Top Converting Keywords</div>
          ${topKeywords.length === 0 ? html`<div class="kb-empty">No conversion data yet.</div>` :
            html`<div style=${{maxHeight:'280px',overflowY:'auto'}}>
            ${topKeywords.map(k => html`
            <div class="seo-kw-row" key=${k.keyword}>
              <div class="seo-kw-name">${k.keyword}</div>
              <div class="seo-kw-meta">
                <span class="seo-kw-stat">${(k.conversion_rate || 0).toFixed(1)}%</span>
                <span class="seo-kw-stat dim">${k.conversions || 0} conv</span>
                <span class="seo-kw-stat dim">$${(k.total_revenue || 0).toFixed(0)}</span>
                <span class=${'seo-kw-comp ' + (k.competition || 'low')}>${k.competition || '?'}</span>
              </div>
            </div>
            `)}
          </div>`}
        </div>
      </div>

      ${content.length > 0 ? html`
      <div class="chart-panel">
        <div class="chart-panel-h">
          <span class="chart-panel-title">Recent Content</span>
          <span class="chart-panel-tag">${content.length} pieces</span>
        </div>
        ${content.slice(0, 8).map(c => html`
        <div class="seo-content-card" key=${c.id || c.keyword}>
          <div class="seo-content-head">
            <span class="seo-content-kw">${c.keyword || '—'}</span>
            <span class="seo-content-niche">${c.niche || ''} · ${c.metro || ''}</span>
          </div>
          <div class="seo-content-title">${c.title_tag || c.h1 || '—'}</div>
          <div class="seo-content-meta">${c.meta_description || ''}</div>
          ${c.attributed_lead_id ? html`<div class="seo-content-attrib">✓ Attributed to lead ${(c.attributed_lead_id || '').slice(0,8)} ${c.converted ? '· Converted' : ''}</div>` : ''}
        </div>
        `)}
      </div>
      ` : ''}

      ${audits.length > 0 ? html`
      <div class="chart-panel" style=${{marginTop: '16px'}}>
        <div class="chart-panel-h">
          <span class="chart-panel-title">Recent Audits</span>
          <span class="chart-panel-tag">${audits.length} sites</span>
        </div>
        ${audits.slice(0, 5).map(a => html`
        <div class="seo-audit-row" key=${a.id}>
          <div class="seo-audit-url">${(a.url || '').slice(0, 50)}</div>
          <div class="seo-audit-scores">
            <span class="seo-audit-score ${a.overall_score >= 70 ? 'ok' : a.overall_score >= 40 ? 'warn' : 'bad'}">${a.overall_score || 0}</span>
            <span class="seo-audit-score dim">M:${a.meta_score || 0}</span>
            <span class="seo-audit-score dim">C:${a.content_score || 0}</span>
            <span class="seo-audit-score dim">T:${a.technical_score || 0}</span>
          </div>
        </div>
        `)}
      </div>
      ` : ''}
    </div>
  `;
}

function App() {
"""

old_app = "function App() {"
if old_app in content:
    content = content.replace(old_app, seo_component)
    changes += 1
    print("3. SEOPanel component: added before App")
else:
    print("3. SEOPanel: NOT FOUND")

# 4. CSS
css_block = """
/* ── SEO PERFORMANCE ─────────────────────────────────────────── */
.seo-kw-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--empire-divider)}
.seo-kw-row:last-child{border-bottom:none}
.seo-kw-name{font-size:11px;color:var(--empire-silver);font-family:var(--font-mono)}
.seo-kw-meta{display:flex;gap:10px;align-items:center}
.seo-kw-stat{font-family:var(--font-mono);font-size:10px;color:var(--signal-teal);font-weight:500}
.seo-kw-stat.dim{color:var(--empire-fog);font-weight:400}
.seo-kw-comp{font-family:var(--font-mono);font-size:8px;letter-spacing:.1em;text-transform:uppercase;padding:1px 6px;border-radius:3px;border:1px solid}
.seo-kw-comp.low{color:var(--signal-teal);border-color:rgba(68,229,184,0.2)}
.seo-kw-comp.medium{color:var(--status-amber);border-color:rgba(255,184,0,0.2)}
.seo-kw-comp.high{color:var(--status-red);border-color:rgba(255,68,68,0.2)}
.seo-content-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:10px 14px;margin-bottom:8px;border-radius:4px}
.seo-content-card:last-child{margin-bottom:0}
.seo-content-head{display:flex;justify-content:space-between;align-items:center;margin-bottom:4px}
.seo-content-kw{font-family:var(--font-mono);font-size:10px;color:var(--strike-cyan);font-weight:500}
.seo-content-niche{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog)}
.seo-content-title{font-size:11px;color:var(--empire-white);font-weight:500;margin-bottom:3px}
.seo-content-meta{font-size:10px;color:var(--empire-mist);line-height:1.4}
.seo-content-attrib{font-family:var(--font-mono);font-size:8px;color:var(--signal-teal);margin-top:6px;padding-top:5px;border-top:1px solid var(--empire-divider)}
.seo-audit-row{display:flex;justify-content:space-between;align-items:center;padding:8px 0;border-bottom:1px solid var(--empire-divider)}
.seo-audit-row:last-child{border-bottom:none}
.seo-audit-url{font-family:var(--font-mono);font-size:10px;color:var(--empire-silver)}
.seo-audit-scores{display:flex;gap:10px}
.seo-audit-score{font-family:var(--font-mono);font-size:10px;font-weight:500}
.seo-audit-score.ok{color:var(--signal-teal)}
.seo-audit-score.warn{color:var(--status-amber)}
.seo-audit-score.bad{color:var(--status-red)}
.seo-audit-score.dim{color:var(--empire-fog);font-weight:400}
"""

css_start = content.index('_SPA_CSS = """')
js_start = content.index('_SPA_JS = r"""')
css_close = content.rfind('"""', css_start, js_start)
content = content[:css_close] + css_block + "\n" + content[css_close:]
changes += 1
print("4. SEO CSS: added")

with open('empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"Done. Total changes: {changes}")
