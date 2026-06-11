const { createElement: h, useState, useEffect, useCallback } = React;
const { createRoot } = ReactDOM;
const html = htm.bind(h);
const apiFetch = async () => ({});
const loadNotes = async () => [];
const deleteNote = async () => {};
const noteInputs = {};
const setNoteInputs = () => {};
const busy = null;
const saveNote = () => {};
const renderNotes = () => "";
const statusActions = [];
function Leads() {
  const [leads, setLeads] = useState(null);
  const [err, setErr] = useState(null);
  const [busy, setBusy] = useState(null);
  const [filterSource, setFilterSource] = useState('all');
  const [filterStatus, setFilterStatus] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [noteInputs, setNoteInputs] = useState({});

  const deleteNote = async (leadId, timestamp) => {
    if (!confirm('Delete this note?')) return;
    setBusy(leadId + ':del:' + timestamp);
    try {
      await apiFetch('/api/v1/inbound/leads/delete-note', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_id: leadId, timestamp }),
      });
      await reload();
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  const renderNotes = (raw, leadId) => {
    if (!raw) return '';
    let entries = [];
    if (typeof raw === 'string') {
      try { const p = JSON.parse(raw); if (Array.isArray(p)) entries = p; else entries = [{text: raw}]; }
      catch { entries = [{text: raw}]; }
    } else if (Array.isArray(raw)) {
      entries = raw;
    }
    if (entries.length === 0) return '';
    return html`<div class="ld-notes-history">${entries.map(e => html`
      <div class="ld-note-entry" key=${e.timestamp || Math.random()}>
        <span class="ld-note-meta">
          ${e.timestamp ? e.timestamp.slice(11, 19) + ' · ' : ''}${e.operator ? html`<span class="ld-note-op">${e.operator}</span>` : ''}
          <button class="ld-note-del" disabled=${busy === leadId + ':del:' + e.timestamp}
            onClick=${() => deleteNote(leadId, e.timestamp)} title="delete note">
            ${busy === leadId + ':del:' + e.timestamp ? '…' : '✕'}
          </button>
        </span>
        <div class="ld-note-text">${e.text}</div>
      </div>
    `)}</div>`;
  };

  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/v1/inbound/leads?limit=200').then(x => x.json());
      setLeads(r.leads || []);
      setErr(null);
    } catch (e) {
      if (e.message !== 'Unauthorized') setErr(e.message);
    }
  }, []);

  useEffect(() => {
    reload();
    const t = setInterval(reload, 15000);
    return () => clearInterval(t);
  }, [reload]);

  const doUpdate = async (leadId, status) => {
    setBusy(leadId + ':' + status);
    try {
      await apiFetch('/api/v1/inbound/leads/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_id: leadId, status }),
      });
      await reload();
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  const saveNote = async (leadId) => {
    const note = (noteInputs[leadId] || '').trim();
    if (!note) return;
    setBusy(leadId + ':note');
    try {
      await apiFetch('/api/v1/inbound/leads/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ lead_id: leadId, notes: note }),
      });
      setNoteInputs(n => { const c = {...n}; delete c[leadId]; return c; });
      await reload();
    } catch (e) { alert('Failed: ' + e.message); }
    setBusy(null);
  };

  if (err) return html`<div class="stub"><div class="stub-title">Could not load Leads</div><div class="stub-body">${err}</div></div>`;

  const allLeads = leads || [];

  // Sources for filter
  const sources = [...new Set(allLeads.map(l => l.source || 'unknown'))].sort();

  // Filter
  let filtered = allLeads;
  if (filterSource !== 'all') filtered = filtered.filter(l => (l.source || 'unknown') === filterSource);
  if (filterStatus !== 'all') filtered = filtered.filter(l => (l.status || 'new') === filterStatus);
  if (searchQuery.trim()) {
    const q = searchQuery.trim().toLowerCase();
    filtered = filtered.filter(l =>
      (l.name || '').toLowerCase().includes(q) ||
      (l.phone || '').toLowerCase().includes(q) ||
      (l.email || '').toLowerCase().includes(q)
    );
  }

  // Stats
  const total = allLeads.length;
  const newCount = allLeads.filter(l => !l.status || l.status === 'new' || l.status === 'pending').length;
  const contacted = allLeads.filter(l => l.status === 'contacted' || l.status === 'qualified').length;
  const closed = allLeads.filter(l => l.status === 'closed' || l.status === 'rejected').length;

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Leads</div>
          <div class="section-sub">Inbound lead pipeline · intake</div>
        </div>
        <div class="section-sub">${total} total · auto-refresh 15s</div>
      </div>

      <div class="ld-stats">
        <div class="ld-stat">
          <div class=${'ld-stat-val ' + (total > 0 ? 'teal' : 'dim')}>${total}</div>
          <div class="ld-stat-lbl">Total Leads</div>
        </div>
        <div class="ld-stat">
          <div class=${'ld-stat-val ' + (newCount > 0 ? 'teal' : 'dim')}>${newCount}</div>
          <div class="ld-stat-lbl">New / Pending</div>
        </div>
        <div class="ld-stat">
          <div class=${'ld-stat-val ' + (contacted > 0 ? 'teal' : 'dim')}>${contacted}</div>
          <div class="ld-stat-lbl">Contacted / Qualified</div>
        </div>
        <div class="ld-stat">
          <div class="ld-stat-val dim">${closed}</div>
          <div class="ld-stat-lbl">Closed / Rejected</div>
        </div>
      </div>

      <div class="ld-filter">
        <span class="ld-filter-tag">Source:</span>
        <button class=${'ld-filter-btn ' + (filterSource === 'all' ? 'active' : '')} onClick=${() => setFilterSource('all')}>All</button>
        ${sources.map(s => html`
          <button class=${'ld-filter-btn ' + (filterSource === s ? 'active' : '')} onClick=${() => setFilterSource(s)} key=${s}>${s}</button>
        `)}
        <span class="ld-filter-tag" style=${{marginLeft: 'auto', opacity: '0.4'}}>|</span>
        <span class="ld-filter-tag">Status:</span>
        <button class=${'ld-filter-btn ' + (filterStatus === 'all' ? 'active' : '')} onClick=${() => setFilterStatus('all')}>All</button>
        <button class=${'ld-filter-btn ' + (filterStatus === 'new' ? 'active' : '')} onClick=${() => setFilterStatus('new')}>New</button>
        <button class=${'ld-filter-btn ' + (filterStatus === 'contacted' ? 'active' : '')} onClick=${() => setFilterStatus('contacted')}>Contacted</button>
        <button class=${'ld-filter-btn ' + (filterStatus === 'qualified' ? 'active' : '')} onClick=${() => setFilterStatus('qualified')}>Qualified</button>
        <button class=${'ld-filter-btn ' + (filterStatus === 'closed' ? 'active' : '')} onClick=${() => setFilterStatus('closed')}>Closed</button>
        <input class="fld-in mono" style=${{flex: '1', minWidth: '180px', padding: '6px 10px', fontSize: '11px'}} value=${searchQuery} onChange=${e => setSearchQuery(e.target.value)} placeholder="filter by name, phone, or email…" />
        ${filtered.length !== allLeads.length ? html`<span class="ld-filter-tag">Showing ${filtered.length}</span>` : ''}
      </div>

      ${allLeads.length > 0 ? html`<div class="chart-panel">
        <div class="chart-panel-h">
          <div class="chart-panel-title">Daily Lead Volume</div>
          <div class="chart-panel-tag">${allLeads.length} total</div>
        </div>
        ${(() => {
          // Group by date (last 14 days)
          const dayCounts = {};
          const now = new Date();
          for (let i = 13; i >= 0; i--) {
            const d = new Date(now); d.setDate(d.getDate() - i);
            const key = d.toISOString().slice(0, 10);
            dayCounts[key] = 0;
          }
          for (const l of allLeads) {
            if (l.created_at) {
              const d = l.created_at.slice(0, 10);
              if (dayCounts[d] !== undefined) dayCounts[d]++;
            }
          }
          const chartData = Object.entries(dayCounts).map(([date, count]) => ({
            label: date.slice(5, 10),
            value: count
          }));
          return html`<${MiniBarChart} data=${chartData} color="var(--signal-teal)" height=${60} />`;
        })()}
      </div>` : ''}

      ${newCount + contacted + closed > 0 ? html`<div class="chart-panel">
        <div class="chart-panel-h">
          <div class="chart-panel-title">Status Distribution</div>
          <div class="chart-panel-tag">${newCount} new · ${contacted} contacted · ${closed} closed</div>
        </div>
        <${DonutChart} data=${[
          {label: 'New / Pending', value: newCount, color: 'var(--signal-teal)'},
          {label: 'Contacted / Qualified', value: contacted, color: 'var(--strike-cyan)'},
