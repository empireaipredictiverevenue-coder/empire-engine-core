import httpx
import os

VONAGE_KEY = os.getenv("VONAGE_API_KEY")
VONAGE_SECRET = os.getenv("VONAGE_API_SECRET")

def initiate_storm_call(lead_phone: str, storm_type: str):
    url = "https://api.nexmo.com/v1/calls"
    payload = {
        "to": [{"type": "phone", "number": lead_phone}],
        "from": {"type": "phone", "number": "12142277528"},
        "ncco": [{"action": "talk", "text": f"Empire AI Alert. We have detected a {storm_type} in your area. Our dispatch team is being alerted."}]
    }
    with httpx.Client(auth=(VONAGE_KEY, VONAGE_SECRET)) as client:
        response = client.post(url, json=payload)
        return response.json()
