"""
EMPIRE V49 · COMMAND DECK · CONSOLE
====================================
Owner-only natural-language operator console. Renders:

  - Stats strip (commands · actions resolved · executed · errors)
  - Big command input box
  - Parse → Preview → Execute flow with destructive confirmation
  - Recent command history (client-side, last 12 in localStorage)
  - Browseable catalog of available actions for this role

Data:
  - POST /api/v1/console/parse    → {ok, action, params, destructive, explanation}
  - POST /api/v1/console/execute  → action's own result shape
  - GET  /api/v1/console/actions  → {actions: [...]}
  - GET  /api/v1/console/stats
"""

from empire_layout import base_layout


def console_view() -> str:
    extra_css = """
    .co-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    }
    @media (max-width: 1000px) { .co-stats { grid-template-columns: repeat(2, 1fr); } }

    .console-input-wrap {
      position: relative;
      margin-bottom: 14px;
    }
    .console-prompt {
      position: absolute;
      left: 16px; top: 50%; transform: translateY(-50%);
      color: var(--signal-teal);
      font-family: var(--font-mono); font-size: 16px;
      pointer-events: none;
      user-select: none;
    }
    .console-input {
      width: 100%;
      background: rgba(0,0,0,0.45);
      border: 1px solid var(--empire-divider);
      color: var(--empire-white);
      font-family: var(--font-mono); font-size: 14px;
      padding: 18px 16px 18px 40px;
      outline: none;
      transition: border-color 0.15s, box-shadow 0.15s;
    }
    .console-input:focus {
      border-color: var(--signal-teal);
      box-shadow: 0 0 0 1px var(--signal-teal-soft);
    }
    .console-input:disabled { opacity: 0.5; }
    .console-hint {
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-fog); letter-spacing: 0.14em;
      margin-top: 8px;
    }
    .console-hint kbd {
      display: inline-block;
      background: rgba(255,255,255,0.05);
      border: 1px solid var(--empire-divider);
      color: var(--empire-silver);
      padding: 1px 6px;
      font-family: var(--font-mono); font-size: 10px;
      border-radius: 3px;
      margin: 0 2px;
    }

    .preview-card {
      background: var(--empire-elevated);
      border: 1px solid var(--empire-divider);
      border-left: 2px solid var(--strike-cyan);
      padding: 18px 20px;
      margin-bottom: 14px;
      animation: empire-fade-up 0.25s var(--ease-out-empire) both;
    }
    .preview-card.destructive { border-left-color: var(--status-red); }
    .preview-card.error       { border-left-color: var(--status-amber); }
    .preview-card.success     { border-left-color: var(--signal-teal); }

    .preview-head {
      display: flex; justify-content: space-between; align-items: baseline;
      gap: 14px; margin-bottom: 12px;
    }
    .preview-action {
      font-family: var(--font-mono); font-weight: 700;
      font-size: 16px; color: var(--strike-cyan);
      letter-spacing: 0.04em;
    }
    .preview-card.destructive .preview-action { color: var(--status-red); }
    .preview-card.success .preview-action     { color: var(--signal-teal); }
    .preview-card.error .preview-action       { color: var(--status-amber); }

    .preview-cmd {
      font-family: var(--font-mono); font-size: 11px;
      color: var(--empire-fog); letter-spacing: 0.04em;
      max-width: 60%;
      text-align: right;
      word-break: break-word;
    }
    .preview-explanation {
      color: var(--empire-silver);
      font-size: 13px; line-height: 1.6;
      margin-bottom: 14px;
    }
    .preview-params {
      background: rgba(0,0,0,0.30);
      border-left: 2px solid var(--empire-divider);
      padding: 12px 14px;
      font-family: var(--font-mono); font-size: 11px;
      color: var(--empire-mist);
      white-space: pre-wrap; word-break: break-word;
      margin-bottom: 14px;
    }
    .preview-result {
      background: rgba(0,0,0,0.30);
      border-left: 2px solid var(--signal-teal);
      padding: 12px 14px;
      font-family: var(--font-mono); font-size: 11px;
      color: var(--signal-teal);
      white-space: pre-wrap; word-break: break-word;
      margin-bottom: 14px;
    }
    .preview-card.error .preview-result { border-left-color: var(--status-amber); color: var(--status-amber); }

    .preview-warn {
      background: rgba(244,63,94,0.06);
      border: 1px solid rgba(244,63,94,0.30);
      color: var(--status-red);
      padding: 9px 14px;
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.14em;
      margin-bottom: 14px;
    }

    .preview-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .btn-execute {
      background: var(--signal-teal); color: #000;
      border: none; padding: 10px 22px;
      font-family: var(--font-ui); font-weight: 700;
      font-size: 11px; letter-spacing: 0.06em;
      cursor: pointer; transition: all 0.15s;
      text-transform: uppercase;
    }
    .btn-execute:hover { background: transparent; color: var(--signal-teal); outline: 1px solid var(--signal-teal); }
    .btn-execute.destructive { background: var(--status-red); color: var(--empire-white); }
    .btn-execute.destructive:hover { background: transparent; color: var(--status-red); outline: 1px solid var(--status-red); }
    .btn-execute:disabled { opacity: 0.4; cursor: wait; }
    .btn-cancel {
      background: transparent; border: 1px solid var(--empire-divider);
      color: var(--empire-mist);
      padding: 10px 18px;
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.14em; text-transform: uppercase;
      cursor: pointer; transition: all 0.15s;
    }
    .btn-cancel:hover { color: var(--status-red); border-color: var(--status-red); }

    .history-row {
      display: flex; gap: 10px;
      padding: 8px 12px;
      background: rgba(0,0,0,0.20);
      border-left: 2px solid var(--empire-divider);
      margin-bottom: 4px;
      font-family: var(--font-mono); font-size: 11px;
      align-items: baseline;
      cursor: pointer;
      transition: all 0.15s;
    }
    .history-row:hover { border-left-color: var(--signal-teal); background: rgba(0,0,0,0.35); }
    .history-row .h-when {
      color: var(--empire-fog); font-size: 9px;
      letter-spacing: 0.10em;
      flex-shrink: 0;
      width: 70px;
    }
    .history-row .h-cmd {
      color: var(--empire-silver);
      flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .history-row .h-action {
      color: var(--strike-cyan);
      flex-shrink: 0;
      font-size: 10px;
      letter-spacing: 0.06em;
    }
    .history-row.destructive .h-action { color: var(--status-red); }

    .action-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
      gap: 8px;
      margin-top: 10px;
    }
    .action-tile {
      background: var(--empire-elevated);
      border: 1px solid var(--empire-divider);
      border-left: 2px solid var(--strike-cyan);
      padding: 12px 14px;
    }
    .action-tile.destructive { border-left-color: var(--status-red); }
    .action-name {
      font-family: var(--font-mono); font-weight: 600;
      color: var(--empire-white); font-size: 12px;
      margin-bottom: 6px;
      letter-spacing: 0.02em;
    }
    .action-desc {
      color: var(--empire-mist); font-size: 11px; line-height: 1.5;
      margin-bottom: 6px;
    }
    .action-params {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-fog); letter-spacing: 0.04em;
    }
    .destructive-badge {
      display: inline-block;
      margin-left: 6px;
      padding: 1px 6px;
      font-family: var(--font-mono); font-size: 8px;
      letter-spacing: 0.18em;
      background: rgba(244,63,94,0.12);
      color: var(--status-red);
      border-radius: 2px;
    }

    .catalog-toggle {
      background: transparent; border: none;
      color: var(--empire-mist);
      font-family: var(--font-mono); font-size: 10px;
      letter-spacing: 0.18em; text-transform: uppercase;
      cursor: pointer;
      padding: 4px 0;
      transition: color 0.15s;
    }
    .catalog-toggle:hover { color: var(--signal-teal); }
    .catalog-body { display: none; margin-top: 10px; }
    .catalog-body.open { display: block; }

    .empty-state {
      padding: 28px 20px; text-align: center;
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-fog); letter-spacing: 0.18em;
      text-transform: uppercase;
    }

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
    """

    content = """
    <div class="e-page">
      <div class="e-page-header">
        <div>
          <div class="e-page-title">Console</div>
          <div class="e-page-sub">Sovereign natural-language operator interface</div>
        </div>
        <button class="btn-refresh" id="co-refresh">Refresh</button>
      </div>

      <div class="co-stats">
        <div class="e-stat teal">
          <div class="e-stat-label">Commands · lifetime</div>
          <div class="e-stat-value teal" id="stat-cmds">—</div>
          <div class="e-stat-delta up">received</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Actions resolved</div>
          <div class="e-stat-value" id="stat-resolved">—</div>
          <div class="e-stat-delta" id="stat-resolved-delta">parse rate</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">Executed</div>
          <div class="e-stat-value" id="stat-executed">—</div>
          <div class="e-stat-delta">committed</div>
        </div>
        <div class="e-stat amber">
          <div class="e-stat-label">Router errors</div>
          <div class="e-stat-value" id="stat-errors">—</div>
          <div class="e-stat-delta warn">Claude failures</div>
        </div>
      </div>

      <div class="e-panel">
        <div class="console-input-wrap">
          <span class="console-prompt">›</span>
          <input class="console-input" id="cmd-input"
                 placeholder="Type a command — e.g. 'approve contractor Acme Restoration' or 'show last 10 payouts'"
                 autofocus autocomplete="off" spellcheck="false">
        </div>
        <div class="console-hint">
          <kbd>Enter</kbd> parse · <kbd>Esc</kbd> clear · destructive actions require confirmation
        </div>

        <div id="preview-slot" style="margin-top:16px;"></div>
      </div>

      <div class="e-panel" style="margin-top:14px;">
        <div class="e-section-label" style="margin-bottom:8px;">Recent commands</div>
        <div id="history-list">
          <div class="empty-state">No commands yet · type one above to begin</div>
        </div>
      </div>

      <div class="e-panel" style="margin-top:14px;">
        <button class="catalog-toggle" id="catalog-toggle">▸ Available actions for your role</button>
        <div class="catalog-body" id="catalog-body">
          <div class="empty-state">Loading...</div>
        </div>
      </div>
    </div>
    """

    extra_js = """
    <script>
    (function() {
      const escape = s => String(s == null ? '' : s).replace(/[&<>"']/g, c =>
        ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
      const fmtTime = ts => new Date(ts).toLocaleTimeString(undefined,
        {hour: '2-digit', minute: '2-digit'});

      const HISTORY_KEY = 'empire_console_history';

      async function api(path, opts) {
        const r = await fetch(path, Object.assign({credentials: 'same-origin'}, opts || {}));
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.detail || data.error || (path + ' → ' + r.status));
        return data;
      }

      // ── HISTORY ──
      function loadHistory() {
        try { return JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]'); }
        catch { return []; }
      }
      function pushHistory(entry) {
        const h = loadHistory();
        h.unshift(entry);
        localStorage.setItem(HISTORY_KEY, JSON.stringify(h.slice(0, 12)));
        renderHistory();
      }
      function renderHistory() {
        const h = loadHistory();
        const wrap = document.getElementById('history-list');
        if (!h.length) {
          wrap.innerHTML = '<div class="empty-state">No commands yet · type one above to begin</div>';
          return;
        }
        wrap.innerHTML = h.map(e => `
          <div class="history-row ${e.destructive ? 'destructive' : ''}" data-cmd="${escape(e.cmd)}">
            <span class="h-when">${fmtTime(e.ts)}</span>
            <span class="h-cmd">${escape(e.cmd)}</span>
            <span class="h-action">${escape(e.action || '—')}</span>
          </div>
        `).join('');
        wrap.querySelectorAll('.history-row').forEach(row => {
          row.addEventListener('click', () => {
            input.value = row.dataset.cmd;
            input.focus();
          });
        });
      }

      // ── STATS ──
      function renderStats(stats) {
        document.getElementById('stat-cmds').textContent     = stats.commands_received ?? '—';
        document.getElementById('stat-resolved').textContent = stats.actions_resolved  ?? '—';
        document.getElementById('stat-executed').textContent = stats.actions_executed  ?? '—';
        document.getElementById('stat-errors').textContent   = stats.router_errors     ?? '—';
        const rate = stats.commands_received > 0
          ? Math.round(100 * (stats.actions_resolved || 0) / stats.commands_received) + '%'
          : '—';
        document.getElementById('stat-resolved-delta').textContent = rate + ' of parsed';
      }

      // ── ACTION CATALOG ──
      function renderCatalog(actions) {
        const wrap = document.getElementById('catalog-body');
        if (!actions.length) {
          wrap.innerHTML = '<div class="empty-state">No actions available for your role</div>';
          return;
        }
        wrap.innerHTML = `<div class="action-grid">${actions.map(a => {
          const params = Object.entries(a.params || {});
          const paramList = params.length
            ? params.map(([n, def]) =>
                `${n}${def.required ? '*' : ''}:${def.type || 'any'}`).join(' · ')
            : 'no params';
          return `
            <div class="action-tile ${a.destructive ? 'destructive' : ''}">
              <div class="action-name">
                ${escape(a.name)}
                ${a.destructive ? '<span class="destructive-badge">destructive</span>' : ''}
              </div>
              <div class="action-desc">${escape(a.description || '')}</div>
              <div class="action-params">${escape(paramList)}</div>
            </div>
          `;
        }).join('')}</div>`;
      }

      // ── PREVIEW + EXECUTE ──
      const previewSlot = document.getElementById('preview-slot');
      const input = document.getElementById('cmd-input');

      function showPreview(parsed, command) {
        const isDestructive = !!parsed.destructive;
        const classes = ['preview-card'];
        if (isDestructive) classes.push('destructive');

        const explanation = parsed.explanation || '(no explanation returned)';
        const paramsBlock = parsed.params && Object.keys(parsed.params).length
          ? `<div class="preview-params">${escape(JSON.stringify(parsed.params, null, 2))}</div>`
          : '';
        const warn = isDestructive
          ? `<div class="preview-warn">⚠ Destructive action — irreversible. Confirm before executing.</div>`
          : '';

        previewSlot.innerHTML = `
          <div class="${classes.join(' ')}">
            <div class="preview-head">
              <div class="preview-action">${escape(parsed.action || '—')}</div>
              <div class="preview-cmd">"${escape(command)}"</div>
            </div>
            <div class="preview-explanation">${escape(explanation)}</div>
            ${paramsBlock}
            ${warn}
            <div class="preview-actions">
              <button class="btn-execute ${isDestructive ? 'destructive' : ''}" id="btn-exec">
                ${isDestructive ? 'Confirm & execute' : 'Execute'}
              </button>
              <button class="btn-cancel" id="btn-cancel">Cancel</button>
            </div>
          </div>
        `;

        document.getElementById('btn-cancel').addEventListener('click', () => {
          previewSlot.innerHTML = '';
          input.focus();
        });
        document.getElementById('btn-exec').addEventListener('click', () => execute(parsed, command));
      }

      function showError(msg, command) {
        previewSlot.innerHTML = `
          <div class="preview-card error">
            <div class="preview-head">
              <div class="preview-action">Could not route</div>
              ${command ? `<div class="preview-cmd">"${escape(command)}"</div>` : ''}
            </div>
            <div class="preview-explanation">${escape(msg)}</div>
            <div class="preview-actions">
              <button class="btn-cancel" id="btn-cancel">Dismiss</button>
            </div>
          </div>
        `;
        document.getElementById('btn-cancel').addEventListener('click', () => {
          previewSlot.innerHTML = '';
          input.focus();
        });
      }

      function showResult(parsed, result, command) {
        const ok = result && (result.ok !== false);
        const cardClass = ok ? 'success' : 'error';
        previewSlot.innerHTML = `
          <div class="preview-card ${cardClass}">
            <div class="preview-head">
              <div class="preview-action">${escape(parsed.action)} · ${ok ? 'executed' : 'failed'}</div>
              <div class="preview-cmd">"${escape(command)}"</div>
            </div>
            <div class="preview-result">${escape(JSON.stringify(result, null, 2))}</div>
            <div class="preview-actions">
              <button class="btn-cancel" id="btn-cancel">Done</button>
            </div>
          </div>
        `;
        document.getElementById('btn-cancel').addEventListener('click', () => {
          previewSlot.innerHTML = '';
          input.focus();
        });
      }

      async function parse(command) {
        input.disabled = true;
        previewSlot.innerHTML = '<div class="empty-state">Routing through Claude...</div>';
        try {
          const r = await api('/api/v1/console/parse', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({command}),
          });
          if (!r.ok) {
            showError(r.error || 'Router returned no action', command);
            return;
          }
          if (!r.action) {
            showError(r.explanation || 'Claude could not map this to an action — try being more specific.', command);
            return;
          }
          showPreview(r, command);
        } catch (e) {
          showError(e.message, command);
        } finally {
          input.disabled = false;
          input.focus();
          // Refresh stats — parse increments commands_received
          api('/api/v1/console/stats').then(renderStats).catch(() => {});
        }
      }

      async function execute(parsed, command) {
        const btn = document.getElementById('btn-exec');
        if (btn) { btn.disabled = true; btn.textContent = 'Executing...'; }
        try {
          const r = await api('/api/v1/console/execute', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({action: parsed.action, params: parsed.params || {}}),
          });
          showResult(parsed, r, command);
          pushHistory({
            ts:          Date.now(),
            cmd:         command,
            action:      parsed.action,
            destructive: !!parsed.destructive,
          });
          input.value = '';
        } catch (e) {
          showResult(parsed, {ok: false, error: e.message}, command);
        } finally {
          api('/api/v1/console/stats').then(renderStats).catch(() => {});
        }
      }

      // ── INPUT WIRING ──
      input.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' && !ev.shiftKey) {
          ev.preventDefault();
          const cmd = input.value.trim();
          if (cmd) parse(cmd);
        } else if (ev.key === 'Escape') {
          input.value = '';
          previewSlot.innerHTML = '';
        }
      });

      // Catalog toggle
      const catalogToggle = document.getElementById('catalog-toggle');
      const catalogBody = document.getElementById('catalog-body');
      catalogToggle.addEventListener('click', () => {
        catalogBody.classList.toggle('open');
        const isOpen = catalogBody.classList.contains('open');
        catalogToggle.textContent = (isOpen ? '▾' : '▸') + ' Available actions for your role';
      });

      document.getElementById('co-refresh').addEventListener('click', refresh);

      async function refresh() {
        try {
          const [stats, actions] = await Promise.all([
            api('/api/v1/console/stats'),
            api('/api/v1/console/actions'),
          ]);
          renderStats(stats);
          renderCatalog(actions.actions || []);
        } catch (e) {
          console.error('[console] refresh failed', e);
        }
      }

      renderHistory();
      refresh();
    })();
    </script>
    """

    return base_layout(
        title="Console",
        subtitle="Sovereign Operator",
        content=content,
        active_module="console",
        extra_css=extra_css,
        extra_js=extra_js,
    )
