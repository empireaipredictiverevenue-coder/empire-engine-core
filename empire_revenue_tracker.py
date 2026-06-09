import json
import datetime
import os

LOG_FILE = "/root/empire-v49/data/call_ledger.json"

def log_call(uuid, status, device):
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    entry = {
        "timestamp": datetime.datetime.now().isoformat(),
        "uuid": uuid,
        "status": status,
        "target": device,
        "value": "PENDING"
    }
    
    # Append to JSON ledger
    data = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            try:
                data = json.load(f)
            except:
                data = []
    
    data.append(entry)
    
    with open(LOG_FILE, "w") as f:
        json.dump(data, f, indent=4)
