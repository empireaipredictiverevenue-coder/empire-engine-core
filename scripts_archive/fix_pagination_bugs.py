#!/usr/bin/env python3
"""Fix indentation, add has_more init, fix hardcoded +50."""
with open('/root/empire-v49/hub.py', 'r') as f:
    content = f.read()

# Fix 1: Initialize has_more before the try block
old = '    db = get_db()\n    try:\n        r = db.table("inbound_leads").select("id,name,notes,created_at").not_.is_("notes", "null").order("created_at", desc=True).range(offset, offset + limit - 1).execute()\n        has_more = len(r.data or []) == limit'
new = '    db = get_db()\n    has_more = False\n    try:\n        r = db.table("inbound_leads").select("id,name,notes,created_at").not_.is_("notes", "null").order("created_at", desc=True).range(offset, offset + limit - 1).execute()\n        has_more = len(r.data or []) == limit'

if old in content:
    content = content.replace(old, new, 1)
    print("FIX: initialized has_more=False before try")
else:
    print("pattern NOT FOUND — checking")
    idx = content.find('has_more')
    if idx >= 0:
        print(repr(content[idx-30:idx+50]))

with open('/root/empire-v49/hub.py', 'w') as f:
    f.write(content)
print("DONE hub.py")
