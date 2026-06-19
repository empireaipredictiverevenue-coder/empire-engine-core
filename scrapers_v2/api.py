from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
import asyncio
from orchestrator import run_all_sources
from models import Lead

app = FastAPI(title="Elite Scraper v2 API")

class ScrapeRequest(BaseModel):
    vertical: Optional[str] = None
    max_results: int = 50

@app.post("/scrape", response_model=List[Lead])
async def scrape(req: ScrapeRequest):
    results = await run_all_sources()
    if req.vertical:
        results = [l for l in results if l.vertical == req.vertical]
    return results[:req.max_results]

@app.get("/health")
async def health():
    return {"status": "ok", "version": "2.0"}

@app.get("/metrics")
async def metrics():
    from metrics import start_metrics_server
    return {"message": "Metrics available on :8002"}
