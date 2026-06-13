"""
EMPIRE V49 · PRODUCT 3: BUYER SPY AI (Network Bypass)
======================================================
Analyzes call transcripts to extract direct end-buyer brand names,
bypassing aggregator middlemen. Wraps the existing buyer_spy_worker.py
into a productized API service with tier-based rate limits.

Integration:
    spy = BuyerSpy(suite_guard, suite_subscriptions)
    result = spy.analyze_transcript(account_id, transcript_text)
    report = spy.generate_report(account_id)
"""
import json as _json
import logging
import uuid
from datetime import datetime, timezone
from typing import Callable, Optional

log = logging.getLogger("empire.product.buyer_spy")


class BuyerSpy:
    """Analyze call transcripts to extract direct buyer identities.
    Wraps the existing buyer_spy_worker logic into a productized API
    with tier-based rate limits and usage metering."""

    def __init__(
        self,
        guard: Optional[Callable] = None,      # SuiteGuard.check_access
        log_usage: Optional[Callable] = None,   # SuiteGuard.log_usage
        ollama_host: str = "localhost",
        ollama_port: int = 11434,
        ollama_model: str = "llama3:8b",
    ):
        self.guard = guard
        self.log_usage = log_usage
        self.ollama_host = ollama_host
        self.ollama_port = ollama_port
        self.ollama_model = ollama_model
        self.stats = {"analyzed": 0, "buyers_found": 0, "errors": 0}
        # In-memory results (in production, persists to Supabase)
        self._results: dict[str, list[dict]] = {}

    async def check_entitlement(self, account_id: str) -> dict:
        if not self.guard:
            return {"ok": False, "error": "No guard configured"}
        return self.guard(account_id, "buyer_spy")

    async def analyze_transcript(self, account_id: str, transcript: str,
                                 call_metadata: Optional[dict] = None) -> dict:
        """Run buyer identification on a call transcript.
        Uses local Ollama to extract the brand/company name from the
        recorded telephone conversation text."""
        entitlement = await self.check_entitlement(account_id)
        if not entitlement.get("ok"):
            self.stats["errors"] += 1
            return {"ok": False, "error": entitlement.get("error", "Access denied")}

        if not transcript or len(transcript.strip()) < 20:
            return {"ok": False, "error": "Transcript too short (min 20 chars)"}

        # Run extraction via local Ollama
        brand = self._consult_spy_matrix(transcript)

        analysis_id = f"spy_{uuid.uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        result = {
            "analysis_id": analysis_id,
            "account_id": account_id,
            "timestamp": now,
            "transcript_length": len(transcript),
            "extracted_brand": brand,
            "raw_brand": brand.upper(),
            "call_metadata": call_metadata or {},
            "tier": entitlement.get("tier", "unknown"),
        }

        self._results.setdefault(account_id, []).append(result)
        self.stats["analyzed"] += 1
        if brand and brand not in ("UNKNOWN_AGGREGATOR", "UNKNOWN"):
            self.stats["buyers_found"] += 1

        # Meter usage
        if self.log_usage:
            try:
                self.log_usage(account_id, "buyer_spy", "spy_analysis",
                               quantity=1, metadata={"brand": brand, "analysis_id": analysis_id})
            except Exception:
                pass

        return {"ok": True, **result}

    def _consult_spy_matrix(self, transcript: str) -> str:
        """Query local Ollama to extract corporate identity from transcript.
        Falls back gracefully if Ollama is unavailable."""
        import http.client as http_client
        conn = http_client.HTTPConnection(self.ollama_host, self.ollama_port, timeout=15)
        try:
            headers = {"Content-Type": "application/json"}
            system = (
                "You are an intake auditor tracking corporate entities. "
                "Analyze the following telephone text and isolate the commercial brand name "
                "mentioned by the answering sales representative. "
                "Return a JSON object containing exactly one key: 'extracted_brand_identity'."
            )
            payload = {
                "model": self.ollama_model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": transcript[:3000]},
                ],
                "stream": False,
                "format": "json",
            }
            conn.request("POST", "/api/chat", _json.dumps(payload), headers)
            res = conn.getresponse()
            raw = _json.loads(res.read().decode())
            content = raw.get("message", {}).get("content", "{}")
            parsed = _json.loads(content)
            return parsed.get("extracted_brand_identity", "UNKNOWN_AGGREGATOR")
        except Exception as e:
            log.debug(f"[buyer_spy] Ollama call failed: {e}")
            return self._fallback_extract(transcript)
        finally:
            conn.close()

    @staticmethod
    def _fallback_extract(transcript: str) -> str:
        """Simple heuristic fallback if Ollama is unavailable.
        Looks for capitalized multi-word patterns that look like company names."""
        import re
        # Look for patterns like "Thank you for calling <Company Name>"
        patterns = [
            r"thank you for (?:calling|dialing|contacting)\s+([A-Z][A-Za-z0-9\s&]+?)(?:\,|\.|my|how|let)",
            r"(?:welcome to|reached)\s+([A-Z][A-Za-z0-9\s&]+?)(?:\,|\.|my|how)",
        ]
        for pat in patterns:
            m = re.search(pat, transcript, re.IGNORECASE)
            if m:
                name = m.group(1).strip()
                if len(name) > 3:
                    return name
        return "UNKNOWN_AGGREGATOR"

    def get_analyses(self, account_id: str, limit: int = 50) -> list[dict]:
        """Return recent analyses for an account."""
        results = self._results.get(account_id, [])
        return results[-limit:][::-1]

    def generate_report(self, account_id: str) -> dict:
        """Generate a buyer intelligence report for this account:
        unique brands found, frequency, trends."""
        analyses = self._results.get(account_id, [])
        brands = {}
        for a in analyses:
            brand = a.get("extracted_brand", "UNKNOWN")
            if brand not in ("UNKNOWN_AGGREGATOR", "UNKNOWN"):
                brands[brand] = brands.get(brand, 0) + 1

        sorted_brands = sorted(brands.items(), key=lambda x: -x[1])
        return {
            "account_id": account_id,
            "total_analyzed": len(analyses),
            "unique_buyers": len(brands),
            "top_buyers": [{"brand": b, "mentions": c} for b, c in sorted_brands[:10]],
            "generated_at": datetime.now(timezone.utc).isoformat(),
        }

    def snapshot(self) -> dict:
        total_accounts = len(self._results)
        total_unique = sum(1 for a_list in self._results.values() for a in a_list
                          if a.get("extracted_brand") not in ("UNKNOWN_AGGREGATOR", "UNKNOWN"))
        return {
            **self.stats,
            "accounts_with_data": total_accounts,
            "total_unique_buyers": total_unique,
        }


class BuyerSpyRoutes:
    """Wire BuyerSpy endpoints into the FastAPI app."""

    def __init__(self, spy: BuyerSpy, require_auth: Optional[Callable] = None):
        self.spy = spy
        self.require_auth = require_auth

    def register(self, app):
        from fastapi import Depends, HTTPException, Request, Query
        from fastapi.responses import JSONResponse

        @app.post("/api/v6/suite/buyer-spy/analyze")
        async def spy_analyze(request: Request, auth: bool = Depends(self.require_auth) if self.require_auth else None):
            """Analyze a call transcript for buyer identity.
            Body: {account_id, transcript, call_metadata?}"""
            try:
                body = await request.json()
            except Exception:
                raise HTTPException(400, "Invalid JSON")
            account_id = (body.get("account_id") or "").strip()
            transcript = (body.get("transcript") or "").strip()
            if not account_id:
                raise HTTPException(400, "account_id required")
            if not transcript:
                raise HTTPException(400, "transcript required")
            result = await self.spy.analyze_transcript(
                account_id, transcript,
                call_metadata=body.get("call_metadata", {}),
            )
            status = 403 if not result.get("ok") and "denied" in str(result.get("error", "")).lower() else (200 if result.get("ok") else 400)
            return JSONResponse(result, status_code=status)

        @app.get("/api/v6/suite/buyer-spy/analyses")
        async def spy_analyses(account_id: str = Query(...), limit: int = Query(50),
                                auth: bool = Depends(self.require_auth) if self.require_auth else None):
            if not account_id:
                raise HTTPException(400, "account_id query param required")
            analyses = self.spy.get_analyses(account_id, limit=min(limit, 200))
            return JSONResponse({"analyses": analyses, "count": len(analyses)})

        @app.get("/api/v6/suite/buyer-spy/report")
        async def spy_report(account_id: str = Query(...),
                              auth: bool = Depends(self.require_auth) if self.require_auth else None):
            if not account_id:
                raise HTTPException(400, "account_id query param required")
            report = self.spy.generate_report(account_id)
            return JSONResponse(report)

        @app.get("/api/v6/suite/buyer-spy/stats")
        async def spy_stats(auth: bool = Depends(self.require_auth) if self.require_auth else None):
            return JSONResponse(self.spy.snapshot())

        log.info("[buyer-spy] Routes registered")
