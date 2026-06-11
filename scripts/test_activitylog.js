const { createElement: h, useState, useEffect } = React;
const { createRoot } = ReactDOM;
const html = htm.bind(h);
const apiFetch = async () => {};
const statusActions = [];
function ActivityLog() {  const [entries, setEntries] = useState(null);
  const [err, setErr] = useState(null);
  const [searchQuery, setSearchQuery] = useState('');

  const reload = useCallback(async () => {
    try {
      const r = await apiFetch('/api/v1/notes/activity').then(x => x.json());
      setEntries(r.entries || []);
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

  if (err) return html`<div class=\"stub\"><div class=\"stub-title\">Could not load Activity Log</div><div class=\"stub-body\">${err}</div></div>`;

  if (!entries) return html`<div class=\"stub\"><div class=\"stub-body\">Loading activity log…</div></div>`;

  // Filter by text or operator name
  let filteredEntries = entries;
  if (searchQuery.trim()) {
    const q = searchQuery.trim().toLowerCase();
    filteredEntries = entries.filter(e =>
      (e.text || '').toLowerCase().includes(q) ||
      (e.operator || '').toLowerCase().includes(q)
    );
  }

  // Group by date
  const groups = {};
  for (const e of filteredEntries) {
    const date = (e.timestamp || '').slice(0, 10);
    if (!groups[date]) groups[date] = [];
    groups[date].push(e);
  }
  const dates = Object.keys(groups).sort().reverse();

  const goToLead = (leadId) => {
    window.location.hash = '#/leads?focus=' + encodeURIComponent(leadId);
  };

  return html`
    <div>
      <div class=\"section-h\">
        <div>
          <div class=\"section-title\">Activity <em>Log</em></div>
          <div class=\"section-sub\">Global notes feed · all operator activity</div>
        </div>
        <div class=\"section-sub\">${entries.length} notes · auto-refresh 15s</div>
      </div>

      <input class=\"fld-in mono\" style=${{flex: '1', maxWidth: '320px', padding: '6px 10px', fontSize: '11px', marginBottom: '14px'}} value=${searchQuery} onChange=${e => setSearchQuery(e.target.value)} placeholder=\"filter by text or operator…\" />\n
      ${filteredEntries.length > 0 ? html`<div class="chart-panel">
        <div class="chart-panel-h">
          <div class="chart-panel-title">Daily Activity</div>
          <div class="chart-panel-tag">${filteredEntries.length} notes · ${dates.length} days</div>
        </div>
        ${(() => {
          const dayCounts = {};
          const now = new Date();
          for (let i = 13; i >= 0; i--) {
            const d = new Date(now); d.setDate(d.getDate() - i);
            const key = d.toISOString().slice(0, 10);
            dayCounts[key] = 0;
          }
          for (const e of filteredEntries) {
            if (e.timestamp) {
              const d = e.timestamp.slice(0, 10);
              if (dayCounts[d] !== undefined) dayCounts[d]++;
            }
          }
          const chartData = Object.entries(dayCounts).map(([date, count]) => ({
            label: date.slice(5, 10),
            value: count
          }));
          return html`<${MiniBarChart} data=${chartData} color="var(--strike-cyan)" height=${60} />`;
        })()}
      </div>` : ''

      ${filteredEntries.length > 0 ? html`<div class="chart-panel">
        <div class="chart-panel-h">
          <div class="chart-panel-title">Operator Activity</div>
          <div class="chart-panel-tag">${[...new Set(filteredEntries.map(e => e.operator))].filter(Boolean).length} operators</div>
        </div>
        ${(() => {
          const opCounts = {};
          for (const e of filteredEntries) {
            const op = e.operator || 'unknown';
            opCounts[op] = (opCounts[op] || 0) + 1;
          }
          const colors = ['var(--strike-cyan)', 'var(--signal-teal)', 'var(--status-amber)', 'var(--empire-mist)', 'var(--status-red)'];
          const opData = Object.entries(opCounts)
            .sort((a, b) => b[1] - a[1])
            .map(([label, value], i) => ({label, value, color: colors[i % colors.length]}));
          return html`<${DonutChart} data=${opData} size=${108} strokeWidth=${22} />`;
        })()}
      </div>` : ''}
}

      <div class=\"act-meta\">Showing ${filteredEntries.length} note${entries.length === 1 ? '' : 's'} across ${dates.length} day${dates.length === 1 ? '' : 's'}</div>

      ${entries.length === 0
        ? html`<div class=\"act-empty\">No notes activity yet. Notes appear when operators add them from the Leads tab.</div>`
        : html`<div class=\"act-feed\">
            ${dates.map(date => html`
              <div class=\"act-day\" key=${date}>${date}</div>
              ${groups[date].map(e => html`
                <div class=\"act-entry\" key=${e.timestamp + e.lead_id}>
                  <span class=\"act-entry-ts\">${(e.timestamp || '')
.slice(11, 19)}</span>
                  <span class=\"act-entry-body\">
                    <span class=\"act-entry-lead\" onClick=${() => goToLead(e.lead_id)} title=\"Go to lead\">${e.lead_name || '—'}</span>
                    <span class=\"act-entry-text\">${e.text}</span>
                  </span>
                  <span class=\"act-entry-operator\">${e.operator || '—'}</span>
                </div>
              `)}
            `)}
          </div>`}
    </div>
  `;
}
