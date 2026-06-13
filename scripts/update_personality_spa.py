#!/usr/bin/env python3
"""
Replace the Personality() React component in empire_command_spa.py with
the enhanced version featuring:
  - Sliders for temperature / confidence threshold / urgency floor
  - System prompt preview
  - Per-operator override UI (3 sub-tabs)
  - Active-profile indicator cards
  - Enhanced profiles tab with tone instruction expansion
  - History tab with operator ID column
"""

import re

FILE = "empire_command_spa.py"

with open(FILE, "r") as f:
    content = f.read()

# Find the Personality component boundaries
start_marker = "function Personality() {"
end_marker = "function Strategist() {"

start_idx = content.find(start_marker)
end_idx = content.find(end_marker, start_idx)

if start_idx == -1:
    print("ERROR: Could not find 'function Personality()'")
    exit(1)
if end_idx == -1:
    print("ERROR: Could not find 'function Strategist()'")
    exit(1)

# The new enhanced Personality component
new_component = r'''function Personality() {
  const [data, setData] = useState(null);
  const [niche, setNiche] = useState('__global__');
  const [persona, setPersona] = useState('balanced');
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState(null);
  const [history, setHistory] = useState([]);
  const [tab, setTab] = useState('config');
  const [confThresh, setConfThresh] = useState(0.6);
  const [tempVal, setTempVal] = useState(0.1);
  const [urgFloor, setUrgFloor] = useState(5);
  const [promptSuffix, setPromptSuffix] = useState('');
  const [operatorId, setOperatorId] = useState('');
  const [opOverrides, setOpOverrides] = useState({});
  const [opTab, setOpTab] = useState('global');

  const reload = useCallback(async () => {
    try {
      const [snap, hist] = await Promise.all([
        apiFetch('/api/brain/personality/snapshot').then(r => r.json()),
        apiFetch('/api/brain/personality/history').then(r => r.json()),
      ]);
      setData(snap);
      setHistory(hist.entries || []);
      const c = (snap.configs || {})[niche] || snap.configs['__global__'] || {};
      setConfThresh(c.confidence_threshold || 0.6);
      setTempVal(c.temperature || 0.1);
      setUrgFloor(c.urgency_floor || 5);
      setPersona(c.persona || 'balanced');
    } catch (e) {
      if (e.message !== 'Unauthorized') console.error(e);
    }
  }, [niche]);

  const loadOperatorOverrides = async (opId) => {
    if (!opId) { setOpOverrides({}); return; }
    try {
      const r = await apiFetch('/api/brain/personality/operator/' + encodeURIComponent(opId)).then(r => r.json());
      setOpOverrides(r.overrides || {});
    } catch (e) { console.error(e); }
  };

  useEffect(() => { reload(); }, [reload]);

  useEffect(() => {
    if (!data) return;
    const c = (tab === 'operator' ? (opOverrides[niche] || opOverrides['__global__'] || {}) : (data.configs || {})[niche] || data.configs['__global__'] || {});
    setConfThresh(c.confidence_threshold != null ? c.confidence_threshold : 0.6);
    setTempVal(c.temperature != null ? c.temperature : 0.1);
    setUrgFloor(c.urgency_floor != null ? c.urgency_floor : 5);
    setPersona(c.persona || 'balanced');
    setPromptSuffix(c.custom_prompt_suffix || '');
  }, [niche, data, opOverrides, tab]);

  const save = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      let url = '/api/brain/personality/set';
      let body = { niche, persona, confidence_threshold: confThresh, urgency_floor: urgFloor, temperature: tempVal, custom_prompt_suffix: promptSuffix };
      if (tab === 'operator' && operatorId) {
        url = '/api/brain/personality/operator/set';
        body.operator_id = operatorId;
      }
      const r = await apiFetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(body),
      }).then(r => r.json());
      setSaveMsg(r.ok ? 'Saved' : 'Error: ' + (r.error || 'unknown'));
      if (r.ok && tab === 'operator') loadOperatorOverrides(operatorId);
      else if (r.ok) reload();
    } catch (e) {
      setSaveMsg('Error: ' + e.message);
    }
    setSaving(false);
  };

  const removeOpOverride = async (n) => {
    if (!operatorId) return;
    try {
      await apiFetch('/api/brain/personality/operator/remove', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ operator_id: operatorId, niche: n }),
      });
      loadOperatorOverrides(operatorId);
    } catch (e) { console.error(e); }
  };

  if (!data) return html`<div class="stub"><div class="stub-body">Loading personality...</div></div>`;

  const configs = data.configs || {};
  const profiles = data.profiles_available || [];
  const details = data.profile_details || {};
  const nicheKeys = Object.keys(configs).filter(k => k !== '__global__').sort();
  const globCfg = configs['__global__'] || {};

  const slider = (label, val, setter, min, max, step, color) => html`
    <div class="fld">
      <div style=${{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
        <div class="fld-lbl">${label}</div>
        <span style=${{fontFamily:'var(--font-mono)',fontSize:'12px',color: color || 'var(--signal-teal)',fontWeight:500}}>${typeof val === 'number' ? (step < 1 ? val.toFixed(3) : val) : val}</span>
      </div>
      <input type="range" min=${min} max=${max} step=${step} value=${val}
        onInput=${e => { const v = parseFloat(e.target.value); setter(v); }}
        style=${{width:'100%',height:'4px',appearance:'none',background:'var(--empire-elevated)',borderRadius:'2px',outline:'none',cursor:'pointer'}} />
    </div>
  `;

  return html`
    <div class="section-h">
      <div>
        <div class="section-title">Brain <em>Personality</em></div>
        <div class="section-sub">Configure brain persona per niche \u00b7 thresholds \u00b7 tone</div>
      </div>
      <div class="topbar-actions">
        <button class="pulse-tab" style=${{opacity: saveMsg ? 1 : 0.5,fontSize:'10px'}}>${saveMsg || 'Idle'}</button>
      </div>
    </div>

    <div class="pulse-tabs" style=${{marginTop:'8px'}}>
      <button class=${"pulse-tab " + (tab === 'config' ? 'active' : '')} onClick=${() => { setTab('config'); setOpTab('global'); }}>Configuration</button>
      <button class=${"pulse-tab " + (tab === 'profiles' ? 'active' : '')} onClick=${() => setTab('profiles')}>Profiles</button>
      <button class=${"pulse-tab " + (tab === 'operator' ? 'active' : '')} onClick=${() => setTab('operator')}>Per-Operator</button>
      <button class=${"pulse-tab " + (tab === 'history' ? 'active' : '')} onClick=${() => setTab('history')}>History</button>
    </div>

    ${tab === 'config' ? html`
    <div class="pipeline-breakdown" style=${{marginTop:'16px'}}>
      <div class="pipeline-h">
        <div class="pipeline-title">Per-Niche <strong>Configuration</strong></div>
        <div class="pipeline-total">${nicheKeys.length + 1} configs \u00b7 ${profiles.length} profiles</div>
      </div>

      <div style=${{display:'flex',gap:'12px',alignItems:'center',marginBottom:'16px',padding:'14px 16px',background:'var(--empire-surface)',border:'1px solid var(--empire-border)'}}>
        <select value=${niche} onChange=${e => { setNiche(e.target.value); }} style=${{flex:1,padding:'8px 10px',background:'var(--empire-elevated)',border:'1px solid var(--empire-border)',color:'var(--empire-mist)',fontFamily:'var(--font-mono)',fontSize:'11px',outline:'none'}}>
          <option value="__global__">__global__ (default)</option>
          ${nicheKeys.map(k => html`<option value=${k} key=${k}>${k}</option>`)}
        </select>
        <div style=${{display:'flex',gap:'4px'}}>
          ${profiles.map(p => html`
            <button class=${"pulse-tab " + (persona === p ? 'active' : '')} style=${{fontSize:'9px',padding:'5px 10px'}} onClick=${() => setPersona(p)} key=${p}>${p}</button>
          `)}
        </div>
      </div>

      <div class="split" style=${{marginBottom:'12px'}}>
        <div class="panel">
          <div class="panel-head">Thresholds</div>
          ${slider('Confidence Threshold', confThresh, setConfThresh, 0.0, 1.0, 0.01, 'var(--signal-teal)')}
          ${slider('Temperature', tempVal, setTempVal, 0.0, 1.0, 0.01, 'var(--strike-cyan)')}
          ${slider('Urgency Floor', urgFloor, setUrgFloor, 1, 10, 1, 'var(--status-amber)')}
        </div>
        <div class="panel">
          <div class="panel-head">Custom Prompt Suffix</div>
          <textarea value=${promptSuffix} onInput=${e => setPromptSuffix(e.target.value)}
            style=${{width:'100%',minHeight:'80px',background:'var(--empire-elevated)',border:'1px solid var(--empire-border)',padding:'8px 10px',color:'var(--empire-silver)',fontFamily:'var(--font-mono)',fontSize:'10px',outline:'none',resize:'vertical'}}
            placeholder="Extra instructions appended to brain prompt for this niche..." />
          <div style=${{marginTop:'8px'}}>
            <button class="btn" style=${{fontSize:'10px',padding:'8px 16px'}} onClick=${save} disabled=${saving}>${saving ? 'Saving...' : 'Apply Configuration'}</button>
          </div>
        </div>
      </div>

      <div class="panel" style=${{marginTop:'8px'}}>
        <div class="panel-head">System Prompt Preview <span style=${{color:'var(--empire-fog)',fontWeight:400}}>(simulated for ${niche})</span></div>
        <pre style=${{background:'var(--empire-elevated)',border:'1px solid var(--empire-divider)',padding:'12px 14px',color:'var(--empire-silver)',fontFamily:'var(--font-mono)',fontSize:'9px',lineHeight:'1.6',overflowX:'auto',whiteSpace:'pre-wrap',maxHeight:'200px',overflowY:'auto'}}>${data.prompt_preview || 'No preview available'}</pre>
      </div>

      <table class="tbl" style=${{width:'100%',fontSize:'10px',marginTop:'16px'}}>
        <thead>
          <tr>
            <th>Niche</th>
            <th>Persona</th>
            <th style=${{textAlign:'right'}}>Conf Threshold</th>
            <th style=${{textAlign:'right'}}>Urgency</th>
            <th style=${{textAlign:'right'}}>Temp</th>
            <th>Notes</th>
            <th>Source</th>
          </tr>
        </thead>
        <tbody>
          <tr style=${{background:'rgba(68,229,184,0.04)',fontWeight:500}}>
            <td>__global__</td>
            <td><span class="rv-bar-lane">${globCfg.persona || 'balanced'}</span></td>
            <td class="tbl-num">${(globCfg.confidence_threshold || 0.6).toFixed(3)}</td>
            <td class="tbl-num">${globCfg.urgency_floor || 5}</td>
            <td class="tbl-num">${(globCfg.temperature || 0.1).toFixed(3)}</td>
            <td style=${{color:'var(--empire-fog)',fontSize:'9px'}}>${(globCfg.operator_notes || '') || '-'}</td>
            <td><span class="bdg active" style=${{fontSize:'8px'}}>global</span></td>
          </tr>
          ${nicheKeys.map(n => {
            const c = configs[n] || {};
            return html`<tr key=${n}>
              <td>${n}</td>
              <td><span class="rv-bar-lane">${c.persona || 'balanced'}</span></td>
              <td class="tbl-num">${(c.confidence_threshold || 0.6).toFixed(3)}</td>
              <td class="tbl-num">${c.urgency_floor || 5}</td>
              <td class="tbl-num">${(c.temperature || 0.1).toFixed(3)}</td>
              <td style=${{color:'var(--empire-fog)',fontSize:'9px'}}>${(c.operator_notes || '') || '-'}</td>
              <td><span class="bdg active" style=${{fontSize:'8px'}}>global</span></td>
            </tr>`;
          })}
        </tbody>
      </table>
    </div>
    ` : null}

    ${tab === 'profiles' ? html`
    <div class="pipeline-breakdown" style=${{marginTop:'16px'}}>
      <div class="pipeline-h">
        <div class="pipeline-title">Available <strong>Personalities</strong></div>
        <div class="pipeline-total">${profiles.length} profiles</div>
      </div>
      <div style=${{display:'flex',gap:'16px',flexWrap:'wrap'}}>
        ${profiles.map(p => {
          const pd = details[p] || {};
          const isActive = persona === p;
          return html`
          <div class="stat-card" style=${{flex:'1',minWidth:'180px',cursor:'pointer',borderColor: isActive ? 'var(--signal-teal)' : 'var(--empire-border)', opacity: isActive ? 1 : 0.7}} onClick=${() => setPersona(p)} key=${p}>
            <div class="stat-label">${pd.label || p}</div>
            <div class="stat-meta" style=${{color:'var(--empire-mist)',fontSize:'11px',marginBottom:'12px'}}>${pd.description || ''}</div>
            ${pd.confidence_threshold != null ? html`
            <div style=${{display:'flex',flexDirection:'column',gap:'8px'}}>
              <div style=${{display:'flex',justifyContent:'space-between',fontFamily:'var(--font-mono)',fontSize:'10px'}}>
                <span style=${{color:'var(--empire-fog)'}}>Confidence</span>
                <span style=${{color: isActive ? 'var(--signal-teal)' : 'var(--empire-mist)'}}>${pd.confidence_threshold.toFixed(2)}</span>
              </div>
              <div style=${{height:'3px',background:'var(--empire-elevated)',borderRadius:'2px',overflow:'hidden'}}>
                <div style=${{height:'100%',width: (pd.confidence_threshold * 100) + '%',background: isActive ? 'var(--signal-teal)' : 'var(--empire-fog)',borderRadius:'2px',transition:'width 0.4s var(--ease-out-empire)'}}></div>
              </div>
              <div style=${{display:'flex',justifyContent:'space-between',fontFamily:'var(--font-mono)',fontSize:'10px'}}>
                <span style=${{color:'var(--empire-fog)'}}>Temperature</span>
                <span style=${{color: isActive ? 'var(--signal-teal)' : 'var(--empire-mist)'}}>${pd.temperature != null ? pd.temperature.toFixed(2) : '0.10'}</span>
              </div>
              <div style=${{display:'flex',justifyContent:'space-between',fontFamily:'var(--font-mono)',fontSize:'10px'}}>
                <span style=${{color:'var(--empire-fog)'}}>Fallback</span>
                <span style=${{color: pd.go_fallback === 'GO' ? 'var(--status-amber)' : 'var(--empire-mist)'}}>${pd.go_fallback || 'NO_GO'}</span>
              </div>
            </div>
            ` : null}
            ${isActive ? html`<div style=${{marginTop:'10px',fontSize:'9px',color:'var(--signal-teal)',fontFamily:'var(--font-mono)',letterSpacing:'0.08em'}}>ACTIVE</div>` : null}
          </div>
          `;
        })}
      </div>
      <div style=${{marginTop:'20px'}}>
        <div class="panel-head" style=${{marginBottom:'12px'}}>Tone Instructions <span style=${{color:'var(--empire-fog)',fontWeight:400}}>(what the LLM sees)</span></div>
        ${profiles.map(p => {
          const pd = details[p] || {};
          const isActive = persona === p;
          return html`
            <div style=${{marginBottom:'10px',padding:'10px 14px',background: isActive ? 'var(--empire-surface)' : 'var(--empire-elevated)',border:'1px solid ' + (isActive ? 'var(--signal-teal-soft)' : 'var(--empire-divider)'),borderRadius:'6px'}} key=${p}>
              <div style=${{display:'flex',justifyContent:'space-between',alignItems:'center',marginBottom:'6px'}}>
                <strong style=${{color:'var(--empire-white)',fontSize:'12px'}}>${pd.label || p}</strong>
                <span style=${{fontFamily:'var(--font-mono)',fontSize:'9px',color: isActive ? 'var(--signal-teal)' : 'var(--empire-fog)'}}>${p}</span>
              </div>
              <div style=${{fontFamily:'var(--font-mono)',fontSize:'9px',color:'var(--empire-silver)',lineHeight:'1.6',whiteSpace:'pre-wrap'}}>
                ${'tone_instruction'}
              </div>
            </div>`;
        })}
      </div>
    </div>
    ` : null}

    ${tab === 'operator' ? html`
    <div class="pipeline-breakdown" style=${{marginTop:'16px'}}>
      <div class="pipeline-h">
        <div class="pipeline-title">Per-Operator <strong>Overrides</strong></div>
        <div class="pipeline-total">Override global personality per operator</div>
      </div>

      <div style=${{display:'flex',gap:'12px',alignItems:'center',marginBottom:'16px',padding:'14px 16px',background:'var(--empire-surface)',border:'1px solid var(--empire-border)'}}>
        <div class="fld" style=${{flex:1,margin:0}}>
          <div class="fld-lbl" style=${{marginBottom:'4px'}}>Operator ID</div>
          <input class="fld-in mono" value=${operatorId} onInput=${e => { setOperatorId(e.target.value); loadOperatorOverrides(e.target.value); }} placeholder="Paste operator UUID..." style=${{width:'100%'}} />
        </div>
      </div>

      ${operatorId ? html`
      <div style=${{marginBottom:'16px'}}>
        <div class="pulse-tabs" style=${{borderBottom:'1px solid var(--empire-divider)',marginBottom:'12px'}}>
          <button class=${"pulse-tab " + (opTab === 'global' ? 'active' : '')} onClick=${() => setOpTab('global')}>Global Override</button>
          <button class=${"pulse-tab " + (opTab === 'niche' ? 'active' : '')} onClick=${() => setOpTab('niche')}>Per-Niche Override</button>
          <button class=${"pulse-tab " + (opTab === 'active' ? 'active' : '')} onClick=${() => setOpTab('active')}>Active Overrides</button>
        </div>

        ${opTab === 'global' ? html`
        <div class="panel">
          <div class="panel-head">Operator Global Default</div>
          <div style=${{display:'flex',gap:'12px',alignItems:'center',marginBottom:'12px'}}>
            ${profiles.map(p => html`
              <button class=${"pulse-tab " + (persona === p ? 'active' : '')} style=${{fontSize:'9px',padding:'5px 10px'}} onClick=${() => setPersona(p)} key=${p}>${p}</button>
            `)}
          </div>
          ${slider('Confidence Threshold', confThresh, setConfThresh, 0.0, 1.0, 0.01)}
          ${slider('Temperature', tempVal, setTempVal, 0.0, 1.0, 0.01)}
          <div style=${{marginTop:'10px'}}>
            <button class="btn" style=${{fontSize:'10px',padding:'8px 16px'}} onClick=${save} disabled=${saving}>${saving ? 'Saving...' : 'Set Global Override'}</button>
          </div>
        </div>
        ` : null}

        ${opTab === 'niche' ? html`
        <div class="panel">
          <div class="panel-head">Per-Niche Override</div>
          <div style=${{display:'flex',gap:'12px',alignItems:'center',marginBottom:'12px'}}>
            <select value=${niche} onChange=${e => setNiche(e.target.value)} style=${{padding:'8px 10px',background:'var(--empire-elevated)',border:'1px solid var(--empire-border)',color:'var(--empire-mist)',fontFamily:'var(--font-mono)',fontSize:'11px',outline:'none',flex:1}}>
              <option value="__global__">__global__</option>
              ${nicheKeys.map(k => html`<option value=${k} key=${k}>${k}</option>`)}
            </select>
          </div>
          <div style=${{display:'flex',gap:'4px',marginBottom:'12px'}}>
            ${profiles.map(p => html`
              <button class=${"pulse-tab " + (persona === p ? 'active' : '')} style=${{fontSize:'9px',padding:'5px 10px'}} onClick=${() => setPersona(p)} key=${p}>${p}</button>
            `)}
          </div>
          ${slider('Confidence Threshold', confThresh, setConfThresh, 0.0, 1.0, 0.01)}
          ${slider('Temperature', tempVal, setTempVal, 0.0, 1.0, 0.01)}
          <div style=${{marginTop:'10px'}}>
            <button class="btn" style=${{fontSize:'10px',padding:'8px 16px'}} onClick=${save} disabled=${saving}>${saving ? 'Saving...' : 'Set Niche Override'}</button>
          </div>
        </div>
        ` : null}

        ${opTab === 'active' ? html`
        <div class="panel">
          <div class="panel-head">Active Operator Overrides</div>
          ${Object.keys(opOverrides).length === 0 ? html`
            <div class="stub" style=${{padding:'24px 14px'}}><div class="stub-body">No operator overrides for this operator</div></div>
          ` : html`
          <table class="tbl" style=${{width:'100%',fontSize:'10px'}}>
            <thead><tr><th>Niche</th><th>Persona</th><th style=${{textAlign:'right'}}>Conf</th><th style=${{textAlign:'right'}}>Temp</th><th></th></tr></thead>
            <tbody>
              ${Object.entries(opOverrides).map(([n, c]) => html`<tr key=${n}>
                <td>${n}</td>
                <td><span class="rv-bar-lane">${c.persona || 'balanced'}</span></td>
                <td class="tbl-num">${(c.confidence_threshold || 0.6).toFixed(3)}</td>
                <td class="tbl-num">${(c.temperature || 0.1).toFixed(3)}</td>
                <td><button class="tbl-action danger" onClick=${() => removeOpOverride(n)}>Remove</button></td>
              </tr>`)}
            </tbody>
          </table>
          `}
        </div>
        ` : null}
      </div>
      ` : html`
      <div class="stub" style=${{padding:'32px 20px'}}><div class="stub-body">Enter an Operator ID above to configure per-operator personality overrides</div></div>
      `}
    </div>
    ` : null}

    ${tab === 'history' ? html`
    <div class="pipeline-breakdown" style=${{marginTop:'16px'}}>
      <div class="pipeline-h">
        <div class="pipeline-title">Operator Preference <strong>Log</strong></div>
        <div class="pipeline-total">${history.length} changes</div>
      </div>
      ${history.length === 0 ? html`
        <div class="stub" style=${{padding:'24px 14px'}}><div class="stub-body">No preference changes logged yet</div></div>
      ` : html`
      <div style=${{maxHeight:'500px',overflowY:'auto'}}>
      <table class="tbl" style=${{width:'100%',fontSize:'10px'}}>
        <thead><tr><th>Time</th><th>Operator</th><th>Niche</th><th>Field</th><th>From</th><th>To</th></tr></thead>
        <tbody>
          ${history.map((h, i) => html`<tr key=${i}>
            <td style=${{fontFamily:'var(--font-mono)',fontSize:'9px',whiteSpace:'nowrap'}}>${(h.created_at || '').slice(11,19)}</td>
            <td style=${{fontSize:'9px'}}>${(h.operator_id || '').slice(0,8)}</td>
            <td style=${{fontSize:'10px'}}>${h.niche}</td>
            <td><span class="rv-bar-lane">${h.field}</span></td>
            <td style=${{color:'var(--empire-fog)',fontFamily:'var(--font-mono)',fontSize:'9px',wordBreak:'break-all',maxWidth:'120px'}}>${h.old_value || '-'}</td>
            <td style=${{color:'var(--signal-teal)',fontFamily:'var(--font-mono)',fontSize:'9px',wordBreak:'break-all',maxWidth:'120px'}}>${h.new_value || '-'}</td>
          </tr>`)}
        </tbody>
      </table>
      </div>
      `}
    </div>
    ` : null}
  `;
}
'''

# Replace the component
old_component = content[start_idx:end_idx]
content = content[:start_idx] + new_component + content[end_idx:]

with open(FILE, "w") as f:
    f.write(content)

print("SUCCESS: Replacement done!")
print(f"Old component: {len(old_component)} chars")
print(f"New component: {len(new_component)} chars")
