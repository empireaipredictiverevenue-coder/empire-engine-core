"""
Empire V49 · Cinematic Command Deck (Owner Mode)
=================================================
The flagship view. Single-screen total situational awareness:
- Live call/strike feed (subscribed to /ws/live)
- Corridor heatmap with gradient fills
- Subconscious Mind status with brain decision log
- Revenue stream (USDC inflows from Solana watcher)
- Infrastructure health pulse

Wire-up in hub.py:
    from empire_command_deck import command_deck_view

    @app.get("/view/command", response_class=HTMLResponse)
    async def view_command(token: str = ""):
        return HTMLResponse(command_deck_view(token=token))

This becomes the default landing view after the splash gateway.
"""

from empire_layout import base_layout
from empire_live import LIVE_CLIENT_JS


def command_deck_view(token: str = "") -> str:
    """Render the Cinematic Command Deck (Owner Mode)."""

    extra_css = """
    /* Command Deck specific layout */
    .deck-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 16px;
    }
    .deck-main {
      display: grid;
      grid-template-columns: 1.4fr 1fr;
      gap: 12px;
      margin-bottom: 16px;
    }
    .deck-infra {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 10px;
    }
    @media (max-width: 1000px) {
      .deck-grid, .deck-infra { grid-template-columns: repeat(2, 1fr); }
      .deck-main { grid-template-columns: 1fr; }
    }

    /* Brain decision log */
    .brain-log {
      max-height: 280px;
      overflow-y: auto;
      padding-right: 4px;
    }
    .brain-row {
      display: flex; align-items: center;
      gap: 12px;
      padding: 10px 12px;
      background: var(--empire-elevated);
      border-radius: var(--radius-sm);
      border-left: 2px solid;
      margin-bottom: 6px;
      font-family: var(--font-mono);
      font-size: 11px;
      animation: empire-fade-up 0.3s var(--ease-out-empire) both;
    }
    .brain-row.go    { border-left-color: var(--signal-teal); }
    .brain-row.no_go { border-left-color: var(--empire-shadow); opacity: 0.7; }
    .brain-row .verdict {
      font-weight: 700;
      letter-spacing: 0.1em;
      flex-shrink: 0;
      width: 48px;
    }
    .brain-row.go .verdict    { color: var(--signal-teal); }
    .brain-row.no_go .verdict { color: var(--empire-mist); }
    .brain-row .target {
      flex: 1; min-width: 0;
      color: var(--empire-silver);
      overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
    }
    .brain-row .urgency {
      color: var(--empire-mist);
      flex-shrink: 0;
    }

    /* Revenue stream */
    .rev-stream {
      max-height: 220px;
      overflow-y: auto;
    }
    .rev-row {
      display: flex; align-items: center; justify-content: space-between;
      padding: 10px 12px;
      background: var(--empire-elevated);
      border-radius: var(--radius-sm);
      border-left: 2px solid var(--signal-teal);
      margin-bottom: 6px;
      animation: empire-fade-up 0.3s var(--ease-out-empire) both;
    }
    .rev-row .amount {
      font-family: var(--font-mono);
      font-weight: 600;
      color: var(--signal-teal);
      font-size: 14px;
    }
    .rev-row .sig {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
    }

    .empty-state {
      padding: 40px 20px;
      text-align: center;
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      letter-spacing: 0.18em;
      text-transform: uppercase;
    }

    /* Connection indicator */
    .conn-status {
      position: fixed;
      bottom: 40px;
      right: 24px;
      z-index: 100;
      padding: 6px 12px;
      background: var(--empire-overlay);
      border: 1px solid var(--empire-divider);
      border-radius: var(--radius-pill);
      font-family: var(--font-mono);
      font-size: 9px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--empire-mist);
      backdrop-filter: blur(20px);
      display: flex; align-items: center; gap: 8px;
      opacity: 0;
      transition: opacity 0.3s;
    }
    .conn-status.visible { opacity: 1; }
    .conn-status.connected { color: var(--signal-teal); border-color: rgba(68, 229, 184, 0.3); }
    .conn-status.disconnected { color: var(--status-amber); border-color: rgba(245, 166, 35, 0.3); }
    """

    content = """
    <div class="e-page">
      <div class="e-page-header">
        <div>
          <div class="e-page-title">Command <em>Deck</em></div>
          <div class="e-page-sub">Owner Mode · Total Situational Awareness</div>
        </div>
        <div class="e-pulse-pill">
          <span class="e-pulse-dot"></span>
          <span id="conn-text">Connecting</span>
        </div>
      </div>

      <!-- Top stat row -->
      <div class="deck-grid">
        <div class="e-stat teal">
          <div class="e-stat-label">Live Calls</div>
          <div class="e-stat-value teal" id="stat-calls">—</div>
          <div class="e-stat-delta" id="stat-calls-delta">tracking</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Revenue Today</div>
          <div class="e-stat-value" id="stat-revenue">$0</div>
          <div class="e-stat-delta up" id="stat-revenue-delta">USDC settled</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Brain Decisions</div>
          <div class="e-stat-value" id="stat-brain">0</div>
          <div class="e-stat-delta" id="stat-brain-delta">GO / NO_GO</div>
        </div>
        <div class="e-stat amber">
          <div class="e-stat-label">Strikes Total</div>
          <div class="e-stat-value" id="stat-strikes">0</div>
          <div class="e-stat-delta warn" id="stat-strikes-delta">subconscious</div>
        </div>
      </div>

      <!-- Main panels -->
      <div class="deck-main">
        <!-- Brain Decision Log -->
        <div class="e-panel">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid var(--empire-divider);">
            <span class="e-section-label" style="margin-bottom:0;">Brain Decision Log</span>
            <span class="e-stat-label" id="brain-meta">awaiting</span>
          </div>
          <div class="brain-log" id="brain-log">
            <div class="empty-state">No decisions yet · subconscious mind standing by</div>
          </div>
        </div>

        <!-- Corridor Heatmap -->
        <div class="e-panel">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid var(--empire-divider);">
            <span class="e-section-label" style="margin-bottom:0;">Active Corridors</span>
            <span class="e-stat-label">NWS</span>
          </div>
          <div id="corridor-list">
            <div class="empty-state">Awaiting NWS data</div>
          </div>
        </div>
      </div>

      <!-- Revenue stream + Infra -->
      <div class="deck-main">
        <div class="e-panel">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid var(--empire-divider);">
            <span class="e-section-label" style="margin-bottom:0;">Revenue Stream · USDC</span>
            <span class="e-stat-label" id="rev-meta">Solana watcher</span>
          </div>
          <div class="rev-stream" id="rev-stream">
            <div class="empty-state">No transfers yet · vault standing by</div>
          </div>
        </div>

        <div class="e-panel">
          <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:14px; padding-bottom:12px; border-bottom:1px solid var(--empire-divider);">
            <span class="e-section-label" style="margin-bottom:0;">Infrastructure</span>
            <span class="e-stat-label">Hetzner · Dokku</span>
          </div>
          <div class="deck-infra" style="grid-template-columns: 1fr;">
            <div class="e-stat muted" style="padding:14px 16px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="e-stat-label">Subconscious</span>
                <span class="e-pulse-dot" id="infra-sub-dot"></span>
              </div>
              <div class="e-stat-value" style="font-size:18px; margin-top:6px;" id="infra-sub">—</div>
            </div>
            <div class="e-stat muted" style="padding:14px 16px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="e-stat-label">Manus Sniper</span>
                <span class="e-pulse-dot amber" id="infra-manus-dot"></span>
              </div>
              <div class="e-stat-value" style="font-size:18px; margin-top:6px;" id="infra-manus">Standby</div>
            </div>
            <div class="e-stat muted" style="padding:14px 16px;">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <span class="e-stat-label">Vonage Bridge</span>
                <span class="e-pulse-dot cyan" id="infra-vonage-dot"></span>
              </div>
              <div class="e-stat-value" style="font-size:18px; margin-top:6px;" id="infra-vonage">Hybrid</div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div class="conn-status" id="conn-status">
      <span class="e-pulse-dot" id="conn-dot"></span>
      <span id="conn-label">Connecting</span>
    </div>
    """

    extra_js = LIVE_CLIENT_JS + """
    <script>
    (function() {
      const fmtMoney = n => n != null ? '$' + Math.round(n).toLocaleString() : '$0';
      const fmtNum   = n => n != null ? Number(n).toLocaleString() : '0';
      const trunc    = (s, n) => s && s.length > n ? s.slice(0, n) + '...' : (s || '');

      // ── CONNECTION INDICATOR ──
      const connStatus = document.getElementById('conn-status');
      const connDot    = document.getElementById('conn-dot');
      const connLabel  = document.getElementById('conn-label');
      const connText   = document.getElementById('conn-text');

      function setConn(state) {
        connStatus.classList.add('visible');
        connStatus.classList.remove('connected', 'disconnected');
        connDot.className = 'e-pulse-dot';
        if (state === 'connected') {
          connStatus.classList.add('connected');
          connLabel.textContent = 'Live';
          connText.textContent  = 'Live';
        } else {
          connStatus.classList.add('disconnected');
          connDot.classList.add('amber');
          connLabel.textContent = 'Reconnecting';
          connText.textContent  = 'Reconnecting';
        }
      }

      if (window.EMPIRE_LIVE) {
        window.EMPIRE_LIVE.on('connect',    () => setConn('connected'));
        window.EMPIRE_LIVE.on('disconnect', () => setConn('disconnected'));
      }
      setTimeout(() => { connStatus.classList.add('visible'); }, 300);

      // ── STATS HANDLER (from /ws/live heartbeat) ──
      let revenueToday = 0;
      let dayStart = new Date(); dayStart.setHours(0, 0, 0, 0);

      function updateStats(payload) {
        const agi = payload.agi || {};
        const rev = payload.revenue || {};

        document.getElementById('stat-strikes').textContent = fmtNum(agi.strikes_total);
        document.getElementById('stat-strikes-delta').textContent =
          `cycle ${fmtNum(agi.cycles)} · ${agi.status}`;

        const brainCalls = agi.brain_calls || 0;
        const brainGo    = agi.brain_go || 0;
        document.getElementById('stat-brain').textContent = fmtNum(brainCalls);
        document.getElementById('stat-brain-delta').textContent =
          brainCalls > 0
            ? `${brainGo} GO · ${brainCalls - brainGo} NO_GO`
            : 'GO / NO_GO';

        // Revenue total comes as USDC float
        document.getElementById('stat-revenue').textContent = fmtMoney(rev.total_usdc);

        // Infra panel
        document.getElementById('infra-sub').textContent =
          agi.running ? (agi.status === 'ok' ? 'Online' : agi.status) : 'Offline';
        const subDot = document.getElementById('infra-sub-dot');
        subDot.className = 'e-pulse-dot' + (agi.running ? '' : ' amber');

        document.getElementById('infra-manus').textContent =
          (agi.manus_fired || 0) > 0 ? `${agi.manus_fired} fired` : 'Standby';
      }

      if (window.EMPIRE_LIVE) {
        window.EMPIRE_LIVE.on('stats', updateStats);
      }

      // ── BRAIN DECISIONS ──
      const brainLog = document.getElementById('brain-log');
      const brainRows = [];

      function addBrainDecision(payload) {
        const { decision, target, urgency, reasoning } = payload;
        const isGo = decision === 'GO';
        const row = document.createElement('div');
        row.className = 'brain-row ' + (isGo ? 'go' : 'no_go');
        row.innerHTML = `
          <span class="verdict">${decision}</span>
          <span class="target" title="${target || ''} · ${reasoning || ''}">${trunc(target, 40)}</span>
          <span class="urgency">${urgency != null ? urgency + '/10' : '—'}</span>
        `;
        if (brainLog.querySelector('.empty-state')) brainLog.innerHTML = '';
        brainLog.insertBefore(row, brainLog.firstChild);
        brainRows.unshift(row);
        // Keep last 20
        while (brainRows.length > 20) {
          const dead = brainRows.pop();
          if (dead && dead.parentNode) dead.parentNode.removeChild(dead);
        }
      }

      if (window.EMPIRE_LIVE) {
        window.EMPIRE_LIVE.on('brain', addBrainDecision);
      }

      // ── STRIKES (also bump the strike counter delta) ──
      let recentStrikes = 0;
      if (window.EMPIRE_LIVE) {
        window.EMPIRE_LIVE.on('strike', (payload) => {
          recentStrikes++;
          document.getElementById('stat-calls').textContent = fmtNum(recentStrikes);
          document.getElementById('stat-calls-delta').textContent =
            `+${recentStrikes} since open`;
        });
      }

      // ── REVENUE STREAM ──
      const revStream = document.getElementById('rev-stream');
      const revRows = [];

      function addRevenue(payload) {
        const transfer = payload.transfer || payload;
        if (!transfer || !transfer.amount) return;
        const row = document.createElement('div');
        row.className = 'rev-row';
        row.innerHTML = `
          <div>
            <div style="font-family:var(--font-mono); font-size:11px; color:var(--empire-silver);">
              ${new Date(transfer.ts || Date.now()).toLocaleTimeString()}
            </div>
            <div class="sig">${trunc(transfer.sig || '', 24)}</div>
          </div>
          <div class="amount">+$${Number(transfer.amount).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
        `;
        if (revStream.querySelector('.empty-state')) revStream.innerHTML = '';
        revStream.insertBefore(row, revStream.firstChild);
        revRows.unshift(row);
        while (revRows.length > 15) {
          const dead = revRows.pop();
          if (dead && dead.parentNode) dead.parentNode.removeChild(dead);
        }
        // Bump today's revenue
        revenueToday += Number(transfer.amount);
        document.getElementById('stat-revenue').textContent = fmtMoney(revenueToday);
      }

      if (window.EMPIRE_LIVE) {
        window.EMPIRE_LIVE.on('settlement', addRevenue);
      }

      // ── CORRIDOR HEATMAP — refreshed from /api/live-storm-radar ──
      async function refreshCorridors() {
        try {
          const r = await fetch('/api/live-storm-radar', {
            headers: { Authorization: 'Bearer ' + window.EMPIRE_TOKEN },
          });
          if (!r.ok) return;
          const d = await r.json();
          const list = document.getElementById('corridor-list');
          const alerts = d.alerts || [];
          if (alerts.length === 0) {
            list.innerHTML = '<div class="empty-state">All corridors clear</div>';
            return;
          }
          // Group by area, count locked targets
          const byArea = {};
          alerts.forEach(a => {
            const key = a.area || 'Unknown';
            if (!byArea[key]) byArea[key] = { locked: 0, severity: 'default' };
            byArea[key].locked += a.targets_locked || 0;
            if (a.severity === 'Extreme') byArea[key].severity = 'extreme';
            else if (a.severity === 'Severe' && byArea[key].severity !== 'extreme')
              byArea[key].severity = 'severe';
          });
          const maxLocked = Math.max(1, ...Object.values(byArea).map(v => v.locked));
          list.innerHTML = Object.entries(byArea).slice(0, 6).map(([area, v]) => {
            const pct = (v.locked / maxLocked) * 100;
            return `
              <div class="e-corridor">
                <div class="e-corridor-row">
                  <span class="e-corridor-name">${area}</span>
                  <span class="e-corridor-value">${v.locked} locked</span>
                </div>
                <div class="e-corridor-track">
                  <div class="e-corridor-fill" style="width: ${pct}%;"></div>
                </div>
              </div>
            `;
          }).join('');
        } catch (e) {}
      }
      refreshCorridors();
      setInterval(refreshCorridors, 60000);

      // ── INITIAL DATA FETCH (in case heartbeat hasn't fired yet) ──
      async function initialLoad() {
        try {
          const [subR, revR] = await Promise.all([
            fetch('/api/subconscious', { headers: { Authorization: 'Bearer ' + window.EMPIRE_TOKEN } }),
            fetch('/api/revenue-watch', { headers: { Authorization: 'Bearer ' + window.EMPIRE_TOKEN } }),
          ]);
          if (subR.ok && revR.ok) {
            updateStats({
              agi: await subR.json(),
              revenue: await revR.json(),
            });
          }
        } catch (e) {}
      }
      initialLoad();
    })();
    </script>
    """

    return base_layout(
        title="Command Deck",
        subtitle="Owner Mode",
        content=content,
        active_module="command",
        extra_css=extra_css,
        extra_js=extra_js,
    )
