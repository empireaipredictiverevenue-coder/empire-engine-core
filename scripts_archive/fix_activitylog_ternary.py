"""Fix the missing `}` on line 2000 of empire_command_spa.py.

The line reads:
      </div>` : ''

But should read:
      </div>` : ''}
"""
import sys

path = sys.argv[1] if len(sys.argv) > 1 else 'empire_command_spa.py'

with open(path, 'rb') as f:
    content = f.read()

# Find the marker: `</div>` : ''\n\n      ${filteredEntries`
# We need to replace `< /div>` : ''` with `< /div>` : ''}` 
# where the one we want has the right context (followed by blank line + next ${)

# Search for the byte pattern
target = b'      </div>` : \'\'\n\n      ${filteredEntries.length > 0 ? html`<div class="chart-panel">'
replacement = b'      </div>` : \'\'}\n\n      ${filteredEntries.length > 0 ? html`<div class="chart-panel">'

if target in content:
    content = content.replace(target, replacement, 1)
    with open(path, 'wb') as f:
        f.write(content)
    print("Fixed: replaced `</div>` : ''` with `</div>` : ''}")
else:
    print("ERROR: Target pattern not found!")
    # Debug: find nearby patterns
    idx = content.find(b'</div>` : \'\'')
    if idx >= 0:
        print(f"Found bare `</div>` : ''` at byte offset {idx}")
        print(f"Context: {content[idx:idx+100]!r}")
    else:
        print("No `</div>` : ''` pattern found at all")
        sys.exit(1)
