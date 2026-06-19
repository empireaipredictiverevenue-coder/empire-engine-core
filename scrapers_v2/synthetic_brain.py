import os
import httpx
from typing import Dict
from models import Lead

SYNTHETIC_BRAIN_URL = os.getenv("SYNTHETIC_BRAIN_URL", "http://127.0.0.1:8005")

async def llm_score_lead(lead: Lead) -> float:
    """
    Use the synthetic_brain (or MiniMax) to score a lead.
    Falls back to rule-based if LLM unavailable.
    """
    prompt = f"""Score this lead from 0-100 based on expected value for a storm damage / B2B contractor lead-gen business.

Vertical: {lead.vertical}
City/State: {lead.city}, {lead.state}
Has phone: {bool(lead.phone)}
Has email: {bool(lead.email)}
Has website: {bool(lead.website)}

Return ONLY a number between 0 and 100."""

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{SYNTHETIC_BRAIN_URL}/api/v1/score",
                json={"prompt": prompt, "max_tokens": 10}
            )
            if resp.status_code == 200:
                score = float(resp.json().get("text", "50").strip())
                return min(max(score, 0), 100)
    except:
        pass

    # Fallback to rule-based
    score = 50.0
    if lead.vertical in ["Public Adjuster", "Restoration"]:
        score += 20
    if lead.phone:
        score += 15
    if lead.email:
        score += 10
    if lead.website:
        score += 5
    return min(score, 100.0)
