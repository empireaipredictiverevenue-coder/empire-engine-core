#!/usr/bin/env python3
"""Fix last-refreshed timestamp: broken conditional and dead code."""

FILE = "/root/empire-v49/empire_command_spa.py"

with open(FILE, 'r') as f:
    content = f.read()

changes = 0

# ── FIX 1: Remove unused setLastRefreshedNow helper ──
old1 = "\n  // Track when lanes were last refreshed\n  function setLastRefreshedNow() {\n    setLastRefreshed(new Date());\n  }"
if old1 in content:
    content = content.replace(old1, "", 1)
    changes += 1
    print("[OK] Fix 1: Removed unused setLastRefreshedNow helper")
else:
    print("[FAIL] Fix 1: Could not find setLastRefreshedNow")

# ── FIX 2: Remove unused lastRefreshedStr variable ──
old2 = "\n  const lastRefreshedStr = lastRefreshed ? html`<span class=\"cpl-last-refreshed\">${(() => { const d = lastRefreshed; const pad = n => String(n).padStart(2,'0'); return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); })()}</span>` : html``;"
if old2 in content:
    content = content.replace(old2, "", 1)
    changes += 1
    print("[OK] Fix 2: Removed unused lastRefreshedStr variable")
else:
    print("[FAIL] Fix 2: Could not find lastRefreshedStr")

# ── FIX 3: Fix the broken conditional that never shows the timestamp ──
# The old code: ${reloadingIndicator || !lastRefreshed ? '' : html`...`}
# The problem: reloadingIndicator is always truthy (even empty html`` is a VNode)
# New code: show timestamp only when NOT reloading AND a timestamp exists
old3 = "${reloadingIndicator}\n        ${reloadingIndicator || !lastRefreshed ? '' : html`<div class=\"cpl-last-refreshed-row\"><span class=\"cpl-last-refreshed\">Last refreshed: ${(() => { const d = lastRefreshed; const pad = n => String(n).padStart(2,'0'); return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); })()}</span></div>`}\n        <div class=\"cpl-nav\">"
new3 = "${reloadingIndicator}\n        ${!reloading && lastRefreshed ? html`<div class=\"cpl-last-refreshed-row\"><span class=\"cpl-last-refreshed\">Last refreshed: ${(() => { const d = lastRefreshed; const pad = n => String(n).padStart(2,'0'); return pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()); })()}</span></div>` : ''}\n        <div class=\"cpl-nav\">"

if old3 in content:
    content = content.replace(old3, new3, 1)
    changes += 1
    print("[OK] Fix 3: Fixed template conditional to use !reloading && lastRefreshed")
else:
    print("[FAIL] Fix 3: Could not find broken conditional")
    # Try to find what's actually there
    idx = content.find('reloadingIndicator || !lastRefreshed')
    if idx > 0:
        start = max(0, idx - 50)
        end = min(len(content), idx + 150)
        print(f"  Context: {repr(content[start:end])}")

if changes == 0:
    print("\n[ERROR] No changes made!")
else:
    with open(FILE, 'w') as f:
        f.write(content)
    print(f"\n[DONE] Applied {changes} fixes")
