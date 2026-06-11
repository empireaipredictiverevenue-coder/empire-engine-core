"""Fix the remaining note button ternary missing '' else branch."""
with open('empire_command_spa.py', 'r') as f:
    c = f.read()

# The pattern: noteInputs[l.id] !== undefined && ... ? html`<button>...</button>`
# Missing ` : ''}`  — currently just `}` (closes ${} but not the ternary else)
# Fix: add ` : ''` before the closing `}`

# The exact text around the note save button close
# Find the pattern: button close, then `}, then </div>
old = "                  </button>\n                `}\n              </div>"
new = "                  </button>\n                ` : ''}\n              </div>"

if old in c:
    c = c.replace(old, new, 1)
    print("FIXED: note button ternary - added : ''")
else:
    print("Pattern not found - searching...")
    # Find the ld-note-save area to debug
    idx = c.find('ld-note-save')
    if idx >= 0:
        snippet = c[idx:idx+300]
        print(repr(snippet))

with open('empire_command_spa.py', 'w') as f:
    f.write(c)
print("Done")
