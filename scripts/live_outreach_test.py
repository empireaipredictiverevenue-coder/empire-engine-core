import asyncio
from bots.predictive_lead_converter_agent import PredictiveLeadConverterAgent
from bots.predictive_outreach_agent import PredictiveOutreachAgent
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv("/root/.env")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

async def live_test():
    print("=== LIVE OUTREACH SYSTEM TEST ===\n")
    
    leads = sb.table("radar_targets").select("*").eq("status", "active").gte("urgency_score", 7).limit(3).execute().data
    print("Found", len(leads), "high-urgency leads\n")
    
    converter = PredictiveLeadConverterAgent()
    outreach = PredictiveOutreachAgent()
    
    for i, lead in enumerate(leads, 1):
        print("--- Lead", i, "---")
        print("Address:", lead.get("address"))
        print("Urgency:", lead.get("urgency_score"))
        print("Email:", lead.get("email"))
        
        converted = await converter.convert_lead(lead)
        print("Converted:", converted.get("converted", False))
        
        await outreach.run_cycle()
        print("Outreach cycle completed\n")
    
    print("=== TEST COMPLETE ===")

asyncio.run(live_test())
