#!/usr/bin/env python3
"""Migrate from synthetic notes in inbound_leads.notes to a dedicated activity_logs table."""

import re

# ─────────────────────────────────────────────────────────
# 1. HUB.PY: Replace delete_inbound_lead_note — remove synthetic note, add activity_logs insert
# ─────────────────────────────────────────────────────────
with open('/root/empire-v49/hub.py', 'r') as f:
    hub = f.read()

# Find the delete-note function and replace the synthetic note + audit section
old_delete_synthetic = '''        # Append a synthetic note for the deletion to the activity feed
        _dop_name = "operator"
        try:
            if isinstance(auth, dict):
                _dop_name = auth.get("name") or auth.get("email", "operator")
        except Exception:
            pass
        entries.append({
            "text": "Note deleted",
            "operator": _dop_name,
            "timestamp": _gdt.utcnow().isoformat(timespec="seconds"),
        })
        db.table("inbound_leads").update({"notes": _gjson.dumps(entries, ensure_ascii=False)}).eq("id", lead_id).execute()
        # Audit trail
        try:
            _audit_id = (auth.get("id") or "") if isinstance(auth, dict) else ""
            _audit_email = (auth.get("email") or "") if isinstance(auth, dict) else ""
            await auth_engine.audit(
                operator_id=_audit_id,
                operator_name=_dop_name,
                operator_email=_audit_email,
                action="lead_note_deleted",
                target_type="inbound_lead",
                target_id=lead_id,
                details={"timestamp": timestamp},
            )
        except Exception:
            pass
        return _jr({"ok": True})'''

new_delete_activity = '''        # Persist the updated note list (no synthetic note)
        db.table("inbound_leads").update({"notes": _gjson.dumps(entries, ensure_ascii=False)}).eq("id", lead_id).execute()

        # Operator name for activity + audit
        _dop_name = "operator"
        _dop_id = ""
        _dop_email = ""
        try:
            if isinstance(auth, dict):
                _dop_name = auth.get("name") or auth.get("email", "operator")
                _dop_id = auth.get("id", "")
                _dop_email = auth.get("email", "")
        except Exception:
            pass

        # Insert into activity_logs table
        try:
            _lead_name_row = db.table("inbound_leads").select("name").eq("id", lead_id).limit(1).execute()
            _lead_name = (_lead_name_row.data[0].get("name") or "") if _lead_name_row.data else ""
            db.table("activity_logs").insert({
                "lead_id": lead_id,
                "lead_name": _lead_name,
                "action": "note_deleted",
                "operator": _dop_name,
                "details": {"timestamp": timestamp},
            }).execute()
        except Exception:
            pass

        # Audit trail
        try:
            await auth_engine.audit(
                operator_id=_dop_id,
                operator_name=_dop_name,
                operator_email=_dop_email,
                action="lead_note_deleted",
                target_type="inbound_lead",
                target_id=lead_id,
                details={"timestamp": timestamp},
            )
        except Exception:
            pass
        return _jr({"ok": True})'''

if old_delete_synthetic in hub:
    hub = hub.replace(old_delete_synthetic, new_delete_activity, 1)
    print("✅ REPLACED: delete-note synthetic note → activity_logs insert")
else:
    print("❌ DELETE-NOTE PATTERN NOT FOUND")

# ─────────────────────────────────────────────────────────
# 2. HUB.PY: Replace update_inbound_lead — remove synthetic status note, add activity_logs inserts
# ─────────────────────────────────────────────────────────

# First, find and replace the synthetic status-change note append section
old_status_synthetic = '''    try:
        # If status changed, append a synthetic note AFTER the notes block ran
        if _status_changed:
            _op_name = "operator"
            try:
                if isinstance(auth, dict):
                    _op_name = auth.get("name") or auth.get("email", "operator")
            except Exception:
                pass
            try:
                _sentries = list(_existing_notes) if '_existing_notes' in dir() and isinstance(_existing_notes, list) else []
                if not _sentries:
                    _sr = db.table("inbound_leads").select("notes").eq("id", lead_id).limit(1).execute()
                    if _sr.data and _sr.data[0].get("notes"):
                        _sraw = _sr.data[0]["notes"]
                        if isinstance(_sraw, list):
                            _sentries = _sraw
                        elif isinstance(_sraw, str):
                            try:
                                _sp = _gjson.loads(_sraw)
                                if isinstance(_sp, list):
                                    _sentries = _sp
                            except Exception:
                                pass
                _sentries.append({
                    "text": "Status changed to " + body["status"],
                    "operator": _op_name,
                    "timestamp": _gdt.utcnow().isoformat(timespec="seconds"),
                })
                update["notes"] = _gjson.dumps(_sentries, ensure_ascii=False)
            except Exception:
                pass'''

new_status_activity = '''    # ── Activity log + Audit trail ─────────────────────────────────
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

if old_status_synthetic in hub:
    hub = hub.replace(old_status_synthetic, new_status_activity, 1)
    print("✅ REPLACED: update status synthetic note → activity_logs insert")
else:
    print("❌ UPDATE STATUS SYNTHETIC PATTERN NOT FOUND")

# ─────────────────────────────────────────────────────────
# 3. HUB.PY: Replace old /api/v1/notes/activity with new /api/v1/leads/activity
# ─────────────────────────────────────────────────────────
old_notes_activity_endpoint = '''# ─── Notes activity endpoint ──────────────────────────────────────
@app.get("/api/v1/notes/activity")
async def notes_activity(limit: int = 50, offset: int = 0, auth: bool = Depends(require_auth)):
    """Return all notes across all leads as a flat reverse-chronological feed."""
    from fastapi.responses import JSONResponse as _jr
    db = get_db()
    has_more = False
    try:
        r = db.table("inbound_leads").select("id,name,notes,created_at").not_.is_("notes", "null").order("created_at", desc=True).range(offset, offset + limit - 1).execute()
        has_more = len(r.data or []) == limit
    except Exception:
        try:
            r = db.table("inbound_leads").select("id,name,notes,created_at").not_.is_("notes", "null").execute()
        except Exception as e:
            return _jr({"entries": [], "error": str(e)[:80]})
    entries = []
    for lead in (r.data or []):
        raw = lead.get("notes")
        note_list = []
        if raw:
            if isinstance(raw, list):
                note_list = raw
            elif isinstance(raw, str):
                try:
                    p = _gjson.loads(raw)
                    if isinstance(p, list):
                        note_list = p
                    else:
                        note_list = [{"text": raw}]
                except Exception:
                    note_list = [{"text": raw}]
        for n in note_list:
            n["lead_id"] = lead.get("id")
            n["lead_name"] = lead.get("name") or "—"
            entries.append(n)
    entries.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
    return _jr({"entries": entries[:limit], "has_more": has_more})'''

new_leads_activity_endpoint = '''# ─── Leads activity endpoint ──────────────────────────────────
@app.get("/api/v1/leads/activity")
async def leads_activity(limit: int = 50, offset: int = 0, lead_id: str = "", auth: bool = Depends(require_auth)):
    """Return lead activity log entries from the activity_logs table (status changes, notes, deletions)."""
    from fastapi.responses import JSONResponse as _jr
    db = get_db()
    has_more = False
    try:
        q = db.table("activity_logs").select("*").order("created_at", desc=True).range(offset, offset + limit - 1)
        if lead_id:
            q = q.eq("lead_id", lead_id)
        r = q.execute()
        has_more = len(r.data or []) == limit
        entries = []
        for row in (r.data or []):
            entries.append({
                "id": row.get("id"),
                "lead_id": row.get("lead_id"),
                "lead_name": row.get("lead_name") or "—",
                "action": row.get("action"),
                "operator": row.get("operator") or "operator",
                "details": row.get("details") or {},
                "timestamp": (row.get("created_at") or "")[:19],
            })
        return _jr({"entries": entries, "has_more": has_more})
    except Exception as e:
        return _jr({"entries": [], "error": str(e)[:80], "has_more": False})'''

if old_notes_activity_endpoint in hub:
    hub = hub.replace(old_notes_activity_endpoint, new_leads_activity_endpoint, 1)
    print("✅ REPLACED: old /api/v1/notes/activity → new /api/v1/leads/activity")
else:
    print("❌ NOTES ACTIVITY ENDPOINT PATTERN NOT FOUND")
    # Try to find it
    idx = hub.find('/api/v1/notes/activity')
    if idx >= 0:
        print(f"   Found at offset {idx}: {repr(hub[idx:idx+80])}")

with open('/root/empire-v49/hub.py', 'w') as f:
    f.write(hub)

print("✅ hub.py written")


# ─────────────────────────────────────────────────────────
# 4. SPA: Update ActivityLog endpoint reference
# ─────────────────────────────────────────────────────────
with open('/root/empire-v49/empire_command_spa.py', 'r') as f:
    spa = f.read()

old_spa_endpoint = '/api/v1/notes/activity?limit=50&offset='
new_spa_endpoint = '/api/v1/leads/activity?limit=50&offset='

if old_spa_endpoint in spa:
    spa = spa.replace(old_spa_endpoint, new_spa_endpoint)
    print("✅ SPA: /api/v1/notes/activity → /api/v1/leads/activity")
else:
    print("❌ SPA ENDPOINT PATTERN NOT FOUND")
    idx = spa.find('notes/activity')
    if idx >= 0:
        print(f"   Found at offset {idx}: {repr(spa[idx-30:idx+60])}")

with open('/root/empire-v49/empire_command_spa.py', 'w') as f:
    f.write(spa)

print("✅ empire_command_spa.py written")
print("\n=== MIGRATION COMPLETE ===")
