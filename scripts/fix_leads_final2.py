#!/usr/bin/env python3
"""Fix Leads closing by analyzing full structure."""
import sys

with open(sys.argv[1], 'r') as f:
    content = f.read()

marker = '_SPA_JS = r"""'
spa_start = content.find(marker)
spa_end = content.rfind('"""')
js_start = spa_start + len(marker)
js = content[js_start:spa_end]

# Find all .map calls that render leads
idx = js.find('leads.map')
if idx < 0:
    print("ERROR: Could not find leads.map")
    sys.exit(1)

# Show context around leads.map
ctx = js[idx:idx+100]
print(f"leads.map context: {repr(ctx)}")

# Find function ActivityLog
act_idx = js.find('function ActivityLog()')
if act_idx >= 0:
    before = js[act_idx-60:act_idx]
    print(f"Before ActivityLog: {repr(before)}")
