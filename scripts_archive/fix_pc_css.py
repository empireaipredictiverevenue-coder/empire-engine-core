"""Fix CSS class names: fb-* → pc-* and remove old panel detail CSS, add agent pool CSS."""
with open('/root/empire-v49/empire_command_spa.py', 'r') as f:
    content = f.read()

changes = 0

# Replace ALL fb- CSS class prefixes with pc-
import re
fb_matches = re.findall(r'\bfb-(summary|decision|mini|score|verdict|detail|judge)[-a-z]*\b', content)
unique = set(fb_matches)
print(f"Found fb-* CSS classes to replace: {sorted(unique)}")

content = content.replace('fb-summary', 'pc-summary')
content = content.replace('fb-decision', 'pc-decision')
content = content.replace('fb-mini-vote', 'pc-mini-vote')
content = content.replace('fb-score-circle', 'pc-score-circle')
content = content.replace('fb-score-ok', 'pc-score-ok')
content = content.replace('fb-score-warn', 'pc-score-warn')
content = content.replace('fb-score-bad', 'pc-score-bad')
content = content.replace('fb-verdict-badge', 'pc-verdict-badge')
content = content.replace('fb-detail-grid', 'pc-detail-grid')
content = content.replace('fb-detail-panel', 'pc-detail-panel')
content = content.replace('fb-detail-decision', 'pc-detail-decision')
content = content.replace('fb-detail-stat', 'pc-detail-stat')
content = content.replace('fb-judge-block', 'pc-judge-block')
content = content.replace('fb-judge-head', 'pc-judge-head')
content = content.replace('fb-judge-weighted', 'pc-judge-weighted')
content = content.replace('fb-judge-reasoning', 'pc-judge-reasoning')
changes += 1
print("1. CSS class prefix: fb- → pc-")

# Add agent pool CSS after the panel court CSS block
old_marker = "/* ── SEO PERFORMANCE ─────────────────────────────────────────── */"
new_css = """/* ── PANEL COURT AGENT POOL ─────────────────────────────────── */
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
.pc-agent-won{font-family:var(--font-mono);font-size:7px;letter-spacing:.1em;text-transform:uppercase;color:var(--signal-teal);text-align:center;margin-top:6px;padding-top:6px;border-top:1px solid var(--empire-divider)}
.pc-decision-panel{background:var(--empire-surface);border:1px solid var(--empire-border);padding:20px}
.pc-decision-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:16px;padding-bottom:14px;border-bottom:1px solid var(--empire-divider)}
.pc-decision-title{font-weight:500;font-size:14px;color:var(--empire-white);letter-spacing:.02em}
.pc-decision-count{font-family:var(--font-mono);font-size:10px;color:var(--signal-teal)}
.pc-decision-list{display:flex;flex-direction:column;gap:8px}
.pc-decision-card{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 18px;transition:border-color .15s var(--ease-snap);cursor:pointer}
.pc-decision-card:hover{border-color:var(--empire-border-hi)}
.pc-decision-card.expanded{border-color:var(--signal-teal-soft)}
.pc-decision-row{display:grid;grid-template-columns:1fr 80px 48px 72px;gap:12px;align-items:center}
.pc-decision-lead{display:flex;flex-direction:column;gap:2px;min-width:0}
.pc-decision-lead-name{font-size:12px;color:var(--empire-white);font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.pc-decision-lead-id{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.06em}
.pc-decision-winner{text-align:center}
.pc-winner-badge{font-family:var(--font-mono);font-size:8px;letter-spacing:.08em;text-transform:uppercase;color:var(--signal-teal);border:1px solid rgba(68,229,184,0.2);padding:2px 6px;border-radius:3px}
.pc-score-circle{width:38px;height:38px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-family:var(--font-mono);font-size:12px;font-weight:600;border:2px solid}
.pc-score-ok{color:var(--signal-teal);border-color:rgba(68,229,184,0.3);background:rgba(68,229,184,0.06)}
.pc-score-warn{color:var(--status-amber);border-color:rgba(255,184,0,0.3);background:rgba(255,184,0,0.06)}
.pc-score-bad{color:var(--status-red);border-color:rgba(255,68,68,0.3);background:rgba(255,68,68,0.06)}
.pc-verdict-badge{display:inline-block;font-family:var(--font-mono);font-size:8px;letter-spacing:.12em;text-transform:uppercase;padding:3px 10px;border-radius:4px;font-weight:600}
.pc-verdict-badge.dispatch{color:var(--signal-teal);border:1px solid var(--signal-teal-soft)}
.pc-verdict-badge.reject{color:var(--status-red);border:1px solid rgba(255,68,68,0.2)}
.pc-decision-detail{margin-top:16px;padding-top:14px;border-top:1px solid var(--empire-divider)}
.pc-detail-title{font-family:var(--font-mono);font-size:9px;color:var(--empire-mist);letter-spacing:.14em;text-transform:uppercase;margin-bottom:12px}
.pc-detail-scores{display:grid;grid-template-columns:repeat(5,1fr);gap:8px;margin-bottom:14px}
.pc-detail-score{background:var(--empire-surface);border:1px solid var(--empire-divider);padding:8px;text-align:center;border-radius:4px}
.pc-detail-score.winner{border-color:rgba(68,229,184,0.3);background:rgba(68,229,184,0.04)}
.pc-detail-aid{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.08em;display:block;margin-bottom:2px}
.pc-detail-pts{font-family:var(--font-mono);font-size:14px;color:var(--empire-white);font-weight:500}
.pc-judge-block{background:var(--empire-elevated);border:1px solid var(--empire-divider);padding:14px 16px;border-radius:4px;border-left:3px solid var(--strike-cyan);margin-top:12px}
.pc-judge-head{font-family:var(--font-mono);font-size:9px;color:var(--strike-cyan);letter-spacing:.1em;text-transform:uppercase;margin-bottom:8px}
.pc-judge-reasoning{font-size:11px;color:var(--empire-silver);line-height:1.6}
.pc-summary-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:20px}
.pc-summary-card{background:var(--empire-surface);border:1px solid var(--empire-border);padding:16px 18px;text-align:center}
.pc-summary-val{font-family:var(--font-display);font-weight:200;font-size:32px;color:var(--empire-white);line-height:1}
.pc-summary-val.teal{color:var(--signal-teal)}
.pc-summary-val.amber{color:var(--status-amber)}
.pc-summary-val.red{color:var(--status-red)}
.pc-summary-val.dim{color:var(--empire-mist)}
.pc-summary-lbl{font-family:var(--font-mono);font-size:8px;color:var(--empire-fog);letter-spacing:.14em;text-transform:uppercase;margin-top:6px}

/* ── SEO PERFORMANCE ─────────────────────────────────────────── */"""

if old_marker in content:
    content = content.replace(old_marker, new_css)
    changes += 1
    print("2. Agent pool CSS: added before SEO section")
else:
    print("2. SEO marker not found")

with open('/root/empire-v49/empire_command_spa.py', 'w') as f:
    f.write(content)

print(f"Done: {changes} changes applied")
