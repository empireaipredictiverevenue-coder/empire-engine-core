#!/usr/bin/env python3
"""Fix Leads closing: the })() doesn't belong since Leads() doesn't use an IIFE."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

# Read the file as bytes to find exact match
marker = b'_SPA_JS = r"""'
spa_start = content.encode().find(marker)
if spa_start < 0:
    print("ERROR: Could not find SPA_JS marker")
    sys.exit(1)

# Find the ActivityLog function
act_log_marker = "function ActivityLog()"
idx = content.find(act_log_marker)
if idx < 0:
    print("ERROR: Could not find ActivityLog")
    sys.exit(1)

# Look backwards from ActivityLog to find the })()} pattern
before = content[idx-100:idx]
print(f"Before ActivityLog:")
print(repr(before))

# Find the })()} and replace with just }
old = "        })()}\n\n// ── ACTIVITY LOG ─────────────────────────────────"
new = "        }\n\n// ── ACTIVITY LOG ─────────────────────────────────"
if old in content:
    content = content.replace(old, new, 1)
    with open(sys.argv[1], 'w') as f:
        f.write(content)
    print("FIXED: Removed extra })() before ActivityLog")
else:
    print("Pattern not found")
