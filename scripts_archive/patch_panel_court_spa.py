"""Update Panel Court SPA component: show 10-agent pool with win rates."""
with open('/root/empire-v49/empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# 1. Update SECTIONS label
old_section = "{ id: 'panel_court',      label: 'Panel Court',    sub: '5-Panel consensus · CFO · Purist · Judge' },"
new_section = "{ id: 'panel_court',      label: 'Panel Court',    sub: '10-Agent ensemble · voting · learning' },"
if old_section in content:
    content = content.replace(old_section, new_section)
    changes += 1
    print("1. SECTIONS label: updated")

# 2. Replace the PanelCourtPanel component body (after the fetch line)
# The old component starts after "function PanelCourtPanel() {" and ends before the next "function"
old_start = "function PanelCourtPanel() {"
old_end = "// ── OPERATORS"

# Find the component boundaries
start_idx = content.find(old_start)
if start_idx == -1:
    print("ERROR: PanelCourtPanel not found")
else:
    # Find the next function after it to get the end
    end_idx = content.find(old_end, start_idx)
    if end_idx == -1:
        end_idx = content.find("function ", start_idx + len(old_start))
    
    new_component = '''function PanelCourtPanel() {
  const [data, setData] = useState(null);
  const [pool, setPool] = useState(null);
  const [err, setErr] = useState(null);
  const [expanded, setExpanded] = useState(null);

  useEffect(() => {
    Promise.all([
      apiFetch('/api/panel_court/decisions?limit=30').then(r => r.json()),
      apiFetch('/api/panel_court/pool').then(r => r.json()),
    ]).then(([decisions, poolData]) => {
      setData(decisions.decisions || []);
      setPool(poolData.agents || []);
    }).catch(e => setErr(e.message));
  }, []);

  const poolErr = pool && pool.error;
  if (err) return html`<div class="stub"><div class="stub-title">Could not load Panel Court</div><div class="stub-body">${err}</div></div>`;
  if (!data) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  const dispatched = data.filter(d => d.verdict === 'DISPATCH').length;
  const rejected = data.filter(d => d.verdict === 'REJECT').length;
  const avgScore = data.length > 0 ? Math.round(data.reduce((s, d) => s + (d.score || 0), 0) / data.length) : 0;
  const totalRuns = pool && pool.agents ? pool.agents.reduce((s, a) => s + (a.total_runs || 0), 0) : 0;

  // Agent pool sorted by win rate
  const agents = (pool && pool.agents ? [...pool.agents] : []).sort((a, b) => (b.win_rate || 0) - (a.win_rate || 0));

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Panel Court <em>10-Agent Ensemble</em></div>
          <div class="section-sub">Parallel scoring · 5-role voting · learning loop</div>
        </div>
        <div class="section-sub">${data.length} decisions · ${totalRuns} agent runs</div>
      </div>

      <!-- ── Summary Cards ── -->
      <div class="pc-summary-grid">
        <div class="pc-summary-card">
          <div class="pc-summary-val teal">${dispatched}</div>
          <div class="pc-summary-lbl">Dispatched</div>
        </div>
        <div class="pc-summary-card">
          <div class="pc-summary-val amber">${rejected}</div>
          <div class="pc-summary-lbl">Rejected</div>
        </div>
        <div class="pc-summary-card">
          <div class=${'pc-summary-val ' + (avgScore >= 80 ? 'teal' : avgScore >= 60 ? 'amber' : 'red')}>${avgScore}</div>
          <div class="pc-summary-lbl">Avg Score</div>
        </div>
        <div class="pc-summary-card">
          <div class="pc-summary-val dim">${totalRuns}</div>
          <div class="pc-summary-lbl">Agent Runs</div>
        </div>
      </div>

      <!-- ── 10-Agent Pool Grid ── -->
      ${agents.length > 0 ? html`
      <div class="pc-pool-panel">
        <div class="pc-pool-head">
          <span class="pc-pool-title">Agent Pool</span>
          <span class="pc-pool-tag">${agents.filter(a => a.total_runs > 0).length}/10 active</span>
        </div>
        <div class="pc-pool-grid">
          ${agents.map(a => {
            const wr = a.win_rate || 0;
            const wrPct = Math.round(wr * 100);
            const tempCls = a.temperature <= 0.3 ? 'cold' : a.temperature >= 0.55 ? 'hot' : 'warm';
            const wonLast = data.length > 0 && data[0].winner_agent_id === a.id;
            return html`
              <div class=${'pc-agent-card' + (wonLast ? ' winner' : '')}>
                <div class="pc-agent-top">
                  <span class="pc-agent-id">#${a.id}</span>
                  <span class=${'pc-agent-temp ' + tempCls}>${a.temperature.toFixed(2)}°</span>
                </div>
                <div class="pc-agent-wins">
                  <span class="pc-agent-wr">${wrPct}%</span>
                  <span class="pc-agent-wl">${a.wins}W ${a.losses}L</span>
                </div>
                <div class="pc-agent-bar-wrap">
                  <div class="pc-agent-bar" style=${{width: Math.max(2, wrPct) + '%'}}></div>
                </div>
                <div class="pc-agent-runs">${a.total_runs} runs</div>
                ${wonLast ? html`<div class="pc-agent-won">★ Last Winner</div>` : ''}
              </div>
            `;
          })}
        </div>
      </div>
      ` : ''}

      <!-- ── Decision List ── -->
      <div class="pc-decision-panel">
        <div class="pc-decision-head">
          <span class="pc-decision-title">Ensemble History</span>
          <span class="pc-decision-count">${data.length} decisions</span>
        </div>
        ${data.length === 0 ? html`
          <div class="tbl-empty">No ensemble decisions yet — run the dispatcher to see Panel Court in action.</div>
        ` : html`
        <div class="pc-decision-list">
          ${data.map(d => {
            const isExpanded = expanded === d.lead_id;
            const scores = typeof d.per_agent_scores === 'string' ? JSON.parse(d.per_agent_scores || '{}') : (d.per_agent_scores || {});
            const winner = d.winner_agent_id;
            return html`
              <div class=${'pc-decision-card' + (isExpanded ? ' expanded' : '')} onClick=${() => setExpanded(isExpanded ? null : d.lead_id)}>
                <div class="pc-decision-row">
                  <div class="pc-decision-lead">
                    <span class="pc-decision-lead-name">${d.lead_summary || '—'}</span>
                    <span class="pc-decision-lead-id">${(d.lead_id || '').slice(0, 12)}</span>
                  </div>
                  <div class="pc-decision-winner">
                    <span class="pc-winner-badge">Agent #${winner}</span>
                  </div>
                  <div class=${'pc-score-circle ' + (d.score >= 80 ? 'pc-score-ok' : d.score >= 50 ? 'pc-score-warn' : 'pc-score-bad')}>
                    ${d.score || '—'}
                  </div>
                  <div class="pc-decision-verdict">
                    <span class=${'pc-verdict-badge ' + (d.verdict === 'DISPATCH' ? 'dispatch' : 'reject')}>${d.verdict || '?'}</span>
                  </div>
                </div>
                ${isExpanded ? html`
                <div class="pc-decision-detail">
                  <div class="pc-detail-title">Per-Agent Scores</div>
                  <div class="pc-detail-scores">
                    ${Object.entries(scores).map(([aid, score]) => {
                      const isWinner = parseInt(aid) === winner;
                      return html`
                        <div class=${'pc-detail-score' + (isWinner ? ' winner' : '')}>
                          <span class="pc-detail-aid">Agent #${aid}</span>
                          <span class="pc-detail-pts">${score}</span>
                        </div>
                      `;
                    })}
                  </div>
                  ${d.judge_reasoning ? html`
                    <div class="pc-judge-block">
                      <div class="pc-judge-head">AGI Judge</div>
                      <div class="pc-judge-reasoning">${d.judge_reasoning}</div>
                    </div>
                  ` : ''}
                </div>
                ` : ''}
              </div>
            `;
          })}
        </div>
        `}
      </div>
    </div>
  `;
}'''

    content = content[:start_idx] + new_component + "\n" + content[end_idx:]
    changes += 1
    print("2. PanelCourtPanel component: replaced")

with open('/root/empire-v49/empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"Done: {changes} changes applied")
