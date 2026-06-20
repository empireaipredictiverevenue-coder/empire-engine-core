import asyncio
from bots.predictive_camofox_scraper import PredictiveCamofoxScraper
from bots.predictive_deep_research_agent import PredictiveDeepResearchAgent
from bots.predictive_outreach_agent import PredictiveOutreachAgent
from supabase import create_client
import os
from dotenv import load_dotenv

load_dotenv("/root/.env")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

async def full_pipeline_test():
    print("=== FULL END-TO-END PIPELINE TEST ===\n")
    
    # Get seeded high-urgency leads
    leads = sb.table("radar_targets").select("*").eq("status", "active").gte("urgency_score", 7).limit(5).execute().data
    print(f"Found {len(leads)} high-urgency leads\n")
    
    scraper = PredictiveCamofoxScraper()
    researcher = PredictiveDeepResearchAgent()
    outreach = PredictiveOutreachAgent()
    
    # Step 1: Scrape (simulated with seeded data)
    print("--- Step 1: Scraper ---")
    scraped = await scraper.run_cycle()
    print(f"Scraped {scraped[count]} opportunities\n")
    
    # Step 2: Research
    print("--- Step 2: Research ---")
    researched = await researcher.run_cycle(scraped.get("opportunities", []))
    print(f"Researched {len(researched)} opportunities\n")
    
    # Step 3: Outreach
    print("--- Step 3: Outreach ---")
    await outreach.run_cycle()
    print("Outreach cycle completed\n")
    
    print("=== PIPELINE TEST COMPLETE ===")

asyncio.run(full_pipeline_test())
