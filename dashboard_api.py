import httpx
import os
from fastapi import FastAPI

app = FastAPI()

@app.get("/api/dashboard/stats")
async def get_dashboard_stats():
    url = f"{os.getenv('SUPABASE_URL')}/rest/v1/predictive_revenue_view"
    headers = {"apikey": os.getenv('SUPABASE_KEY'), "Authorization": f"Bearer {os.getenv('SUPABASE_KEY')}"}
    
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers)
        return response.json()
