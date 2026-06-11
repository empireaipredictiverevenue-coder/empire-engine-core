#!/usr/bin/env python3
"""Add audit logging for lead status changes and note deletions."""
with open('/root/empire-v49/hub.py', 'r') as f:
    content = f.read()

# === DELETE-NOTE: Add audit after the synthetic note is saved, before return ===
old_del = """        entries.append({
            "text": "Note deleted",
            "operator": _dop_name,
            "timestamp": _gdt.utcnow().isoformat(timespec="seconds"),
        })
        db.table("inbound_leads").update({"notes": _gjson.dumps(entries, ensure_ascii=False)}).eq("id", lead_id).execute()
        return _jr({"ok": True})"""

new_del = """        entries.append({
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
        return _jr({"ok": True})"""

if old_del in content:
    content = content.replace(old_del, new_del, 1)
    print("OK: audit added to delete-note")
else:
    print("FAIL: delete-note pattern not found")

# === UPDATE: Add audit after the final save, before return ===
old_upd = """        if update:
            db.table("inbound_leads").update(update).eq("id", lead_id).execute()
        return _jr({"ok": True})"""

# Need to find this AFTER the status note is appended
new_upd = """        if update:
            db.table("inbound_leads").update(update).eq("id", lead_id).execute()
        # Audit trail for status changes
        if _status_changed:
            try:
                _audit_id = (auth.get("id") or "") if isinstance(auth, dict) else ""
                _audit_email = (auth.get("email") or "") if isinstance(auth, dict) else ""
                await auth_engine.audit(
                    operator_id=_audit_id,
                    operator_name=_operator_name,
                    operator_email=_audit_email,
                    action="lead_status_changed",
                    target_type="inbound_lead",
                    target_id=lead_id,
                    details={"new_status": body["status"]},
                )
            except Exception:
                pass
        return _jr({"ok": True})"""

if old_upd in content:
    content = content.replace(old_upd, new_upd, 1)
    print("OK: audit added to update")
else:
    print("FAIL: update pattern not found")

with open('/root/empire-v49/hub.py', 'w') as f:
    f.write(content)
print("DONE")
