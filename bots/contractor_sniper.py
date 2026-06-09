import os
import sys
import time
import re
from datetime import datetime, timezone

sys.path.append("/root/empire-v49")

try:
    import dotenv
    dotenv.load_dotenv("/root/empire-v49/.env")
except ImportError:
    pass

from supabase import create_client

from empire_outbound_dialer import initiate_storm_call, ComplianceBlock

LEAD_DIR = "/root/empire-v49/leads"
PROCESSED_DIR = "/root/empire-v49/leads/processed"

_sb = create_client(os.getenv("SUPABASE_URL", ""), os.getenv("SUPABASE_SERVICE_KEY", ""))


def log_compliance_block(phone: str, rule: str, reason: str, file: str = ""):
    """Log a compliance block to the audit trail."""
    try:
        _sb.table("compliance_audit_logs").insert({
            "action": "outbound_call_blocked",
            "entity_type": "outbound_call",
            "entity_id": phone,
            "details": {"rule": rule, "reason": reason, "source_file": file},
        }).execute()
    except Exception as e:
        print(f"[COMPLIANCE] Audit log failed: {e}")


def heartbeat(status="ACTIVE", leads_today=0, blocked=0):
    try:
        _sb.table("agent_registry").upsert({
            "agent_name": "contractor_sniper",
            "status": status,
            "leads_today": leads_today,
            "last_ping": datetime.now(timezone.utc).isoformat(),
            "enabled": True,
        }, on_conflict="agent_name").execute()
    except Exception as e:
        print(f"[HEARTBEAT] Error: {e}")


def run():
    print("[DISPATCHER] Engine Online: Watching for valid phone leads...")
    heartbeat("ACTIVE")
    leads_today = 0
    blocked_today = 0
    
    while True:
        try:
            files = [f for f in os.listdir(LEAD_DIR) if f.endswith('.txt')]
            for file in files:
                file_path = os.path.join(LEAD_DIR, file)
                print(f"[DISPATCHER] Processing lead file: {file}")
                
                try:
                    with open(file_path, "r") as f:
                        lines = f.readlines()
                    
                    for line in lines:
                        line = line.strip()
                        if not line:
                            continue
                        
                        parts = line.split(",")
                        raw_target = parts[0].strip()
                        storm_type = parts[1].strip() if len(parts) > 1 else "hail storm"
                        
                        phone = re.sub(r'\D', '', raw_target)
                        
                        if len(phone) >= 10:
                            print(f"[DISPATCHER] Verifying compliance for {phone}...")
                            try:
                                response = initiate_storm_call(phone, storm_type)
                                print(f"[DISPATCHER] Vonage Response: {response}")
                                leads_today += 1
                            except ComplianceBlock as cb:
                                print(f"[COMPLIANCE] Blocked call to {phone}: {cb}")
                                log_compliance_block(phone, cb.rule, str(cb), file)
                                blocked_today += 1
                            except Exception as ce:
                                print(f"[DISPATCHER] Call failed: {ce}")
                        else:
                            print(f"[SKIP] Invalid phone: {raw_target}")
                    
                    os.makedirs(PROCESSED_DIR, exist_ok=True)
                    os.rename(file_path, os.path.join(PROCESSED_DIR, file))
                    print(f"[DISPATCHER] Processed and archived {file}")
                    
                except Exception as e:
                    print(f"[DISPATCHER] Error processing {file}: {e}")
        except Exception as e:
            print(f"[DISPATCHER] Loop error: {e}")
        
        heartbeat("ACTIVE", leads_today, blocked_today)
        time.sleep(5)


if __name__ == "__main__":
    run()
