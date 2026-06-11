#!/usr/bin/env python3
"""Fix review issues: redundant lead-name lookups + duplicate operator extraction in hub.py."""

with open('/root/empire-v49/hub.py', 'r') as f:
    hub = f.read()

# ─────────────────────────────────────────────────────────────────
# FIX 1: In delete-note, reuse the already-fetched lead row to get lead_name
# ─────────────────────────────────────────────────────────────────
# The lead row was already fetched at: r = db.table("inbound_leads").select("notes")...
# But it doesn't include "name". However, we can add "name" to the select.
# The simplest fix: add "name" to the initial select and extract it.
old_delete_select = 'r = db.table("inbound_leads").select("notes").eq("id", lead_id).limit(1).execute()'
new_delete_select = 'r = db.table("inbound_leads").select("notes,name").eq("id", lead_id).limit(1).execute()'

if old_delete_select in hub:
    hub = hub.replace(old_delete_select, new_delete_select, 1)
    print("✅ FIX 1a: delete-note select now includes name")
else:
    print("❌ FIX 1a: delete select pattern not found")

# Remove the extra lead_name fetch in delete-note; use the already-fetched row
old_del_name_fetch = '''        # Insert into activity_logs table
        try:
            _lead_name_row = db.table("inbound_leads").select("name").eq("id", lead_id).limit(1).execute()
            _lead_name = (_lead_name_row.data[0].get("name") or "") if _lead_name_row.data else ""
            db.table("activity_logs").insert({'''

new_del_name_fetch = '''        # Insert into activity_logs table
        try:
            _lead_name = (r.data[0].get("name") or "") if r.data else ""
            db.table("activity_logs").insert({'''

if old_del_name_fetch in hub:
    hub = hub.replace(old_del_name_fetch, new_del_name_fetch, 1)
    print("✅ FIX 1b: delete-note reuses fetched row for lead_name")
else:
    print("❌ FIX 1b: delete name fetch pattern not found")

# ─────────────────────────────────────────────────────────────────
# FIX 2: In update endpoint, extract lead name once and reuse + remove duplicate operator extraction
# ─────────────────────────────────────────────────────────────────
# The update endpoint already has _operator_name from the top.
# Remove the redundant _dop_id/_dop_email extraction that the migration added.
old_update_extract = '''    # ── Activity log + Audit trail ─────────────────────────────────
    _dop_id = ""
    _dop_email = ""
    try:
        if isinstance(auth, dict):
            _dop_id = auth.get("id", "")
            _dop_email = auth.get("email", "")
    except Exception:
        pass

    try:
        # If status changed, insert into activity_logs
        if _status_changed:
            _lead_name_row = db.table("inbound_leads").select("name").eq("id", lead_id).limit(1).execute()
            _lead_name = (_lead_name_row.data[0].get("name") or "") if _lead_name_row.data else ""
            db.table("activity_logs").insert({
                "lead_id": lead_id,
                "lead_name": _lead_name,
                "action": "status_changed",
                "operator": _operator_name,
                "details": {"new_status": body["status"]},
            }).execute()
        # If a note was added, insert into activity_logs
        if "notes" in body and body["notes"] is not None and str(body["notes"])[:1000].strip():
            _lead_name_row = db.table("inbound_leads").select("name").eq("id", lead_id).limit(1).execute()
            _lead_name = (_lead_name_row.data[0].get("name") or "") if _lead_name_row.data else ""
            db.table("activity_logs").insert({
                "lead_id": lead_id,
                "lead_name": _lead_name,
                "action": "note_added",
                "operator": _operator_name,
                "details": {"note_snippet": str(body["notes"])[:200].strip()},
            }).execute()
    except Exception:
        pass'''

new_update_activity = '''    # ── Activity log ──────────────────────────────────────────────
    try:
        # Fetch lead name once for activity_logs entries
        _act_lead_name = ""
        try:
            _lr = db.table("inbound_leads").select("name").eq("id", lead_id).limit(1).execute()
            _act_lead_name = (_lr.data[0].get("name") or "") if _lr.data else ""
        except Exception:
            pass
        # If status changed, insert into activity_logs
        if _status_changed:
            db.table("activity_logs").insert({
                "lead_id": lead_id,
                "lead_name": _act_lead_name,
                "action": "status_changed",
                "operator": _operator_name,
                "details": {"new_status": body["status"]},
            }).execute()
        # If a note was added, insert into activity_logs
        if "notes" in body and body["notes"] is not None and str(body["notes"])[:1000].strip():
            db.table("activity_logs").insert({
                "lead_id": lead_id,
                "lead_name": _act_lead_name,
                "action": "note_added",
                "operator": _operator_name,
                "details": {"note_snippet": str(body["notes"])[:200].strip()},
            }).execute()
    except Exception:
        pass'''

if old_update_extract in hub:
    hub = hub.replace(old_update_extract, new_update_activity, 1)
    print("✅ FIX 2: update endpoint — single lead_name fetch, removed duplicate operator extraction")
else:
    print("❌ FIX 2: update extract pattern not found")

with open('/root/empire-v49/hub.py', 'w') as f:
    f.write(hub)

print("✅ hub.py written")
