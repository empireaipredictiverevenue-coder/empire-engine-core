"""
EMPIRE V49 · HOOK & TREND DECIDER ENGINE
=========================================
Ingests raw social hooks, compares them against the viral formula database
via mathematical pattern triggers, and scores whether there is enough
momentum to back a new paid vertical.

Pipeline:
    Raw hook text → formula comparison → velocity scoring
        → viability computation → verdict (LAUNCH | REJECT)
        → telemetry logging to storm_alerts.sqlite

Standalone API:
    POST /api/v6/hooks/evaluate  — Evaluate a detected hook pattern
    GET  /api/v6/hooks/formulas  — List registered hook formulas
    GET  /api/v6/hooks/trends    — Recent trend telemetry
"""

import json as _json
import logging
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, status

log = logging.getLogger("empire.hook_analytics")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"


# ── Trend Viability Formula ────────────────────────────────────────────
# Viability Score = (Velocity Multiplier * 40)
#                 + (Sample Size Weight * 30)
#                 + (Keyword Priority * 30)

def compute_trend_viability(
    niche_category: str,
    hook_text: str,
    sample_size_videos: int,
    average_velocity_multiplier: float,
) -> float:
    """
    Computes if a hook pattern has passed the statistical velocity threshold.

    Formula Framework:
        base_velocity_weight = velocity_multiplier * 40
        sample_size_weight   = min(sample_size * 1.5, 30)  # capped at 30
        keyword_bonus        = 0–30 based on niche priority
    """
    base_velocity_weight = average_velocity_multiplier * 40.0
    sample_size_weight = min(sample_size_videos * 1.5, 30.0)  # Cap sample weight at 30

    # Priority niche keyword multiplier bonuses
    keyword_bonus = 0.0
    lower_hook = hook_text.lower()
    lower_niche = niche_category.lower()

    if "mass tort" in lower_hook or "lawsuit" in lower_hook or "mass_tort" in lower_niche:
        keyword_bonus = 30.0
    elif "roof" in lower_hook or "storm" in lower_hook or "roofing" in lower_niche:
        keyword_bonus = 25.0
    elif "financial" in lower_niche or "cpa" in lower_niche or "tax" in lower_hook:
        keyword_bonus = 22.0
    elif "legal" in lower_niche or "attorney" in lower_hook:
        keyword_bonus = 28.0
    elif "commercial" in lower_niche or "warehouse" in lower_hook:
        keyword_bonus = 20.0

    return base_velocity_weight + sample_size_weight + keyword_bonus


# ── Database Helpers ───────────────────────────────────────────────────

def _init_tables():
    """Ensure the hook_frameworks SQL schema is present in the DB."""
    schema_path = BASE_DIR / "database" / "hook_frameworks.sql"
    if schema_path.exists():
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.executescript(schema_path.read_text())
            conn.commit()
        except Exception as e:
            log.warning(f"[hooks] schema init: {e}")
        finally:
            conn.close()


def _get_formulas() -> list[dict]:
    """Return all registered hook formulas."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "SELECT formula_id, formula_name, verbal_template, psychological_trigger, "
            "target_retention_benchmark, created_at FROM viral_hook_formulas ORDER BY formula_name"
        )
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        log.debug(f"[hooks] formulas fetch: {e}")
        return []
    finally:
        conn.close()


def _get_recent_trends(limit: int = 20) -> list[dict]:
    """Return recent trend telemetry entries."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        cur = conn.execute(
            "SELECT trend_id, niche_category, hook_text_detected, sample_size_videos, "
            "average_velocity_multiplier, trend_viability_score, evaluated_at "
            "FROM incoming_trend_telemetry ORDER BY evaluated_at DESC LIMIT ?",
            (limit,),
        )
        columns = [d[0] for d in cur.description]
        return [dict(zip(columns, row)) for row in cur.fetchall()]
    except Exception as e:
        log.debug(f"[hooks] trends fetch: {e}")
        return []
    finally:
        conn.close()


def _record_trend(
    trend_id: str,
    niche_category: str,
    hook_text: str,
    sample_size: int,
    velocity: float,
    score: float,
):
    """Persist a trend evaluation to the telemetry table."""
    conn = sqlite3.connect(str(DB_PATH))
    try:
        conn.execute(
            """INSERT INTO incoming_trend_telemetry
               (trend_id, niche_category, hook_text_detected,
                sample_size_videos, average_velocity_multiplier, trend_viability_score)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (trend_id, niche_category, hook_text, sample_size, velocity, round(score, 2)),
        )
        conn.commit()
    except Exception as e:
        log.warning(f"[hooks] failed to record trend: {e}")
    finally:
        conn.close()


# ── FastAPI App ────────────────────────────────────────────────────────

app = FastAPI(title="Empire AI · Hook Trend Decider Engine", version="1.0.0")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    _init_tables()
    log.info("[hooks] Hook & Trend Decider Engine operational")


# ── Request / Response Models ──────────────────────────────────────────

from pydantic import BaseModel, Field


class TrendEvaluationPayload(BaseModel):
    niche_category: str = Field(..., description="mass_tort, roofing, financial, legal, commercial")
    hook_text_detected: str = Field(..., description="The raw hook text observed in the wild")
    sample_size_videos: int = Field(default=0, ge=0, description="Number of videos observed")
    average_velocity_multiplier: float = Field(default=1.0, ge=0.0, description="View acceleration multiplier")


# ── Endpoints ──────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": "Empire AI · Hook Trend Decider Engine",
        "version": "1.0.0",
        "endpoints": [
            "POST /api/v6/hooks/evaluate  — Evaluate a detected hook pattern",
            "GET  /api/v6/hooks/formulas  — List registered hook formulas",
            "GET  /api/v6/hooks/trends    — Recent trend telemetry",
        ],
    }


@app.post("/api/v6/hooks/evaluate", status_code=status.HTTP_200_OK)
async def evaluate_incoming_hook_trend(payload: TrendEvaluationPayload):
    """
    Ingests hook data, applies formula mechanics, and updates the trend
    evaluation database.

    Decision Matrix: Requires a baseline viability score of 75.0 to launch
    a paid campaign target.
    """
    trend_id = "trnd_" + str(uuid.uuid4())[:8]
    computed_score = compute_trend_viability(
        niche_category=payload.niche_category,
        hook_text=payload.hook_text_detected,
        sample_size_videos=payload.sample_size_videos,
        average_velocity_multiplier=payload.average_velocity_multiplier,
    )

    # Decision threshold: ≥ 75.0 → launch campaign
    action_verdict = (
        "LAUNCH_IMMEDIATE_CAMPAIGN"
        if computed_score >= 75.0
        else "REJECT_TREND_INSUFFICIENT_MOMENTUM"
    )

    # Persist the evaluation
    _record_trend(
        trend_id=trend_id,
        niche_category=payload.niche_category,
        hook_text=payload.hook_text_detected,
        sample_size=payload.sample_size_videos,
        velocity=payload.average_velocity_multiplier,
        score=computed_score,
    )

    return {
        "trend_id": trend_id,
        "niche": payload.niche_category,
        "calculated_viability_score": round(computed_score, 2),
        "verdict": action_verdict,
        "intro_retention_target": "70% Minimum",
        "matched_formulas": _get_formulas()[:5],
    }


@app.get("/api/v6/hooks/formulas")
async def list_hook_formulas():
    """Return all registered viral hook formulas."""
    return {"formulas": _get_formulas(), "count": len(_get_formulas())}


@app.get("/api/v6/hooks/trends")
async def list_recent_trends(limit: int = 20):
    """Return recent trend telemetry evaluations."""
    return {"trends": _get_recent_trends(min(limit, 100)), "count": len(_get_recent_trends(min(limit, 100)))}


# ── Hub Route Registration ─────────────────────────────────────────────

class HookRoutes:
    """Wire hook endpoints into the main hub app."""

    def __init__(self, require_auth: Optional[callable] = None):
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, Query
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/hooks/evaluate")
        async def _evaluate(
            payload: TrendEvaluationPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            return JSONResponse(await evaluate_incoming_hook_trend(payload))

        @app.get("/api/v6/hooks/formulas")
        async def _formulas(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            return JSONResponse(await list_hook_formulas())

        @app.get("/api/v6/hooks/trends")
        async def _trends(
            limit: int = Query(20),
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            return JSONResponse(await list_recent_trends(limit))

        log.info("[hook-routes] Registered · /api/v6/hooks/*")


# ═════════════════════════════════════════════════════════════════════════
# STANDALONE APP (uvicorn port 8046)
# ═════════════════════════════════════════════════════════════════════════
# Used by scripts/deploy_hooks.sh for standalone deployment.
# Routes are also available on the main hub (integrated mode via hub.py).

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("HOOK_ANALYTICS_PORT", "8046"))
    host = os.environ.get("HOOK_ANALYTICS_HOST", "0.0.0.0")
    log.info(f"[hooks] Starting Hook Trend Decider on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
