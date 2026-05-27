"""
EMPIRE V49 · COMMAND DECK · OPERATORS
======================================
Owner-only operator roster management. Renders:

  - Stats strip (total · active · by role)
  - Invite form (email + name + role → fires magic link)
  - Operator table with inline role change + activate/deactivate

Data: GET /api/v1/auth/me, /api/v1/auth/operators
Mutations: POST /api/v1/auth/invite, /api/v1/auth/operators/update
"""

from empire_layout import base_layout


def operators_view() -> str:
    extra_css = """
    .op-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    }
    @media (max-width: 1000px) { .op-stats { grid-template-columns: repeat(2, 1fr); } }

    .invite-form {
      display: grid;
      grid-template-columns: 1fr 1fr 140px 140px;
      gap: 10px;
      align-items: end;
      padding: 14px 0;
      border-bottom: 1px solid var(--empire-divider);
      margin-bottom: 14px;
    }
    @media (max-width: 800px) { .invite-form { grid-template-columns: 1fr 1fr; } }

    .field { display: flex; flex-direction: column; gap: 4px; }
    .field label {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-fog); letter-spacing: 0.18em;
      text-transform: uppercase;
    }
    .field input, .field select {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--empire-divider);
      color: var(--empire-silver);
      font-family: var(--font-mono); font-size: 12px;
      padding: 9px 11px;
      outline: none;
      transition: border-color 0.15s;
    }
    .field input:focus, .field select:focus { border-color: var(--signal-teal); }

    .btn-primary {
      background: var(--signal-teal); color: #000;
      border: none; padding: 10px 22px;
      font-family: var(--font-ui); font-weight: 700;
      font-size: 11px; letter-spacing: 0.06em;
      cursor: pointer; transition: all 0.15s;
      text-transform: uppercase;
    }
    .btn-primary:hover { background: transparent; color: var(--signal-teal); outline: 1px solid var(--signal-teal); }
    .btn-primary:disabled { opacity: 0.4; cursor: wait; }

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

    .op-table {
      width: 100%; border-collapse: collapse;
    }
    .op-table th {
      text-align: left; padding: 12px 14px;
      font-family: var(--font-mono); font-size: 9px;
      letter-spacing: 0.18em; text-transform: uppercase;
      color: var(--empire-fog); font-weight: 400;
      border-bottom: 1px solid var(--empire-divider);
    }
    .op-table td {
      padding: 14px;
      color: var(--empire-silver);
      border-bottom: 1px solid var(--empire-divider);
      vertical-align: middle;
    }
    .op-table tr.inactive td { opacity: 0.5; }
    .op-table tr:hover td { background: rgba(255,255,255,0.02); }
    .op-name { color: var(--empire-white); font-size: 13px; font-weight: 500; }
    .op-name .self-badge {
      display: inline-block;
      margin-left: 8px;
      padding: 2px 7px;
      font-family: var(--font-mono); font-size: 9px;
      letter-spacing: 0.14em; text-transform: uppercase;
      background: var(--signal-teal-soft); color: var(--signal-teal);
      border-radius: 2px;
    }
    .op-email { color: var(--empire-mist); font-family: var(--font-mono); font-size: 11px; }
    .op-when  { color: var(--empire-fog); font-family: var(--font-mono); font-size: 10px; }

    .role-select {
      background: rgba(0,0,0,0.3);
      border: 1px solid var(--empire-divider);
      color: var(--empire-silver);
      font-family: var(--font-mono); font-size: 11px;
      padding: 6px 8px;
      outline: none;
    }
    .role-select:disabled { opacity: 0.5; cursor: not-allowed; }

    .role-badge {
      display: inline-block;
      padding: 3px 9px;
      font-family: var(--font-mono); font-size: 9px;
      letter-spacing: 0.14em; text-transform: uppercase;
      border-radius: 2px;
    }
    .role-badge.owner    { background: rgba(68,229,184,0.10); color: var(--signal-teal); }
    .role-badge.operator { background: rgba(90,200,250,0.10); color: var(--strike-cyan); }
    .role-badge.viewer   { background: rgba(122,140,163,0.10); color: var(--empire-mist); }

    .status-pill {
      display: inline-block;
      padding: 3px 9px;
      font-family: var(--font-mono); font-size: 9px;
      letter-spacing: 0.14em; text-transform: uppercase;
      border-radius: 2px;
    }
    .status-pill.active   { background: rgba(68,229,184,0.10); color: var(--signal-teal); }
    .status-pill.inactive { background: rgba(122,140,163,0.10); color: var(--empire-mist); }

    .btn-toggle {
      background: transparent;
      border: 1px solid var(--empire-divider);
      color: var(--empire-mist);
      padding: 6px 12px;
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.14em; text-transform: uppercase;
      cursor: pointer; transition: all 0.15s;
    }
    .btn-toggle.activate:hover   { color: var(--signal-teal); border-color: var(--signal-teal); }
    .btn-toggle.deactivate:hover { color: var(--status-red); border-color: var(--status-red); }
    .btn-toggle:disabled { opacity: 0.3; cursor: not-allowed; }

    .flash {
      padding: 10px 14px;
      margin: 0 0 14px;
      font-family: var(--font-mono); font-size: 11px;
      letter-spacing: 0.04em;
      display: none;
    }
    .flash.show { display: block; }
    .flash.success { color: var(--signal-teal); background: rgba(68,229,184,0.06); border: 1px solid rgba(68,229,184,0.25); }
    .flash.error   { color: var(--status-red);  background: rgba(244,63,94,0.06); border: 1px solid rgba(244,63,94,0.25); }

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
          <div class="e-page-title">Operators</div>
          <div class="e-page-sub">Roster · roles · invites</div>
        </div>
        <button class="btn-refresh" id="op-refresh">Refresh</button>
      </div>

      <div class="op-stats">
        <div class="e-stat teal">
          <div class="e-stat-label">Total</div>
          <div class="e-stat-value teal" id="stat-total">—</div>
          <div class="e-stat-delta up" id="stat-total-delta">all operators</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Active</div>
          <div class="e-stat-value" id="stat-active">—</div>
          <div class="e-stat-delta" id="stat-active-delta">can sign in</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">Owners</div>
          <div class="e-stat-value" style="color:var(--signal-teal);" id="stat-owners">—</div>
          <div class="e-stat-delta">full access</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">Last login · 7d</div>
          <div class="e-stat-value" id="stat-recent">—</div>
          <div class="e-stat-delta">distinct operators</div>
        </div>
      </div>

      <div class="e-panel">
        <div class="e-section-label">Invite new operator</div>
        <div class="invite-form">
          <div class="field">
            <label>Email</label>
            <input type="email" id="inv-email" placeholder="name@empire-ai.co.uk" />
          </div>
          <div class="field">
            <label>Name</label>
            <input type="text" id="inv-name" placeholder="Display name" />
          </div>
          <div class="field">
            <label>Role</label>
            <select id="inv-role">
              <option value="operator">operator</option>
              <option value="viewer">viewer</option>
              <option value="owner">owner</option>
            </select>
          </div>
          <button class="btn-primary" id="inv-submit">Send invite</button>
        </div>
        <div class="flash" id="inv-flash"></div>
      </div>

      <div class="e-panel" style="margin-top:14px;">
        <div class="e-section-label" style="margin-bottom:14px;">Roster</div>
        <div id="op-list">
          <div class="empty-state">Loading...</div>
        </div>
      </div>
    </div>
    """

    extra_js = """
    <script>
    (function() {
      const fmtTime = ts => ts ? new Date(ts).toLocaleString(undefined,
        {month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : 'never';
      const fmtRel = ts => {
        if (!ts) return 'never';
        const ms = Date.now() - new Date(ts).getTime();
        if (ms < 60_000) return 'just now';
        if (ms < 3_600_000) return Math.round(ms/60_000) + 'm ago';
        if (ms < 86_400_000) return Math.round(ms/3_600_000) + 'h ago';
        return Math.round(ms/86_400_000) + 'd ago';
      };
      const escape = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

      async function api(path, opts) {
        const r = await fetch(path, Object.assign({credentials: 'same-origin'}, opts || {}));
        const data = await r.json().catch(() => ({}));
        if (!r.ok) {
          const err = new Error(data.detail || data.error || (path + ' → ' + r.status));
          err.status = r.status;
          throw err;
        }
        return data;
      }

      let me = null;
      let operators = [];

      function flash(el, msg, ok) {
        el.textContent = msg;
        el.className = 'flash show ' + (ok ? 'success' : 'error');
        if (ok) setTimeout(() => el.classList.remove('show'), 4000);
      }

      function renderStats() {
        document.getElementById('stat-total').textContent  = operators.length;
        document.getElementById('stat-active').textContent = operators.filter(o => o.active).length;
        document.getElementById('stat-owners').textContent = operators.filter(o => o.role === 'owner').length;
        const weekAgo = Date.now() - 7 * 86_400_000;
        const recent = operators.filter(o => o.last_login && new Date(o.last_login).getTime() > weekAgo).length;
        document.getElementById('stat-recent').textContent = recent;
      }

      function renderTable() {
        const wrap = document.getElementById('op-list');
        if (!operators.length) {
          wrap.innerHTML = '<div class="empty-state">No operators</div>';
          return;
        }
        const sorted = [...operators].sort((a, b) => {
          if (a.active !== b.active) return a.active ? -1 : 1;
          return (a.created_at || '').localeCompare(b.created_at || '');
        });
        wrap.innerHTML = `
          <table class="op-table">
            <thead>
              <tr><th>Operator</th><th>Role</th><th>Status</th><th>Last login</th><th>Joined</th><th></th></tr>
            </thead>
            <tbody>
              ${sorted.map(o => {
                const isSelf = me && o.id === me.id;
                return `
                  <tr class="${o.active ? '' : 'inactive'}" data-id="${escape(o.id)}">
                    <td>
                      <div class="op-name">${escape(o.name)}${isSelf ? '<span class="self-badge">you</span>' : ''}</div>
                      <div class="op-email">${escape(o.email)}</div>
                    </td>
                    <td>
                      <select class="role-select" data-id="${escape(o.id)}" ${isSelf ? 'disabled' : ''}>
                        <option value="owner"    ${o.role === 'owner'    ? 'selected' : ''}>owner</option>
                        <option value="operator" ${o.role === 'operator' ? 'selected' : ''}>operator</option>
                        <option value="viewer"   ${o.role === 'viewer'   ? 'selected' : ''}>viewer</option>
                      </select>
                    </td>
                    <td>
                      <span class="status-pill ${o.active ? 'active' : 'inactive'}">${o.active ? 'active' : 'inactive'}</span>
                    </td>
                    <td class="op-when" title="${escape(o.last_login || '')}">${fmtRel(o.last_login)}</td>
                    <td class="op-when">${fmtTime(o.created_at)}</td>
                    <td>
                      <button class="btn-toggle ${o.active ? 'deactivate' : 'activate'}"
                              data-id="${escape(o.id)}"
                              data-active="${o.active ? '1' : '0'}"
                              ${isSelf ? 'disabled title="Cannot deactivate yourself"' : ''}>
                        ${o.active ? 'Deactivate' : 'Activate'}
                      </button>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        `;
      }

      let inflight = false;
      async function refresh() {
        if (inflight) return;
        inflight = true;
        try {
          const [meData, opsData] = await Promise.all([
            api('/api/v1/auth/me'),
            api('/api/v1/auth/operators'),
          ]);
          me = meData;
          operators = opsData.operators || [];
          renderStats();
          renderTable();
        } catch (e) {
          console.error('[operators] refresh failed', e);
          document.getElementById('op-list').innerHTML =
            `<div class="empty-state">Failed to load · ${escape(e.message)}</div>`;
        } finally {
          inflight = false;
        }
      }

      // Invite handler
      document.getElementById('inv-submit').addEventListener('click', async () => {
        const email = document.getElementById('inv-email').value.trim();
        const name  = document.getElementById('inv-name').value.trim();
        const role  = document.getElementById('inv-role').value;
        const flashEl = document.getElementById('inv-flash');
        const btn = document.getElementById('inv-submit');

        if (!email || !email.includes('@')) return flash(flashEl, '✗ Valid email required', false);
        if (!name) return flash(flashEl, '✗ Name required', false);

        btn.disabled = true; btn.textContent = 'Sending...';
        try {
          const r = await api('/api/v1/auth/invite', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({email, name, role}),
          });
          if (r.ok) {
            flash(flashEl, `✓ Invited ${name} as ${role} · magic link sent to ${email}`, true);
            document.getElementById('inv-email').value = '';
            document.getElementById('inv-name').value = '';
            document.getElementById('inv-role').value = 'operator';
            setTimeout(refresh, 400);
          } else {
            flash(flashEl, '✗ ' + (r.error || 'Invite failed'), false);
          }
        } catch (e) {
          flash(flashEl, '✗ ' + e.message, false);
        } finally {
          btn.disabled = false; btn.textContent = 'Send invite';
        }
      });

      // Role change + activate/deactivate delegation
      document.addEventListener('change', async (ev) => {
        if (!ev.target.classList.contains('role-select')) return;
        const id = ev.target.dataset.id;
        const newRole = ev.target.value;
        const op = operators.find(o => o.id === id);
        if (!op || op.role === newRole) return;
        if (!confirm(`Change ${op.name}'s role from "${op.role}" to "${newRole}"?`)) {
          ev.target.value = op.role;
          return;
        }
        try {
          await api('/api/v1/auth/operators/update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({operator_id: id, role: newRole}),
          });
          setTimeout(refresh, 300);
        } catch (e) {
          alert('Role change failed: ' + e.message);
          ev.target.value = op.role;
        }
      });

      document.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('.btn-toggle');
        if (!btn || btn.disabled) return;
        const id = btn.dataset.id;
        const wasActive = btn.dataset.active === '1';
        const op = operators.find(o => o.id === id);
        const verb = wasActive ? 'Deactivate' : 'Reactivate';
        if (!confirm(`${verb} ${op ? op.name : 'this operator'}?`)) return;
        btn.disabled = true; btn.textContent = wasActive ? 'Deactivating...' : 'Activating...';
        try {
          await api('/api/v1/auth/operators/update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({operator_id: id, active: !wasActive}),
          });
          setTimeout(refresh, 300);
        } catch (e) {
          alert('Update failed: ' + e.message);
          btn.disabled = false;
          btn.textContent = wasActive ? 'Deactivate' : 'Activate';
        }
      });

      document.getElementById('op-refresh').addEventListener('click', refresh);

      refresh();
    })();
    </script>
    """

    return base_layout(
        title="Operators",
        subtitle="Operator Console",
        content=content,
        active_module="operators",
        extra_css=extra_css,
        extra_js=extra_js,
    )
