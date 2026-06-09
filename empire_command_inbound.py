"""
EMPIRE V49 · COMMAND DECK · INBOUND
====================================
Owner-only view of inbound calls (voice + voicemail). Renders:

  - Stats strip (new · reviewed · high-urgency 24h · processed lifetime)
  - Status tabs (new · reviewed · called back · closed · all)
  - Call cards with transcript, urgency badge, disposition, actions

Live updates via /ws/live subscriptions to:
  - inbound_call          (call landed, disposition decided)
  - voicemail_transcribed (recording transcribed and scored)
"""

from empire_layout import base_layout


def inbound_view() -> str:
    extra_css = """
    .in-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    }
    @media (max-width: 1000px) { .in-stats { grid-template-columns: repeat(2, 1fr); } }

    .in-tabs {
      display: flex; gap: 4px;
      margin-bottom: 14px;
      border-bottom: 1px solid var(--empire-divider);
      flex-wrap: wrap;
    }
    .in-tab {
      background: transparent; border: none;
      color: var(--empire-mist);
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.16em; text-transform: uppercase;
      padding: 11px 16px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: all 0.15s;
    }
    .in-tab:hover { color: var(--empire-silver); }
    .in-tab.active { color: var(--signal-teal); border-bottom-color: var(--signal-teal); }
    .in-tab .count {
      color: var(--empire-fog);
      margin-left: 6px;
      font-weight: 600;
    }
    .in-tab.active .count { color: var(--signal-teal); }

    .call-card {
      background: var(--empire-elevated);
      border: 1px solid var(--empire-divider);
      border-left: 2px solid var(--empire-shadow);
      border-radius: var(--radius-sm);
      padding: 16px 18px;
      margin-bottom: 10px;
      animation: empire-fade-up 0.3s var(--ease-out-empire) both;
    }
    .call-card.urg-high   { border-left-color: var(--status-red); }
    .call-card.urg-medium { border-left-color: var(--status-amber); }
    .call-card.urg-low    { border-left-color: var(--empire-mist); }
    .call-card.s-closed,
    .call-card.s-called_back { opacity: 0.65; }

    .call-head {
      display: flex; justify-content: space-between; gap: 14px;
      align-items: baseline;
      margin-bottom: 8px;
    }
    .call-from {
      font-family: var(--font-mono); font-weight: 600;
      font-size: 15px; color: var(--empire-white);
    }
    .call-when {
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-fog);
    }

    .call-badges {
      display: flex; flex-wrap: wrap; gap: 6px;
      margin-bottom: 10px;
    }
    .badge {
      display: inline-block;
      padding: 3px 9px;
      font-family: var(--font-mono); font-size: 9px;
      letter-spacing: 0.14em; text-transform: uppercase;
      border-radius: 2px;
    }
    .badge-urgency.high   { background: rgba(244,63,94,0.15); color: var(--status-red); }
    .badge-urgency.medium { background: rgba(245,166,35,0.12); color: var(--status-amber); }
    .badge-urgency.low    { background: rgba(122,140,163,0.10); color: var(--empire-mist); }

    .badge-intent {
      background: rgba(90,200,250,0.10); color: var(--strike-cyan);
    }
    .badge-disp {
      background: rgba(122,140,163,0.10); color: var(--empire-mist);
    }
    .badge-status {
      background: rgba(122,140,163,0.10); color: var(--empire-mist);
    }
    .badge-status.s-new        { background: rgba(245,166,35,0.12); color: var(--status-amber); }
    .badge-status.s-reviewed   { background: rgba(90,200,250,0.12); color: var(--strike-cyan); }
    .badge-status.s-called_back{ background: rgba(68,229,184,0.12); color: var(--signal-teal); }

    .call-transcript {
      background: rgba(0,0,0,0.30);
      padding: 12px 14px;
      border-left: 2px solid var(--empire-divider);
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.65;
      margin: 10px 0;
      max-height: 200px;
      overflow-y: auto;
    }
    .call-transcript .placeholder {
      color: var(--empire-shadow); font-style: italic;
    }

    .call-lead {
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-fog);
      letter-spacing: 0.04em;
      margin: 6px 0 10px;
    }
    .call-lead strong { color: var(--empire-silver); }

    .call-actions {
      display: flex; flex-wrap: wrap; gap: 8px;
      padding-top: 10px;
      border-top: 1px solid var(--empire-divider);
      align-items: center;
    }
    .btn-step {
      background: transparent;
      border: 1px solid var(--empire-divider);
      color: var(--empire-mist);
      padding: 7px 13px;
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.14em; text-transform: uppercase;
      cursor: pointer; transition: all 0.15s;
    }
    .btn-step:hover { color: var(--signal-teal); border-color: var(--signal-teal); }
    .btn-step.danger:hover { color: var(--status-red); border-color: var(--status-red); }
    .btn-step:disabled { opacity: 0.35; cursor: not-allowed; }

    .play-link {
      color: var(--strike-cyan); text-decoration: none;
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.14em; text-transform: uppercase;
      padding: 7px 13px;
      border: 1px solid rgba(90,200,250,0.30);
      transition: all 0.15s;
    }
    .play-link:hover { background: rgba(90,200,250,0.10); border-color: var(--strike-cyan); }

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
          <div class="e-page-title">Inbound</div>
          <div class="e-page-sub">Calls · voicemail · triage</div>
        </div>
        <button class="btn-refresh" id="in-refresh">Refresh</button>
      </div>

      <div class="in-stats">
        <div class="e-stat amber">
          <div class="e-stat-label">New · unreviewed</div>
          <div class="e-stat-value" id="stat-new">—</div>
          <div class="e-stat-delta warn">awaiting triage</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Reviewed · lifetime</div>
          <div class="e-stat-value" id="stat-reviewed">—</div>
          <div class="e-stat-delta">operator-touched</div>
        </div>
        <div class="e-stat amber">
          <div class="e-stat-label">High urgency · 24h</div>
          <div class="e-stat-value" id="stat-hot">—</div>
          <div class="e-stat-delta warn">urgency ≥ 8</div>
        </div>
        <div class="e-stat teal">
          <div class="e-stat-label">Recordings processed</div>
          <div class="e-stat-value teal" id="stat-rec">—</div>
          <div class="e-stat-delta up">transcribed</div>
        </div>
      </div>

      <div class="e-panel">
        <div class="in-tabs" id="in-tabs"></div>
        <div id="call-list">
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
      const fmtRel = ts => {
        if (!ts) return '—';
        const ms = Date.now() - new Date(ts).getTime();
        if (ms < 60_000) return Math.round(ms/1000) + 's ago';
        if (ms < 3_600_000) return Math.round(ms/60_000) + 'm ago';
        if (ms < 86_400_000) return Math.round(ms/3_600_000) + 'h ago';
        return Math.round(ms/86_400_000) + 'd ago';
      };
      const fmtDuration = secs => {
        const n = Number(secs || 0);
        if (n < 60) return n + 's';
        return Math.floor(n / 60) + 'm ' + (n % 60) + 's';
      };
      const fmtPhone = p => {
        if (!p) return '—';
        // Bare US-ish prettify: +15551234567 -> +1 (555) 123-4567
        const m = String(p).match(/^\\+?1?(\\d{3})(\\d{3})(\\d{4})$/);
        return m ? `+1 (${m[1]}) ${m[2]}-${m[3]}` : p;
      };
      const escape = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

      function urgencyClass(u) {
        const n = Number(u || 0);
        if (n >= 8) return 'high';
        if (n >= 5) return 'medium';
        return 'low';
      }

      async function api(path, opts) {
        const headers = Object.assign({'Authorization': 'Bearer Jaykub20*'}, (opts || {}).headers || {});
        const r = await fetch(path, Object.assign({credentials: 'same-origin', headers: headers}, opts || {}));
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || data.error || (path + ' → ' + r.status));
        return data;
      }

      let allCalls = [];
      let currentStatus = 'new';

      function applyFilter() {
        return currentStatus === 'all' ? allCalls : allCalls.filter(c => c.status === currentStatus);
      }

      function renderTabs() {
  console.log("DEBUG: renderTabs triggered");
        const c = {new: 0, reviewed: 0, called_back: 0, closed: 0};
        for (const r of allCalls) { if (c[r.status] != null) c[r.status]++; }
        const tabs = [
          ['new',         'New'],
          ['reviewed',    'Reviewed'],
          ['called_back', 'Called back'],
          ['closed',      'Closed'],
          ['leads',       'Leads'],
          ['all',         'All'],
        ];
        document.getElementById('in-tabs').innerHTML = tabs.map(([k, label]) => {
          const isActive = k === currentStatus;
          const count = k === 'all' ? allCalls.length : (c[k] || 0);
          return `<button class="in-tab${isActive ? ' active' : ''}" data-status="${k}">
            ${label} <span class="count">${count}</span>
          </button>`;
        }).join('');
      }

      function renderStats() {
        const newCount = allCalls.filter(c => c.status === 'new').length;
        const reviewed = allCalls.filter(c => c.status !== 'new').length;
        const dayAgo = Date.now() - 86_400_000;
        const hot = allCalls.filter(c =>
          (c.urgency_score || 0) >= 8 && new Date(c.created_at).getTime() > dayAgo).length;
        const withRec = allCalls.filter(c => c.recording_url).length;
        document.getElementById('stat-new').textContent      = newCount;
        document.getElementById('stat-reviewed').textContent = reviewed;
        document.getElementById('stat-hot').textContent      = hot;
        document.getElementById('stat-rec').textContent      = withRec;
      }

      function renderCard(c) {
        const uc = urgencyClass(c.urgency_score);
        const meta = c.meta || {};
        const matchedAddr = meta.matched_addr;
        const operatorNotes = meta.operator_notes;
        const recBtn = c.recording_url
          ? `<a class="play-link" href="${escape(c.recording_url)}" target="_blank" rel="noopener">▶ Play recording</a>`
          : '';

        // Action buttons depend on current status — show forward-progress only
        const sn = c.status === 'new';
        const sr = c.status === 'reviewed';
        const sc = c.status === 'called_back';
        const actions = `
          <div class="call-actions">
            ${recBtn}
            <button class="btn-step" data-id="${c.id}" data-next="reviewed"    ${sn ? '' : 'disabled'}>Mark reviewed</button>
            <button class="btn-step" data-id="${c.id}" data-next="called_back" ${(sn||sr) ? '' : 'disabled'}>Called back</button>
            <button class="btn-step" data-id="${c.id}" data-next="closed"      ${c.status === 'closed' ? 'disabled' : ''}>Close</button>
            <button class="btn-step" data-id="${c.id}" data-note="1">Add note</button>
          </div>
        `;

        const transcriptBlock = c.transcript
          ? `<div class="call-transcript">${escape(c.transcript)}</div>`
          : (c.disposition === 'voicemail'
              ? `<div class="call-transcript"><span class="placeholder">Voicemail — transcript pending</span></div>`
              : '');

        const notesBlock = operatorNotes
          ? `<div class="call-transcript" style="border-left-color:var(--signal-teal);"><strong style="color:var(--signal-teal);">Operator note:</strong> ${escape(operatorNotes)}</div>`
          : '';

        return `
          <div class="call-card urg-${uc} s-${c.status}" data-id="${c.id}">
            <div class="call-head">
              <div>
                <div class="call-from">${escape(fmtPhone(c.from_number))}</div>
                <div class="call-when" title="${escape(c.created_at || '')}">${fmtTime(c.created_at)} · ${fmtRel(c.created_at)}</div>
              </div>
              <div class="call-when">${c.duration ? fmtDuration(c.duration) + ' · ' : ''}${escape(c.disposition || '')}</div>
            </div>
            <div class="call-badges">
              <span class="badge badge-urgency ${uc}">urgency ${c.urgency_score ?? '—'}/10</span>
              <span class="badge badge-intent">${escape(c.intent || 'general_inquiry')}</span>
              <span class="badge badge-disp">${escape(c.disposition || 'unknown')}</span>
              <span class="badge badge-status s-${c.status}">${escape(c.status)}</span>
            </div>
            ${matchedAddr ? `<div class="call-lead">Matched lead: <strong>${escape(matchedAddr)}</strong></div>` : ''}
            ${transcriptBlock}
            ${notesBlock}
            ${actions}
          </div>
        `;
      }

      function renderList(rows) {
        const wrap = document.getElementById('call-list');
        if (!rows.length) {
          wrap.innerHTML = '<div class="empty-state">No calls in this state</div>';
          return;
        }
        wrap.innerHTML = rows.map(renderCard).join('');
      }

      let inflight = false;
      async function refresh() {
        if (inflight) return;
        inflight = true;
        try {
          const data = currentStatus === 'leads' 
            ? await api('/api/v1/inbound/leads?limit=200') 
            : await api('/api/v1/inbound/calls?status=all&limit=200');
          allCalls = currentStatus === 'leads' ? (data.leads || []) : (data.calls || []);
          renderStats();
          renderTabs();
          renderList(applyFilter());
        } catch (e) {
          console.error('[inbound] refresh failed', e);
          document.getElementById('call-list').innerHTML =
            `<div class="empty-state">Failed to load · ${escape(e.message)}</div>`;
        } finally {
          inflight = false;
        }
      }

      // Tab clicks
      document.getElementById('in-tabs').addEventListener('click', async ev => {
        const t = ev.target.closest('.in-tab');
        if (!t) return;
        currentStatus = t.dataset.status;
        renderTabs();
        await refresh();
      });

      // Action buttons (status step + add note)
      document.addEventListener('click', async (ev) => {
        const btn = ev.target.closest('.btn-step');
        if (!btn || btn.disabled) return;
        const id = btn.dataset.id;

        if (btn.dataset.note) {
          const notes = prompt('Operator note:', '');
          if (notes == null || !notes.trim()) return;
          btn.disabled = true; btn.textContent = 'Saving...';
          try {
            await api('/api/v1/inbound/calls/update', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({call_id: id, notes: notes.trim()}),
            });
            setTimeout(refresh, 300);
          } catch (e) {
            alert('Save failed: ' + e.message);
            btn.disabled = false; btn.textContent = 'Add note';
          }
          return;
        }

        const next = btn.dataset.next;
        if (!next) return;
        btn.disabled = true;
        const oldText = btn.textContent;
        btn.textContent = '...';
        try {
          await api('/api/v1/inbound/calls/update', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({call_id: id, status: next}),
          });
          setTimeout(refresh, 300);
        } catch (e) {
          alert('Update failed: ' + e.message);
          btn.disabled = false; btn.textContent = oldText;
        }
      });

      document.getElementById('in-refresh').addEventListener('click', refresh);

      // Live: refresh on new call / voicemail transcribed
      function bindLive() {
        if (!window.EMPIRE_LIVE || !window.EMPIRE_LIVE.on) {
          return setTimeout(bindLive, 400);
        }
        ['inbound_call', 'voicemail_transcribed']
          .forEach(t => window.EMPIRE_LIVE.on(t, refresh));
      }
      renderTabs(); refresh();

      refresh();
    })();
    </script>
    """

    return base_layout(
        title="Inbound",
        subtitle="Operator Console",
        content=content,
        active_module="inbound",
        extra_css=extra_css,
        extra_js=extra_js,
    )
