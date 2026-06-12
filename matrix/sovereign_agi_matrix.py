"""
EMPIRE V49 · SOVEREIGN SYNTHETIC MATRIX
========================================
Autonomous AGI endpoints for affiliate prospecting and buyer provisioning.
Runs as a standalone FastAPI service on port 8010.

ENDPOINTS
─────────
  POST /api/v6/matrix/affiliate-hunter  → AI-drafted outreach to publishers
  POST /api/v6/matrix/buyer-locksmith   → Provision buyer + trigger media engine
"""

import os
import json
import http.client
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel

log = logging.getLogger("empire.matrix.agi")

app = FastAPI(title="Empire_AI_Sovereign_Synthetic_Matrix", version="6.0.0")

BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / "data" / "growth_logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# ── Models ────────────────────────────────────────────────────────────
class AffiliateLead(BaseModel):
    publisher_name: str
    traffic_source: str
    contact_info: str
    estimated_daily_calls: int


class BuyerContract(BaseModel):
    buyer_company: str
    target_niche: str
    active_zip_codes: list
    cost_per_call_agreement: float


# ── Ollama Helper ─────────────────────────────────────────────────────
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "localhost")
_OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
_OLLAMA_MODEL = os.environ.get("OLLAMA_MATRIX_MODEL", "llama3:8b")


def _call_local_brain(system_rules: str, user_context: str) -> dict:
    """Call local Ollama with a structured prompt, expecting JSON response."""
    conn = http.client.HTTPConnection(_OLLAMA_HOST, _OLLAMA_PORT, timeout=30)
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_rules},
            {"role": "user", "content": user_context},
        ],
        "stream": False,
        "format": "json",
    }
    try:
        conn.request("POST", "/api/chat", json.dumps(payload), headers)
        res = conn.getresponse()
        raw = res.read().decode()
        data = json.loads(raw)
        content = data.get("message", {}).get("content", "{}")
        return json.loads(content)
    except Exception as e:
        log.warning(f"[matrix] Ollama call failed: {e}")
        return {"error": f"Local brain connection dropped: {str(e)}"}
    finally:
        conn.close()


# ── Routes ────────────────────────────────────────────────────────────
@app.get("/api/v6/matrix/health")
async def matrix_health():
    """Health check for the sovereign matrix."""
    return {"status": "OPERATIONAL", "service": "sovereign-synthetic-matrix", "version": "6.0.0"}


@app.post("/api/v6/matrix/affiliate-hunter", status_code=status.HTTP_201_CREATED)
async def process_autonomous_affiliate(payload: AffiliateLead):
    """Review publisher details and auto-generate an outreach pitch."""
    sys_rules = (
        "You are the Affiliate Director for Empire AI. Review the publisher details "
        "and generate an automated outreach response. Pitch our high pay-per-call payouts "
        "for roofing and solar campaigns. Focus on predictive revenue. "
        "Return a JSON object containing exactly one key: 'outreach_message'."
    )
    user_data = (
        f"Publisher: {payload.publisher_name} | "
        f"Source: {payload.traffic_source} | "
        f"Traffic: {payload.estimated_daily_calls} calls/day"
    )
    ai_decision = _call_local_brain(sys_rules, user_data)
    message_to_send = ai_decision.get(
        "outreach_message", "Let's scale your traffic. Connect with us."
    )

    record = {
        **payload.model_dump(),
        "ai_action_drafted": message_to_send,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(LOGS_DIR / "affiliates_matrix.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return {
        "status": "SUCCESS",
        "action_taken": "OUTREACH_DRAFTED",
        "draft": message_to_send,
    }


@app.post("/api/v6/matrix/buyer-locksmith", status_code=status.HTTP_201_CREATED)
async def process_autonomous_buyer(payload: BuyerContract):
    """Provision a new buyer: select target city and trigger media engine."""
    sys_rules = (
        "You are the Operations Director for Empire AI. A new buyer needs high-volume "
        "phone calls. Select the primary target city from their regional list and output "
        "a creative command string for our rendering machine. "
        "Return a JSON object with exactly one key: 'media_engine_command'."
    )
    user_data = (
        f"Company: {payload.buyer_company} | "
        f"Niche: {payload.target_niche} | "
        f"Covered Locations: {json.dumps(payload.active_zip_codes)}"
    )
    ai_decision = _call_local_brain(sys_rules, user_data)
    engine_cmd = ai_decision.get(
        "media_engine_command",
        f"Build a vertical {payload.target_niche} ad framework.",
    )

    # Trigger Sovereign Media Engine (port 8005)
    media_status = "MEDIA_ENGINE_OFFLINE"
    try:
        conn = http.client.HTTPConnection("localhost", 8005, timeout=10)
        headers = {"Content-Type": "application/json"}
        media_payload = {"command": engine_cmd}
        conn.request(
            "POST", "/api/v6/sovereign/deploy", json.dumps(media_payload), headers
        )
        res = conn.getresponse()
        media_status = res.status
    except Exception as e:
        log.warning(f"[matrix] media engine trigger failed: {e}")
    finally:
        conn.close()

    # Log the buyer provisioning
    record = {
        **payload.model_dump(),
        "engine_command": engine_cmd,
        "media_pipeline_status": media_status,
        "processed_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(LOGS_DIR / "buyers_matrix.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")

    return {
        "status": "BUYER_PROVISIONED",
        "allocated_strategy": engine_cmd,
        "media_pipeline_trigger": media_status,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8010)
