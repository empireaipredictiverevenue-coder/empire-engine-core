"""
EMPIRE V49 · COMMAND DECK · CONTRACTORS
========================================
Owner-only section view for the contractor onboarding pipeline. Renders:

  - Stats strip (pending review · pending email · approved · rejected)
  - Status filter tabs
  - Application cards with approve / reject actions

Live updates via /ws/live subscriptions to:
  - contractor_application_received
  - contractor_verified
  - contractor_approved
  - contractor_rejected
"""

from empire_layout import base_layout


def contractors_view() -> str:
    extra_css = """
    .ct-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    }
    @media (max-width: 1000px) { .ct-stats { grid-template-columns: repeat(2, 1fr); } }

    .ct-tabs {
      display: flex; gap: 4px;
      margin-bottom: 14px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .ct-tab {
      background: transparent; border: none;
      color: var(--empire-mist);
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.18em; text-transform: uppercase;
      padding: 12px 18px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: all 0.15s;
    }
    .ct-tab:hover { color: var(--empire-silver); }
    .ct-tab.active {
      color: var(--signal-teal);
      border-bottom-color: var(--signal-teal);
    }
    .ct-tab .count {
      color: var(--empire-fog);
      margin-left: 6px;
      font-weight: 600;
    }
    .ct-tab.active .count { color: var(--signal-teal); }

    .app-card {
      background: var(--empire-elevated);
      border: 1px solid var(--empire-divider);
      border-left: 2px solid var(--empire-shadow);
      border-radius: var(--radius-sm);
      padding: 16px 18px;
      margin-bottom: 10px;
      animation: empire-fade-up 0.3s var(--ease-out-empire) both;
    }
    .app-card.status-pending_review { border-left-color: var(--status-amber); }
    .app-card.status-pending_email  { border-left-color: var(--empire-shadow); opacity: 0.85; }
    .app-card.status-approved       { border-left-color: var(--signal-teal); }
    .app-card.status-rejected       { border-left-color: var(--status-red); opacity: 0.6; }

    .app-head {
      display: flex; justify-content: space-between; gap: 14px;
      align-items: baseline;
      margin-bottom: 10px;
    }
    .app-name {
      font-family: var(--font-ui); font-weight: 500;
      font-size: 15px; color: var(--empire-white);
    }
    .app-meta {
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-fog); letter-spacing: 0.14em;
      text-transform: uppercase;
      margin-top: 2px;
    }
    .app-when {
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-fog);
      flex-shrink: 0;
    }

    .app-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 6px 24px;
      font-size: 12px;
      margin: 12px 0;
    }
    @media (max-width: 700px) { .app-grid { grid-template-columns: 1fr; } }
    .app-row {
      display: flex; gap: 10px;
      color: var(--empire-silver);
    }
    .app-row .k {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-fog); letter-spacing: 0.18em;
      text-transform: uppercase;
      flex-shrink: 0; width: 84px;
      padding-top: 2px;
    }
    .app-row .v { color: var(--empire-silver); flex: 1; word-break: break-word; }
    .app-row .v.empty { color: var(--empire-shadow); font-style: italic; }
    .app-tags {
      display: flex; flex-wrap: wrap; gap: 5px;
    }
    .app-tag {
      background: rgba(90,200,250,0.08);
      color: var(--strike-cyan);
      font-family: var(--font-mono); font-size: 9px;
      padding: 2px 7px;
      border-radius: 2px;
      letter-spacing: 0.08em;
    }
    .app-notes {
      background: rgba(0,0,0,0.25);
      padding: 10px 12px;
      border-left: 2px solid var(--empire-divider);
      font-size: 11px;
      color: var(--empire-mist);
      line-height: 1.6;
      margin-top: 8px;
    }
    .app-actions {
      display: flex; gap: 8px;
      padding-top: 10px;
      border-top: 1px solid var(--empire-divider);
    }
    .btn-approve {
      background: var(--signal-teal); color: #000;
      border: none; padding: 9px 22px;
      font-family: var(--font-ui); font-weight: 700;
      font-size: 11px; letter-spacing: 0.04em;
      cursor: pointer; transition: all 0.15s;
    }
    .btn-approve:hover { background: transparent; color: var(--signal-teal); outline: 1px solid var(--signal-teal); }
    .btn-approve:disabled { opacity: 0.4; cursor: wait; }
    .btn-reject {
      background: transparent; color: var(--status-red);
      border: 1px solid rgba(244,63,94,0.4);
      padding: 9px 22px;
      font-family: var(--font-ui); font-weight: 600;
      font-size: 11px; letter-spacing: 0.04em;
      cursor: pointer; transition: all 0.15s;
    }
    .btn-reject:hover { background: rgba(244,63,94,0.12); border-color: var(--status-red); }

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
          <div class="e-page-title">Contractors</div>
          <div class="e-page-sub">Applications · approvals · network growth</div>
        </div>
        <button class="btn-refresh" id="ct-refresh">Refresh</button>
      </div>

      <div class="ct-stats">
        <div class="e-stat amber">
          <div class="e-stat-label">Pending review</div>
          <div class="e-stat-value" id="stat-pr">—</div>
          <div class="e-stat-delta warn">awaiting decision</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">Pending email</div>
          <div class="e-stat-value" id="stat-pe">—</div>
          <div class="e-stat-delta">unverified</div>
        </div>
        <div class="e-stat teal">
          <div class="e-stat-label">Approved · lifetime</div>
          <div class="e-stat-value teal" id="stat-ap">—</div>
          <div class="e-stat-delta up">in dispatch pool</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">Rejected · lifetime</div>
          <div class="e-stat-value" id="stat-rj">—</div>
          <div class="e-stat-delta">declined</div>
        </div>
      </div>

      <div class="e-panel">
        <div class="ct-tabs">
          <button class="ct-tab active" data-status="pending_review">Pending review <span class="count" id="tc-pr">—</span></button>
          <button class="ct-tab" data-status="pending_email">Pending email <span class="count" id="tc-pe">—</span></button>
          <button class="ct-tab" data-status="approved">Approved <span class="count" id="tc-ap">—</span></button>
          <button class="ct-tab" data-status="rejected">Rejected <span class="count" id="tc-rj">—</span></button>
          <button class="ct-tab" data-status="all">All <span class="count" id="tc-al">—</span></button>
        </div>
        <div id="app-list">
          <div class="empty-state">Loading...</div>
        </div>
      </div>
    </div>
    """

    extra_js = """
    <script>
    (function() {
      const fmtTime = ts => ts ? new Date(ts).toLocaleString(undefined,
        {month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : '—';
      const escape  = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const empty   = v => v == null || v === '' ? '<span class="v empty">—</span>' : `<span class="v">${escape(v)}</span>`;

      async function api(path, opts) {
        const r = await fetch(path, Object.assign({credentials: 'same-origin'}, opts || {}));
        if (!r.ok) throw new Error(path + ' → ' + r.status);
        return r.json();
      }

      function renderCard(a) {
        const specs = (a.specialties || []).map(s =>
          `<span class="app-tag">${escape(s)}</span>`).join('');
        const license = a.license_no
          ? `${escape(a.license_no)}${a.license_state ? ' · ' + escape(a.license_state) : ''}`
          : '';
        const actions = a.status === 'pending_review'
          ? `<div class="app-actions">
               <button class="btn-approve" data-id="${a.id}">Approve</button>
               <button class="btn-reject"  data-id="${a.id}">Reject</button>
             </div>`
          : '';
        const notesBlock = a.notes
          ? `<div class="app-notes">${escape(a.notes)}</div>` : '';
        const rejectedBlock = a.status === 'rejected' && a.rejected_reason
          ? `<div class="app-notes" style="border-left-color:var(--status-red); color:var(--status-red);">
               Rejected: ${escape(a.rejected_reason)}
             </div>` : '';
        return `
          <div class="app-card status-${a.status}">
            <div class="app-head">
              <div>
                <div class="app-name">${escape(a.name)}${a.company ? ' · ' + escape(a.company) : ''}</div>
                <div class="app-meta">${escape(a.metro || '—')}${a.years_in_biz ? ' · ' + escape(a.years_in_biz) + 'y in biz' : ''}</div>
              </div>
              <div class="app-when">${fmtTime(a.created_at)}</div>
            </div>
            <div class="app-grid">
              <div class="app-row"><span class="k">Email</span>${empty(a.email)}</div>
              <div class="app-row"><span class="k">Phone</span>${empty(a.phone)}</div>
              <div class="app-row"><span class="k">License</span>${license ? '<span class="v">' + license + '</span>' : empty(null)}</div>
              <div class="app-row"><span class="k">Insurance</span>${empty(a.insurance_carrier)}</div>
              <div class="app-row" style="grid-column:1/-1;">
                <span class="k">Specialties</span>
                <span class="v">${specs ? `<div class="app-tags">${specs}</div>` : '<span class="empty">none</span>'}</span>
              </div>
            </div>
            ${notesBlock}
            ${rejectedBlock}
            ${actions}
          </div>
        `;
      }

      let currentStatus = 'pending_review';

      function renderTabCounts(all) {
        const c = {pending_review: 0, pending_email: 0, approved: 0, rejected: 0};
        for (const a of all) { if (c[a.status] != null) c[a.status]++; }
        document.getElementById('tc-pr').textContent = c.pending_review;
        document.getElementById('tc-pe').textContent = c.pending_email;
        document.getElementById('tc-ap').textContent = c.approved;
        document.getElementById('tc-rj').textContent = c.rejected;
        document.getElementById('tc-al').textContent = all.length;
        document.getElementById('stat-pr').textContent = c.pending_review;
        document.getElementById('stat-pe').textContent = c.pending_email;
        document.getElementById('stat-ap').textContent = c.approved;
        document.getElementById('stat-rj').textContent = c.rejected;
      }

      function renderList(rows) {
        const wrap = document.getElementById('app-list');
        if (!rows.length) {
          wrap.innerHTML = `<div class="empty-state">No applications in this state</div>`;
          return;
        }
        wrap.innerHTML = rows.map(renderCard).join('');
      }

      let inflight = false;
      async function refresh() {
        if (inflight) return;
        inflight = true;
        try {
          // Always fetch "all" once to compute tab counts, then filter client-side
          const all = await api('/api/v1/contractors/applications?status=all&limit=200');
          const list = Array.isArray(all) ? all : [];
          renderTabCounts(list);
          const filtered = currentStatus === 'all'
            ? list
            : list.filter(a => a.status === currentStatus);
          renderList(filtered);
        } catch (e) {
          console.error('[contractors] refresh failed', e);
        } finally {
          inflight = false;
        }
      }

      // Tab clicks
      document.querySelectorAll('.ct-tab').forEach(t => {
        t.addEventListener('click', () => {
          document.querySelectorAll('.ct-tab').forEach(o => o.classList.remove('active'));
          t.classList.add('active');
          currentStatus = t.dataset.status;
          refresh();
        });
      });

      // Approve / reject delegation
      document.addEventListener('click', async (ev) => {
        const ap = ev.target.closest('.btn-approve');
        if (ap) {
          const id = ap.dataset.id;
          ap.disabled = true; ap.textContent = 'Approving...';
          try {
            const r = await api('/api/v1/contractors/approve', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({application_id: id}),
            });
            if (!r.ok) throw new Error(r.error || 'approve failed');
          } catch (e) {
            ap.disabled = false; ap.textContent = 'Retry';
            alert('Approval failed: ' + e.message);
          }
          setTimeout(refresh, 400);
          return;
        }
        const rj = ev.target.closest('.btn-reject');
        if (rj) {
          const id = rj.dataset.id;
          const reason = prompt('Reason for rejection (optional):', '') || '';
          if (reason === null) return;  // cancelled
          rj.disabled = true; rj.textContent = 'Rejecting...';
          try {
            await api('/api/v1/contractors/reject', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({application_id: id, reason}),
            });
          } catch (e) {
            rj.disabled = false; rj.textContent = 'Retry';
            alert('Reject failed: ' + e.message);
          }
          setTimeout(refresh, 400);
        }
      });

      document.getElementById('ct-refresh').addEventListener('click', refresh);

      // Live: re-fetch on relevant events
      function bindLive() {
        if (!window.EMPIRE_LIVE || !window.EMPIRE_LIVE.on) {
          return setTimeout(bindLive, 400);
        }
        ['contractor_application_received', 'contractor_verified',
         'contractor_approved', 'contractor_rejected']
          .forEach(t => window.EMPIRE_LIVE.on(t, refresh));
      }
      bindLive();

      refresh();
    })();
    </script>
    """

    return base_layout(
        title="Contractors",
        subtitle="Operator Console",
        content=content,
        active_module="contractors",
        extra_css=extra_css,
        extra_js=extra_js,
    )
