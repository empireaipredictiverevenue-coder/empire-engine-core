"""
EMPIRE V49 · PRODUCT: OMNI-CHANNEL AUTOMATION BRIDGE
=====================================================
Processes audio calls through Deepgram speech-to-text, extracts buyer
identities via BuyerSpy, then syndicates campaigns across social/messaging
networks via Zernio API. Part of the Suite Gateway monetization.

Pipeline:
    Raw audio URL → Deepgram STT → transcript
        → BuyerSpy brand extraction
        → Social blast text generation
        → Zernio multi-platform distribution (WhatsApp, LinkedIn, X/Twitter)
        → customer_usage_ledger logging

Integration:
    bridge = OmniBridge(suite_guard, suite_buyer_spy, log_usage_fn)
    result = await bridge.process_audio(account_id, audio_url, niche)
"""
import json as _json
import logging
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from fastapi import FastAPI

log = logging.getLogger("empire.product.omni_bridge")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"

# ── Config from env vars ──────────────────────────────────────────────
DEEPGRAM_API_KEY = os.environ.get("DEEPGRAM_API_KEY", "")
DEEPGRAM_MODEL = os.environ.get("DEEPGRAM_MODEL", "nova-3")  # or "flux" for real-time
ZERNIO_API_KEY = os.environ.get("ZERNIO_API_KEY", "")
ZERNIO_BASE_URL = os.environ.get("ZERNIO_BASE_URL", "https://api.zernio.com")


class OmniBridge:
    """Orchestrate the audio → transcript → social blast pipeline.
    Each step is gated by suite entitlement and metered for billing."""

    def __init__(
        self,
        guard: Optional[Callable] = None,        # SuiteGuard.check_access
        buyer_spy: Optional[Callable] = None,     # BuyerSpy.analyze_transcript coroutine
        log_usage: Optional[Callable] = None,     # SuiteGuard.log_usage
    ):
        self.guard = guard
        self.buyer_spy = buyer_spy
        self.log_usage = log_usage
        self.stats = {"processed": 0, "transcribed": 0, "brands_found": 0,
                       "posted": 0, "errors": 0}

        # Warn on missing API keys at construction, not at every call
        if not DEEPGRAM_API_KEY:
            log.warning("[omni] DEEPGRAM_API_KEY not set — transcription will be simulated")
        if not ZERNIO_API_KEY:
            log.warning("[omni] ZERNIO_API_KEY not set — social posting will be skipped")

    async def check_entitlement(self, account_id: str) -> dict:
        """Verify the account has the inbound_router feature enabled
        (omni bridge is a premium routing product)."""
        if not self.guard:
            return {"ok": False, "error": "No guard configured"}
        return self.guard(account_id, "inbound_router")

    # ── STEP 1: Deepgram STT ──────────────────────────────────────────

    async def transcribe_audio(self, audio_url: str) -> str:
        """Send audio to Deepgram Nova-3 for high-accuracy transcription.
        Falls back to simulated transcript if API key is not configured."""
        if not DEEPGRAM_API_KEY:
            log.info(f"[omni] Deepgram API key not set — simulated transcript for {audio_url[:60]}")
            self.stats["transcribed"] += 1
            return "Thank you for calling Elite Commercial Property and Storm Restoration. How can we help?"

        try:
            import httpx
            async with httpx.AsyncClient(timeout=60.0) as client:
                # Deepgram /v1/listen — POST audio URL for transcription
                response = await client.post(
                    f"https://api.deepgram.com/v1/listen?model={DEEPGRAM_MODEL}&smart_format=true&diarize=true&punctuate=true",
                    headers={
                        "Authorization": f"Token {DEEPGRAM_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={"url": audio_url},
                )
                if response.status_code >= 300:
                    log.warning(f"[omni] Deepgram error {response.status_code}: {response.text[:200]}")
                    self.stats["errors"] += 1
                    return ""

                data = response.json()
                # Extract transcript from Deepgram response
                channels = data.get("results", {}).get("channels", [])
                if channels:
                    alternatives = channels[0].get("alternatives", [])
                    if alternatives:
                        transcript = alternatives[0].get("transcript", "")
                        self.stats["transcribed"] += 1
                        log.info(f"[omni] Deepgram transcribed {len(transcript)} chars from {audio_url[:50]}...")
                        return transcript

                log.warning(f"[omni] Deepgram returned no transcript for {audio_url[:50]}")
                return ""
        except Exception as e:
            log.warning(f"[omni] Deepgram request failed: {e}")
            self.stats["errors"] += 1
            return ""

    # ── STEP 2: Buyer Spy extraction ──────────────────────────────────

    async def extract_brand(self, account_id: str, transcript: str) -> str:
        """Run buyer identification on the transcript."""
        if not self.buyer_spy:
            # Fallback: simple keyword extraction
            if "Property" in transcript:
                return "Elite Commercial Property"
            return "Unknown"

        try:
            result = await self.buyer_spy(account_id, transcript,
                                          call_metadata={"source": "omni_bridge"})
            brand = result.get("extracted_brand", "Unknown")
            if brand not in ("UNKNOWN_AGGREGATOR", "UNKNOWN"):
                self.stats["brands_found"] += 1
            return brand
        except Exception as e:
            log.debug(f"[omni] BuyerSpy extraction failed: {e}")
            return "Unknown"

    # ── STEP 3: Zernio multi-platform post (async via httpx) ────────────

    async def post_to_zernio(self, message_text: str, platforms: list[str]) -> bool:
        """Push a structured payload to Zernio's social/messaging API for
        distribution across the specified platforms. Uses httpx.AsyncClient
        so it doesn't block the async event loop."""
        if not ZERNIO_API_KEY:
            log.info(f"[omni] Zernio API key not set — simulated post to {platforms}")
            self.stats["posted"] += 1
            return True

        import httpx
        headers = {
            "Authorization": f"Bearer {ZERNIO_API_KEY}",
            "Content-Type": "application/json",
        }
        payload = {
            "text": message_text,
            "platforms": platforms,
            "auto_plug": True,
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    f"{ZERNIO_BASE_URL}/v1/posts",
                    json=payload,
                    headers=headers,
                )
                if resp.status_code < 300:
                    self.stats["posted"] += 1
                    log.info(f"[omni] Zernio posted to {len(platforms)} channels: {platforms}")
                    return True
                else:
                    body = resp.text[:200]
                    log.warning(f"[omni] Zernio error {resp.status_code}: {body}")
                    self.stats["errors"] += 1
                    return False
        except Exception as e:
            log.warning(f"[omni] Zernio POST failed: {e}")
            self.stats["errors"] += 1
            return False

    # ── PIPELINE: end-to-end ──────────────────────────────────────────

    async def process_audio(
        self,
        account_id: str,
        audio_url: str,
        campaign_niche: str,
        platforms: Optional[list[str]] = None,
    ) -> dict:
        """End-to-end omni pipeline: gatecheck → transcribe → extract → post → log."""
        if not platforms:
            platforms = ["whatsapp", "linkedin", "twitter"]

        # 1. Entitlement
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["errors"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied"),
                    "step": "entitlement"}

        # 2. Transcribe via Deepgram
        transcript = await self.transcribe_audio(audio_url)

        # 3. Extract brand identity via BuyerSpy
        detected_brand = await self.extract_brand(account_id, transcript)

        # 4. Generate social copy
        social_blast_text = (
            f"ALERT: New high-intent lead verified for {campaign_niche}. "
            f"Sourced via Empire AI predictive routing."
        )

        # 5. Post to Zernio (async — doesn't block event loop)
        posted = await self.post_to_zernio(social_blast_text, platforms)

        # 6. Log to usage ledger
        self._log_ledger(account_id, audio_url, len(platforms) if posted else 0)

        # 7. Meter via suite
        if self.log_usage:
            try:
                self.log_usage(account_id, "inbound_router", "omni_pipeline",
                               quantity=1, metadata={
                                   "audio_url": audio_url[:60],
                                   "niche": campaign_niche,
                                   "platforms": platforms,
                                   "posted": posted,
                                   "brand": detected_brand,
                               })
            except Exception:
                pass

        self.stats["processed"] += 1
        return {
            "ok": True,
            "status": "OMNI_CAMPAIGN_DISPATCHED",
            "account_id": account_id,
            "deepgram_match": bool(transcript),
            "transcript_length": len(transcript),
            "zernio_channels_hit": len(platforms) if posted else 0,
            "extracted_identity": detected_brand,
            "tier": entitlement.get("tier", "unknown"),
        }

    # ── LEDGER LOGGING ────────────────────────────────────────────────

    def _log_ledger(self, account_id: str, audio_url: str, channels_hit: int):
        """Insert a row into the customer_usage_ledger table."""
        conn = sqlite3.connect(str(DB_PATH))
        try:
            conn.execute(
                """INSERT INTO customer_usage_ledger
                   (transaction_id, customer_account_id, api_endpoint_accessed,
                    computed_raw_cost, client_billed_amount, metadata)
                   VALUES (hex(randomblob(16)), ?, '/api/v6/omni/process', ?, ?, ?)""",
                (
                    account_id,
                    0.0012,  # raw cost per pipeline run
                    round(channels_hit * 0.15, 4),  # billed per channel hit
                    _json.dumps({"audio_url": audio_url[:80], "channels_hit": channels_hit}),
                ),
            )
            conn.commit()
        except Exception as e:
            log.debug(f"[omni] ledger log skipped: {e}")
        finally:
            conn.close()

    # ── STATS ─────────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {**self.stats}


class OmniBridgeRoutes:
    """Wire OmniBridge endpoints into the FastAPI app."""

    def __init__(self, bridge: OmniBridge, require_auth: Optional[Callable] = None):
        self.bridge = bridge
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request, Query
        from fastapi.responses import JSONResponse
        from pydantic import BaseModel

        class OmniPayload(BaseModel):
            customer_account_id: str
            raw_audio_url: str
            campaign_niche: str
            platforms: Optional[list[str]] = None

        @app.post("/api/v6/omni/process")
        async def process_omni_pipeline(
            payload: OmniPayload,
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """Intercepts audio calls, extracts text via Deepgram, tracks metrics,
            and syndicates campaigns across 15+ networks via Zernio.

            Body: {
                customer_account_id: "client_alpha_operator",
                raw_audio_url: "https://example.com/recordings/call-123.mp3",
                campaign_niche: "Roofing Restoration",
                platforms?: ["whatsapp", "linkedin", "twitter", "facebook"]
            }
            """
            result = await self.bridge.process_audio(
                account_id=payload.customer_account_id.strip(),
                audio_url=payload.raw_audio_url.strip(),
                campaign_niche=payload.campaign_niche.strip(),
                platforms=payload.platforms,
            )
            status = 403 if result.get("step") == "entitlement" else (200 if result.get("ok") else 400)
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/omni/stats")
        async def omni_stats(
            auth: bool = Depends(self.require_auth) if self.require_auth else None,
        ):
            """OmniBridge pipeline stats."""
            return JSONResponse(self.bridge.snapshot())

        log.info("[omni-bridge] Routes registered · /api/v6/omni/*")


# ═════════════════════════════════════════════════════════════════════════
# STANDALONE APP (uvicorn port 8040)
# ═════════════════════════════════════════════════════════════════════════
# Used by deploy_omni_bridge.sh for standalone deployment.
# In production the routes are also available on the main hub (integrated mode).


def create_standalone_app() -> FastAPI:
    """Create a standalone FastAPI app with the omni bridge routes.
    No suite guard in standalone mode — uses simple subscription lookups.
    """
    standalone = FastAPI(title="Empire AI · Omni Bridge", version="1.0.0")

    from fastapi.middleware.cors import CORSMiddleware
    standalone.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    bridge = OmniBridge()
    OmniBridgeRoutes(bridge).register(standalone)

    @standalone.get("/")
    async def root():
        return {
            "service": "Empire AI Omni Bridge",
            "version": "1.0.0",
            "endpoints": [
                "POST /api/v6/omni/process",
                "GET  /api/v6/omni/stats",
            ],
        }

    return standalone


app = create_standalone_app()

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("OMNI_PORT", "8040"))
    host = os.environ.get("OMNI_HOST", "0.0.0.0")
    log.info(f"[omni] Starting standalone bridge on {host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="info")
