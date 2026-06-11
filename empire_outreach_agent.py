import json
import os
from empire_compliance import is_lead_compliant

LEAD_DIR = "/root/empire-v49/leads"
QUALIFIED_QUEUE = "/root/empire-v49/leads/hot_queue.json"

# Lead-scoring tunables. Mutated at runtime by the SI Adaptive engine
# (outreach.hot_threshold / outreach.score_per_click / outreach.score_per_reply).
HOT_THRESHOLD  = 5   # minimum score to push lead to dialer queue
SCORE_PER_CLICK = 5  # points awarded for clicking the lead magnet
SCORE_PER_REPLY = 10  # points awarded for replying to an SMS

def process_lead(lead_data):
    # First: Run the Legal Guardrail
    if not is_lead_compliant(lead_data):
        print(f"[COMPLIANCE] Lead {lead_data.get('id')} rejected.")
        return "REJECTED"

    # Second: Score the lead
    score = 0
    if lead_data.get("clicked_magnet"): score += SCORE_PER_CLICK
    if lead_data.get("replied_to_sms"): score += SCORE_PER_REPLY
    
    # Third: Qualification Threshold
    if score >= HOT_THRESHOLD:
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
