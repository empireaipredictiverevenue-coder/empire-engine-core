"""
EMPIRE V49 · FLEET DASHBOARD
=============================
Full-screen SPA dashboard showing every agent as an independent OS instance.
Each agent card shows:
  - Vault (SOUL + SKILLS + knowledge notes)
  - Status (online/offline/error)
  - Capabilities / skills
  - Last heartbeat
  - Live IPC events

Architecture:
  - React 18 + htm via esm.sh import map (no build step)
  - Bearer auth via localStorage.hub_token
  - WebSocket /ws/live for live event tail
  - Routes: /fleet
"""

from empire_tokens import EMPIRE_FONTS, EMPIRE_TOKENS_CSS, EMPIRE_BASE_CSS


def fleet_dashboard_page() -> str:
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Empire AI · Fleet Dashboard</title>
{EMPIRE_FONTS}
<style>{EMPIRE_TOKENS_CSS}</style>
<style>{EMPIRE_BASE_CSS}</style>
<style>{_FLEET_CSS}</style>
</head>
<body>
<div id="root"></div>
<script type="importmap">
{{
  "imports": {{
    "react":           "https://esm.sh/react@18.3.1",
    "react-dom/client":"https://esm.sh/react-dom@18.3.1/client",
    "htm":             "https://esm.sh/htm@3.1.1"
  }}
}}
</script>
<script type="module">{_FLEET_JS}</script>
</body>
</html>"""


_FLEET_CSS = """
* { margin:0; padding:0; box-sizing:border-box; }
:root {
  --bg: #030812;
  --surface: #0B1729;
  --elevated: #11243F;
  --border: rgba(122,140,163,0.15);
  --border-hi: rgba(122,140,163,0.3);
  --text: #F0F4F8;
  --text-sec: #94A3B8;
  --text-muted: #4A5A72;
  --accent: #44E5B8;
  --accent-dim: rgba(68,229,184,0.08);
  --blue: #5AC8FA;
  --amber: #F59E0B;
  --red: #F43F5E;
  --font-mono: 'SF Mono','Fira Code','JetBrains Mono',monospace;
  --font-display: 'Geist','Inter',system-ui,sans-serif;
}
html,body { height:100%; background:var(--bg); color:var(--text); font-family:var(--font-display); overflow-x:hidden; }

/* ── TOP BAR ────────────────────────────────────────────────── */
.fleet-topbar {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 28px;
  border-bottom: 1px solid var(--border);
  background: var(--surface);
  position: sticky; top: 0; z-index: 10;
}
.fleet-logo {
  display: flex; align-items: center; gap: 12px;
  font-family: var(--font-mono); font-size: 10px;
  letter-spacing: 0.2em; text-transform: uppercase;
  color: var(--accent);
}
.fleet-logo .dot {
  width: 7px; height: 7px; border-radius: 50%;
  background: var(--accent);
  animation: fpulse 1.6s ease-in-out infinite;
}
@keyframes fpulse {
  0%,100% { opacity:1; box-shadow:0 0 0 0 rgba(68,229,184,0.4); }
  50% { opacity:.6; box-shadow:0 0 0 8px rgba(68,229,184,0); }
}
.fleet-topbar-right {
  display: flex; align-items: center; gap: 20px;
  font-family: var(--font-mono); font-size: 9px;
  color: var(--text-muted); letter-spacing: 0.1em;
}
.fleet-count {
  display: flex; align-items: center; gap: 6px;
}
.fleet-count strong { color: var(--accent); font-weight: 500; }

/* ── AGENT GRID ─────────────────────────────────────────────── */
.fleet-agents {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(420px, 1fr));
  gap: 16px;
  padding: 20px 28px;
}

/* ── AGENT CARD ─────────────────────────────────────────────── */
.agent-card {
  background: var(--surface);
  border: 1px solid var(--border);
  transition: border-color 0.2s ease;
  overflow: hidden;
  display: flex; flex-direction: column;
}
.agent-card:hover { border-color: var(--border-hi); }

.agent-card-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  cursor: pointer;
  transition: background 0.15s;
}
.agent-card-header:hover { background: rgba(255,255,255,0.01); }

.agent-card-info { display: flex; align-items: center; gap: 12px; }
.agent-card-avatar {
  width: 36px; height: 36px; border-radius: 6px;
  display: flex; align-items: center; justify-content: center;
  font-size: 18px;
  flex-shrink: 0;
}
.agent-card-avatar.brain { background: rgba(68,229,184,0.12); }
.agent-card-avatar.storm { background: rgba(90,200,250,0.12); }
.agent-card-avatar.traffic { background: rgba(245,158,11,0.12); }
.agent-card-avatar.revenue { background: rgba(57,255,20,0.12); }
.agent-card-avatar.hermes { background: rgba(200,162,200,0.12); }
.agent-card-avatar.contractor { background: rgba(244,63,94,0.12); }
.agent-card-avatar.trading { background: rgba(255,215,0,0.12); }

.agent-card-name { font-weight: 500; font-size: 14px; color: var(--text); }
.agent-card-role { font-family: var(--font-mono); font-size: 9px; color: var(--text-muted); letter-spacing: 0.1em; text-transform: uppercase; margin-top: 2px; }

.agent-card-status {
  font-family: var(--font-mono); font-size: 8px;
  letter-spacing: 0.14em; text-transform: uppercase;
  padding: 4px 10px; border-radius: 4px; border: 1px solid;
  display: flex; align-items: center; gap: 6px;
}
.agent-card-status.online { color: var(--accent); border-color: var(--accent-dim); }
.agent-card-status.offline { color: var(--text-muted); border-color: var(--border); }
.agent-card-status.error { color: var(--red); border-color: rgba(244,63,94,0.25); }
.agent-card-status-dot {
  width: 5px; height: 5px; border-radius: 50%; background: currentColor;
}
.agent-card-status.online .agent-card-status-dot {
  box-shadow: 0 0 6px rgba(68,229,184,0.6);
  animation: fpulse 1.6s ease-in-out infinite;
}

/* ── AGENT CARD BODY (expandable) ───────────────────────────── */
.agent-card-body {
  max-height: 0;
  overflow: hidden;
  transition: max-height 0.35s ease, padding 0.25s ease;
  padding: 0 20px;
}
.agent-card.expanded .agent-card-body {
  max-height: 2000px;
  padding: 16px 20px;
}

/* ── TABS INSIDE BODY ───────────────────────────────────────── */
.agent-tabs { display: flex; gap: 0; border-bottom: 1px solid var(--border); margin-bottom: 14px; }
.agent-tab {
  padding: 8px 16px;
  font-family: var(--font-mono); font-size: 9px;
  letter-spacing: 0.12em; text-transform: uppercase;
  color: var(--text-muted);
  cursor: pointer; background: none; border: none;
  border-bottom: 2px solid transparent;
  transition: all 0.15s;
}
.agent-tab:hover { color: var(--text-sec); }
.agent-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

/* ── SOUL section ───────────────────────────────────────────── */
.soul-block {
  font-size: 12px; color: var(--text-sec);
  line-height: 1.7; max-height: 200px; overflow-y: auto;
  white-space: pre-wrap;
  font-family: var(--font-mono);
  padding: 10px 12px;
  background: rgba(0,0,0,0.2);
  border-left: 2px solid var(--accent-dim);
}
.soul-block::-webkit-scrollbar { width: 3px; }
.soul-block::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── SKILLS section ─────────────────────────────────────────── */
.skill-list { display: flex; flex-direction: column; gap: 6px; }
.skill-item {
  background: rgba(0,0,0,0.15);
  padding: 8px 12px;
  border-left: 2px solid var(--blue);
  transition: border-color 0.15s;
}
.skill-item:hover { border-left-color: var(--accent); }
.skill-name {
  font-family: var(--font-mono); font-size: 11px;
  color: var(--blue); font-weight: 500;
  letter-spacing: 0.04em;
}
.skill-desc { font-size: 11px; color: var(--text-sec); margin-top: 2px; line-height: 1.5; }
.skill-dep {
  font-family: var(--font-mono); font-size: 9px;
  color: var(--text-muted); margin-top: 4px;
  letter-spacing: 0.06em;
}

/* ── KNOWLEDGE section ──────────────────────────────────────── */
.knowledge-list { display: flex; flex-direction: column; gap: 8px; }
.knowledge-item {
  background: rgba(0,0,0,0.15);
  padding: 10px 12px;
  border: 1px solid var(--border);
}
.knowledge-item-title {
  font-family: var(--font-mono); font-size: 10px;
  color: var(--accent); letter-spacing: 0.08em;
  margin-bottom: 4px;
}
.knowledge-item-preview {
  font-size: 11px; color: var(--text-sec);
  line-height: 1.5; max-height: 80px; overflow-y: hidden;
}

/* ── KPIs ───────────────────────────────────────────────────── */
.agent-kpis {
  display: grid; grid-template-columns: repeat(2, 1fr);
  gap: 8px; margin-top: 12px;
}
.agent-kpi {
  background: rgba(0,0,0,0.15);
  padding: 8px 10px;
  text-align: center;
}
.agent-kpi-label {
  font-family: var(--font-mono); font-size: 8px;
  color: var(--text-muted); letter-spacing: 0.12em;
  text-transform: uppercase; margin-bottom: 2px;
}
.agent-kpi-value {
  font-family: var(--font-mono); font-size: 16px;
  color: var(--accent); font-weight: 500;
}
.agent-kpi-value.dim { color: var(--text-sec); }
.agent-kpi-value.amber { color: var(--amber); }
.agent-kpi-value.blue { color: var(--blue); }
.agent-kpi-value.red { color: var(--red); }

/* ── EMPTY / LOADING ────────────────────────────────────────── */
.fleet-loading {
  display: flex; flex-direction: column;
  align-items: center; justify-content: center;
  height: 60vh; text-align: center;
  color: var(--text-muted);
}
.fleet-loading .spinner {
  width: 24px; height: 24px; border-radius: 50%;
  border: 2px solid var(--border);
  border-top-color: var(--accent);
  animation: spin 0.8s linear infinite;
  margin-bottom: 16px;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── LIVE EVENTS BAR ────────────────────────────────────────── */
.fleet-live-bar {
  position: fixed; bottom: 0; left: 0; right: 0;
  height: 40px;
  background: var(--surface);
  border-top: 1px solid var(--border);
  display: flex; align-items: center;
  padding: 0 28px;
  font-family: var(--font-mono); font-size: 9px;
  color: var(--text-muted); gap: 16px;
  z-index: 20;
}
.fleet-live-dot {
  width: 6px; height: 6px; border-radius: 50%;
  background: var(--accent);
  animation: fpulse 1.2s ease-in-out infinite;
}
.fleet-live-event {
  flex: 1; overflow: hidden;
  white-space: nowrap; text-overflow: ellipsis;
  color: var(--text-sec);
}

/* ── RESPONSIVE ─────────────────────────────────────────────── */
@media (max-width: 900px) {
  .fleet-agents { grid-template-columns: 1fr; padding: 14px; }
  .fleet-topbar { padding: 10px 16px; }
}

/* ── FEATURED SECTION: OS RUNTIME ───────────────────────────── */
.os-runtime {
  display: grid; grid-template-columns: 1fr 1fr;
  gap: 8px; margin-top: 12px;
}
.os-runtime-item {
  padding: 6px 10px;
  background: rgba(0,0,0,0.12);
  font-family: var(--font-mono); font-size: 9px;
  color: var(--text-sec); letter-spacing: 0.06em;
}
.os-runtime-label { color: var(--text-muted); font-size: 8px; letter-spacing: 0.1em; text-transform: uppercase; }
.os-runtime-value { color: var(--text); font-weight: 500; }
.os-runtime-value.accent { color: var(--accent); }
"""

_FLEET_JS = """
(function() {
  const TOKEN = window.EMPIRE_TOKEN || localStorage.getItem('hub_token') || '';
  const root = document.getElementById('root');

  // ── AGENT OS DEFINITIONS ──────────────────────────────────────────
  const AGENT_OS = [
    {
      id: 'brain',
      icon: '🧠',
      name: 'Brain',
      role: 'Decision Engine',
      vaultPath: '/agent_os/brain_os',
      color: 'brain',
    },
    {
      id: 'storm',
      icon: '🌪️',
      name: 'Storm Orchestrator',
      role: 'NWS Alert Pipeline',
      vaultPath: '/agent_os/storm_os',
      color: 'storm',
    },
    {
      id: 'traffic',
      icon: '📊',
      name: 'Traffic Director',
      role: 'Channel Optimization',
      vaultPath: '/agent_os/traffic_os',
      color: 'traffic',
    },
    {
      id: 'revenue',
      icon: '💰',
      name: 'Revenue Forecaster',
      role: 'Predictive Modeling',
      vaultPath: '/agent_os/revenue_os',
      color: 'revenue',
    },
    {
      id: 'hermes',
      icon: '🔗',
      name: 'Hermes Mesh',
      role: 'Task Queue Orchestrator',
      vaultPath: '/agent_os/hermes_os',
      color: 'hermes',
    },
    {
      id: 'contractor',
      icon: '👷',
      name: 'Contractor Sniper',
      role: 'Recruitment & Onboarding',
      vaultPath: '/agent_os/contractor_os',
      color: 'contractor',
    },
    {
      id: 'trading',
      icon: '📈',
      name: 'Trading Brain',
      role: 'Markets & Execution',
      vaultPath: '/agent_os/trading_os',
      color: 'trading',
    },
  ];

  // ── VAULT CACHE ──────────────────────────────────────────────────
  const vaultCache = {};

  async function fetchVault(agentId, vaultPath) {
    const key = agentId;
    if (vaultCache[key]) return vaultCache[key];
    try {
      // Try to fetch SOUL.md, SKILLS.md, and knowledge notes from vault API
      const [soulRes, skillsRes, knowledgeRes] = await Promise.all([
        fetch(`/api/v1/vault/read/${vaultPath}/SOUL.md`, {
          headers: { 'Authorization': 'Bearer ' + TOKEN }
        }).catch(() => null),
        fetch(`/api/v1/vault/read/${vaultPath}/SKILLS.md`, {
          headers: { 'Authorization': 'Bearer ' + TOKEN }
        }).catch(() => null),
        fetch(`/api/v1/vault/list/${vaultPath}/knowledge`, {
          headers: { 'Authorization': 'Bearer ' + TOKEN }
        }).catch(() => null),
      ]);
      const soul = soulRes && soulRes.ok ? await soulRes.text() : '# SOUL\nIdentity document not loaded.';
      const skills = skillsRes && skillsRes.ok ? await skillsRes.text() : '# SKILLS\nSkills registry not loaded.';
      let knowledgeNotes = [];
      if (knowledgeRes && knowledgeRes.ok) {
        const kd = await knowledgeRes.json();
        knowledgeNotes = (kd.files || kd.rows || []).slice(0, 5);
      }
      const result = { soul, skills, knowledgeNotes };
      vaultCache[key] = result;
      return result;
    } catch (e) {
      return { soul: '# SOUL\\nUnavailable', skills: '# SKILLS\\nUnavailable', knowledgeNotes: [] };
    }
  }

  // ── FETCH FLEET STATUS ──────────────────────────────────────────
  async function fetchFleetStatus() {
    try {
      const r = await fetch('/api/v1/fleet/status', {
        headers: { 'Authorization': 'Bearer ' + TOKEN }
      });
      if (r.ok) return await r.json();
    } catch (e) {}
    return { total: 0, active: [], stale: [], unknown: [] };
  }

  async function fetchAgentOS() {
    try {
      const r = await fetch('/api/agent-os/status', {
        headers: { 'Authorization': 'Bearer ' + TOKEN }
      });
      if (r.ok) return await r.json();
    } catch (e) {}
    return null;
  }

  // ── RENDER ──────────────────────────────────────────────────────
  function escape(s) {
    if (s == null) return '';
    return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  }

  function truncate(text, maxLen) {
    if (!text || text.length <= maxLen) return text || '';
    return text.slice(0, maxLen) + '...';
  }

  function parseSoulSummary(soulText) {
    const lines = soulText.split('\\n').filter(l => l.trim());
    // Find the purpose/identity line
    const purpose = lines.find(l => l.startsWith('I am') || l.startsWith('My purpose'));
    const principles = lines.filter(l => l.startsWith('1.') || l.startsWith('2.') || l.startsWith('3.'));
    return { purpose: purpose || '', principles: principles.slice(0, 3) };
  }

  function parseSkills(skillsText) {
    const skills = [];
    const lines = skillsText.split('\\n');
    let currentSkill = null;
    for (const line of lines) {
      const match = line.match(/^###\s+\d+\.\s+`(.+?)`/);
      if (match) {
        if (currentSkill) skills.push(currentSkill);
        currentSkill = { name: match[1], desc: '', deps: [] };
      } else if (currentSkill) {
        const depMatch = line.match(/Depends on:\s*(.+)/i);
        if (depMatch) {
          currentSkill.deps = depMatch[1].split(',').map(d => d.trim());
        } else if (line.trim() && !line.startsWith('-') && !line.startsWith('#')) {
          if (!currentSkill.desc) currentSkill.desc = line.trim();
        }
      }
    }
    if (currentSkill) skills.push(currentSkill);
    return skills;
  }

  function renderApp() {
    // Auth check — redirect if no token
    if (!TOKEN) {
      root.innerHTML = '<div class="fleet-loading"><div style="color:var(--amber);font-size:24px;margin-bottom:12px;">🔒</div><div style="font-size:16px;margin-bottom:8px;">Authentication required</div><div style="color:var(--text-muted);font-size:12px;">Please log in at <a href="/auth/login" style="color:var(--accent);">/auth/login</a></div></div>';
      return;
    }
    root.innerHTML = '<div class="fleet-loading"><div class="spinner"></div><div>Loading Fleet OS...</div></div>';

    // Fetch fleet + vault data
    Promise.all([
      fetchFleetStatus(),
      fetchAgentOS(),
      ...AGENT_OS.map(a => fetchVault(a.id, a.vaultPath)),
    ]).then(([fleetStatus, agentOS, ...vaults]) => {
      const agentStatusMap = {};
      if (fleetStatus && fleetStatus.active) {
        fleetStatus.active.forEach(a => { agentStatusMap[a.agent_name] = 'online'; });
        fleetStatus.stale.forEach(a => { agentStatusMap[a.agent_name] = 'offline'; });
        fleetStatus.unknown.forEach(a => { agentStatusMap[a.agent_name] = 'error'; });
      }

      // Build agent registry mapping from agentOS if available
      const agentOSProcesses = agentOS && agentOS.processes ? agentOS.processes.agents || {} : {};
      const agentOSBoot = agentOS && agentOS.boot_results || {};

      let html = '';

      // ── TOP BAR ──
      html += '<div class="fleet-topbar">';
      html += '  <div class="fleet-logo"><span class="dot"></span> AGENT OS · FLEET DASHBOARD</div>';
      html += '  <div class="fleet-topbar-right">';
      html += '    <span class="fleet-count">Total: <strong>' + AGENT_OS.length + '</strong></span>';
      html += '    <span class="fleet-count">Active: <strong id="fleet-active-count">' +
        fleetStatus.active.length + '</strong></span>';
      html += '    <span class="fleet-count" style="color:var(--text-muted)">Stale: <strong>' +
        fleetStatus.stale.length + '</strong></span>';
      html += '  </div>';
      html += '</div>';

      // ── AGENT GRID ──
      html += '<div class="fleet-agents">';

      AGENT_OS.forEach((agent, idx) => {
        const vault = vaults[idx] || { soul: '', skills: '', knowledgeNotes: [] };
        const status = agentStatusMap[agent.id] || 'offline';
        const soulInfo = parseSoulSummary(vault.soul);
        const skillList = parseSkills(vault.skills);
        const processInfo = agentOSProcesses[agent.id] || {};

        html += '<div class="agent-card" id="card-' + agent.id + '">';
        html += '  <div class="agent-card-header" onclick="toggleAgent(\'' + agent.id + '\')">';
        html += '    <div class="agent-card-info">';
        html += '      <div class="agent-card-avatar ' + agent.color + '">' + agent.icon + '</div>';
        html += '      <div>';
        html += '        <div class="agent-card-name">' + agent.name + '</div>';
        html += '        <div class="agent-card-role">' + agent.role + '</div>';
        html += '      </div>';
        html += '    </div>';
        html += '    <div class="agent-card-status ' + status + '">';
        html += '      <span class="agent-card-status-dot"></span>';
        html += status;
        html += '    </div>';
        html += '  </div>';

        // ── BODY (expandable) ──
        html += '  <div class="agent-card-body">';
        html += '    <div class="agent-tabs" id="tabs-' + agent.id + '">';
        html += '      <button class="agent-tab active" data-tab="soul" onclick="switchTab(\'' + agent.id + '\',\'soul\')">SOUL</button>';
        html += '      <button class="agent-tab" data-tab="skills" onclick="switchTab(\'' + agent.id + '\',\'skills\')">Skills</button>';
        html += '      <button class="agent-tab" data-tab="knowledge" onclick="switchTab(\'' + agent.id + '\',\'knowledge\')">Knowledge</button>';
        html += '      <button class="agent-tab" data-tab="runtime" onclick="switchTab(\'' + agent.id + '\',\'runtime\')">Runtime</button>';
        html += '    </div>';

        // ── TAB: SOUL ──
        html += '    <div class="tab-content" data-tab="soul" id="soul-' + agent.id + '">';
        html += '      <div class="soul-block">' + escape(truncate(vault.soul, 800)) + '</div>';
        if (soulInfo.purpose) {
          html += '      <div style="margin-top:10px;font-size:11px;color:var(--accent);line-height:1.6">' +
            escape(soulInfo.purpose) + '</div>';
        }
        html += '      <div class="agent-kpis">';
        html += '        <div class="agent-kpi"><div class="agent-kpi-label">Identity</div>';
        html += '          <div class="agent-kpi-value">' + (vault.soul.startsWith('#') ? 'Active' : 'N/A') + '</div></div>';
        html += '        <div class="agent-kpi"><div class="agent-kpi-label">Principles</div>';
        html += '          <div class="agent-kpi-value">' + Math.min(skillList.length, 9) + '</div></div>';
        html += '      </div>';
        html += '    </div>';

        // ── TAB: SKILLS ──
        html += '    <div class="tab-content" data-tab="skills" id="skills-' + agent.id + '" style="display:none">';
        html += '      <div class="skill-list">';
        skillList.slice(0, 8).forEach(s => {
          html += '        <div class="skill-item">';
          html += '          <div class="skill-name">' + escape(s.name) + '</div>';
          if (s.desc) html += '          <div class="skill-desc">' + escape(s.desc) + '</div>';
          if (s.deps && s.deps.length) html += '          <div class="skill-dep">→ Depends: ' + escape(s.deps.join(', ')) + '</div>';
          html += '        </div>';
        });
        if (skillList.length > 8) html += '<div style="font-family:var(--font-mono);font-size:9px;color:var(--text-muted);text-align:center;padding:8px;">+' + (skillList.length - 8) + ' more</div>';
        html += '      </div>';
        html += '    </div>';

        // ── TAB: KNOWLEDGE ──
        html += '    <div class="tab-content" data-tab="knowledge" id="knowledge-' + agent.id + '" style="display:none">';
        html += '      <div class="knowledge-list">';
        if (vault.knowledgeNotes.length) {
          vault.knowledgeNotes.forEach(n => {
            html += '        <div class="knowledge-item">';
            html += '          <div class="knowledge-item-title">' + escape(n.name || n.path || 'note') + '</div>';
            html += '          <div class="knowledge-item-preview">' + escape(truncate(n.summary || n.preview || '', 200)) + '</div>';
            html += '        </div>';
          });
        } else {
          html += '<div style="font-family:var(--font-mono);font-size:10px;color:var(--text-muted);text-align:center;padding:16px;">No knowledge notes loaded</div>';
        }
        html += '      </div>';
        html += '    </div>';

        // ── TAB: RUNTIME ──
        html += '    <div class="tab-content" data-tab="runtime" id="runtime-' + agent.id + '" style="display:none">';
        html += '      <div class="os-runtime">';
        const proc = processInfo;
        html += '        <div class="os-runtime-item"><span class="os-runtime-label">Status</span><br><span class="os-runtime-value ' + (proc.status === 'RUNNING' ? 'accent' : '') + '">' + escape(proc.status || '—') + '</span></div>';
        html += '        <div class="os-runtime-item"><span class="os-runtime-label">Interval</span><br><span class="os-runtime-value">' + (proc.interval ? proc.interval + 's' : '—') + '</span></div>';
        html += '        <div class="os-runtime-item"><span class="os-runtime-label">Priority</span><br><span class="os-runtime-value">' + (proc.priority || '—') + '</span></div>';
        html += '        <div class="os-runtime-item"><span class="os-runtime-label">Retries</span><br><span class="os-runtime-value">' + (proc.retry_count || 0) + '/' + (proc.max_retries || 3) + '</span></div>';
        html += '      </div>';
        html += '      <div class="agent-kpis">';
        html += '        <div class="agent-kpi"><div class="agent-kpi-label">Capabilities</div>';
        html += '          <div class="agent-kpi-value blue">' + ((proc.capabilities || []).length) + '</div></div>';
        html += '        <div class="agent-kpi"><div class="agent-kpi-label">Dependencies</div>';
        html += '          <div class="agent-kpi-value dim">' + ((proc.dependencies || []).length) + '</div></div>';
        html += '      </div>';
        html += '    </div>';

        html += '  </div>'; // body
        html += '</div>'; // agent-card
      });

      html += '</div>'; // fleet-agents

      // ── LIVE EVENTS BAR ──
      html += '<div class="fleet-live-bar">';
      html += '  <span class="fleet-live-dot"></span>';
      html += '  <span>LIVE</span>';
      html += '  <span class="fleet-live-event" id="fleet-live-event">Connected · ' + AGENT_OS.length + ' agent OS instances monitored</span>';
      html += '</div>';

      root.innerHTML = html;
    }).catch(err => {
      root.innerHTML = '<div class="fleet-loading"><div style="color:var(--red);font-size:14px;">⚠ ' + escape(String(err)) + '</div></div>';
    });
  }

  // ── GLOBAL HELPERS ──────────────────────────────────────────────
  window.toggleAgent = function(id) {
    const card = document.getElementById('card-' + id);
    if (card) card.classList.toggle('expanded');
  };

  window.switchTab = function(agentId, tab) {
    // Update tab buttons
    const tabs = document.querySelectorAll('#tabs-' + agentId + ' .agent-tab');
    tabs.forEach(t => t.classList.toggle('active', t.dataset.tab === tab));
    // Update tab content
    const contents = document.querySelectorAll('#card-' + agentId + ' .tab-content');
    contents.forEach(c => c.style.display = c.dataset.tab === tab ? 'block' : 'none');
  };

  // ── INIT ──
  renderApp();

  // ── WS LIVE EVENTS ──
  function connectWS() {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(proto + '//' + window.location.host + '/ws/live?token=' + TOKEN);
    ws.onmessage = function(e) {
      try {
        const d = JSON.parse(e.data);
        const eventEl = document.getElementById('fleet-live-event');
        if (eventEl) {
          eventEl.textContent = d.type + ' · ' + (d.text || d.data || '') + '';
        }
      } catch (e) {}
    };
    ws.onclose = function() {
      setTimeout(connectWS, 3000);
    };
  }
  connectWS();
})();
"""
