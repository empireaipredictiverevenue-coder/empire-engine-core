#!/usr/bin/env python3
"""Fix the unclosed template literal in the Leads function of empire_command_spa.py.

The bug: line 1911 opens a template `${statusActions.length > 0 ? html` that is never
closed. Line 1912 has a stray 'n' and leaked comment. This causes the ES module parser
to treat subsequent code as template literal content, leading to 'Unexpected token class'
in the ActivityLog function.

The fix replaces lines 1911-1912 with proper template code that:
1. Renders status action buttons
2. Closes all open templates, interpolations, and the Leads function
"""

import re, subprocess, sys

def main():
    with open('empire_command_spa.py', 'r', encoding='utf-8') as f:
        content = f.read()
        lines = content.split('\n')

    # Verify the expected lines
    assert 'statusActions.length > 0 ? html`' in lines[1910], f"Expected statusActions at line 1911, got: {lines[1910][:60]}"
    assert lines[1911].startswith('n//'), f"Expected stray n at line 1912, got: {lines[1911][:60]}"

    print(f"Found bug: line 1911 = {repr(lines[1910][:80])}")
    print(f"Found bug: line 1912 = {repr(lines[1911][:80])}")

    # The replacement: status actions template + proper closures
    # Indentation matches the surrounding code (14 spaces for outer level)
    replacement = """              ${statusActions.length > 0 ? html`
                <div class="ld-actions">
                  ${statusActions.map(a => html`
                    <button key=${a.status} class=${'ld-action-btn ' + a.cls}
                      onClick=${() => apiFetch('/api/v1/inbound/leads/update', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ lead_id: l.id, status: a.status })
                      }).then(() => reload()).catch(e => alert('Failed: ' + e.message))}
                      disabled=${busy === l.id + ':status:' + a.status}>
                      ${busy === l.id + ':status:' + a.status ? '...' : a.label}
                    </button>
                  `)}
                </div>
              ` : ''}
            </div>
          `)}
        `;
      }"""

    # Apply replacement
    new_lines = lines[:1910] + [replacement] + lines[1912:]
    new_content = '\n'.join(new_lines)

    # Save the fixed file
    with open('empire_command_spa.py', 'w', encoding='utf-8') as f:
        f.write(new_content)

    print("File updated successfully!")
    
    # Extract JS and test
    marker = '_SPA_JS = r"""'
    start = new_content.find(marker)
    rest = new_content[start + len(marker):]
    end = rest.rfind('"""')
    js = rest[:end]
    
    with open('/tmp/spa_fixed_final.mjs', 'w') as f:
        f.write(js)
    
    r = subprocess.run(['node', '--check', '/tmp/spa_fixed_final.mjs'], 
                       capture_output=True, text=True, timeout=15)
    
    if r.returncode == 0:
        print("node --check (.mjs): PASS!")
        return 0
    else:
        print(f"node --check (.mjs): FAIL")
        print(r.stderr[:500])
        
        # Extract line number from error
        m = re.search(r':(\d+):', r.stderr)
        if m:
            line = int(m.group(1))
            js_lines = js.split('\n')
            print(f"\nContext around error at line {line}:")
            for i in range(max(0, line-3), min(len(js_lines), line+3)):
                marker_str = '>>>' if i == line-1 else '   '
                print(f"{marker_str} {i+1}: {js_lines[i][:150]}")
        return 1

if __name__ == '__main__':
    sys.exit(main())
