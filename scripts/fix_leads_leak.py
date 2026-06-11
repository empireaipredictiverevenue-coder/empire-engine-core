"""
Fix: Close the statusActions template in Leads function
that leaks into ActivityLog.
"""
with open('empire_command_spa.py', 'r') as f:
    c = f.read()

old = '${statusActions.length > 0 ? html`\\nn// ── ACTIVITY LOG ─────────────────────────────────────────────────────'
new = '''${statusActions.length > 0 ? html`
                <div class="ld-actions">
                  ${statusActions.map(a => html`
                    <button class="ld-action-btn ${a.cls}" onClick=${() => doUpdate(l.id, a.status)} disabled=${busy === (l.id + \\':\\' + a.status)}>
                      ${a.label}
                    </button>
                  `)}
                </div>
              ` : ''}
            </div>
          `;
        })()}
      </div>
    </div>
  `;
}

// ── ACTIVITY LOG ─────────────────────────────────────────────────────'''

if old in c:
    c = c.replace(old, new, 1)
    print("FIXED: statusActions template closed properly")
else:
    print("Pattern not found!")
    idx = c.find('statusActions.length > 0 ? html`')
    if idx >= 0:
        print(f"Found at {idx}")
        print(repr(c[idx:idx+120]))

with open('empire_command_spa.py', 'w') as f:
    f.write(c)
print("File written")
