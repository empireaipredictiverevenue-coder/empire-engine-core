"""
EMPIRE V49 · COMMAND DECK · DISPATCH
=====================================
Owner-only view of the matching + leaderboard pipeline. Renders:

  - Stats strip (matches computed · dispatches sent · accepted · avg score)
  - Match preview tool (metro + specialties → scored contractor list)
  - Contractor leaderboard (active, ranked by trust score)

Data:
  - POST /api/v1/matching/preview     (preview a hypothetical lead)
  - GET  /api/v1/matching/stats
  - GET  /api/v1/matching/leaderboard?limit=N
"""

import json

from empire_layout import base_layout
from empire_contractors import SPECIALTIES, METROS


def dispatch_view() -> str:
    extra_css = """
    .ds-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    }
    @media (max-width: 1000px) { .ds-stats { grid-template-columns: repeat(2, 1fr); } }

    .preview-grid {
      display: grid;
      grid-template-columns: 240px 1fr 80px 100px;
      gap: 10px;
      align-items: end;
      margin-bottom: 14px;
    }
    @media (max-width: 800px) { .preview-grid { grid-template-columns: 1fr 1fr; } }

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

    .spec-chips {
      display: flex; flex-wrap: wrap; gap: 6px;
      padding: 8px;
      background: rgba(0,0,0,0.2);
      border: 1px solid var(--empire-divider);
      min-height: 40px;
      max-height: 80px;
      overflow-y: auto;
    }
    .spec-chip {
      background: rgba(122,140,163,0.10);
      color: var(--empire-mist);
      font-family: var(--font-mono); font-size: 10px;
      padding: 4px 9px;
      cursor: pointer;
      user-select: none;
      transition: all 0.15s;
      letter-spacing: 0.04em;
      border-radius: 2px;
    }
    .spec-chip:hover { color: var(--empire-silver); background: rgba(122,140,163,0.18); }
    .spec-chip.active {
      background: var(--signal-teal-soft); color: var(--signal-teal);
      box-shadow: 0 0 0 1px rgba(68,229,184,0.4);
    }

    .btn-primary {
      background: var(--signal-teal); color: #000;
      border: none; padding: 10px 16px;
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

    .match-table, .lb-table {
      width: 100%; border-collapse: collapse;
    }
    .match-table th, .lb-table th {
      text-align: left; padding: 10px 12px;
      font-family: var(--font-mono); font-size: 9px;
      letter-spacing: 0.18em; text-transform: uppercase;
      color: var(--empire-fog); font-weight: 400;
      border-bottom: 1px solid var(--empire-divider);
      white-space: nowrap;
    }
    .match-table td, .lb-table td {
      padding: 12px;
      color: var(--empire-silver);
      border-bottom: 1px solid var(--empire-divider);
      vertical-align: middle;
      font-family: var(--font-mono); font-size: 11px;
    }
    .match-table tr:last-child td, .lb-table tr:last-child td { border-bottom: none; }
    .match-table tr:hover td, .lb-table tr:hover td { background: rgba(255,255,255,0.02); }

    .rank {
      font-family: var(--font-mono); font-weight: 700;
      color: var(--empire-fog); font-size: 11px;
      width: 36px;
    }
    .rank.top1 { color: var(--signal-teal); font-size: 14px; }
    .rank.top2 { color: var(--strike-cyan); }
    .rank.top3 { color: var(--status-amber); }

    .ct-name { color: var(--empire-white); font-weight: 600; font-size: 13px; font-family: var(--font-ui); }
    .ct-metro { color: var(--empire-mist); font-size: 10px; }

    .score-bar {
      display: inline-flex; align-items: center; gap: 8px;
    }
    .score-track {
      width: 80px; height: 6px;
      background: rgba(0,0,0,0.4);
      border-radius: 3px;
      overflow: hidden;
      position: relative;
    }
    .score-fill {
      height: 100%;
      background: linear-gradient(90deg, var(--signal-teal), var(--strike-cyan));
      transition: width 0.3s;
    }
    .score-val {
      color: var(--empire-white); font-weight: 600; font-size: 11px;
      min-width: 36px;
    }

    .trust-val {
      color: var(--signal-teal); font-weight: 600;
    }
    .components {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-fog); letter-spacing: 0.04em;
      display: flex; gap: 10px;
      flex-wrap: wrap;
    }
    .components span { color: var(--empire-mist); }

    .spec-tags {
      display: flex; flex-wrap: wrap; gap: 4px;
    }
    .spec-tag {
      background: rgba(90,200,250,0.08);
      color: var(--strike-cyan);
      font-family: var(--font-mono); font-size: 9px;
      padding: 2px 6px;
      border-radius: 2px;
    }

    .empty-state {
      padding: 40px 20px; text-align: center;
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-fog); letter-spacing: 0.18em;
      text-transform: uppercase;
    }

    .panel-head {
      display: flex; justify-content: space-between; align-items: center;
      margin-bottom: 14px; padding-bottom: 12px;
      border-bottom: 1px solid var(--empire-divider);
    }
    """

    specialties_json = json.dumps(SPECIALTIES)
    metros_json      = json.dumps(METROS)

    content = f"""
    <div class="e-page">
      <div class="e-page-header">
        <div>
          <div class="e-page-title">Dispatch</div>
          <div class="e-page-sub">Contractor matching · leaderboard · preview</div>
        </div>
        <button class="btn-refresh" id="ds-refresh">Refresh</button>
      </div>

      <div class="ds-stats">
        <div class="e-stat teal">
          <div class="e-stat-label">Matches computed</div>
          <div class="e-stat-value teal" id="stat-matches">—</div>
          <div class="e-stat-delta up">lifetime</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Dispatches sent</div>
          <div class="e-stat-value" id="stat-sent">—</div>
          <div class="e-stat-delta" id="stat-sent-delta">contractor pings</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">Accepted</div>
          <div class="e-stat-value" id="stat-accepted">—</div>
          <div class="e-stat-delta" id="stat-accept-rate">accept rate</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">Avg match score</div>
          <div class="e-stat-value" style="font-size:22px;" id="stat-avg">—</div>
          <div class="e-stat-delta">last match</div>
        </div>
      </div>

      <div class="e-panel">
        <div class="e-section-label">Match preview</div>
        <div class="e-page-sub" style="margin-bottom:12px;">
          Pick a metro + required specialties to see the top-ranked contractors who would receive a dispatch.
        </div>
        <div class="preview-grid">
          <div class="field">
            <label>Metro</label>
            <select id="prev-metro"></select>
          </div>
          <div class="field" style="grid-column: span 2;">
            <label>Required specialties (click to toggle)</label>
            <div class="spec-chips" id="prev-specs"></div>
          </div>
          <div class="field">
            <label>Top N</label>
            <input type="number" id="prev-topn" value="5" min="1" max="20" />
          </div>
        </div>
        <button class="btn-primary" id="prev-go">Run preview</button>

        <div id="match-list" style="margin-top:18px;"></div>
      </div>

      <div class="e-panel" style="margin-top:14px;">
        <div class="panel-head">
          <span class="e-section-label" style="margin-bottom:0;">Leaderboard · active contractors</span>
          <span class="e-stat-label" id="lb-meta">—</span>
        </div>
        <div id="lb-list">
          <div class="empty-state">Loading...</div>
        </div>
      </div>
    </div>

    <script>
      window.__SPECIALTIES = {specialties_json};
      window.__METROS      = {metros_json};
    </script>
    """

    extra_js = """
    <script>
    (function() {
      const fmtCount = n => Number(n || 0).toLocaleString();
      const fmtTime  = ts => ts ? new Date(ts).toLocaleString(undefined,
        {month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : '—';
      const fmtRel   = ts => {
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
        if (!r.ok) throw new Error(data.detail || data.error || (path + ' → ' + r.status));
        return data;
      }

      // Populate metros + specialty chips
      const metroSelect = document.getElementById('prev-metro');
      metroSelect.innerHTML = window.__METROS.map(m =>
        `<option value="${escape(m)}">${escape(m)}</option>`).join('');

      const specWrap = document.getElementById('prev-specs');
      specWrap.innerHTML = window.__SPECIALTIES.map(s =>
        `<div class="spec-chip" data-spec="${escape(s)}">${escape(s)}</div>`).join('');
      specWrap.addEventListener('click', ev => {
        const chip = ev.target.closest('.spec-chip');
        if (!chip) return;
        chip.classList.toggle('active');
      });

      function selectedSpecialties() {
        return Array.from(specWrap.querySelectorAll('.spec-chip.active')).map(c => c.dataset.spec);
      }

      function rankClass(i) {
        return i === 0 ? 'top1' : i === 1 ? 'top2' : i === 2 ? 'top3' : '';
      }

      function renderStats(stats) {
        document.getElementById('stat-matches').textContent  = fmtCount(stats.matches_computed);
        document.getElementById('stat-sent').textContent     = fmtCount(stats.dispatches_sent);
        document.getElementById('stat-accepted').textContent = fmtCount(stats.dispatches_accepted);
        const rate = stats.dispatches_sent > 0
          ? Math.round(100 * (stats.dispatches_accepted || 0) / stats.dispatches_sent) + '%'
          : '—';
        document.getElementById('stat-accept-rate').textContent = rate + ' accept rate';
        document.getElementById('stat-avg').textContent =
          stats.last_match_score_avg != null ? Number(stats.last_match_score_avg).toFixed(2) : '—';
      }

      function renderLeaderboard(contractors) {
        const wrap = document.getElementById('lb-list');
        document.getElementById('lb-meta').textContent =
          contractors.length ? `${contractors.length} contractor${contractors.length === 1 ? '' : 's'}` : '';
        if (!contractors.length) {
          wrap.innerHTML = '<div class="empty-state">No active contractors</div>';
          return;
        }
        wrap.innerHTML = `
          <table class="lb-table">
            <thead>
              <tr>
                <th>#</th><th>Contractor</th><th>Trust</th><th>Completed</th>
                <th>Specialties</th><th>Last dispatched</th>
              </tr>
            </thead>
            <tbody>
              ${contractors.map((c, i) => `
                <tr>
                  <td class="rank ${rankClass(i)}">${i + 1}</td>
                  <td>
                    <div class="ct-name">${escape(c.name)}</div>
                    <div class="ct-metro">${escape(c.metro || '—')}</div>
                  </td>
                  <td class="trust-val">${Number(c.trust_score || 0).toFixed(2)}</td>
                  <td>${fmtCount(c.completed_jobs)}</td>
                  <td>
                    <div class="spec-tags">
                      ${(c.specialties || []).slice(0, 6).map(s =>
                        `<span class="spec-tag">${escape(s)}</span>`).join('')}
                    </div>
                  </td>
                  <td class="ct-metro" title="${escape(c.last_dispatched_at || '')}">
                    ${fmtRel(c.last_dispatched_at)}
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }

      function renderMatches(matches) {
        const wrap = document.getElementById('match-list');
        if (!matches.length) {
          wrap.innerHTML = '<div class="empty-state">No matches · no contractors fit this metro/specialty combo</div>';
          return;
        }
        const maxScore = Math.max(...matches.map(m => m.score), 1);
        wrap.innerHTML = `
          <table class="match-table">
            <thead>
              <tr>
                <th>#</th><th>Contractor</th><th>Trust</th><th>Score</th>
                <th>Components</th>
              </tr>
            </thead>
            <tbody>
              ${matches.map((m, i) => {
                const fill = (m.score / maxScore) * 100;
                const components = m.components || {};
                return `
                  <tr>
                    <td class="rank ${rankClass(i)}">${i + 1}</td>
                    <td>
                      <div class="ct-name">${escape(m.contractor_name)}</div>
                      <div class="ct-metro">${escape(m.metro || '—')} ·
                        ${(m.specialties || []).slice(0, 4).join(', ') || 'no specialties'}
                      </div>
                    </td>
                    <td class="trust-val">${Number(m.trust_score || 0).toFixed(2)}</td>
                    <td>
                      <div class="score-bar">
                        <div class="score-track"><div class="score-fill" style="width:${fill}%"></div></div>
                        <span class="score-val">${Number(m.score || 0).toFixed(3)}</span>
                      </div>
                    </td>
                    <td>
                      <div class="components">
                        ${Object.entries(components).map(([k, v]) =>
                          `<span>${escape(k)}: ${typeof v === 'number' ? Number(v).toFixed(2) : escape(String(v))}</span>`).join('')}
                      </div>
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
          const [stats, lb] = await Promise.all([
            api('/api/v1/matching/stats'),
            api('/api/v1/matching/leaderboard?limit=50'),
          ]);
          renderStats(stats);
          renderLeaderboard(lb.contractors || []);
        } catch (e) {
          console.error('[dispatch] refresh failed', e);
        } finally {
          inflight = false;
        }
      }

      // Preview submit
      document.getElementById('prev-go').addEventListener('click', async () => {
        const metro = document.getElementById('prev-metro').value;
        const specialties = selectedSpecialties();
        const top_n = Math.max(1, Math.min(20, Number(document.getElementById('prev-topn').value) || 5));
        const wrap = document.getElementById('match-list');
        const btn = document.getElementById('prev-go');
        btn.disabled = true; btn.textContent = 'Running...';
        wrap.innerHTML = '<div class="empty-state">Computing matches...</div>';
        try {
          const r = await api('/api/v1/matching/preview', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({metro, specialties, top_n}),
          });
          renderMatches(r.matches || []);
          // Refresh stats — preview increments matches_computed
          api('/api/v1/matching/stats').then(renderStats).catch(() => {});
        } catch (e) {
          wrap.innerHTML = `<div class="empty-state">Preview failed · ${escape(e.message)}</div>`;
        } finally {
          btn.disabled = false; btn.textContent = 'Run preview';
        }
      });

      document.getElementById('ds-refresh').addEventListener('click', refresh);

      // Live: refresh leaderboard when dispatch fires
      function bindLive() {
        if (!window.EMPIRE_LIVE || !window.EMPIRE_LIVE.on) {
          return setTimeout(bindLive, 400);
        }
        ['dispatch', 'dispatch_sent', 'dispatch_accepted', 'contractor_approved']
          .forEach(t => window.EMPIRE_LIVE.on(t, refresh));
      }
      bindLive();

      refresh();
    })();
    </script>
    """

    return base_layout(
        title="Dispatch",
        subtitle="Operator Console",
        content=content,
        active_module="dispatch",
        extra_css=extra_css,
        extra_js=extra_js,
    )
