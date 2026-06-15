#!/usr/bin/env python3
"""Patch empire_command_spa.py to add lastRefreshed timestamp to the reloading bar."""

import sys

FILE = "/root/empire-v49/empire_command_spa.py"

with open(FILE, 'r') as f:
    content = f.read()

changes = 0

# ── EDIT 1: Add lastRefreshed state after autoRefresh state ──
old1 = "  const [autoRefresh, setAutoRefresh] = React.useState(false);\n  const [cmpNicheFilter, setCmpNicheFilter] = React.useState(null);"
new1 = "  const [autoRefresh, setAutoRefresh] = React.useState(false);\n  const [lastRefreshed, setLastRefreshed] = React.useState(null);\n  const [cmpNicheFilter, setCmpNicheFilter] = React.useState(null);"

if old1 in content:
    content = content.replace(old1, new1, 1)
    changes += 1
    print("[OK] Edit 1: Added lastRefreshed state")
else:
    print("[FAIL] Edit 1: Could not find autoRefresh state line")

# ── EDIT 2: Add setLastRefreshed to fetchLanes success callback ──
old2 = "fetchLanes(modelToParam(modelFilter));\n    setPage(1);\n  }, [modelFilter]);"
new2 = "fetchLanes(modelToParam(modelFilter));\n    setPage(1);\n  }, [modelFilter]);\n\n  // Track when lanes were last refreshed\n  function setLastRefreshedNow() {\n    setLastRefreshed(new Date());\n  }"

if old2 in content:
    content = content.replace(old2, new2, 1)
    changes += 1
    print("[OK] Edit 2: Added setLastRefreshedNow helper")
else:
    print("[FAIL] Edit 2: Could not find modelFilter useEffect")

# ── EDIT 3: Add setLastRefreshedNow() to auto-refresh success handler ──
old3 = ".then(data => { setLanes(prepareLaneData(data.lanes || data)); setReloading(false); })\n        .catch(e => { setReloading(false); /* silent refresh failure */ });"
new3 = ".then(data => { setLanes(prepareLaneData(data.lanes || data)); setReloading(false); setLastRefreshed(new Date()); })\n        .catch(e => { setReloading(false); /* silent refresh failure */ });"

if old3 in content:
    content = content.replace(old3, new3, 1)
    changes += 1
    print("[OK] Edit 3: Added setLastRefreshed to auto-refresh")
else:
    print("[FAIL] Edit 3: Could not find auto-refresh success handler")

# ── EDIT 4: Add setLastRefreshed to initial load + fetchLanes ──
# fetchLanes success
old4a = ".then(data => { setLanes(prepareLaneData(data.lanes || data)); setLoading(false); setReloading(false); })\n      .catch(e => { setError(e.message || 'Failed to load CPL data'); setLoading(false); setReloading(false); });\n  };\n\n  React.useEffect(() => {\n    fetchLanes(modelToParam(modelFilter));"
new4a = ".then(data => { setLanes(prepareLaneData(data.lanes || data)); setLoading(false); setReloading(false); setLastRefreshed(new Date()); })\n      .catch(e => { setError(e.message || 'Failed to load CPL data'); setLoading(false); setReloading(false); });\n  };\n\n  React.useEffect(() => {\n    fetchLanes(modelToParam(modelFilter));"

if old4a in content:
    content = content.replace(old4a, new4a, 1)
    changes += 1
    print("[OK] Edit 4a: Added setLastRefreshed to fetchLanes success")
else:
    print("[FAIL] Edit 4a: Could not find fetchLanes success handler")

# initial load success
old4b = ".then(data => { setLanes(prepareLaneData(data.lanes || data)); setLoading(false); setReloading(false); })\n      .catch(e => { setError(e.message || 'Failed to load CPL data'); setLoading(false); setReloading(false); });\n  }, []);\n\n  if (loading)"
new4b = ".then(data => { setLanes(prepareLaneData(data.lanes || data)); setLoading(false); setReloading(false); setLastRefreshed(new Date()); })\n      .catch(e => { setError(e.message || 'Failed to load CPL data'); setLoading(false); setReloading(false); });\n  }, []);\n\n  if (loading)"

if old4b in content:
    content = content.replace(old4b, new4b, 1)
    changes += 1
    print("[OK] Edit 4b: Added setLastRefreshed to initial load")
else:
    print("[FAIL] Edit 4b: Could not find initial load success handler")

# ── EDIT 5: Update reloadingIndicator to include timestamp ──
old5 = "const reloadingIndicator = reloading ? html`<div class=\"cpl-reloading-bar\"><div class=\"cpl-reloading-bar-inner\"></div></div>` : html``;"
new5 = "const reloadingIndicator = reloading ? html`<div class=\"cpl-reloading-bar\"><div class=\"cpl-reloading-bar-inner\"></div></div>` : html``;\n  const lastRefreshedStr = lastRefreshed ? html`<span class=\"cpl-last-refreshed\">${(() => { const d = lastRefreshed; const pad = n => String(n).padStart(2,'0'); return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); })()}</span>` : html``;"

if old5 in content:
    content = content.replace(old5, new5, 1)
    changes += 1
    print("[OK] Edit 5: Added lastRefreshedStr")
else:
    print("[FAIL] Edit 5: Could not find reloadingIndicator")

# ── EDIT 6: Use lastRefreshedStr in template next to reloading bar ──
old6 = "${reloadingIndicator}\n        <div class=\"cpl-nav\">"
new6 = "${reloadingIndicator}\n        ${reloadingIndicator || !lastRefreshed ? '' : html`<div class=\"cpl-last-refreshed-row\"><span class=\"cpl-last-refreshed\">Last refreshed: ${(() => { const d = lastRefreshed; const pad = n => String(n).padStart(2,'0'); return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); })()}</span></div>`}\n        <div class=\"cpl-nav\">"

if old6 in content:
    content = content.replace(old6, new6, 1)
    changes += 1
    print("[OK] Edit 6: Added lastRefreshed display to template")
else:
    print("[FAIL] Edit 6: Could not find reloadingIndicator in template")

# ── EDIT 7: Add CSS for last-refreshed timestamp ──
old7 = ".cpl-reloading-bar{height:2px;background:var(--empire-divider);overflow:hidden;margin-bottom:8px;border-radius:2px}"
new7 = ".cpl-last-refreshed-row{display:flex;align-items:center;justify-content:flex-end;margin-bottom:6px;gap:6px}\n.cpl-last-refreshed{font-family:var(--font-mono);font-size:9px;color:var(--empire-fog);letter-spacing:.06em}\n.cpl-reloading-bar{height:2px;background:var(--empire-divider);overflow:hidden;margin-bottom:8px;border-radius:2px}"

if old7 in content:
    content = content.replace(old7, new7, 1)
    changes += 1
    print("[OK] Edit 7: Added CSS for last-refreshed timestamp")
else:
    print("[FAIL] Edit 7: Could not find cpl-reloading-bar CSS")

if changes == 0:
    print("\n[ERROR] No changes were made! Exiting.")
    sys.exit(1)

with open(FILE, 'w') as f:
    f.write(content)

print(f"\n[DONE] Applied {changes} edits to {FILE}")
