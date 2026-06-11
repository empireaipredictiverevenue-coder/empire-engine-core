#!/usr/bin/env python3
"""Add offset pagination + has_more flag to /api/v1/notes/activity endpoint."""
with open('/root/empire-v49/hub.py', 'r') as f:
    content = f.read()

# Replace the function signature and query to add offset + has_more
old_sig = 'async def notes_activity(limit: int = 100, auth: bool = Depends(require_auth)):'
new_sig = 'async def notes_activity(limit: int = 50, offset: int = 0, auth: bool = Depends(require_auth)):'

if old_sig in content:
    content = content.replace(old_sig, new_sig, 1)
else:
    print("SIG NOT FOUND")

# Replace the query to use range + track has_more
old_query = '.order("created_at", desc=True).limit(limit).execute()'
new_query = '.order("created_at", desc=True).range(offset, offset + limit - 1).execute()\n        has_more = len(r.data or []) == limit'

if old_query in content:
    content = content.replace(old_query, new_query, 1)
else:
    print("QUERY NOT FOUND")

# Add has_more = False to the fallback
old_fallback = '.order("created_at", desc=True).execute()'
new_fallback = '.order("created_at", desc=True).execute()\n            has_more = False'

if old_fallback in content:
    content = content.replace(old_fallback, new_fallback, 1)
else:
    print("FALLBACK NOT FOUND")

# Replace return to include has_more
old_ret = 'return _jr({"entries": entries[:limit]})'
new_ret = 'return _jr({"entries": entries[:limit], "has_more": has_more})'

if old_ret in content:
    content = content.replace(old_ret, new_ret, 1)
else:
    print("RETURN NOT FOUND")

with open('/root/empire-v49/hub.py', 'w') as f:
    f.write(content)
print("DONE")
