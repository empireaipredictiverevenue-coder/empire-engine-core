"""Apply QC dashboard edits to empire_command_spa.py."""
import re

with open('empire_command_spa.py', 'r') as f:
    content = f.read()

# 1. Add QC nav entry in SYSTEM group (after bridge line)
old1 = "      { id: 'bridge',         label: 'Bridge',         sub: 'Voice-first interface \u00b7 full-screen' },\n    ]\n  },\n];\n\n// Flattened lookup"
new1 = "      { id: 'bridge',         label: 'Bridge',         sub: 'Voice-first interface \u00b7 full-screen' },\n      { id: 'qc',             label: 'QC',              sub: 'Quality control events \u00b7 resolve' },\n    ]\n  },\n];\n\n// Flattened lookup"
count1 = content.count(old1)
print(f"Edit 1: found {count1} occurrences")
if count1 != 1:
    print("ERROR: unexpected count for edit 1")
    exit(1)
content = content.replace(old1, new1, 1)
print("Edit 1: OK - added QC nav entry")

# 2. Add QC route case
old2 = "            active.id === 'cpl-pricing'   ? html`<${CplPricing} />` :\n            html`<${Stub} section=${active} />`"
new2 = "            active.id === 'cpl-pricing'   ? html`<${CplPricing} />` :\n            active.id === 'qc'            ? html`<${QC} />` :\n            html`<${Stub} section=${active} />`"
count2 = content.count(old2)
print(f"Edit 2: found {count2} occurrences")
if count2 != 1:
    print("ERROR: unexpected count for edit 2")
    exit(1)
content = content.replace(old2, new2, 1)
print("Edit 2: OK - added QC route case")

# 3. Add QC CSS styles before COMMAND CENTER PRO section
old3 = "/* \u2500\u2500 COMMAND CENTER PRO \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */\n.ccp-dash{padding:0 4px}"
qc_css = """/* \u2500\u2500 QC DASHBOARD \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500 */
.qc-summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.qc-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;position:relative;overflow:hidden}
.qc-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--signal-teal-soft),transparent)}
.qc-card-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.18em;text-transform:uppercase;margin-bottom:8px}
.qc-card-val{font-family:var(--font-display);font-weight:200;font-size:32px;color:var(--empire-white);line-height:1}
.qc-card-val.teal{color:var(--signal-teal)}
.qc-card-val.amber{color:#FFB800}
.qc-card-val.red{color:#FF4444}
.qc-card-val.dim{color:var(--empire-mist)}
.qc-card-sub{font-family:var(--font-mono);font-size:10px;color:var(--empire-fog);margin-top:6px}
.qc-filter-bar{display:flex;gap:12px;align-items:center;margin-bottom:16px;flex-wrap:wrap}
.qc-filter-group{display:flex;align-items:center;gap:6px}
.qc-filter-label{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.12em;text-transform:uppercase}
.qc-filter-select{padding:5px 10px;border:1px solid var(--empire-border);border-radius:4px;background:var(--empire-raised);color:var(--empire-white);font-family:var(--font-mono);font-size:10px;outline:none;cursor:pointer;transition:border-color .12s var(--ease-snap)}
.qc-filter-select:hover{border-color:var(--empire-border-hi)}
.qc-filter-select:focus{border-color:var(--signal-teal)}
.qc-filter-toggle{display:inline-flex;align-items:center;gap:6px;padding:5px 12px;border:1px solid var(--empire-border);border-radius:4px;cursor:pointer;font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);background:transparent;transition:all .12s var(--ease-snap)}
.qc-filter-toggle:hover{border-color:var(--empire-border-hi);color:var(--empire-white)}
.qc-filter-toggle.active{border-color:var(--signal-teal-soft);color:var(--signal-teal);background:rgba(68,229,184,0.04)}
.qc-refresh-btn{padding:6px 14px;border:1px solid var(--signal-teal-soft);border-radius:4px;cursor:pointer;font-family:var(--font-mono);font-size:9px;color:var(--signal-teal);background:transparent;transition:all .12s var(--ease-snap);margin-left:auto}
.qc-refresh-btn:hover{background:rgba(68,229,184,0.08)}
.qc-refresh-btn:disabled{opacity:.5;cursor:default}
.qc-table-wrap{overflow-x:auto;background:var(--empire-surface);border:1px solid var(--empire-border)}
.qc-table{width:100%;border-collapse:collapse;font-size:11px;min-width:900px}
.qc-table th{text-align:left;padding:10px 12px;color:var(--empire-fog);font-weight:500;border-bottom:1px solid var(--empire-border);text-transform:uppercase;font-size:9px;letter-spacing:.08em;background:var(--empire-elevated);white-space:nowrap}
.qc-table td{padding:9px 12px;border-bottom:1px solid var(--empire-divider);color:var(--empire-white);vertical-align:middle}
.qc-table tr:hover td{background:var(--empire-elevated)}
.qc-table tr.qc-expanded td{background:var(--empire-elevated)}
.qc-table tr:last-child td{border-bottom:none}
.qc-severity{display:inline-block;padding:2px 8px;border-radius:4px;font-size:9px;font-weight:600;text-transform:uppercase;letter-spacing:.08em}
.qc-severity.tier_1{color:var(--signal-teal);background:rgba(68,229,184,0.1)}
.qc-severity.tier_2{color:#FFB800;background:rgba(255,184,0,0.1)}
.qc-severity.tier_3{color:#FF4444;background:rgba(255,68,68,0.1)}
.qc-category{font-size:10px;color:var(--empire-mist);letter-spacing:.04em;font-family:var(--font-mono)}
.qc-subject-id{font-family:var(--font-mono);font-size:10px;color:var(--strike-cyan);max-width:140px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:middle}
.qc-summary{font-size:11px;color:var(--empire-silver);max-width:280px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;display:inline-block;vertical-align:middle}
.qc-check{font-family:var(--font-mono);font-size:9px;text-align:center}
.qc-check.yes{color:var(--signal-teal)}
.qc-check.no{color:var(--empire-fog)}
.qc-resolve-btn{padding:4px 12px;border:1px solid var(--signal-teal-soft);border-radius:4px;cursor:pointer;font-family:var(--font-mono);font-size:9px;color:var(--signal-teal);background:transparent;transition:all .12s var(--ease-snap);font-weight:600;white-space:nowrap}
.qc-resolve-btn:hover{background:rgba(68,229,184,0.1)}
.qc-resolve-btn:disabled{opacity:.4;cursor:not-allowed;border-color:var(--empire-border);color:var(--empire-fog)}
.qc-resolve-btn.done{opacity:.5;border-color:var(--empire-border);color:var(--empire-mist);cursor:default}
.qc-detail-panel{padding:14px 16px;background:var(--empire-elevated);border:1px solid var(--empire-divider);margin:4px 12px 12px;border-radius:6px;animation:empire-fade-up .2s var(--ease-out-empire)}
.qc-detail-head{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-bottom:10px;display:flex;align-items:center;gap:8px}
.qc-detail-json{font-family:var(--font-mono);font-size:10px;color:var(--empire-silver);white-space:pre-wrap;word-break:break-word;line-height:1.5;max-height:300px;overflow-y:auto;background:var(--empire-surface);padding:10px 12px;border-radius:4px;border:1px solid var(--empire-divider)}
.qc-detail-meta{display:flex;gap:16px;flex-wrap:wrap;font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);margin-bottom:10px;padding-bottom:10px;border-bottom:1px solid var(--empire-divider)}
.qc-detail-meta span strong{color:var(--empire-white)}
.qc-empty{text-align:center;padding:48px 0;color:var(--empire-fog);font-family:var(--font-ui);font-size:12px;font-style:italic}
.qc-loading{text-align:center;padding:48px 0;color:var(--empire-fog);font-family:var(--font-mono);font-size:11px}
.qc-error{background:rgba(255,68,68,0.08);border:1px solid rgba(255,68,68,0.2);border-radius:6px;padding:14px 18px;color:#FF4444;font-size:12px;margin-bottom:20px}

"""
new3 = qc_css + old3
count3 = content.count(old3)
print(f"Edit 3: found {count3} occurrences")
if count3 != 1:
    print("ERROR: unexpected count for edit 3")
    exit(1)
content = content.replace(old3, new3, 1)
print("Edit 3: OK - added QC CSS styles")

# 4. Add QC React component before createRoot
old4 = "createRoot(document.getElementById('root')).render(html`<${App} />`);"
qc_component = """// \u2500\u2500 QC DASHBOARD \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500
function QC() {
  const [events, setEvents] = useState(null);
  const [err, setErr] = useState(null);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState(null);
  const [resolving, setResolving] = useState({});
  const [severity, setSeverity] = useState('');
  const [showResolved, setShowResolved] = useState(false);
  const [timeRange, setTimeRange] = useState('24h');

  const fetchEvents = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      let url = '/api/v1/qc/events?limit=100';
      if (severity) url += '&severity=' + encodeURIComponent(severity);
      if (!showResolved) url += '&resolved=false';
      const since = timeRange === '7d' ? new Date(Date.now() - 7*86400000).toISOString() : timeRange === '30d' ? new Date(Date.now() - 30*86400000).toISOString() : '';
      if (since) url += '&since=' + encodeURIComponent(since);
      const r = await apiFetch(url).then(x => x.json());
      if (r.ok === false) { setErr(r.error || 'API error'); setEvents([]); }
      else { setEvents(r.events || []); }
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
      setEvents([]);
    }
    setLoading(false);
  }, [severity, showResolved, timeRange]);

  useEffect(() => { fetchEvents(); }, [fetchEvents]);

  const resolveEvent = async (id) => {
    setResolving(r => ({ ...r, [id]: true }));
    try {
      const r = await apiFetch('/api/v1/qc/events/' + id + '/resolve', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resolved_by: 'operator' }),
      }).then(x => x.json());
      if (r.ok) {
        setEvents(evts => (evts || []).map(e => e.id === id ? { ...e, resolved: true, resolved_at: r.resolved_at, resolved_by: r.resolved_by } : e));
      }
    } catch (e) {}
    setResolving(r => ({ ...r, [id]: false }));
  };

  const toggleExpand = (id) => {
    setExpandedId(prev => prev === id ? null : id);
  };

  if (err) return html`<div class="qc-error">${err}</div>`;

  const totalEvents = events ? events.length : 0;
  const unresolvedTier2 = events ? events.filter(e => e.severity === 'tier_2' && !e.resolved).length : 0;
  const autoRemediated24h = events ? events.filter(e => e.auto_remediated).length : 0;
  const lastSummary = events ? events.filter(e => e.category === 'daily_summary').sort((a,b) => new Date(b.created_at) - new Date(a.created_at))[0] : null;

  return html`
    <div>
      <div class="section-h">
        <div class="section-title">Quality <em>Control</em></div>
        <div class="section-sub">Events \u00b7 severity \u00b7 resolve</div>
      </div>
      <div class="qc-summary-grid">
        <div class="qc-card">
          <div class="qc-card-label">Total Events (24h)</div>
          <div class="qc-card-val ${totalEvents > 0 ? 'teal' : 'dim'}">${totalEvents}</div>
          <div class="qc-card-sub">In current view</div>
        </div>
        <div class="qc-card">
          <div class="qc-card-label">Unresolved Tier-2</div>
          <div class="qc-card-val ${unresolvedTier2 > 0 ? 'amber' : 'teal'}">${unresolvedTier2}</div>
          <div class="qc-card-sub">${unresolvedTier2 > 0 ? 'Needs your attention' : 'All clear'}</div>
        </div>
        <div class="qc-card">
          <div class="qc-card-label">Auto-Remediations</div>
          <div class="qc-card-val teal">${autoRemediated24h}</div>
          <div class="qc-card-sub">Tier-1 auto-fixes in view</div>
        </div>
        <div class="qc-card">
          <div class="qc-card-label">Last Daily Summary</div>
          <div class="qc-card-val ${lastSummary ? 'teal' : 'dim'}">${lastSummary ? new Date(lastSummary.created_at).toLocaleDateString() : '\u2014'}</div>
          <div class="qc-card-sub">${lastSummary ? new Date(lastSummary.created_at).toLocaleTimeString() : 'No summary yet'}</div>
        </div>
      </div>
      <div class="qc-filter-bar">
        <div class="qc-filter-group">
          <span class="qc-filter-label">Severity</span>
          <select class="qc-filter-select" value=${severity} onChange=${e => setSeverity(e.target.value)}>
            <option value="">All</option>
            <option value="tier_1">Tier 1</option>
            <option value="tier_2">Tier 2</option>
            <option value="tier_3">Tier 3</option>
          </select>
        </div>
        <div class="qc-filter-group">
          <span class="qc-filter-label">Time</span>
          <select class="qc-filter-select" value=${timeRange} onChange=${e => setTimeRange(e.target.value)}>
            <option value="24h">Last 24h</option>
            <option value="7d">Last 7 days</option>
            <option value="30d">Last 30 days</option>
          </select>
        </div>
        <button class=${'qc-filter-toggle ' + (showResolved ? 'active' : '')} onClick=${() => setShowResolved(r => !r)}>
          ${showResolved ? '\u2713' : '\u25cb'} Show Resolved
        </button>
        <button class="qc-refresh-btn" onClick=${fetchEvents} disabled=${loading}>
          ${loading ? '\u27f3' : '\u21bb'} Refresh
        </button>
      </div>
      ${loading ? html`<div class="qc-loading">Loading QC events\u2026</div>` : !events || events.length === 0 ? html`<div class="qc-empty">No QC events found</div>` : html`
        <div class="qc-table-wrap">
          <table class="qc-table">
            <thead>
              <tr>
                <th>Created</th>
                <th>Severity</th>
                <th>Category</th>
                <th>Subject</th>
                <th>Summary</th>
                <th class="qc-check">Auto</th>
                <th class="qc-check">TG</th>
                <th>Resolved</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${events.map(e => {
                const isExpanded = expandedId === e.id;
                return html`
                  <tr key=${e.id} class=${isExpanded ? 'qc-expanded' : ''} onClick=${() => toggleExpand(e.id)} style=${{cursor:'pointer'}}>
                    <td style=${{whiteSpace:'nowrap',fontFamily:'var(--font-mono)',fontSize:'10px',color:'var(--empire-fog)'}}>${new Date(e.created_at).toLocaleString()}</td>
                    <td><span class=${'qc-severity ' + e.severity}>${e.severity.replace('_', ' ')}</span></td>
                    <td><span class="qc-category">${e.category || '\u2014'}</span></td>
                    <td><span class="qc-subject-id" title=${e.subject_id || ''}>${(e.subject_id || '\u2014').slice(0,24)}</span></td>
                    <td><span class="qc-summary" title=${e.summary || ''}>${e.summary || '\u2014'}</span></td>
                    <td class=${'qc-check ' + (e.auto_remediated ? 'yes' : 'no')}>${e.auto_remediated ? '\u2713' : '\u2014'}</td>
                    <td class=${'qc-check ' + (e.telegram_pinged ? 'yes' : 'no')}>${e.telegram_pinged ? '\u2713' : '\u2014'}</td>
                    <td>${e.resolved ? html`<span style=${{color:'var(--empire-mist)',fontSize:'10px',fontFamily:'var(--font-mono)'}}>\u2713 ${(e.resolved_at || '').slice(0,10)}</span>` : html`<span style=${{color:'var(--status-amber)',fontSize:'10px',fontFamily:'var(--font-mono)'}}>Pending</span>`}</td>
                    <td>
                      ${!e.resolved ? html`
                        <button class="qc-resolve-btn"
                                onClick=${(ev) => { ev.stopPropagation(); resolveEvent(e.id); }}
                                disabled=${resolving[e.id]}>
                          ${resolving[e.id] ? '\u2026' : 'Resolve'}
                        </button>
                      ` : html`
                        <button class="qc-resolve-btn done" disabled>Done</button>
                      `}
                    </td>
                  </tr>
                  ${isExpanded ? html`
                    <tr key=${e.id + '-detail'}>
                      <td colspan="9" style=${{padding:'0'}}>
                        <div class="qc-detail-panel">
                          <div class="qc-detail-meta">
                            <span>Source: <strong>${e.source_agent || '\u2014'}</strong></span>
                            <span>Kind: <strong>${e.subject_kind || '\u2014'}</strong></span>
                            <span>ID: <strong>${e.subject_id || '\u2014'}</strong></span>
                            ${e.auto_remediated ? html`<span>Remediation: <strong>${e.remediation || 'auto'}</strong></span>` : ''}
                            ${e.resolved ? html`<span>Resolved by: <strong>${e.resolved_by || '\u2014'}</strong></span>` : ''}
                          </div>
                          <div class="qc-detail-head">Detail Context</div>
                          <div class="qc-detail-json">${JSON.stringify(e.detail || {}, null, 2)}</div>
                        </div>
                      </td>
                    </tr>
                  ` : ''}
                `;
              })}
            </tbody>
          </table>
        </div>
      `}
    </div>
  `;
}

"""
new4 = qc_component + old4
count4 = content.count(old4)
print(f"Edit 4: found {count4} occurrences")
if count4 != 1:
    print("ERROR: unexpected count for edit 4")
    exit(1)
content = content.replace(old4, new4, 1)
print("Edit 4: OK - added QC React component")

with open('empire_command_spa.py', 'w') as f:
    f.write(content)

print("\nAll 4 edits applied successfully!")
