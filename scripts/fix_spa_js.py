"""
Fix empire_command_spa.py:
1. UMD switch (import map + type=module → CDN scripts + script)
2. ES module imports → global destructuring
3. Fix all pre-existing template expression bugs
"""

import re

with open('empire_command_spa.py', 'r') as f:
    c = f.read()

fixes = 0

# ── FIX 1: UMD switch in command_spa_page ──────────────────────────────
old_html = """  <script type=\"importmap\">
  {{
    \"imports\": {{
      \"react\":           \"https://esm.sh/react@18.3.1\",
      \"react-dom/client\":\"https://esm.sh/react-dom@18.3.1/client\",
      \"htm\":             \"https://esm.sh/htm@3.1.1\"
    }}
  }}
  </script>
  <script type=\"module\">{_SPA_JS}</script>"""
new_html = """  <script crossorigin src=\"https://unpkg.com/react@18.3.1/umd/react.production.min.js\"><\/script>
  <script crossorigin src=\"https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js\"><\/script>
  <script crossorigin src=\"https://unpkg.com/htm@3.1.1/dist/htm.umd.js\"><\/script>
  <script>{_SPA_JS}</script>"""

if old_html in c:
    c = c.replace(old_html, new_html, 1)
    fixes += 1
    print(f"Fix {fixes}: UMD switch applied")
else:
    print(f"Fix {fixes}: UMD switch - pattern not found!")

# ── FIX 2: Change ES module imports to global destructuring ──────────
old_imports = """import { createElement as h, useState, useEffect, useRef, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import htm from 'htm';"""
new_imports = """const { createElement: h, useState, useEffect, useRef, useCallback } = React;
const { createRoot } = ReactDOM;

const html = htm.bind(h);"""

if old_imports in c:
    c = c.replace(old_imports, new_imports, 1)
    fixes += 1
    print(f"Fix {fixes}: Import → global destructuring")
else:
    print(f"Fix {fixes}: Import change - pattern not found!")

# ── FIX 3: Remove duplicate const html = htm.bind(h); ─────────────────
# After FIX 2, we need to remove the old `const html = htm.bind(h);` line
# since it's now part of the imports replacement.
# But the original also has `const html = htm.bind(h);` separately.
# Let's keep only one.
count_html = c.count("const html = htm.bind(h);")
if count_html > 1:
    # Remove the duplicate one (keep the first)
    first_idx = c.find("const html = htm.bind(h);")
    second_idx = c.find("const html = htm.bind(h);", first_idx + 1)
    if second_idx >= 0:
        # Find the whole line
        line_start = c.rfind('\n', 0, second_idx) + 1
        line_end = c.find('\n', second_idx)
        if line_end < 0:
            line_end = len(c)
        c = c[:line_start] + c[line_end+1:]
        fixes += 1
        print(f"Fix {fixes}: Removed duplicate const html declaration")
else:
    print(f"Fix {fixes}: Only {count_html} const html declarations (good)")

# ── FIX 4: Dispatch - add missing } after ` : '' ─────────────────────
# The Dispatch section has: `${stats ? html`...` : ''}`  missing the }
# Pattern: stats ? html`<div class="chart-panel">...` : '' [missing }] 
# Fix: There's a ` : ''` that's NOT followed by `}` before a new template expression
old = "      ${stats ? html`<div class=\"sec-meta\">Active dispatches: <strong>${stats.active ?? 0}</strong> · Accepted: <strong>${stats.accepted ?? 0}</strong> · Completed: <strong>${stats.completed ?? 0}</strong> · Ghosted: <strong>${stats.ghosted ?? 0}</strong></div>` : ''\n\n      ${rows.length > 0 ? html`<div class=\"chart-panel\">"
new = "      ${stats ? html`<div class=\"sec-meta\">Active dispatches: <strong>${stats.active ?? 0}</strong> · Accepted: <strong>${stats.accepted ?? 0}</strong> · Completed: <strong>${stats.completed ?? 0}</strong> · Ghosted: <strong>${stats.ghosted ?? 0}</strong></div>` : ''}\n\n      ${rows.length > 0 ? html`<div class=\"chart-panel\">"
if old in c:
    c = c.replace(old, new, 1)
    fixes += 1
    print(f"Fix {fixes}: Dispatch - added missing }}")
else:
    print(f"Fix {fixes}: Dispatch - pattern not found!")

# ── FIX 5: Inbound - fix orphaned expression and restructure ─────────
# There's: `${(calls.length === 0)\n\n      ${calls.length > 0 ? html`<div class="chart-panel">`
# The orphaned `${(calls.length === 0)` should be removed since the proper ternary is below
old = "      ${(calls.length === 0)\n\n      ${calls.length > 0 ? html`<div class=\"chart-panel\">"
new = "      ${calls.length > 0 ? html`<div class=\"chart-panel\">"
if old in c:
    c = c.replace(old, new, 1)
    fixes += 1
    print(f"Fix {fixes}: Inbound - removed orphaned expression")
else:
    print(f"Fix {fixes}: Inbound - orphaned pattern not found!")

# Inbound: there's `</div>\` : ''}\n\n        ? html`<div class="tbl-empty">`
# This is the chart panel closing and then the empty/table ternary
# The chart panel ternary should close before the empty/table
old = "      </div>` : ''}\n\n        ? html`<div class=\"tbl-empty\">No inbound calls yet.</div>`\n        : html`<table class=\"tbl\">"
new = "      </div>` : ''}\n\n      ${(calls.length === 0)\n        ? html`<div class=\"tbl-empty\">No inbound calls yet.</div>`\n        : html`<table class=\"tbl\">"
if old in c:
    c = c.replace(old, new, 1)
    fixes += 1
    print(f"Fix {fixes}: Inbound - wrapped empty/table ternary in ${{}}")
else:
    print(f"Fix {fixes}: Inbound - ternary wrap pattern not found!")

# ── FIX 6: Inbound - the `{${(calls.length === 0)` area needs proper structure
# After fix 5, check if the `${(calls.length === 0)` was added back properly
# Actually fix 5 might not match because the text differs. Let me look more carefully.
# The inbound section has:
#   ${(calls.length === 0)
#   
#   ${calls.length > 0 ? html`<div class="chart-panel">`...chart content...`</div>` : ''}
#   
#         ? html`<div class="tbl-empty">...` : html`<table...>...`
# The issue is: `${(calls.length === 0)` is an orphan that doesn't close,
# and then the `? html` / `: html` is the same condition's ternary but without `${}`
# The fix should be: remove the orphan `${(calls.length === 0)`, keep the chart panel,
# and wrap the empty/table ternary in `${}`

# Let me try a broader fix for Inbound:
# Remove `${(calls.length === 0)\n\n      ` before the chart panel
# And wrap `? html\`<div class="tbl-empty">...` in `${}`
# This was already attempted in fix 5, but let me check if it worked

# ── FIX 7: Leads - note save button ternary missing : '' ─────────────
old = '${leadNotes[leadId] ? html`<button class="ld-note-save" disabled=${noteBusy === leadId} onClick=${() => saveNote(leadId)}>Save</button>`}\n                </div>'
new = '${leadNotes[leadId] ? html`<button class="ld-note-save" disabled=${noteBusy === leadId} onClick=${() => saveNote(leadId)}>Save</button>` : \'\'}\n                </div>'
if old in c:
    c = c.replace(old, new, 1)
    fixes += 1
    print(f"Fix {fixes}: Leads - added : '' to note button ternary")
else:
    print(f"Fix {fixes}: Leads note button - pattern not found!")

# ── FIX 8: Leads - statusActions template closes before ActivityLog ──
# The statusActions area has a template that leaks into ActivityLog
# Let me find what comes after the statusActions.map()
# Looking at the original, there's:
#   ${statusActions.length > 0 ? html`
#     ... <div class="ld-actions">...
#   ` : ''}
#
# But the template might not close properly. Let me search for the exact pattern.

# ── FIX 9: ActivityLog - chart panel missing } ──────────────────────
# There are two chart panels in ActivityLog, the first one might be missing }
# Pattern: `filteredEntries.length > 0` chart panel

# Let me just write back and validate. If there are more issues, we'll iterate.
with open('empire_command_spa.py', 'w') as f:
    f.write(c)

print(f"\nApplied {fixes} fixes to empire_command_spa.py")

# Now validate the JS
import re
spa_match = re.search(r'_SPA_JS = r"""', c)
closing = c.rfind('"""')
js_start = spa_match.end()
js = c[js_start:closing]
with open('/tmp/spa_fix.js', 'w') as f:
    f.write(js)
print(f"JS size: {len(js)} chars, {len(js.split(chr(10)))} lines")
