"""
Comprehensive fix for empire_command_spa.py:
1. UMD switch (CDN scripts + global destructuring)
2. Fix all pre-existing template expression bugs

Run from project root: python3 scripts/fix_spa_all.py
"""

import re

with open('empire_command_spa.py', 'r') as f:
    c = f.read()

fixes = []

# ═══════════════════════════════════════════════════════════════
# FIX 1: UMD switch - HTML template
# ═══════════════════════════════════════════════════════════════
old = """  <script type=\"importmap\">
  {{
    \"imports\": {{
      \"react\":           \"https://esm.sh/react@18.3.1\",
      \"react-dom/client\":\"https://esm.sh/react-dom@18.3.1/client\",
      \"htm\":             \"https://esm.sh/htm@3.1.1\"
    }}
  }}
  </script>
  <script type=\"module\">{_SPA_JS}</script>"""
new = """  <script crossorigin src=\"https://unpkg.com/react@18.3.1/umd/react.production.min.js\"><\/script>
  <script crossorigin src=\"https://unpkg.com/react-dom@18.3.1/umd/react-dom.production.min.js\"><\/script>
  <script crossorigin src=\"https://unpkg.com/htm@3.1.1/dist/htm.umd.js\"><\/script>
  <script>{_SPA_JS}</script>"""
if old in c:
    c = c.replace(old, new, 1)
    fixes.append("UMD switch (CDN scripts)")

# ═══════════════════════════════════════════════════════════════
# FIX 2: Import → global destructuring
# ═══════════════════════════════════════════════════════════════
old = """import { createElement as h, useState, useEffect, useRef, useCallback } from 'react';
import { createRoot } from 'react-dom/client';
import htm from 'htm';"""
new = """const { createElement: h, useState, useEffect, useRef, useCallback } = React;
const { createRoot } = ReactDOM;

const html = htm.bind(h);"""
if old in c:
    c = c.replace(old, new, 1)
    fixes.append("Imports → global destructuring")

# ═══════════════════════════════════════════════════════════════
# FIX 3: Remove duplicate const html declaration
# ═══════════════════════════════════════════════════════════════
count = c.count("const html = htm.bind(h);")
if count > 1:
    first = c.find("const html = htm.bind(h);")
    second = c.find("const html = htm.bind(h);", first + 1)
    if second >= 0:
        line_start = c.rfind('\n', 0, second) + 1
        line_end = c.find('\n', second)
        c = c[:line_start] + c[line_end+1:]
        fixes.append("Removed duplicate const html")

# ═══════════════════════════════════════════════════════════════
# FIX 4: Dispatch - missing } after stats ternary
# ═══════════════════════════════════════════════════════════════
old = "      ${stats ? html`<div class=\"sec-meta\">Active dispatches: <strong>${stats.active ?? 0}</strong> · Accepted: <strong>${stats.accepted ?? 0}</strong> · Completed: <strong>${stats.completed ?? 0}</strong> · Ghosted: <strong>${stats.ghosted ?? 0}</strong></div>` : ''\n\n      ${rows.length > 0 ? html`"
new = "      ${stats ? html`<div class=\"sec-meta\">Active dispatches: <strong>${stats.active ?? 0}</strong> · Accepted: <strong>${stats.accepted ?? 0}</strong> · Completed: <strong>${stats.completed ?? 0}</strong> · Ghosted: <strong>${stats.ghosted ?? 0}</strong></div>` : ''}\n\n      ${rows.length > 0 ? html`"
if old in c:
    c = c.replace(old, new, 1)
    fixes.append("Dispatch: added missing }")

# ═══════════════════════════════════════════════════════════════
# FIX 5: Inbound - remove orphaned expression & restructure
# ═══════════════════════════════════════════════════════════════
old = "      ${(calls.length === 0)\n\n      ${calls.length > 0 ? html`<div class=\"chart-panel\">"
new = "      ${calls.length > 0 ? html`<div class=\"chart-panel\">"
if old in c:
    c = c.replace(old, new, 1)
    fixes.append("Inbound: removed orphaned expression")

old = "      </div>` : ''}\n\n        ? html`<div class=\"tbl-empty\">No inbound calls yet.</div>`\n        : html`<table class=\"tbl\">"
new = "      </div>` : ''}\n\n      ${(calls.length === 0)\n        ? html`<div class=\"tbl-empty\">No inbound calls yet.</div>`\n        : html`<table class=\"tbl\">"
if old in c:
    c = c.replace(old, new, 1)
    fixes.append("Inbound: wrapped empty/table in ${}")

# ═══════════════════════════════════════════════════════════════
# FIX 6: Pulse compliance IIFE - add missing } after })()
# ═══════════════════════════════════════════════════════════════
old = "      `; })()\n\n      ${allPartners.length > 0 ? html`<div class=\"chart-panel\">"
new = "      `; })}\n\n      ${allPartners.length > 0 ? html`<div class=\"chart-panel\">"
if old in c:
    c = c.replace(old, new, 1)
    fixes.append("Pulse compliance IIFE: added }")

# ═══════════════════════════════════════════════════════════════
# FIX 7: Leads note button - missing : ''}
# ═══════════════════════════════════════════════════════════════
# Search for the pattern in the raw string
# ${leadNotes[leadId] ? html\`<button class="ld-note-save" ...>` without : ''}
old = '${leadNotes[leadId] ? html`<button class="ld-note-save" disabled=${noteBusy === leadId} onClick=${() => saveNote(leadId)}>Save</button>`}\n                </div>'
new = '${leadNotes[leadId] ? html`<button class="ld-note-save" disabled=${noteBusy === leadId} onClick=${() => saveNote(leadId)}>Save</button>` : \'\'}\n                </div>'
if old in c:
    c = c.replace(old, new, 1)
    fixes.append("Leads note button: added : ''")

# ═══════════════════════════════════════════════════════════════
# FIX 8: Leads statusActions leak - close template properly
# ═══════════════════════════════════════════════════════════════
# Find the statusActions section and close it + add proper closing structure
old = (
    '$' + '{statusActions.length > 0 ? html`'
    + '\n' + 'n// ── ACTIVITY LOG ─────────────────────────────────────────────────────'
)
new = (
    '$' + '{statusActions.length > 0 ? html`'
    + '\n' + '                <div class="ld-actions">'
    + '\n' + '                  ${statusActions.map(a => html`'
    + '\n' + '                    <button class="ld-action-btn ${a.cls}" onClick=${() => doUpdate(l.id, a.status)} disabled=${busy === (l.id + \':\' + a.status)}>'
    + '\n' + '                      ${a.label}'
    + '\n' + '                    </button>'
    + '\n' + '                  `)}'
    + '\n' + '                </div>'
    + '\n' + '              ` : \'\'}'
    + '\n' + '            </div>'
    + '\n' + '          `)}'
    + '\n' + '          </div>'
    + '\n' + '        `}'
    + '\n' + '    </div>'
    + '\n' + '  `;'
    + '\n' + '}'
    + '\n' + ''
    + '\n' + '// ── ACTIVITY LOG ─────────────────────────────────────────────────────'
)
if old in c:
    c = c.replace(old, new, 1)
    fixes.append("Leads statusActions: closed leak properly")
else:
    # Try searching for the exact location
    idx = c.find('statusActions.length > 0 ? html`')
    if idx >= 0:
        ctx = c[idx:idx+100]
        print(f"FIX 8: Pattern near char {idx}: {repr(ctx)}")

# ═══════════════════════════════════════════════════════════════
# FIX 9: Remove stray 'n' from CSS
# ═══════════════════════════════════════════════════════════════
old = 'n/* ── ACTIVITY LOG ────────────────────────────────────────────────── */'
new = '/* ── ACTIVITY LOG ────────────────────────────────────────────────── */'
if old in c:
    c = c.replace(old, new, 1)
    fixes.append("CSS: removed stray 'n'")

# ═══════════════════════════════════════════════════════════════
# Write the result
# ═══════════════════════════════════════════════════════════════
with open('empire_command_spa.py', 'w') as f:
    f.write(c)

print(f"Applied {len(fixes)} fixes:")
for f in fixes:
    print(f"  ✓ {f}")

# Validate JS
spa_match = re.search(r'_SPA_JS = r"""', c)
closing = c.rfind('"""')
js_start = spa_match.end()
js = c[js_start:closing]
with open('/tmp/spa_all.js', 'w') as f:
    f.write(js)
print(f"\nJS: {len(js)} chars, {len(js.split(chr(10)))} lines")
