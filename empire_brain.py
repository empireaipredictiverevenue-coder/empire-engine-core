import sys
import json
import os
sys.path.append("/root/empire-v49")

from empire_compliance import is_lead_compliant
from empire_outreach_agent import process_lead
from empire_outbound_dialer import initiate_legal_call, ComplianceBlock
from empire_revenue_tracker import log_call
from supabase import create_client

_sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))


def _log_compliance_block(phone: str, rule: str, reason: str, lead_id: str = ""):
    try:
        _sb.table("compliance_audit_logs").insert({
            "action": "legal_call_blocked",
            "entity_type": "outbound_call",
            "entity_id": phone,
            "details": {"rule": rule, "reason": reason, "lead_id": lead_id},
        }).execute()
    except Exception:
        pass


def run_empire_brain():
    print("[SYSTEM] Empire Brain Online: Scanning for Opportunities...")
    lead_queue = "/root/empire-v49/leads/raw_leads.json"
    
    if not os.path.exists(lead_queue):
        print("[BRAIN] No leads found in queue.")
        return

    with open(lead_queue, 'r') as f:
        try:
            leads = json.load(f)
        except:
            print("[BRAIN] Error reading leads file.")
            return

    for lead in leads:
        if not is_lead_compliant(lead):
            print(f"[COMPLIANCE] Lead {lead.get('id')} rejected.")
            _log_compliance_block(lead.get('phone',''), "lead_rejected", "Lead failed is_lead_compliant check", lead.get('id'))
            continue

        decision = process_lead(lead)
        
        if decision == "HOT":
            print(f"[BRAIN] Strategy: High-Intent. Initiating Dial.")
            try:
                call_resp = initiate_legal_call(lead['phone'], lead['device'])
                log_call(call_resp.uuid, "STARTED", lead['device'])
            except ComplianceBlock as cb:
                print(f"[COMPLIANCE] Legal call blocked: {cb}")
                _log_compliance_block(lead.get('phone',''), cb.rule, str(cb), lead.get('id'))
            except Exception as ce:
                print(f"[BRAIN] Call failed: {ce}")
            
        elif decision == "NURTURE":
            print(f"[BRAIN] Strategy: Low-Intent. Queueing for Email.")
            
    with open(lead_queue, 'w') as f:
        json.dump([], f)

if __name__ == "__main__":
    run_empire_brain()
