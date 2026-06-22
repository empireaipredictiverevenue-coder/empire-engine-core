"""
EMPIRE V49 · LANDING PAGE MATRIX
==================================
Dynamic page engine that queries local storm alerts and generates
personalized landing page copy via Ollama. Runs on port 8030.

ENDPOINTS
─────────
  POST /api/v6/landing/render  → Generate dynamic landing page config
  GET  /api/v6/landing/health  → Health check
"""

import os
import json
import sqlite3
import http.client
import logging
from pathlib import Path

from fastapi import FastAPI, status
from pydantic import BaseModel

log = logging.getLogger("empire.landing.matrix")

app = FastAPI(title="Empire_AI_Landing_Page_Matrix", version="6.0.0")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"

# ── Models ────────────────────────────────────────────────────────────
class PageRequest(BaseModel):
    visitor_zip: str
    traffic_source: str
    niche: str


# ── Ollama Helper ─────────────────────────────────────────────────────
_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "localhost")
_OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
_OLLAMA_MODEL = os.environ.get("OLLAMA_LANDING_MODEL", "llama3.2:3b")


def _fetch_dynamic_copy(system_rules: str, context: str) -> dict:
    """Call Ollama for conversion-focused copy generation."""
    conn = http.client.HTTPConnection(_OLLAMA_HOST, _OLLAMA_PORT, timeout=10)
    headers = {"Content-Type": "application/json"}
    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_rules},
            {"role": "user", "content": context},
        ],
        "stream": False,
        "format": "json",
    }
    try:
        conn.request("POST", "/api/chat", json.dumps(payload), headers)
        res = conn.getresponse()
        raw = json.loads(res.read().decode())
        content = raw.get("message", {}).get("content", "{}")
        return json.loads(content)
    except Exception:
        return {
            "headline": "Emergency Commercial Roofing Specialists",
            "subheadline": "Fast inspections for storm-hit commercial properties.",
        }
    finally:
        conn.close()


# ── Routes ────────────────────────────────────────────────────────────
@app.get("/api/v6/landing/health")
async def landing_health():
    """Health check."""
    return {"status": "OPERATIONAL", "service": "landing-page-matrix", "version": "6.0.0"}


@app.post("/api/v6/landing/render", status_code=status.HTTP_200_OK)
async def get_landing_page_config(payload: PageRequest):
    """Generate dynamic landing page content based on visitor zip + storm data."""
    storm_match = None
    if DB_PATH.exists():
        try:
            conn = sqlite3.connect(str(DB_PATH))
            cursor = conn.cursor()
            cursor.execute(
                "SELECT event FROM storm_alerts WHERE zip_code = ?",
                (payload.visitor_zip,),
            )
            storm_match = cursor.fetchone()
            conn.close()
        except Exception as e:
            log.warning(f"[landing] SQLite query failed: {e}")

    if storm_match:
        storm_type = storm_match[0]
        sys_rules = (
            "You are a conversion copywriting expert. A user is visiting our landing page "
            f"from a zip code that was just hit by a severe {storm_type}. Write an aggressive, "
            "high-converting headline and subheadline targeting commercial property owners who "
            "need roof inspections immediately. Keep it short and hard-hitting. "
            "Return a JSON object with 'headline' and 'subheadline'."
        )
    else:
        sys_rules = (
            "You are a conversion copywriting expert. Write a direct-response headline and "
            f"subheadline for a commercial {payload.niche} company. Focus on cutting waste "
            "and maximizing value. "
            "Return a JSON object with 'headline' and 'subheadline'."
        )

    user_context = (
        f"Niche: {payload.niche} | "
        f"Traffic: {payload.traffic_source} | "
        f"Zip: {payload.visitor_zip}"
    )
    page_copy = _fetch_dynamic_copy(sys_rules, user_context)

    return {
        "status": "RENDER_READY",
        "show_ugly_banner": storm_match is not None,
        "banner_text": (
            f"ALERT: Severe weather recorded in {payload.visitor_zip}. "
            f"Local inspectors available."
        ) if storm_match else None,
        "copy": page_copy,
        "visitor_zip": payload.visitor_zip,
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8030)
