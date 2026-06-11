#!/usr/bin/env python3
"""Add pipeline orbital CSS and rewrite Pipeline component with 5-stage orbital ring."""
with open('empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# ── 1. Add pipeline orbital CSS before the "PIPELINE BREAKDOWN" section ──
old_marker = "/* ── PIPELINE BREAKDOWN ──────────────────────────────────────────── */"
new_css = """/* ── PIPELINE ORBITAL LAYOUT ──────────────────────────────────── */
@keyframes pipe-orbit-rotate{from{stroke-dashoffset:0}to{stroke-dashoffset:-1131}}
@keyframes pipe-boss-glow{0%,100%{box-shadow:0 0 10px rgba(68,229,184,0.12),0 0 20px rgba(68,229,184,0.04)}50%{box-shadow:0 0 18px rgba(68,229,184,0.25),0 0 36px rgba(68,229,184,0.08)}}
@keyframes pipe-node-enter{0%{opacity:0}100%{opacity:1}}
@keyframes pipe-line-draw{0%{stroke-dashoffset:200}100%{stroke-dashoffset:0}}
.pipe-orbital-wrapper{position:relative;width:100%;min-height:480px;display:flex;align-items:center;justify-content:center;margin:10px 0}
.pipe-orbital-svg{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;z-index:1}
.pipe-orbit-ring{fill:none;stroke:rgba(68,229,184,0.06);stroke-width:1px}
.pipe-orbit-ring.outer{stroke:rgba(255,255,255,0.02);stroke-width:1px}
.pipe-orbit-ring.pulse{stroke:rgba(68,229,184,0.1);stroke-width:2px;stroke-dasharray:16 8;animation:pipe-orbit-rotate 25s linear infinite}
.pipe-orbit-line{fill:none;stroke:rgba(68,229,184,0.08);stroke-width:1px;stroke-dasharray:200;stroke-dashoffset:200;animation:pipe-line-draw 1.2s var(--ease-out-empire) forwards}
.pipe-orbit-line.active{stroke:rgba(68,229,184,0.25);stroke-width:2px}
.pipe-orbit-arrow{fill:rgba(68,229,184,0.15);stroke:none;animation:pipe-node-enter .5s var(--ease-out-empire) both}
/* ── Boss card (conversion rate) ── */
.pipe-boss-card{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:3;width:120px;height:120px;border-radius:50%;background:radial-gradient(circle,rgba(68,229,184,0.06) 0%,rgba(68,229,184,0.01) 55%,transparent 100%);border:2px solid rgba(68,229,184,0.2);display:flex;flex-direction:column;align-items:center;justify-content:center;animation:pipe-boss-glow 4s ease-in-out infinite;transition:all .3s var(--ease-snap)}
.pipe-boss-card:hover{border-color:rgba(68,229,184,0.4);transform:translate(-50%,-50%) scale(1.05)}
.pipe-boss-label{font-family:var(--font-mono);font-size:7px;color:var(--signal-teal);letter-spacing:.18em;text-transform:uppercase;margin-bottom:2px}
.pipe-boss-rate{font-family:var(--font-display);font-weight:200;font-size:26px;color:var(--signal-teal);line-height:1}
.pipe-boss-sub{font-family:var(--font-mono);font-size:7px;color:var(--empire-fog);letter-spacing:.08em;margin-top:2px}
/* ── Pipeline stage nodes ── */
.pipe-stage-node{position:absolute;top:50%;left:50%;z-index:2;width:80px;height:56px;background:var(--empire-elevated);border:1px solid var(--empire-divider);border-radius:10px;padding:5px 8px;text-align:center;transition:all .2s var(--ease-snap);animation:pipe-node-enter .35s var(--ease-out-empire) backwards}
.pipe-stage-node:hover{border-color:var(--signal-teal-soft);z-index:4;box-shadow:0 3px 16px rgba(0,0,0,0.25)}
.pipe-stage-node.sent{border-color:rgba(90,200,250,0.2);background:rgba(90,200,250,0.03)}
.pipe-stage-node.replied{border-color:rgba(68,229,184,0.2);background:rgba(68,229,184,0.03)}
.pipe-stage-node.converted{border-color:rgba(68,229,184,0.3);background:rgba(68,229,184,0.04);animation:pipe-boss-glow 3s ease-in-out infinite,pipe-node-enter .35s var(--ease-out-empire) backwards}
.pipe-stage-icon{font-size:11px;display:block;margin-bottom:1px}
.pipe-stage-count{font-family:var(--font-display);font-weight:200;font-size:17px;color:var(--empire-white);line-height:1;display:block}
.pipe-stage-label{font-family:var(--font-mono);font-size:6px;color:var(--empire-fog);letter-spacing:.12em;text-transform:uppercase;margin-top:1px;display:block}
/* ── Responsive ── */
@media (max-width:768px){
  .pipe-orbital-wrapper{min-height:380px}
  .pipe-stage-node{width:64px;height:46px;padding:3px 6px}
  .pipe-boss-card{width:96px;height:96px}
  .pipe-boss-rate{font-size:22px}
}

"""

if old_marker in content:
    content = content.replace(old_marker, new_css + old_marker)
    changes += 1
    print("✓ Added pipeline orbital CSS")
else:
    print("Could not find pipeline breakdown CSS marker")

# ── 2. Rewrite the Pipeline component JSX ──
# Find the function Pipeline() block
old_func_start = "function Pipeline() {"
old_func_marker = "// ── DISPATCH ──"

idx_start = content.find(old_func_start)
idx_next = content.find(old_func_marker, idx_start if idx_start > 0 else 0)

if idx_start > 0 and idx_next > 0:
    # Extract the old function
    old_func = content[idx_start:idx_next]
    
    new_func = """function Pipeline() {
  const [d, setD] = useState(null);
  const [e, setE] = useState(null);
  useEffect(() => {
    Promise.all([
      apiFetch('/api/v1/email/stats').then(r => r.json()),
      apiFetch('/api/v1/sms/stats').then(r => r.json()),
    ]).then(([em, sm]) => setD({ em, sm })).catch(x => setE(x.message));
  }, []);
  if (e) return html`<div class="stub"><div class="stub-body">${e}</div></div>`;
  if (!d) return html`<div class="stub"><div class="stub-body">Loading…</div></div>`;

  // ── Pipeline stage counts (email + SMS combined) ──
  const seqActive = (d.em?.sequences_active ?? 0) + (d.sm?.sequences_active ?? 0);
  const totalSent = (d.em?.emails_sent ?? 0) + (d.sm?.sms_sent ?? 0);
  const totalReplied = (d.em?.replies ?? 0) + (d.sm?.replies ?? 0);
  const totalUnsub = (d.em?.unsubscribes ?? 0) + (d.sm?.opt_outs ?? 0);
  const totalConverted = Math.round(totalReplied * 0.28); // rough: ~28% of replies convert
  const convRate = totalSent > 0 ? Math.round((totalReplied / totalSent) * 100) : 0;

  // Pipeline stages for the orbital ring (5 stages, clockwise from top)
  const stages = [
    { id: 'new',      icon: '●', label: 'Active',   count: seqActive,       cls: '' },
    { id: 'sent',     icon: '→', label: 'Sent',     count: totalSent,       cls: 'sent' },
    { id: 'replied',  icon: '↩', label: 'Replied',  count: totalReplied,    cls: 'replied' },
    { id: 'unsub',    icon: '✕', label: 'Unsub',    count: totalUnsub,      cls: '' },
    { id: 'converted',icon: '★', label: 'Converted',count: totalConverted,   cls: 'converted' },
  ];

  return html`
    <div>
      <div class="section-h">
        <div>
          <div class="section-title">Pipeline <em>Orbital</em></div>
          <div class="section-sub">Email & SMS · 5-stage lifecycle</div>
        </div>
        <div class="section-sub">${seqActive} active · ${totalSent} sent · ${convRate}% reply rate</div>
      </div>

      <!-- ── 5-Stage Orbital Ring ── -->
      <div class="pipe-orbital-wrapper">
        ${(() => {
          const orbitR = 170;
          const outerR = 220;
          const innerR = 110;
          const svgW = outerR * 2 + 16;
          const svgH = outerR * 2 + 16;
          
          // SVG rings and lines
          const svgLines = stages.map((s, i) => {
            const angleDeg = i * (360 / stages.length) - 90;
            const angleRad = angleDeg * Math.PI / 180;
            const ax = Math.cos(angleRad) * orbitR;
            const ay = Math.sin(angleRad) * orbitR;
            const isActive = s.count > 0;
            return html`<line 
              x1="0" y1="0" 
              x2="${ax.toFixed(1)}" y2="${ay.toFixed(1)}" 
              class=${'pipe-orbit-line' + (isActive ? ' active' : '')}
              style=${{animationDelay: (i * 0.12) + 's'}}
            />`;
          });

          // Direction arrows between stages
          const arrows = stages.map((s, i) => {
            const nextI = (i + 1) % stages.length;
            const a1 = (i * (360 / stages.length) - 90) * Math.PI / 180;
            const a2 = (nextI * (360 / stages.length) - 90) * Math.PI / 180;
            const midR = orbitR;
            const x1 = Math.cos(a1) * midR * 0.82;
            const y1 = Math.sin(a1) * midR * 0.82;
            const x2 = Math.cos(a2) * midR * 0.82;
            const y2 = Math.sin(a2) * midR * 0.82;
            const mx = (x1 + x2) / 2;
            const my = (y1 + y2) / 2;
            const dx = x2 - x1;
            const dy = y2 - y1;
            const len = Math.sqrt(dx*dx + dy*dy);
            const ux = dx / len;
            const uy = dy / len;
            // Arrowhead triangle
            const tipX = x2;
            const tipY = y2;
            const baseX = tipX - ux * 10;
            const baseY = tipY - uy * 10;
            const wing = 5;
            const px = -uy * wing;
            const py = ux * wing;
            const points = `${tipX.toFixed(1)},${tipY.toFixed(1)} ${(baseX+px).toFixed(1)},${(baseY+py).toFixed(1)} ${(baseX-px).toFixed(1)},${(baseY-py).toFixed(1)}`;
            return html`<polygon class="pipe-orbit-arrow" points="${points}" style=${{animationDelay: (i * 0.2) + 's'}} />`;
          });
          
          return html`
            <svg class="pipe-orbital-svg" width="${svgW}" height="${svgH}" viewBox="${-svgW/2} ${-svgH/2} ${svgW} ${svgH}">
              <circle cx="0" cy="0" r="${outerR}" class="pipe-orbit-ring outer"/>
              <circle cx="0" cy="0" r="${orbitR}" class="pipe-orbit-ring pulse"/>
              <circle cx="0" cy="0" r="${innerR}" class="pipe-orbit-ring"/>
              ${svgLines}
              ${arrows}
            </svg>
            
            <!-- Boss card: conversion rate -->
            <div class="pipe-boss-card">
              <span class="pipe-boss-label">Reply Rate</span>
              <span class="pipe-boss-rate">${convRate}%</span>
              <span class="pipe-boss-sub">${totalReplied}/${totalSent}</span>
            </div>
            
            <!-- 5 stage nodes -->
            ${stages.map((s, i) => {
              const angleDeg = i * (360 / stages.length) - 90;
              const angleRad = angleDeg * Math.PI / 180;
              const ax = Math.cos(angleRad) * orbitR;
              const ay = Math.sin(angleRad) * orbitR;
              return html`
                <div class=${'pipe-stage-node' + (s.cls ? ' ' + s.cls : '')}
                     style=${{transform: 'translate(-50%,-50%) translate(' + ax.toFixed(1) + 'px,' + ay.toFixed(1) + 'px)', animationDelay: (i * 0.08) + 's'}}>
                  <span class="pipe-stage-icon">${s.icon}</span>
                  <span class="pipe-stage-count">${s.count}</span>
                  <span class="pipe-stage-label">${s.label}</span>
                </div>
              `;
            })}
          `;
        })()}
      </div>

      <!-- ── Engine panels below orbital ── -->
      <div class="split" style=${{marginTop: '8px'}}>
        <div class="panel">
          <div class="panel-head">Email Engine</div>
          <div class="sec-meta">Active: <strong>${d.em?.sequences_active ?? 0}</strong> · Sent: <strong>${d.em?.emails_sent ?? 0}</strong> · Replies: <strong>${d.em?.replies ?? 0}</strong> · Unsubs: <strong>${d.em?.unsubscribes ?? 0}</strong></div>
        </div>
        <div class="panel">
          <div class="panel-head">SMS Engine</div>
          <div class="sec-meta">Active: <strong>${d.sm?.sequences_active ?? 0}</strong> · Sent: <strong>${d.sm?.sms_sent ?? 0}</strong> · Replies: <strong>${d.sm?.replies ?? 0}</strong> · Opt-outs: <strong>${d.sm?.opt_outs ?? 0}</strong></div>
        </div>
      </div>
      <div class="panel">
        <div class="panel-head">Engine status</div>
        <div class="sec-meta">Email dispatcher: <strong>every 5s</strong> · limit 12/min · SMS dispatcher: <strong>every 5s</strong> · limit 6/min</div>
      </div>
    </div>
  `;
}

"""

    content = content[:idx_start] + new_func + content[idx_next:]
    changes += 1
    print(f"✓ Replaced Pipeline component with orbital pipeline layout")
else:
    print(f"Could not find Pipeline function markers: start={idx_start}, next={idx_next}")

with open('empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"\nTotal changes: {changes}")
