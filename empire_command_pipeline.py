"""
EMPIRE V49 · COMMAND DECK · PIPELINE
=====================================
Owner-only section view for the email + SMS sequence pipeline. Renders:

  - Stats strip (active · done · bounced / opted-out · sent today)
  - Channel toggle (Email · SMS)
  - Status filter tabs
  - Sequence table (sorted by next_send_at desc)

Refresh model: 30s client poll. Engine-side WS push deferred — adding it
later only requires emitting state-change broadcasts (sequence_completed,
email_bounced, sms_optout, sms_replied) and subscribing here.
"""

from empire_layout import base_layout


def pipeline_view() -> str:
    extra_css = """
    .pl-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    }
    @media (max-width: 1000px) { .pl-stats { grid-template-columns: repeat(2, 1fr); } }

    .channel-toggle {
      display: inline-flex;
      gap: 0;
      margin-bottom: 14px;
      border: 1px solid var(--empire-divider);
    }
    .channel-toggle button {
      background: transparent; border: none; color: var(--empire-mist);
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.18em; text-transform: uppercase;
      padding: 9px 22px;
      cursor: pointer;
      transition: all 0.15s;
      border-right: 1px solid var(--empire-divider);
    }
    .channel-toggle button:last-child { border-right: none; }
    .channel-toggle button.active {
      background: var(--signal-teal-soft);
      color: var(--signal-teal);
    }

    .pl-tabs {
      display: flex; gap: 4px;
      margin: 14px 0 12px;
      border-bottom: 1px solid var(--empire-divider);
      flex-wrap: wrap;
    }
    .pl-tab {
      background: transparent; border: none;
      color: var(--empire-mist);
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.16em; text-transform: uppercase;
      padding: 10px 14px;
      cursor: pointer;
      border-bottom: 2px solid transparent;
      margin-bottom: -1px;
      transition: all 0.15s;
    }
    .pl-tab:hover { color: var(--empire-silver); }
    .pl-tab.active { color: var(--signal-teal); border-bottom-color: var(--signal-teal); }
    .pl-tab .count {
      color: var(--empire-fog);
      margin-left: 6px;
      font-weight: 600;
    }
    .pl-tab.active .count { color: var(--signal-teal); }

    .seq-table {
      width: 100%; border-collapse: collapse;
      font-family: var(--font-mono); font-size: 11px;
    }
    .seq-table th {
      text-align: left; padding: 10px 12px;
      font-size: 9px; letter-spacing: 0.18em;
      text-transform: uppercase; color: var(--empire-fog);
      border-bottom: 1px solid var(--empire-divider);
      font-weight: 400;
      white-space: nowrap;
    }
    .seq-table td {
      padding: 10px 12px;
      color: var(--empire-silver);
      border-bottom: 1px solid var(--empire-divider);
      vertical-align: top;
    }
    .seq-table tr:last-child td { border-bottom: none; }
    .seq-table tr:hover td { background: rgba(255,255,255,0.02); }
    .seq-table .recipient { color: var(--empire-white); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .seq-table .target { color: var(--empire-mist); font-size: 10px; max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .seq-table .step { color: var(--empire-mist); }
    .seq-table .when { color: var(--empire-fog); font-size: 10px; }

    .status-pill {
      display: inline-block;
      padding: 2px 7px;
      font-size: 9px; letter-spacing: 0.14em;
      text-transform: uppercase;
      border-radius: 2px;
    }
    .status-active      { background: rgba(68,229,184,0.12); color: var(--signal-teal); }
    .status-done        { background: rgba(122,140,163,0.10); color: var(--empire-mist); }
    .status-unsubscribed{ background: rgba(245,166,35,0.10); color: var(--status-amber); }
    .status-bounced     { background: rgba(244,63,94,0.15); color: var(--status-red); }
    .status-opted_out   { background: rgba(245,166,35,0.10); color: var(--status-amber); }
    .status-replied     { background: rgba(90,200,250,0.12); color: var(--strike-cyan); }

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
    .poll-hint {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-shadow); letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-left: 8px;
    }
    """

    content = """
    <div class="e-page">
      <div class="e-page-header">
        <div>
          <div class="e-page-title">Pipeline</div>
          <div class="e-page-sub">
            Email & SMS sequences · dispatcher state
            <span class="poll-hint">· auto-refresh 30s</span>
          </div>
        </div>
        <button class="btn-refresh" id="pl-refresh">Refresh now</button>
      </div>

      <div class="pl-stats">
        <div class="e-stat teal">
          <div class="e-stat-label" id="stat-active-label">Active sequences</div>
          <div class="e-stat-value teal" id="stat-active">—</div>
          <div class="e-stat-delta up" id="stat-active-delta">dispatching</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Sent · last 24h</div>
          <div class="e-stat-value" id="stat-sent24">—</div>
          <div class="e-stat-delta" id="stat-sent24-delta">attempted today</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">Completed</div>
          <div class="e-stat-value" id="stat-done">—</div>
          <div class="e-stat-delta">sequence finished</div>
        </div>
        <div class="e-stat amber">
          <div class="e-stat-label" id="stat-bad-label">Bounced</div>
          <div class="e-stat-value" id="stat-bad">—</div>
          <div class="e-stat-delta warn" id="stat-bad-delta">delivery failed</div>
        </div>
      </div>

      <div class="e-panel">
        <div class="channel-toggle">
          <button class="active" data-channel="email">Email</button>
          <button data-channel="sms">SMS</button>
        </div>

        <div class="pl-tabs" id="pl-tabs"></div>

        <div id="seq-list">
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
        const ms = new Date(ts).getTime() - Date.now();
        const abs = Math.abs(ms);
        const future = ms > 0;
        if (abs < 60_000)        return future ? 'soon' : 'just now';
        if (abs < 3_600_000)     return Math.round(abs/60_000) + 'm ' + (future ? '' : 'ago');
        if (abs < 86_400_000)    return Math.round(abs/3_600_000) + 'h ' + (future ? '' : 'ago');
        return Math.round(abs/86_400_000) + 'd ' + (future ? '' : 'ago');
      };
      const escape = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

      // Channel-specific config
      const CHANNELS = {
        email: {
          path:        '/api/v1/email/sequences',
          stats_path:  '/api/v1/email/stats',
          recipient:   r => r.email,
          bad_label:   'Bounced',
          bad_status:  'bounced',
          statuses:    ['active', 'done', 'unsubscribed', 'bounced'],
          stats_keys:  {active:'sequences_active', done:'sequences_done', bad:'sequences_bounced', sent:'emails_sent'},
        },
        sms: {
          path:        '/api/v1/sms/sequences',
          stats_path:  '/api/v1/sms/stats',
          recipient:   r => r.phone,
          bad_label:   'Opted out',
          bad_status:  'opted_out',
          statuses:    ['active', 'done', 'replied', 'opted_out'],
          stats_keys:  {active:'sequences_active', done:'sequences_done', bad:'sequences_optout', sent:'messages_sent'},
        },
      };

      let channel = 'email';
      let currentStatus = 'all';
      let lastFetchedAll = [];   // cached rows for current channel for tab counts

      async function api(path, opts) {
        const r = await fetch(path, Object.assign({credentials: 'same-origin'}, opts || {}));
        if (!r.ok) throw new Error(path + ' → ' + r.status);
        return r.json();
      }

      function renderTabs() {
        const c = CHANNELS[channel];
        const counts = {all: lastFetchedAll.length};
        for (const s of c.statuses) counts[s] = 0;
        for (const r of lastFetchedAll) {
          if (counts[r.status] != null) counts[r.status]++;
        }
        const tabs = ['all'].concat(c.statuses).map(s => {
          const isActive = s === currentStatus;
          return `<button class="pl-tab${isActive ? ' active' : ''}" data-status="${s}">
                    ${s.replace('_', ' ')} <span class="count">${counts[s]}</span>
                  </button>`;
        }).join('');
        document.getElementById('pl-tabs').innerHTML = tabs;
      }

      function renderStats(stats) {
        const c = CHANNELS[channel];
        document.getElementById('stat-active').textContent = stats[c.stats_keys.active] ?? '—';
        document.getElementById('stat-done').textContent   = stats[c.stats_keys.done]   ?? '—';
        document.getElementById('stat-bad-label').textContent = c.bad_label;
        document.getElementById('stat-bad').textContent    = stats[c.stats_keys.bad]    ?? '—';
        document.getElementById('stat-sent24').textContent = stats[c.stats_keys.sent]   ?? '—';
        document.getElementById('stat-sent24-delta').textContent =
          (channel === 'email' ? 'emails' : 'messages') + ' lifetime';
      }

      function renderTable(rows) {
        const c = CHANNELS[channel];
        const wrap = document.getElementById('seq-list');
        if (!rows.length) {
          wrap.innerHTML = `<div class="empty-state">No sequences in this state</div>`;
          return;
        }
        wrap.innerHTML = `
          <table class="seq-table">
            <thead>
              <tr>
                <th>${channel === 'email' ? 'Email' : 'Phone'}</th>
                <th>Target</th>
                <th>Type</th>
                <th>Step</th>
                <th>Status</th>
                <th>Next send</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(r => `
                <tr>
                  <td class="recipient">${escape(c.recipient(r))}</td>
                  <td class="target">${escape(r.target_addr || '—')}</td>
                  <td>${escape(r.sequence_type || '—')}</td>
                  <td class="step">${r.current_step ?? '—'}</td>
                  <td><span class="status-pill status-${r.status}">${r.status}</span></td>
                  <td class="when" title="${escape(r.next_send_at || '')}">${fmtRel(r.next_send_at)}</td>
                  <td class="when">${fmtTime(r.updated_at || r.created_at)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }

      let inflight = false;
      async function refresh() {
        if (inflight) return;
        inflight = true;
        try {
          const c = CHANNELS[channel];
          const [list, stats] = await Promise.all([
            api(c.path + '?status=all&limit=200'),
            api(c.stats_path),
          ]);
          lastFetchedAll = list.sequences || [];
          renderStats(stats);
          renderTabs();
          const filtered = currentStatus === 'all'
            ? lastFetchedAll
            : lastFetchedAll.filter(r => r.status === currentStatus);
          renderTable(filtered);
        } catch (e) {
          console.error('[pipeline] refresh failed', e);
        } finally {
          inflight = false;
        }
      }

      // Channel toggle
      document.querySelectorAll('.channel-toggle button').forEach(b => {
        b.addEventListener('click', () => {
          if (b.classList.contains('active')) return;
          document.querySelectorAll('.channel-toggle button').forEach(o => o.classList.remove('active'));
          b.classList.add('active');
          channel = b.dataset.channel;
          currentStatus = 'all';
          lastFetchedAll = [];
          refresh();
        });
      });

      // Tab clicks (delegated, since tabs re-render)
      document.getElementById('pl-tabs').addEventListener('click', ev => {
        const t = ev.target.closest('.pl-tab');
        if (!t) return;
        currentStatus = t.dataset.status;
        renderTabs();
        const filtered = currentStatus === 'all'
          ? lastFetchedAll
          : lastFetchedAll.filter(r => r.status === currentStatus);
        renderTable(filtered);
      });

      document.getElementById('pl-refresh').addEventListener('click', refresh);

      // 30s auto-refresh
      setInterval(refresh, 30_000);

      refresh();
    })();
    </script>
    """

    return base_layout(
        title="Pipeline",
        subtitle="Operator Console",
        content=content,
        active_module="pipeline",
        extra_css=extra_css,
        extra_js=extra_js,
    )
