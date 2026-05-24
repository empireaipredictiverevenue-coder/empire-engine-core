"""
EMPIRE V49 · COMMAND DECK · AUDIT LOG
======================================
Owner-only view of the operator audit trail. Renders:

  - Stats strip (total today · most active operator · top action · last entry)
  - Operator + action + time-range filters
  - Audit row table with expandable details JSON

Data source: GET /api/v1/auth/audit?limit=500 (owner-only)
"""

from empire_layout import base_layout


def audit_view() -> str:
    extra_css = """
    .au-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    }
    @media (max-width: 1000px) { .au-stats { grid-template-columns: repeat(2, 1fr); } }

    .au-filters {
      display: flex; gap: 12px; flex-wrap: wrap;
      align-items: center;
      margin-bottom: 14px;
      padding-bottom: 14px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .au-filter {
      display: flex; flex-direction: column; gap: 4px;
    }
    .au-filter label {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-fog); letter-spacing: 0.18em;
      text-transform: uppercase;
    }
    .au-filter select, .au-filter input {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--empire-divider);
      color: var(--empire-silver);
      font-family: var(--font-mono); font-size: 11px;
      padding: 7px 10px;
      min-width: 160px;
      outline: none;
      transition: border-color 0.15s;
    }
    .au-filter select:focus, .au-filter input:focus { border-color: var(--signal-teal); }

    .au-table {
      width: 100%; border-collapse: collapse;
      font-family: var(--font-mono); font-size: 11px;
    }
    .au-table th {
      text-align: left; padding: 10px 12px;
      font-size: 9px; letter-spacing: 0.18em;
      text-transform: uppercase; color: var(--empire-fog);
      border-bottom: 1px solid var(--empire-divider);
      font-weight: 400; white-space: nowrap;
    }
    .au-table td {
      padding: 10px 12px;
      color: var(--empire-silver);
      border-bottom: 1px solid var(--empire-divider);
      vertical-align: top;
    }
    .au-table tr:hover td { background: rgba(255,255,255,0.02); }
    .au-table tr.has-details { cursor: pointer; }
    .au-table .when    { color: var(--empire-fog); font-size: 10px; white-space: nowrap; }
    .au-table .op-name { color: var(--empire-white); }
    .au-table .op-system { color: var(--empire-shadow); font-style: italic; }
    .au-table .action {
      font-weight: 600; color: var(--strike-cyan); letter-spacing: 0.04em;
    }
    .au-table .target { color: var(--empire-mist); font-size: 10px; }
    .au-table .ip     { color: var(--empire-shadow); font-size: 10px; }
    .au-table .expand-cell {
      color: var(--empire-shadow);
      text-align: center; width: 24px;
      transition: transform 0.15s, color 0.15s;
    }
    .au-table tr.expanded .expand-cell { color: var(--signal-teal); transform: rotate(90deg); }
    .au-details {
      background: rgba(0,0,0,0.3);
      padding: 14px 18px;
      font-family: var(--font-mono); font-size: 11px;
      color: var(--empire-mist);
      white-space: pre-wrap; word-break: break-word;
      border-left: 2px solid var(--signal-teal);
    }
    .au-table tr.details-row td { padding: 0; }

    .action-badge {
      display: inline-block;
      padding: 2px 7px;
      font-size: 9px; letter-spacing: 0.10em;
      text-transform: lowercase;
      border-radius: 2px;
      background: rgba(90,200,250,0.10);
      color: var(--strike-cyan);
    }
    .action-badge.login    { background: rgba(68,229,184,0.10); color: var(--signal-teal); }
    .action-badge.logout   { background: rgba(122,140,163,0.10); color: var(--empire-mist); }
    .action-badge.payout   { background: rgba(245,166,35,0.10); color: var(--status-amber); }
    .action-badge.danger   { background: rgba(244,63,94,0.10); color: var(--status-red); }

    .btn-refresh {
      background: transparent;
      border: 1px solid var(--empire-divider);
      color: var(--empire-mist);
      padding: 8px 14px;
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.18em; text-transform: uppercase;
      cursor: pointer; transition: all 0.15s;
    }
    .btn-refresh:hover { color: var(--signal-teal); border-color: var(--signal-teal); }

    .empty-state {
      padding: 40px 20px; text-align: center;
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-fog); letter-spacing: 0.18em;
      text-transform: uppercase;
    }
    """

    content = """
    <div class="e-page">
      <div class="e-page-header">
        <div>
          <div class="e-page-title">Audit Log</div>
          <div class="e-page-sub">Operator action history · accountability trail</div>
        </div>
        <button class="btn-refresh" id="au-refresh">Refresh</button>
      </div>

      <div class="au-stats">
        <div class="e-stat teal">
          <div class="e-stat-label">Entries · last 24h</div>
          <div class="e-stat-value teal" id="stat-today">—</div>
          <div class="e-stat-delta up" id="stat-today-delta">recorded</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Active operators · 24h</div>
          <div class="e-stat-value" id="stat-ops">—</div>
          <div class="e-stat-delta" id="stat-ops-delta">distinct actors</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">Top action · 24h</div>
          <div class="e-stat-value" style="font-size:18px;" id="stat-top">—</div>
          <div class="e-stat-delta" id="stat-top-delta">—</div>
        </div>
        <div class="e-stat amber">
          <div class="e-stat-label">Last entry</div>
          <div class="e-stat-value" style="font-size:18px;" id="stat-last">—</div>
          <div class="e-stat-delta warn" id="stat-last-delta">—</div>
        </div>
      </div>

      <div class="e-panel">
        <div class="au-filters">
          <div class="au-filter">
            <label>Operator</label>
            <select id="filter-op">
              <option value="">All operators</option>
            </select>
          </div>
          <div class="au-filter">
            <label>Action</label>
            <select id="filter-action">
              <option value="">All actions</option>
            </select>
          </div>
          <div class="au-filter">
            <label>Window</label>
            <select id="filter-window">
              <option value="3600">Last hour</option>
              <option value="86400" selected>Last 24h</option>
              <option value="604800">Last 7 days</option>
              <option value="0">All available</option>
            </select>
          </div>
          <div class="au-filter">
            <label>Search target</label>
            <input id="filter-search" type="text" placeholder="target id, action, ip..." />
          </div>
        </div>

        <div id="au-list">
          <div class="empty-state">Loading...</div>
        </div>
      </div>
    </div>
    """

    extra_js = """
    <script>
    (function() {
      const fmtTime = ts => ts ? new Date(ts).toLocaleString(undefined,
        {month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit', second:'2-digit'}) : '—';
      const fmtRel = ts => {
        if (!ts) return '—';
        const ms = Date.now() - new Date(ts).getTime();
        if (ms < 60_000) return Math.round(ms/1000) + 's ago';
        if (ms < 3_600_000) return Math.round(ms/60_000) + 'm ago';
        if (ms < 86_400_000) return Math.round(ms/3_600_000) + 'h ago';
        return Math.round(ms/86_400_000) + 'd ago';
      };
      const escape = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

      function actionClass(action) {
        const a = (action || '').toLowerCase();
        if (a === 'login')  return 'login';
        if (a === 'logout') return 'logout';
        if (a.includes('payout')) return 'payout';
        if (a.includes('cancel') || a.includes('reject') || a.includes('revok')) return 'danger';
        return '';
      }

      async function api(path, opts) {
        const r = await fetch(path, Object.assign({credentials: 'same-origin'}, opts || {}));
        if (!r.ok) throw new Error(path + ' → ' + r.status);
        return r.json();
      }

      let allRows = [];

      function applyFilters() {
        const opId  = document.getElementById('filter-op').value;
        const act   = document.getElementById('filter-action').value;
        const winS  = Number(document.getElementById('filter-window').value);
        const q     = document.getElementById('filter-search').value.trim().toLowerCase();
        const since = winS > 0 ? Date.now() - winS * 1000 : 0;
        return allRows.filter(r => {
          if (opId && r.operator_id !== opId) return false;
          if (act && r.action !== act) return false;
          if (since && new Date(r.created_at).getTime() < since) return false;
          if (q) {
            const hay = [
              r.operator_name, r.action, r.target_type, r.target_id, r.ip,
              JSON.stringify(r.details || {})
            ].join(' ').toLowerCase();
            if (!hay.includes(q)) return false;
          }
          return true;
        });
      }

      function renderStats() {
        const dayAgo = Date.now() - 86_400_000;
        const today = allRows.filter(r => new Date(r.created_at).getTime() > dayAgo);
        document.getElementById('stat-today').textContent = today.length;

        const ops = new Set(today.map(r => r.operator_id).filter(Boolean));
        document.getElementById('stat-ops').textContent = ops.size;

        const actionCounts = {};
        for (const r of today) {
          actionCounts[r.action] = (actionCounts[r.action] || 0) + 1;
        }
        const topAction = Object.entries(actionCounts).sort((a,b) => b[1]-a[1])[0];
        document.getElementById('stat-top').textContent = topAction ? topAction[0] : '—';
        document.getElementById('stat-top-delta').textContent = topAction ? topAction[1] + '×' : '';

        const last = allRows[0];
        document.getElementById('stat-last').textContent = last ? fmtRel(last.created_at) : '—';
        document.getElementById('stat-last-delta').textContent = last ? (last.operator_name || 'system') : '';
      }

      function rebuildFilterDropdowns() {
        const opSelect = document.getElementById('filter-op');
        const actSelect = document.getElementById('filter-action');
        const prevOp  = opSelect.value;
        const prevAct = actSelect.value;

        const opMap = {};
        const actSet = new Set();
        for (const r of allRows) {
          if (r.operator_id && r.operator_name) opMap[r.operator_id] = r.operator_name;
          if (r.action) actSet.add(r.action);
        }
        opSelect.innerHTML = '<option value="">All operators</option>' +
          Object.entries(opMap).sort((a,b) => a[1].localeCompare(b[1]))
            .map(([id, name]) => `<option value="${escape(id)}">${escape(name)}</option>`).join('');
        opSelect.value = prevOp;

        actSelect.innerHTML = '<option value="">All actions</option>' +
          Array.from(actSet).sort()
            .map(a => `<option value="${escape(a)}">${escape(a)}</option>`).join('');
        actSelect.value = prevAct;
      }

      function renderTable(rows) {
        const wrap = document.getElementById('au-list');
        if (!rows.length) {
          wrap.innerHTML = '<div class="empty-state">No entries match these filters</div>';
          return;
        }
        wrap.innerHTML = `
          <table class="au-table">
            <thead>
              <tr>
                <th>When</th>
                <th>Operator</th>
                <th>Action</th>
                <th>Target</th>
                <th>IP</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              ${rows.map((r, i) => {
                const hasDetails = r.details && Object.keys(r.details).length > 0;
                const opCell = r.operator_name
                  ? `<span class="op-name">${escape(r.operator_name)}</span>`
                  : `<span class="op-system">${escape(r.operator_id || 'system')}</span>`;
                const targetCell = r.target_type
                  ? `${escape(r.target_type)}${r.target_id ? ' · ' + escape(r.target_id).slice(0, 24) : ''}`
                  : '—';
                return `
                  <tr class="${hasDetails ? 'has-details' : ''}" data-idx="${i}" title="${escape(r.created_at)}">
                    <td class="when">${fmtTime(r.created_at)}</td>
                    <td>${opCell}</td>
                    <td><span class="action-badge ${actionClass(r.action)}">${escape(r.action)}</span></td>
                    <td class="target">${targetCell}</td>
                    <td class="ip">${escape(r.ip || '—')}</td>
                    <td class="expand-cell">${hasDetails ? '▸' : ''}</td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        `;
        // Wire expand handlers
        wrap.querySelectorAll('tr.has-details').forEach(tr => {
          tr.addEventListener('click', () => {
            const idx = Number(tr.dataset.idx);
            const row = rows[idx];
            const next = tr.nextElementSibling;
            if (next && next.classList.contains('details-row')) {
              next.remove();
              tr.classList.remove('expanded');
              return;
            }
            const detailsTr = document.createElement('tr');
            detailsTr.className = 'details-row';
            detailsTr.innerHTML = `<td colspan="6"><div class="au-details">${escape(JSON.stringify(row.details, null, 2))}</div></td>`;
            tr.classList.add('expanded');
            tr.after(detailsTr);
          });
        });
      }

      function applyAndRender() {
        renderStats();
        rebuildFilterDropdowns();
        renderTable(applyFilters());
      }

      let inflight = false;
      async function refresh() {
        if (inflight) return;
        inflight = true;
        try {
          const data = await api('/api/v1/auth/audit?limit=500');
          allRows = data.audit || [];
          applyAndRender();
        } catch (e) {
          console.error('[audit] refresh failed', e);
          document.getElementById('au-list').innerHTML =
            `<div class="empty-state">Failed to load · ${escape(e.message)}</div>`;
        } finally {
          inflight = false;
        }
      }

      // Wire filter changes
      ['filter-op', 'filter-action', 'filter-window'].forEach(id =>
        document.getElementById(id).addEventListener('change', () =>
          renderTable(applyFilters())));
      document.getElementById('filter-search').addEventListener('input', () =>
        renderTable(applyFilters()));

      document.getElementById('au-refresh').addEventListener('click', refresh);

      // 30s auto-refresh — audit log is owner-eyeballed, low write rate
      setInterval(refresh, 30_000);

      refresh();
    })();
    </script>
    """

    return base_layout(
        title="Audit Log",
        subtitle="Operator Console",
        content=content,
        active_module="audit",
        extra_css=extra_css,
        extra_js=extra_js,
    )
