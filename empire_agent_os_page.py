"""
EMPIRE V49 · AGENT OS — PUBLIC VISUALIZATION DASHBOARD
======================================================
Self-contained HTML page at /agent-os showing:
  - Kernel status (booted, uptime)
  - Agent grid with status, capabilities, intervals
  - IPC bus events and subscriptions
  - Capability registry
  - Auto-refreshes every 10s via /api/agent-os/public/snapshot
"""

_AGENT_OS_PAGE_HTML = '''<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent OS · Empire AI</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@200;400;500;600;700&family=Geist+Mono:wght@300;400;500;600;700&family=Inter:wght@200;400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --canvas: #0A1A2F;
  --surface: #15263F;
  --elevated: #1A2D4A;
  --white: #F8FAFD;
  --silver: #C8D4E4;
  --mist: #7A8CA3;
  --fog: #4A5A72;
  --shadow: #2A3A52;
  --teal: #44E5B8;
  --teal-soft: rgba(68,229,184,0.08);
  --teal-glow: rgba(68,229,184,0.6);
  --cyan: #5AC8FA;
  --amber: #F5A623;
  --red: #FF4757;
  --divider: rgba(122,140,163,0.12);
  --border: rgba(122,140,163,0.18);
  --font-ui: 'Geist','Inter',sans-serif;
  --font-mono: 'Geist Mono',monospace;
  --radius: 8px;
  --radius-lg: 12px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--canvas);
  color:var(--white);
  font-family:var(--font-ui);
  -webkit-font-smoothing:antialiased;
  letter-spacing:-0.02em;
}
body::before{content:'';position:fixed;inset:0;pointer-events:none;z-index:0;
  background:radial-gradient(ellipse 60% 40% at 50% 15%,rgba(68,229,184,0.05) 0%,transparent 50%),
             radial-gradient(ellipse 60% 40% at 50% 85%,rgba(90,200,250,0.04) 0%,transparent 50%);}

.header{z-index:1;position:relative;padding:48px 32px 32px;text-align:center}
.header-title{font-weight:200;font-size:36px;letter-spacing:-0.03em}
.header-title em{font-style:italic;color:var(--teal);font-weight:500}
.header-sub{font-family:var(--font-mono);font-size:10px;color:var(--mist);letter-spacing:0.18em;text-transform:uppercase;margin-top:8px}
.header-bar{width:80px;height:1px;background:linear-gradient(90deg,transparent,var(--teal),transparent);margin:16px auto 0}

.container{z-index:1;position:relative;max-width:1100px;margin:0 auto;padding:0 24px 60px}

/* STATUS ROW */
.status-row{display:flex;gap:16px;margin-bottom:24px;flex-wrap:wrap}
.status-card{flex:1;min-width:200px;background:var(--surface);border:1px solid var(--border);padding:20px;border-radius:var(--radius-lg);position:relative;overflow:hidden;transition:border-color .2s}
.status-card::before{content:'';position:absolute;top:0;left:0;right:0;height:1px;background:linear-gradient(90deg,transparent,var(--teal-soft),transparent)}
.status-card:hover{border-color:rgba(122,140,163,0.3)}
.status-dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:8px}
.status-dot.online{background:var(--teal);box-shadow:0 0 12px var(--teal-glow);animation:pulse 2s infinite}
.status-dot.offline{background:var(--fog)}
.status-label{font-family:var(--font-mono);font-size:10px;color:var(--mist);letter-spacing:0.18em;text-transform:uppercase;margin-bottom:12px}
.status-value{font-family:var(--font-mono);font-weight:500;font-size:28px;color:var(--white);line-height:1}
.status-value.teal{color:var(--teal)}
.status-value.cyan{color:var(--cyan)}
.status-value.amber{color:var(--amber)}
.status-value.dim{color:var(--mist)}
.status-meta{font-family:var(--font-mono);font-size:10px;color:var(--fog);margin-top:8px;letter-spacing:0.04em}

/* TABS */
.tabs{display:flex;gap:0;margin-bottom:24px;border-bottom:1px solid var(--divider)}
.tab{padding:10px 22px;font-family:var(--font-mono);font-size:11px;letter-spacing:0.14em;text-transform:uppercase;color:var(--mist);cursor:pointer;border-bottom:2px solid transparent;transition:all .15s;background:none;border-top:none;border-left:none;border-right:none}
.tab:hover{color:var(--white)}
.tab.active{color:var(--teal);border-bottom-color:var(--teal)}
.tab-count{font-size:9px;color:var(--fog);margin-left:4px}
.tab.active .tab-count{color:var(--teal)}

/* PANELS */
.panel{background:var(--surface);border:1px solid var(--border);padding:20px;border-radius:var(--radius-lg)}
.panel-h{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--divider)}
.panel-title{font-weight:500;font-size:13px;letter-spacing:0.02em}
.panel-tag{font-family:var(--font-mono);font-size:9px;color:var(--mist);letter-spacing:0.14em;text-transform:uppercase}

/* AGENT GRID */
.agent-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.agent-card{background:var(--elevated);border:1px solid var(--divider);padding:16px 18px;border-radius:var(--radius);transition:border-color .15s}
.agent-card:hover{border-color:rgba(122,140,163,0.3)}
.agent-row{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.agent-name{font-weight:500;font-size:14px;color:var(--white)}
.badge{display:inline-flex;align-items:center;gap:5px;font-family:var(--font-mono);font-size:8px;letter-spacing:0.1em;text-transform:uppercase;padding:3px 8px;border-radius:20px;border:1px solid}
.badge.RUNNING{color:var(--teal);border-color:rgba(68,229,184,0.3);background:var(--teal-soft)}
.badge.STOPPED{color:var(--fog);border-color:rgba(122,140,163,0.2)}
.badge.ERROR{color:var(--red);border-color:rgba(255,71,87,0.2);background:rgba(255,71,87,0.04)}
.badge.BOOTING{color:var(--amber);border-color:rgba(245,166,35,0.2);background:rgba(245,166,35,0.04)}
.badge-dot{width:5px;height:5px;border-radius:50%;background:currentColor;box-shadow:0 0 5px currentColor}
.agent-meta{font-family:var(--font-mono);font-size:9px;color:var(--fog);display:flex;flex-wrap:wrap;gap:8px}
.agent-meta span{display:inline-flex;align-items:center;gap:4px}
.agent-caps{display:flex;gap:4px;flex-wrap:wrap;margin-top:10px;padding-top:10px;border-top:1px solid var(--divider)}
.agent-cap{font-family:var(--font-mono);font-size:8px;letter-spacing:0.06em;padding:2px 7px;border-radius:3px;color:var(--teal);background:var(--teal-soft);border:1px solid rgba(68,229,184,0.15)}

/* IPC EVENTS */
.event-list{max-height:400px;overflow-y:auto}
.event-row{display:grid;grid-template-columns:90px 120px 1fr;gap:12px;padding:8px 0;border-bottom:1px solid var(--divider);font-family:var(--font-mono);font-size:10px;align-items:baseline}
.event-row:last-child{border-bottom:none}
.event-ts{color:var(--fog)}
.event-type{color:var(--teal);text-transform:uppercase;letter-spacing:0.08em}
.event-source{color:var(--mist)}
.event-data{color:var(--silver);word-break:break-word}

/* CAPABILITY TABLE */
.cap-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:12px}
.cap-card{background:var(--elevated);border:1px solid var(--divider);padding:12px 16px;border-radius:var(--radius)}
.cap-name{font-family:var(--font-mono);font-size:11px;color:var(--cyan);letter-spacing:0.04em;margin-bottom:8px}
.cap-agents{display:flex;gap:4px;flex-wrap:wrap}
.cap-agent{font-family:var(--font-mono);font-size:9px;color:var(--mist);padding:2px 7px;border:1px solid var(--border);border-radius:3px}

/* EMPTY */
.empty{font-family:var(--font-ui);font-size:12px;color:var(--fog);font-style:italic;padding:40px 0;text-align:center}

/* REFRESH */
.refresh-bar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px}
.refresh-tag{font-family:var(--font-mono);font-size:10px;color:var(--mist);letter-spacing:0.08em}
.refresh-tag strong{color:var(--teal)}

/* ANIMATIONS */
@keyframes pulse{0%,100%{opacity:1;transform:scale(1)}50%{opacity:.6;transform:scale(.88)}}
@keyframes fadeUp{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}

.fade-in{animation:fadeUp .3s ease-out}

/* RESPONSIVE */
@media(max-width:768px){
  .status-row{flex-direction:column}
  .agent-grid{grid-template-columns:1fr}
  .event-row{grid-template-columns:70px 80px 1fr;font-size:9px}
}

/* BOOT ORDER */
.boot-list{display:flex;flex-direction:column;gap:8px}
.boot-item{display:flex;align-items:center;gap:12px;padding:10px 14px;background:var(--elevated);border:1px solid var(--divider);border-radius:var(--radius);font-family:var(--font-mono);font-size:11px}
.boot-item .boot-idx{color:var(--fog);font-size:10px;min-width:28px}
.boot-item .boot-name{color:var(--white);flex:1}
.boot-item .boot-pri{font-size:9px;color:var(--mist)}
.boot-item .boot-status{font-size:9px;text-transform:uppercase;letter-spacing:0.08em}
.boot-item .boot-status.ok{color:var(--teal)}
.boot-item .boot-status.fail{color:var(--red)}
</style>
<script>
async function fetchSnapshot(){try{const res=await fetch('/api/agent-os/public/snapshot');if(!res.ok)throw new Error(res.status);return await res.json()}catch(e){return{error:e.message}}}

function renderOverview(snap){
  const k=snap.kernel||{};
  const p=snap.processes||{};
  const ipc=snap.ipc||{};
  const caps=snap.capabilities||{};
  const bootResults=snap.boot_results||{};

  let uptime='';
  if(k.uptime_seconds){
    const h=Math.floor(k.uptime_seconds/3600);
    const m=Math.floor((k.uptime_seconds%3600)/60);
    const s=Math.floor(k.uptime_seconds%60);
    uptime=`${h}h ${m}m ${s}s`;
  }

  const healthPct=p.total_agents>0?Math.round((p.running/max(p.total_agents,1))*100):0;
  const healthClass=healthPct>=80?'teal':healthPct>=50?'amber':'red';

  return `<div class="status-row">
    <div class="status-card">
      <div class="status-label"><span class="status-dot ${k.booted?'online':'offline'}"></span>Kernel</div>
      <div class="status-value ${k.booted?'teal':'dim'}">${k.booted?'BOOTED':'OFFLINE'}</div>
      <div class="status-meta">uptime: ${uptime||'—'} · started: ${(k.started_at||'').slice(11,19)||'—'}</div>
    </div>
    <div class="status-card">
      <div class="status-label">Agents</div>
      <div class="status-value">${p.total_agents||0}</div>
      <div class="status-meta">${p.running||0} running · ${p.error||0} errors · ${p.stopped||0} stopped</div>
    </div>
    <div class="status-card">
      <div class="status-label">Health</div>
      <div class="status-value ${healthClass}">${healthPct}%</div>
      <div class="status-meta">${p.running||0}/${p.total_agents||0} agents running</div>
    </div>
    <div class="status-card">
      <div class="status-label">IPC Events</div>
      <div class="status-value cyan">${ipc.total_events_tracked||0}</div>
      <div class="status-meta">${Object.keys(ipc.subscriptions||{}).length||0} subscriptions · ${Object.keys(ipc.inbox_sizes||{}).length||0} inboxes</div>
    </div>
  </div>`;
}

function renderAgents(snap){
  const agents=snap.processes?.agents||{};
  const names=Object.keys(agents);
  if(!names.length)return '<div class="empty">No agents registered.</div>';

  return '<div class="agent-grid">'+names.map(name=>{
    const a=agents[name];
    const caps=(a.capabilities||[]).map(c=>`<span class="agent-cap">${escapeHtml(c)}</span>`).join('');
    return `<div class="agent-card fade-in">
      <div class="agent-row">
        <span class="agent-name">${escapeHtml(name)}</span>
        <span class="badge ${a.status||'STOPPED'}"><span class="badge-dot"></span>${a.status||'STOPPED'}</span>
      </div>
      <div class="agent-meta">
        <span>⚡ ${a.interval||0}s</span>
        <span>⭐ ${a.priority||0}</span>
        <span>🔄 ${a.retry_count||0}/${a.max_retries||3}</span>
        ${a.dependencies&&a.dependencies.length?`<span>📎 deps: ${a.dependencies.join(', ')}</span>`:''}
      </div>
      <div class="agent-caps">${caps||'<span class="agent-cap" style="color:var(--fog);background:transparent;border-color:var(--border)">no capabilities</span>'}</div>
    </div>`;
  }).join('')+'</div>';
}

function renderIpcEvents(snap){
  const events=snap.ipc?.recent_events||[];
  if(!events.length)return '<div class="empty">No recent IPC events.</div>';

  return '<div class="event-list">'+events.map(e=>{
    const d=typeof e.data==='object'?JSON.stringify(e.data).slice(0,120):String(e.data||'').slice(0,80);
    return `<div class="event-row fade-in">
      <span class="event-ts">${(e.ts||'').slice(11,19)}</span>
      <span class="event-type">${escapeHtml(e.event_type||'')}</span>
      <span class="event-source">← ${escapeHtml(e.source||'system')}</span>
      <span class="event-data">${escapeHtml(d)}</span>
    </div>`;
  }).join('')+'</div>';
}

function renderCapabilities(snap){
  const caps=snap.capabilities||{};
  const byCap=caps.by_capability||{};
  const capNames=Object.keys(byCap);
  if(!capNames.length)return '<div class="empty">No capabilities registered.</div>';

  return '<div class="cap-grid">'+capNames.map(name=>{
    const agents=byCap[name]||[];
    return `<div class="cap-card fade-in">
      <div class="cap-name">${escapeHtml(name)}</div>
      <div class="cap-agents">${agents.map(a=>`<span class="cap-agent">${escapeHtml(a)}</span>`).join('')}</div>
    </div>`;
  }).join('')+'</div>';
}

function renderBootOrder(snap){
  const order=snap.processes?.boot_order||[];
  const agents=snap.processes?.agents||{};
  const results=snap.boot_results||{};
  if(!order.length)return '<div class="empty">No boot order computed.</div>';

  return '<div class="boot-list">'+order.map((name,i)=>{
    const agent=agents[name]||{};
    const status=results[name];
    const statusLabel=status===undefined?'pending':status?'ok':'fail';
    return `<div class="boot-item fade-in">
      <span class="boot-idx">#${i+1}</span>
      <span class="boot-name">${escapeHtml(name)}</span>
      <span class="boot-pri">pri ${agent.priority||'—'}</span>
      <span class="boot-status ${statusLabel}">${statusLabel}</span>
    </div>`;
  }).join('')+'</div>';
}

function max(a,b){return a>b?a:b}
function escapeHtml(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}

let currentTab='overview';
let currentSnap=null;

async function refresh(){
  const snap=await fetchSnapshot();
  if(snap.error){document.getElementById('main').innerHTML=`<div class="empty">API error: ${snap.error}. Retrying in 10s...</div>`;return}
  currentSnap=snap;
  render();
  document.getElementById('last-refresh').textContent=new Date().toLocaleTimeString();
}

function render(){
  const s=currentSnap;
  if(!s)return;
  document.getElementById('overview').innerHTML=renderOverview(s);
  document.getElementById('agents').innerHTML=renderAgents(s);
  document.getElementById('ipc').innerHTML=renderIpcEvents(s);
  document.getElementById('capabilities').innerHTML=renderCapabilities(s);
  document.getElementById('boot').innerHTML=renderBootOrder(s);
  showTab(currentTab);

  // Update counts
  const p=s.processes||{};
  const agents=p.agents||{};
  const ipc=s.ipc||{};
  const caps=s.capabilities||{};
  document.getElementById('count-agents').textContent=Object.keys(agents).length;
  document.getElementById('count-ipc').textContent=(ipc.recent_events||[]).length;
  document.getElementById('count-caps').textContent=Object.keys(caps.by_capability||{}).length;
}

function showTab(name){
  currentTab=name;
  document.querySelectorAll('.tab').forEach(t=>t.classList.toggle('active',t.dataset.tab===name));
  document.querySelectorAll('.tab-panel').forEach(p=>p.style.display=p.dataset.tab===name?'block':'none');
}

// Auto-refresh every 10s
setInterval(refresh,10000);
// Initial load
window.addEventListener('DOMContentLoaded',refresh);
</script>
</head>
<body>
<div class="header">
  <div class="header-title">Agent <em>OS</em></div>
  <div class="header-sub">Unified Runtime · Real-Time Kernel Dashboard</div>
  <div class="header-bar"></div>
</div>

<div class="container">
  <div class="refresh-bar">
    <span class="refresh-tag">Auto-refresh · last: <strong id="last-refresh">—</strong></span>
  </div>

  <div id="overview"></div>

  <div class="tabs">
    <button class="tab active" data-tab="agents-view" onclick="showTab('agents-view')">Agents <span class="tab-count" id="count-agents">0</span></button>
    <button class="tab" data-tab="ipc-view" onclick="showTab('ipc-view')">IPC Events <span class="tab-count" id="count-ipc">0</span></button>
    <button class="tab" data-tab="caps-view" onclick="showTab('caps-view')">Capabilities <span class="tab-count" id="count-caps">0</span></button>
    <button class="tab" data-tab="boot-view" onclick="showTab('boot-view')">Boot Order</button>
  </div>

  <div id="agents-view" class="tab-panel panel" data-tab="agents-view">
    <div class="panel-h"><span class="panel-title">Registered Agents</span><span class="panel-tag">Lifecycle & Status</span></div>
    <div id="agents"></div>
  </div>

  <div id="ipc-view" class="tab-panel panel" data-tab="ipc-view" style="display:none">
    <div class="panel-h"><span class="panel-title">IPC Event Stream</span><span class="panel-tag">Recent Events</span></div>
    <div id="ipc"></div>
  </div>

  <div id="caps-view" class="tab-panel panel" data-tab="caps-view" style="display:none">
    <div class="panel-h"><span class="panel-title">Capability Registry</span><span class="panel-tag">Discovery & Routing</span></div>
    <div id="capabilities"></div>
  </div>

  <div id="boot-view" class="tab-panel panel" data-tab="boot-view" style="display:none">
    <div class="panel-h"><span class="panel-title">Boot Order</span><span class="panel-tag">Dependency-Resolved</span></div>
    <div id="boot"></div>
  </div>
</div>
</body>
</html>'''


def agent_os_dashboard_page() -> str:
    """Return the Agent OS public visualization dashboard HTML."""
    return _AGENT_OS_PAGE_HTML
