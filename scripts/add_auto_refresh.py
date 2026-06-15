"""
Add auto-refresh toggle to the CplPricing component in empire_command_spa.py.
Changes:
1. CSS for refresh toggle button and pulsing dot animation
2. autoRefresh state + polling useEffect
3. Toggle button in the export bar
"""
SPA = "/root/empire-v49/empire_command_spa.py"

with open(SPA, "r") as f:
    src = f.read()

changes = 0

# --- 1. ADD CSS FOR REFRESH TOGGLE ---
# Insert after the .cpl-export-btn:hover block (before the SVG rule)
old_css = """/* -- PRINT STYLES ------------------------------------------------- */"""
new_css = """/* -- AUTO-REFRESH TOGGLE ----------------------------------------- */
@keyframes cpl-refresh-pulse{0%,100%{opacity:1}50%{opacity:0.3}}
.cpl-refresh-btn{padding:6px 14px;border:1px solid var(--empire-border);border-radius:5px;cursor:pointer;font-family:var(--font-mono);font-size:10px;color:var(--empire-mist);background:transparent;transition:all 0.15s var(--ease-snap);display:flex;align-items:center;gap:6px}
.cpl-refresh-btn:hover{border-color:var(--signal-teal);color:var(--signal-teal);background:var(--signal-teal-soft)}
.cpl-refresh-btn.active{border-color:var(--signal-teal);color:var(--signal-teal);background:rgba(68,229,184,0.08)}
.cpl-refresh-dot{width:8px;height:8px;border-radius:50%;background:var(--empire-fog);flex-shrink:0;transition:all 0.3s var(--ease-snap)}
.cpl-refresh-btn.active .cpl-refresh-dot{background:var(--signal-teal);box-shadow:0 0 8px rgba(68,229,184,0.6);animation:cpl-refresh-pulse 2s ease-in-out infinite}
.cpl-refresh-label{font-size:9px;letter-spacing:0.06em}
/* -- PRINT STYLES ------------------------------------------------- */"""

if old_css in src:
    src = src.replace(old_css, new_css)
    changes += 1
    print("[OK] Added refresh toggle CSS")
else:
    print("[WARN] Could not find print styles CSS marker")

# --- 2. ADD autoRefresh STATE ---
old_state = """  const [roiLoading, setRoiLoading] = React.useState(false);

  React.useEffect(() => {"""
new_state = """  const [roiLoading, setRoiLoading] = React.useState(false);
  const [autoRefresh, setAutoRefresh] = React.useState(false);

  // Initial data fetch
  const fetchLanes = () => {
    apiFetch('/api/v1/cpl/lanes?model=both&monthly_volume=100')
      .then(data => { setLanes(data.lanes || data); setLoading(false); })
      .catch(e => { setError(e.message || 'Failed to load CPL data'); setLoading(false); });
  };

  React.useEffect(() => {
    fetchLanes();
  }, []);

  // Auto-refresh: poll every 30 seconds when toggled on
  React.useEffect(() => {
    if (!autoRefresh) return;
    const interval = setInterval(() => {
      apiFetch('/api/v1/cpl/lanes?model=both&monthly_volume=100')
        .then(data => { setLanes(data.lanes || data); })
        .catch(e => { /* silent refresh failure */ });
    }, 30000);
    return () => clearInterval(interval);
  }, [autoRefresh]);"""

if old_state in src:
    src = src.replace(old_state, new_state)
    changes += 1
    print("[OK] Added autoRefresh state and polling useEffect")
else:
    print("[WARN] Could not find state declarations")

# --- 3. ADD REFRESH TOGGLE BUTTON IN EXPORT BAR ---
# Add refresh button before the CSV button
old_export_bar = """        <div class="cpl-export-bar">
          <button class="cpl-export-btn\" """
# Actually, let me be more precise. I'll add the refresh toggle at the end of the export bar, after the PDF button
old_export_bar = """            PDF
          </button>
        </div>
        <div class="cpl-tabs\">"""
new_export_bar = """            PDF
          </button>
          <button class="cpl-refresh-btn ${autoRefresh ? 'active' : ''}" onClick=${() => setAutoRefresh(!autoRefresh)} title="Toggle auto-refresh (30s)">
            <span class="cpl-refresh-dot"></span>
            <span class="cpl-refresh-label">${autoRefresh ? 'LIVE' : 'AUTO'}</span>
          </button>
        </div>
        <div class="cpl-tabs\">"""

if old_export_bar in src:
    src = src.replace(old_export_bar, new_export_bar)
    changes += 1
    print("[OK] Added refresh toggle button in export bar")
else:
    print("[WARN] Could not find export bar — trying alternative approach")
    # Try finding the closing </div> of cpl-export-bar followed by cpl-tabs
    idx = src.find('cpl-export-bar')
    if idx > 0:
        # Find the closing </div> of cpl-export-bar
        close_idx = src.find('</div>', idx)
        if close_idx > 0:
            # Insert the refresh button before </div>
            insert = '\n          <button class="cpl-refresh-btn ${autoRefresh ? \'active\' : \'\'}" onClick=${() => setAutoRefresh(!autoRefresh)} title="Toggle auto-refresh (30s)">\n            <span class="cpl-refresh-dot"></span>\n            <span class="cpl-refresh-label">${autoRefresh ? \'LIVE\' : \'AUTO\'}</span>\n          </button>'
            src = src[:close_idx] + insert + src[close_idx:]
            changes += 1
            print("[OK] Added refresh toggle button via fallback approach")
        else:
            print("[WARN] Could not find </div> in export bar")

# --- WRITE ---
with open(SPA, "w") as f:
    f.write(src)

print(f"\nDone -- {changes} changes applied")
