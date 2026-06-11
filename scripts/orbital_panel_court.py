#!/usr/bin/env python3
"""Replace grid layout with radial orbital layout for Panel Court agent pool."""
import re

with open('empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# ── 1. Replace the agent pool CSS section (pc-pool-grid, pc-agent-card, etc.) ──
old_css_block = """/* ── PANEL COURT AGENT POOL ─────────────────────────────────── */
.pc-pool-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:20px}
.pc-pool-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.pc-pool-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.pc-pool-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em}
.pc-pool-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}
.pc-agent-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:12px 14px;border-radius:6px;transition:border-color .15s var(--ease-snap);position:relative}
.pc-agent-card:hover{border-color:var(--empire-border-hi)}
.pc-agent-card.winner{border-color:rgba(68,229,184,0.25);background:rgba(68,229,184,0.03)}
.pc-agent-top{display:flex;justify-content:space-between;align-items:center;margin-bottom:8px}
.pc-agent-id{font-family:var(--font-mono);font-size:11px;color:var(--empire-white);font-weight:500}
.pc-agent-temp{font-family:var(--font-mono);font-size:8px;letter-spacing:.1em;padding:1px 5px;border-radius:3px}
.pc-agent-temp.cold{color:var(--strike-cyan);border:1px solid rgba(90,200,250,0.2);background:rgba(90,200,250,0.04)}
.pc-agent-temp.warm{color:var(--status-amber);border:1px solid rgba(255,184,0,0.2);background:rgba(255,184,0,0.04)}
.pc-agent-temp.hot{color:var(--status-red);border:1px solid rgba(255,68,68,0.2);background:rgba(255,68,68,0.04)}
.pc-agent-wins{display:flex;flex-direction:column;align-items:center;margin-bottom:6px}
.pc-agent-wr{font-family:var(--font-display);font-weight:200;font-size:28px;color:var(--signal-teal);line-height:1}
.pc-agent-wl{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.08em}
.pc-agent-bar-wrap{height:4px;background:var(--empire-surface);border-radius:2px;overflow:hidden;margin-bottom:6px}
.pc-agent-bar{height:100%;background:var(--signal-teal);border-radius:2px;transition:width .6s var(--ease-out-empire)}
.pc-agent-runs{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.06em;text-align:center}
.pc-agent-won{font-family:var(--font-mono);font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:var(--signal-teal);text-align:center;margin-top:6px;padding-top:6px;border-top:1px solid var(--empire-divider)}"""

# Check which variant exists
if "pc-pool-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}" not in content:
    # Try the multiline version that might have newlines
    for variant in [
        "pc-pool-grid{display:grid;grid-template-columns:repeat(5,1fr);gap:10px}",
        "repeat(5,1fr)",
    ]:
        if variant in content:
            print(f"Found variant: {variant[:50]}...")
            break
    else:
        print("WARNING: Could not find pc-pool-grid CSS. Searching...")
        # Find the section
        idx = content.find("PANEL COURT AGENT POOL")
        if idx > 0:
            print(f"Found at index {idx}")
        else:
            print("Could not find PANEL COURT AGENT POOL section at all!")

new_css_block = """/* ── PANEL COURT ORBITAL LAYOUT ──────────────────────────────── */
@keyframes pc-orbit-pulse{0%,100%{box-shadow:0 0 8px rgba(68,229,184,0.2)}50%{box-shadow:0 0 18px rgba(68,229,184,0.5)}}
@keyframes pc-orbit-rotate{from{stroke-dashoffset:0}to{stroke-dashoffset:-628.32}}
@keyframes pc-boss-glow{0%,100%{box-shadow:0 0 12px rgba(90,200,250,0.15),0 0 24px rgba(90,200,250,0.05)}50%{box-shadow:0 0 20px rgba(90,200,250,0.3),0 0 40px rgba(90,200,250,0.1)}}
@keyframes pc-agent-enter{0%{opacity:0;transform:translate(-50%,-50%) scale(0.6)}100%{opacity:1;transform:translate(-50%,-50%) scale(1)}}
@keyframes pc-line-draw{0%{stroke-dashoffset:200}100%{stroke-dashoffset:0}}
.pc-pool-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px;margin-bottom:20px}
.pc-pool-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.pc-pool-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.pc-pool-tag{font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);letter-spacing:.14em}
/* ── Orbital wrapper ── */
.pc-orbital-wrapper{position:relative;width:100%;min-height:540px;display:flex;align-items:center;justify-content:center;margin:10px 0}
.pc-orbital-svg{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);pointer-events:none;z-index:1}
.pc-orbit-ring{fill:none;stroke:rgba(255,255,255,0.04);stroke-width:1px}
.pc-orbit-ring.outer{stroke:rgba(255,255,255,0.03);stroke-width:1px}
.pc-orbit-ring.inner{stroke:rgba(68,229,184,0.06);stroke-width:1px;stroke-dasharray:4 8}
.pc-orbit-ring.pulse{stroke:rgba(68,229,184,0.08);stroke-width:2px;stroke-dasharray:20 10;animation:pc-orbit-rotate 20s linear infinite}
.pc-orbit-line{fill:none;stroke:rgba(90,200,250,0.1);stroke-width:1px;stroke-dasharray:200;stroke-dashoffset:200;animation:pc-line-draw 1.5s var(--ease-out-empire) forwards}
.pc-orbit-line.winner{stroke:rgba(68,229,184,0.25);stroke-width:1.5px}
/* ── Boss agent (center) ── */
.pc-boss-card{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);z-index:3;width:130px;height:130px;border-radius:50%;background:radial-gradient(circle,rgba(90,200,250,0.08) 0%,rgba(90,200,250,0.02) 60%,transparent 100%);border:2px solid rgba(90,200,250,0.2);display:flex;flex-direction:column;align-items:center;justify-content:center;animation:pc-boss-glow 3s ease-in-out infinite;transition:all .3s var(--ease-snap)}
.pc-boss-card:hover{border-color:rgba(90,200,250,0.4);transform:translate(-50%,-50%) scale(1.05)}
.pc-boss-label{font-family:var(--font-mono);font-size:7px;color:var(--strike-cyan);letter-spacing:.18em;text-transform:uppercase;margin-bottom:4px}
.pc-boss-title{font-weight:500;font-size:13px;color:var(--empire-white);letter-spacing:.02em;margin-bottom:2px}
.pc-boss-sub{font-family:var(--font-mono);font-size:7px;color:var(--empire-fog);letter-spacing:.1em}
.pc-boss-roles{display:flex;gap:3px;margin-top:6px;flex-wrap:wrap;justify-content:center}
.pc-boss-role{font-family:var(--font-mono);font-size:6px;letter-spacing:.08em;text-transform:uppercase;padding:1px 4px;border-radius:2px;border:1px solid;color:var(--empire-mist);border-color:var(--empire-divider)}
/* ── Orbiting agent cards ── */
.pc-orbital-agent{position:absolute;z-index:2;width:82px;height:52px;background:var(--empire-elevated);border:1px solid var(--empire-divider);border-radius:8px;padding:6px 8px;text-align:center;transition:all .2s var(--ease-snap);animation:pc-agent-enter .4s var(--ease-out-empire) both;transform-origin:center center}
.pc-orbital-agent:hover{border-color:var(--empire-border-hi);z-index:4;transform:translate(-50%,-50%) scale(1.12) !important;box-shadow:0 4px 20px rgba(0,0,0,0.3)}
.pc-orbital-agent.winner{border-color:rgba(68,229,184,0.35);background:rgba(68,229,184,0.04);animation:pc-orbit-pulse 2s ease-in-out infinite,pc-agent-enter .4s var(--ease-out-empire) both}
.pc-orbital-agent-id{font-family:var(--font-mono);font-size:9px;color:var(--empire-white);font-weight:500;display:block;margin-bottom:1px}
.pc-orbital-agent-temp{font-family:var(--font-mono);font-size:7px;letter-spacing:.08em;padding:0 3px;border-radius:2px;display:inline-block}
.pc-orbital-agent-temp.cold{color:var(--strike-cyan);border:1px solid rgba(90,200,250,0.2);background:rgba(90,200,250,0.04)}
.pc-orbital-agent-temp.warm{color:var(--status-amber);border:1px solid rgba(255,184,0,0.2);background:rgba(255,184,0,0.04)}
.pc-orbital-agent-temp.hot{color:var(--status-red);border:1px solid rgba(255,68,68,0.2);background:rgba(255,68,68,0.04)}
.pc-orbital-agent-wr{font-family:var(--font-display);font-weight:200;font-size:15px;color:var(--signal-teal);line-height:1;display:block}
.pc-orbital-agent-wl{font-family:var(--font-mono);font-size:6px;color:var(--empire-fog);letter-spacing:.06em}
.pc-orbital-agent-won{font-family:var(--font-mono);font-size:6px;letter-spacing:.08em;text-transform:uppercase;color:var(--signal-teal);position:absolute;top:-8px;left:50%;transform:translateX(-50%);background:var(--empire-surface);padding:1px 5px;border-radius:3px;border:1px solid rgba(68,229,184,0.2);white-space:nowrap}
/* ── Responsive ── */
@media (max-width:768px){
  .pc-orbital-wrapper{min-height:440px}
  .pc-orbital-agent{width:65px;height:44px;padding:4px 6px}
  .pc-boss-card{width:100px;height:100px}
  .pc-boss-title{font-size:11px}
}"""

if old_css_block in content:
    content = content.replace(old_css_block, new_css_block)
    changes += 1
    print("✓ Replaced agent pool CSS with orbital layout CSS")
else:
    # Try alternative: the first line varies
    first_line = "/* ── PANEL COURT AGENT POOL ─────────────────────────────────── */"
    if first_line in content:
        # Find the full block by scanning
        idx = content.find(first_line)
        # Find where the next section starts
        next_section = "/* ── PANEL COURT AGENT POOL ─────────────────────────────────── */"
        next_idx = content.find(next_section, idx + len(next_section))
        if next_idx > 0:
            # There's a duplicate; find the second occurrence and replace from first to second
            old_block = content[idx:next_idx]
            content = content[:idx] + new_css_block + "\n\n" + content[next_idx:]
            changes += 1
            print("✓ Replaced first agent pool CSS block with orbital layout CSS")
        else:
            # Find the end of this block (before pc-decision-panel)
            end_marker = ".pc-decision-panel"
            end_idx = content.find(end_marker, idx)
            if end_idx > 0:
                old_block = content[idx:end_idx]
                content = content[:idx] + new_css_block + "\n\n" + content[end_idx:]
                changes += 1
                print("✓ Replaced agent pool CSS with orbital layout CSS (using end marker)")
            else:
                print("Could not find end of css block")
    else:
        print("Could not find agent pool CSS section header")

# ── 2. Also replace the DUPLICATE CSS block (second occurrence) ──
# The file has duplicate CSS blocks for pc-summary-grid etc. Let's clean those up while we're at it
# by finding the second "PANEL COURT AGENT POOL" occurrence if any
first_pool_idx = content.find("/* ── PANEL COURT ORBITAL LAYOUT ──────────────────────────────── */")
second_pool_idx = content.find("/* ── PANEL COURT AGENT POOL ─────────────────────────────────── */", first_pool_idx + 50)
if second_pool_idx > 0:
    # Find the next section after this duplicate
    next_seo = content.find("/* ── SEO PERFORMANCE", second_pool_idx)
    if next_seo > 0:
        content = content[:second_pool_idx] + content[next_seo:]
        changes += 1
        print("✓ Removed duplicate agent pool CSS block")

# ── 3. Replace the JSX agent pool grid section ──
old_jsx = """      <!-- ── 10-Agent Pool Grid ── -->
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
      ` : ''}"""

new_jsx = """      <!-- ── 10-Agent Orbital Ring ── -->
      ${agents.length > 0 ? html`
      <div class="pc-pool-panel">
        <div class="pc-pool-head">
          <span class="pc-pool-title">Agent Pool</span>
          <span class="pc-pool-tag">${agents.filter(a => a.total_runs > 0).length}/10 active · orbital mesh</span>
        </div>
        <div class="pc-orbital-wrapper">
          ${(() => {
            const cx = 0, cy = 0;
            const orbitR = 180;  // radius for the 10-agent ring
            const innerR = 110;  // inner decorative ring
            const outerR = 240;  // outer decorative ring
            const svgW = outerR * 2 + 20;
            const svgH = outerR * 2 + 20;
            
            // SVG for rings and connection lines
            const winnerId = data.length > 0 ? data[0].winner_agent_id : null;
            const svgLines = agents.map((a, i) => {
              const angleDeg = (i * 360 / agents.length) - 90; // start from top
              const angleRad = angleDeg * Math.PI / 180;
              const ax = Math.cos(angleRad) * orbitR;
              const ay = Math.sin(angleRad) * orbitR;
              const isWinner = a.id === winnerId;
              return html`<line 
                x1="0" y1="0" 
                x2="${ax}" y2="${ay}" 
                class=${'pc-orbit-line' + (isWinner ? ' winner' : '')} 
                style=${{animationDelay: (i * 0.1) + 's'}}
              />`;
            });
            
            return html`
              <svg class="pc-orbital-svg" width="${svgW}" height="${svgH}" viewBox="${-svgW/2} ${-svgH/2} ${svgW} ${svgH}">
                <!-- Outer ring -->
                <circle cx="0" cy="0" r="${outerR}" class="pc-orbit-ring outer"/>
                <!-- Main orbit ring -->
                <circle cx="0" cy="0" r="${orbitR}" class="pc-orbit-ring pulse"/>
                <!-- Inner ring -->
                <circle cx="0" cy="0" r="${innerR}" class="pc-orbit-ring inner"/>
                <!-- Connection lines from center -->
                ${svgLines}
              </svg>
              
              <!-- Boss agent (center) -->
              <div class="pc-boss-card">
                <span class="pc-boss-label">Panel Court</span>
                <span class="pc-boss-title">The Judge</span>
                <span class="pc-boss-sub">5-Role Panel</span>
                <div class="pc-boss-roles">
                  <span class="pc-boss-role">CFO</span>
                  <span class="pc-boss-role">Growth</span>
                  <span class="pc-boss-role">Strategy</span>
                  <span class="pc-boss-role">Purist</span>
                  <span class="pc-boss-role">Judge</span>
                </div>
              </div>
              
              <!-- 10 orbiting agents -->
              ${agents.map((a, i) => {
                const angleDeg = (i * 360 / agents.length) - 90;
                const angleRad = angleDeg * Math.PI / 180;
                const ax = Math.cos(angleRad) * orbitR;
                const ay = Math.sin(angleRad) * orbitR;
                const wr = a.win_rate || 0;
                const wrPct = Math.round(wr * 100);
                const tempCls = a.temperature <= 0.3 ? 'cold' : a.temperature >= 0.55 ? 'hot' : 'warm';
                const wonLast = data.length > 0 && data[0].winner_agent_id === a.id;
                
                return html`
                  <div class=${'pc-orbital-agent' + (wonLast ? ' winner' : '')}
                       style=${{transform: 'translate(-50%,-50%) translate(' + ax + 'px,' + ay + 'px)', animationDelay: (i * 0.05) + 's'}}>
                    <span class="pc-orbital-agent-id">#${a.id}</span>
                    <span class=${'pc-orbital-agent-temp ' + tempCls}>${a.temperature.toFixed(2)}°</span>
                    <span class="pc-orbital-agent-wr">${wrPct}%</span>
                    <span class="pc-orbital-agent-wl">${a.wins}W ${a.losses}L</span>
                    ${wonLast ? html`<span class="pc-orbital-agent-won">★ Winner</span>` : ''}
                  </div>
                `;
              })}
            `;
          })()}
        </div>
      </div>
      ` : ''}"""

if old_jsx in content:
    content = content.replace(old_jsx, new_jsx)
    changes += 1
    print("✓ Replaced agent pool grid JSX with orbital layout JSX")
else:
    print("Could not find exact JSX block. Searching for partial match...")
    # Try finding the section header
    marker = "<!-- ── 10-Agent Pool Grid ── -->"
    if marker in content:
        print("Found marker. Attempting regex-based replacement...")
        # Find start of the block
        start_idx = content.find(marker)
        # Find end of the block (before the next comment)
        next_marker = "<!-- ── Decision List ── -->"
        end_idx = content.find(next_marker, start_idx)
        if end_idx > 0:
            old_block = content[start_idx:end_idx]
            content = content[:start_idx] + new_jsx + "\n\n      " + content[end_idx:]
            changes += 1
            print(f"✓ Replaced JSX block using markers ({len(old_block)} chars → {len(new_jsx)} chars)")
        else:
            print("Could not find end marker")
    else:
        # Try variant comment
        for variant in ["10-Agent Pool", "Agent Pool Grid", "pc-pool-grid"]:
            if variant in content:
                idx = content.find(variant)
                print(f"Found partial marker '{variant}' at index {idx}")
                break
        else:
            print("Could not find any marker for agent pool grid JSX")

with open('empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"\nTotal changes: {changes}")
