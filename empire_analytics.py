import httpx
import os

def log_event(event_type: str, dispatch_id: str, metadata: dict):
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/dashboard_events"
    headers = {
        "apikey": os.getenv('SUPABASE_KEY'), 
        "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}", 
        "Content-Type": "application/json",
        "Prefer": "return=minimal"
    }
    payload = {
        "event_type": event_type, 
        "dispatch_id": dispatch_id, 
        "metadata": metadata
    }
    
    with httpx.Client() as client:
        try:
            client.post(url, headers=headers, json=payload)
        except Exception as e:
            print(f"[Analytics] Log failed: {e}")
