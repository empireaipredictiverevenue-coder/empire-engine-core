import httpx
import os

def check_revenue_health():
    # Fetch from your predictive view
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/predictive_revenue_view"
    headers = {"apikey": os.getenv('SUPABASE_KEY'), "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}"}
    
    with httpx.Client() as client:
        data = client.get(url, headers=headers).json()
        if data and data[0]['projected_revenue'] < 5000:
            print("[ALERT] Revenue floor breached. Dispatching extra drone nodes.")
