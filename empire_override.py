import json

def get_manual_override():
    # If this file says "MANUAL_MODE", the AGI pauses its decisions
    try:
        with open("/root/empire-v49/override.json", "r") as f:
            return json.load(f)
    except:
        return {"mode": "AUTO"}
