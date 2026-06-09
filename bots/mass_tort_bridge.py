import sys
sys.path.append("/root/empire-v49")
from empire_outbound_dialer import initiate_legal_call, ComplianceBlock
from mass_tort_scout import fetch_latest_recall
from empire_revenue_tracker import log_call
from supabase import create_client

_sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))


def _log_compliance_block(phone: str, rule: str, reason: str, device: str = ""):
    try:
        _sb.table("compliance_audit_logs").insert({
            "action": "legal_bridge_blocked",
            "entity_type": "outbound_call",
            "entity_id": phone,
            "details": {"rule": rule, "reason": reason, "device": device},
        }).execute()
    except Exception:
        pass


def bridge_live_target():
    recall_data = fetch_latest_recall()
    if not recall_data or "error" in recall_data:
        return

    device = recall_data.get("device", "Unknown Device")
    
    try:
        response = initiate_legal_call("+12142277528", device)
        log_call(response.uuid, response.status, device)
        print(f"[BRIDGE] Call Dispatched: {response.uuid}")
    except ComplianceBlock as cb:
        print(f"[COMPLIANCE] Legal bridge call blocked: {cb}")
        _log_compliance_block("+12142277528", cb.rule, str(cb), device)
    except Exception as e:
        print(f"[BRIDGE ERROR] {e}")

if __name__ == "__main__":
    bridge_live_target()
