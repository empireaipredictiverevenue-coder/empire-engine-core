"""
EMPIRE V49 · COMMAND DECK · PAYOUTS
====================================
Owner-only section view for the payouts pipeline. Renders:

  - Stats strip (pending / approved / sent-24h / lifetime)
  - Pending list grouped by settlement tx_signature
  - Recent history table

Live updates via /ws/live subscriptions to:
  - settlement_attributed  (new pending arrives)
  - payout_approved        (group approved)
  - payout_cancelled       (one row cancelled)
  - payout_sent            (Solana txn confirmed)

Wire-up in hub.py:
    from empire_command_payouts import payouts_view
    @app.get("/command/payouts", response_class=HTMLResponse)
    async def view_payouts(op: dict = Depends(require_owner)):
        return HTMLResponse(payouts_view())
"""

from empire_layout import base_layout


def payouts_view() -> str:
    extra_css = """
    .payouts-stats {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin-bottom: 18px;
    }
    @media (max-width: 1000px) {
      .payouts-stats { grid-template-columns: repeat(2, 1fr); }
    }

    .settlement-card {
      background: var(--empire-elevated);
      border: 1px solid var(--empire-divider);
      border-left: 2px solid var(--status-amber);
      border-radius: var(--radius-sm);
      padding: 16px 18px;
      margin-bottom: 12px;
      animation: empire-fade-up 0.3s var(--ease-out-empire) both;
    }
    .settlement-head {
      display: flex; justify-content: space-between; align-items: baseline;
      gap: 16px; margin-bottom: 12px;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .settlement-sig {
      font-family: var(--font-mono); font-size: 12px;
      color: var(--empire-silver); letter-spacing: 0.02em;
    }
    .settlement-meta {
      font-family: var(--font-mono); font-size: 10px;
      color: var(--empire-fog); letter-spacing: 0.12em;
      text-transform: uppercase;
      margin-top: 2px;
    }
    .settlement-total {
      font-family: var(--font-mono); font-weight: 700;
      font-size: 18px; color: var(--signal-teal);
    }

    .split-row {
      display: grid;
      grid-template-columns: 90px 1fr auto 32px;
      gap: 12px;
      align-items: center;
      padding: 8px 0;
      font-size: 12px;
    }
    .split-type {
      font-family: var(--font-mono); font-size: 9px;
      color: var(--empire-fog); letter-spacing: 0.18em;
      text-transform: uppercase;
    }
    .split-recipient { color: var(--empire-silver); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .split-amount   { font-family: var(--font-mono); font-weight: 600; color: var(--empire-white); }
    .split-cancel-btn {
      background: transparent;
      border: 1px solid var(--empire-divider);
      color: var(--empire-fog);
      width: 24px; height: 24px;
      font-family: var(--font-mono); font-size: 14px;
      line-height: 1; cursor: pointer;
      transition: all 0.15s;
      border-radius: 2px;
    }
    .split-cancel-btn:hover { color: var(--status-red); border-color: var(--status-red); }

    .settlement-actions {
      display: flex; gap: 8px; margin-top: 12px;
      padding-top: 10px; border-top: 1px solid var(--empire-divider);
    }
    .btn-approve {
      background: var(--signal-teal); color: #000;
      border: none; padding: 10px 22px;
      font-family: var(--font-ui); font-weight: 700;
      font-size: 12px; letter-spacing: 0.04em;
      cursor: pointer; transition: all 0.15s;
    }
    .btn-approve:hover { background: transparent; color: var(--signal-teal); outline: 1px solid var(--signal-teal); }
    .btn-approve:disabled { opacity: 0.4; cursor: wait; }

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

    .history-table {
      width: 100%; border-collapse: collapse;
      font-family: var(--font-mono); font-size: 11px;
    }
    .history-table th {
      text-align: left; padding: 10px 12px;
      font-size: 9px; letter-spacing: 0.18em;
      text-transform: uppercase; color: var(--empire-fog);
      border-bottom: 1px solid var(--empire-divider);
      font-weight: 400;
    }
    .history-table td {
      padding: 10px 12px;
      color: var(--empire-silver);
      border-bottom: 1px solid var(--empire-divider);
    }
    .history-table tr:last-child td { border-bottom: none; }
    .history-table .h-amt { color: var(--empire-white); font-weight: 600; }
    .history-table .h-sig { color: var(--empire-fog); font-size: 10px; }
    .status-pill {
      display: inline-block;
      padding: 2px 8px;
      font-size: 9px; letter-spacing: 0.14em;
      text-transform: uppercase;
      border-radius: 2px;
    }
    .status-pending   { background: rgba(245,166,35,0.12); color: var(--status-amber); }
    .status-approved  { background: rgba(90,200,250,0.12); color: var(--strike-cyan); }
    .status-executing { background: rgba(90,200,250,0.20); color: var(--strike-cyan); }
    .status-sent      { background: rgba(68,229,184,0.12); color: var(--signal-teal); }
    .status-cancelled { background: rgba(244,63,94,0.10); color: var(--status-red); }
    .status-failed    { background: rgba(244,63,94,0.20); color: var(--status-red); }

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

    content = """
    <div class="e-page">
      <div class="e-page-header">
        <div>
          <div class="e-page-title">Payouts</div>
          <div class="e-page-sub">Pending approvals · settlement queue · history</div>
        </div>
        <button class="btn-refresh" id="po-refresh">Refresh</button>
      </div>

      <div class="payouts-stats">
        <div class="e-stat amber">
          <div class="e-stat-label">Pending settlements</div>
          <div class="e-stat-value" id="stat-pending-count">—</div>
          <div class="e-stat-delta warn" id="stat-pending-sum">awaiting approval</div>
        </div>
        <div class="e-stat cyan">
          <div class="e-stat-label">Approved · awaiting send</div>
          <div class="e-stat-value" id="stat-approved-count">—</div>
          <div class="e-stat-delta" id="stat-approved-sum">queued for Solana</div>
        </div>
        <div class="e-stat teal">
          <div class="e-stat-label">Sent · last 24h</div>
          <div class="e-stat-value teal" id="stat-sent-count">—</div>
          <div class="e-stat-delta up" id="stat-sent-sum">USDC settled</div>
        </div>
        <div class="e-stat">
          <div class="e-stat-label">USDC paid out · lifetime</div>
          <div class="e-stat-value" id="stat-lifetime-sum">—</div>
          <div class="e-stat-delta" id="stat-lifetime-count">total payouts</div>
        </div>
      </div>

      <div class="e-panel">
        <div class="panel-head">
          <span class="e-section-label" style="margin-bottom:0;">Pending Approval</span>
          <span class="e-stat-label" id="pending-meta">—</span>
        </div>
        <div id="pending-list">
          <div class="empty-state">Loading...</div>
        </div>
      </div>

      <div class="e-panel" style="margin-top:14px;">
        <div class="panel-head">
          <span class="e-section-label" style="margin-bottom:0;">Recent History</span>
          <span class="e-stat-label">Last 50</span>
        </div>
        <div id="history-wrap">
          <div class="empty-state">Loading...</div>
        </div>
      </div>
    </div>
    """

    extra_js = """
    <script>
    (function() {
      const fmtMoney = n => '$' + Number(n || 0).toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2});
      const fmtCount = n => Number(n || 0).toLocaleString();
      const trunc    = (s, n) => s && s.length > n ? s.slice(0, n) + '...' : (s || '');
      const fmtTime  = ts => ts ? new Date(ts).toLocaleString(undefined, {month:'short', day:'2-digit', hour:'2-digit', minute:'2-digit'}) : '—';

      async function api(path, opts) {
        const r = await fetch(path, Object.assign({credentials: 'same-origin'}, opts || {}));
        if (!r.ok) throw new Error(path + ' → ' + r.status);
        return r.json();
      }

      function groupBySettlement(rows) {
        const groups = {};
        for (const p of rows) {
          const k = p.tx_sig || '(unattributed)';
          if (!groups[k]) groups[k] = {tx_sig: k, total: 0, payouts: [], contractor_name: null, lead_addr: null, created_at: p.created_at};
          groups[k].payouts.push(p);
          groups[k].total += Number(p.amount_usdc || 0);
          const meta = p.meta || {};
          if (meta.contractor_name && !groups[k].contractor_name) groups[k].contractor_name = meta.contractor_name;
          if (meta.lead_addr && !groups[k].lead_addr) groups[k].lead_addr = meta.lead_addr;
        }
        return Object.values(groups).sort((a,b) => (b.created_at || '').localeCompare(a.created_at || ''));
      }

      function renderPending(rows) {
        const wrap = document.getElementById('pending-list');
        const groups = groupBySettlement(rows);
        document.getElementById('pending-meta').textContent =
          groups.length ? `${groups.length} settlement${groups.length===1?'':'s'} · ${rows.length} payouts` : '';

        if (!groups.length) {
          wrap.innerHTML = '<div class="empty-state">No pending payouts · all clear</div>';
          return;
        }

        wrap.innerHTML = groups.map(g => {
          const splits = g.payouts.map(p => `
            <div class="split-row">
              <span class="split-type">${p.recipient_type || '—'}</span>
              <span class="split-recipient">${(p.meta && p.meta.contractor_name) || p.recipient_wallet || '—'}</span>
              <span class="split-amount">${fmtMoney(p.amount_usdc)}</span>
              <button class="split-cancel-btn" data-payout-id="${p.id}" title="Cancel this payout">×</button>
            </div>
          `).join('');
          return `
            <div class="settlement-card" data-tx="${g.tx_sig}">
              <div class="settlement-head">
                <div>
                  <div class="settlement-sig">${trunc(g.tx_sig, 32)}</div>
                  <div class="settlement-meta">
                    ${g.contractor_name ? g.contractor_name + ' · ' : ''}${g.lead_addr ? trunc(g.lead_addr, 40) : 'no lead address'}
                  </div>
                </div>
                <div class="settlement-total">${fmtMoney(g.total)}</div>
              </div>
              ${splits}
              <div class="settlement-actions">
                <button class="btn-approve" data-tx="${g.tx_sig}">Approve all ${g.payouts.length}</button>
              </div>
            </div>
          `;
        }).join('');
      }

      function renderHistory(rows) {
        const wrap = document.getElementById('history-wrap');
        if (!rows.length) {
          wrap.innerHTML = '<div class="empty-state">No history yet</div>';
          return;
        }
        wrap.innerHTML = `
          <table class="history-table">
            <thead>
              <tr>
                <th>When</th><th>Status</th><th>Recipient</th><th>Amount</th><th>Tx Sig</th>
              </tr>
            </thead>
            <tbody>
              ${rows.map(p => `
                <tr>
                  <td>${fmtTime(p.executed_at || p.approved_at || p.created_at)}</td>
                  <td><span class="status-pill status-${p.status}">${p.status}</span></td>
                  <td>${(p.meta && p.meta.contractor_name) || p.recipient_type || '—'}</td>
                  <td class="h-amt">${fmtMoney(p.amount_usdc)}</td>
                  <td class="h-sig">${trunc(p.tx_sig || '', 20)}</td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }

      function renderStats(pending, history) {
        const pendingSum = pending.reduce((a,p) => a + Number(p.amount_usdc || 0), 0);
        const pendingSettlements = new Set(pending.map(p => p.tx_sig)).size;
        document.getElementById('stat-pending-count').textContent = fmtCount(pendingSettlements);
        document.getElementById('stat-pending-sum').textContent = fmtMoney(pendingSum) + ' awaiting';

        const approved = history.filter(h => h.status === 'approved' || h.status === 'executing');
        document.getElementById('stat-approved-count').textContent = fmtCount(approved.length);
        document.getElementById('stat-approved-sum').textContent =
          fmtMoney(approved.reduce((a,h) => a + Number(h.amount_usdc || 0), 0)) + ' queued';

        const dayAgo = Date.now() - 24*60*60*1000;
        const sent24h = history.filter(h =>
          h.status === 'sent' && h.executed_at && new Date(h.executed_at).getTime() > dayAgo);
        document.getElementById('stat-sent-count').textContent = fmtCount(sent24h.length);
        document.getElementById('stat-sent-sum').textContent =
          fmtMoney(sent24h.reduce((a,h) => a + Number(h.amount_usdc || 0), 0)) + ' settled';

        const lifetimeSent = history.filter(h => h.status === 'sent');
        document.getElementById('stat-lifetime-sum').textContent =
          fmtMoney(lifetimeSent.reduce((a,h) => a + Number(h.amount_usdc || 0), 0));
        document.getElementById('stat-lifetime-count').textContent =
          fmtCount(lifetimeSent.length) + ' payouts';
      }

      let inflight = false;
      async function refresh() {
        if (inflight) return;
        inflight = true;
        try {
          const [pen, hist] = await Promise.all([
            api('/api/v1/payouts/pending'),
            api('/api/v1/payouts/history?limit=50'),
          ]);
          const pending = pen.pending || [];
          const history = hist.history || [];
          renderPending(pending);
          renderHistory(history);
          renderStats(pending, history);
        } catch (e) {
          console.error('[payouts] refresh failed', e);
        } finally {
          inflight = false;
        }
      }

      // Approve / cancel handlers via event delegation
      document.addEventListener('click', async (ev) => {
        const approveBtn = ev.target.closest('.btn-approve');
        if (approveBtn) {
          const tx = approveBtn.dataset.tx;
          approveBtn.disabled = true;
          approveBtn.textContent = 'Approving...';
          try {
            const r = await api('/api/v1/payouts/approve', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({settlement_id: tx}),
            });
            if (!r.ok) throw new Error(r.error || 'approval failed');
          } catch (e) {
            approveBtn.disabled = false;
            approveBtn.textContent = 'Retry';
            alert('Approval failed: ' + e.message);
          }
          // refresh comes via WS · also force-refresh in case of WS lag
          setTimeout(refresh, 400);
          return;
        }

        const cancelBtn = ev.target.closest('.split-cancel-btn');
        if (cancelBtn) {
          const id = cancelBtn.dataset.payoutId;
          if (!confirm('Cancel this payout? Other splits in the same settlement stay pending.')) return;
          try {
            await api('/api/v1/payouts/cancel', {
              method: 'POST',
              headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({payout_id: id}),
            });
          } catch (e) {
            alert('Cancel failed: ' + e.message);
          }
          setTimeout(refresh, 400);
        }
      });

      document.getElementById('po-refresh').addEventListener('click', refresh);

      // ── LIVE: re-fetch on relevant WS events ──
      function bindLive() {
        if (!window.EMPIRE_LIVE || !window.EMPIRE_LIVE.on) {
          return setTimeout(bindLive, 400);
        }
        ['settlement_attributed', 'payout_approved', 'payout_cancelled', 'payout_sent']
          .forEach(t => window.EMPIRE_LIVE.on(t, refresh));
      }
      bindLive();

      // initial load
      refresh();
    })();
    </script>
    """

    return base_layout(
        title="Payouts",
        subtitle="Operator Console",
        content=content,
        active_module="payouts",
        extra_css=extra_css,
        extra_js=extra_js,
    )
