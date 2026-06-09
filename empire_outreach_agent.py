import json
import os
from empire_compliance import is_lead_compliant

LEAD_DIR = "/root/empire-v49/leads"
QUALIFIED_QUEUE = "/root/empire-v49/leads/hot_queue.json"

def process_lead(lead_data):
    # First: Run the Legal Guardrail
    if not is_lead_compliant(lead_data):
        print(f"[COMPLIANCE] Lead {lead_data.get('id')} rejected.")
        return "REJECTED"

    # Second: Score the lead
    score = 0
    if lead_data.get("clicked_magnet"): score += 5
    if lead_data.get("replied_to_sms"): score += 10
    
    # Third: Qualification Threshold
    if score >= 5:
        add_to_dialer_queue(lead_data)
        return "HOT"
    return "NURTURE"

def add_to_dialer_queue(lead_data):
    data = []
    if os.path.exists(QUALIFIED_QUEUE):
        with open(QUALIFIED_QUEUE, "r") as f:
            try: data = json.load(f)
            except: data = []
    
    data.append(lead_data)
    
    with open(QUALIFIED_QUEUE, "w") as f:
        json.dump(data, f, indent=4)
    print(f"[AGENT] Lead {lead_data.get('id')} pushed to Dialer Queue.")

if __name__ == "__main__":
    print("[AGENT] Standing by for leads...")
