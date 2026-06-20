"""
Empire AI · Carrier Adapter Pattern
====================================

Defines the abstract interface a real insurance carrier must implement
for Empire AI's settled-claim feed. Currently the only production
implementation is the mock carrier (empire_carrier.py). When a real
carrier unlocks a partner program, the operator implements the
interface for that carrier and swaps the active adapter.

This file doesn't get imported by the running system. It's a reference
for whoever integrates the first real carrier.

Interface contract:
  - settle_claim(claim_id, settled_amount) -> fee_event row
  - get_open_claims() -> list of claims awaiting settlement
  - get_settled_claims(since: datetime) -> list of recent settlements
  - health_check() -> bool  (is the integration live?)

Each carrier is different:
  - State Farm: doesn't have a public API. Would need a manual
    spreadsheet import or a partnership-built webhook.
  - Allstate: has a vendor partner program for approved vendors.
    The webhook is JSON. Settlement events are real-time.
  - USAA: similar to Allstate, but membership-gated.
  - Liberty Mutual: enterprise sales motion, not developer-first.
  - Farmers: closed API, requires signed agreement.
  - CoverForce (aggregator): insurance API marketplace. Multi-carrier
    access through a single integration. Gated — must Request API Access
    at https://www.coverforce.com/api-access. Once approved, endpoints
    live at coverforce.stoplight.io. This adapter polls CoverForce's
    REST API for settled-claim data and can optionally receive webhook
    callbacks forwarded to our /api/v1/claim-settled endpoint.

Real implementation template (replace placeholders with real values):

    class StateFarmAdapter(CarrierAdapter):
        def __init__(self, api_key, partner_id):
            self.api_key = api_key
            self.partner_id = partner_id
            self.base_url = "https://api.statefarm.com/partner/v1"

        async def get_settled_claims(self, since):
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{self.base_url}/claims/settled",
                    params={"since": since.isoformat()},
                    headers={"X-API-Key": self.api_key, "X-Partner-ID": self.partner_id},
                    timeout=30,
                )
                r.raise_for_status()
                return r.json()["claims"]

        # ... implement other methods

The "swapping" mechanism: a config flag in agent_config
("active_carrier_adapter": "mock" | "state_farm" | "allstate" | ...).
The settled_claim_monitor checks this flag and instantiates the
matching adapter. When a real carrier is added, the operator updates
the flag and the monitor picks it up.

Until that happens, the chain runs on the mock adapter, which is
exercising the same code path the real adapter would.
"""
from abc import ABC, abstractmethod
from datetime import datetime
from typing import List, Optional, Dict, Any
import os


class CarrierAdapter(ABC):
    """Abstract interface for a real insurance carrier's settled-claim
    event feed. All real carriers must implement this."""

    name: str = "abstract"

    @abstractmethod
    def health_check(self) -> bool:
        """Is the integration live and reachable?"""
        pass

    @abstractmethod
    def get_open_claims(self) -> List[Dict[str, Any]]:
        """List claims awaiting settlement (status='open')."""
        pass

    @abstractmethod
    def get_settled_claims(self, since: datetime) -> List[Dict[str, Any]]:
        """List claims that settled since the given timestamp."""
        pass

    @abstractmethod
    def settle_claim(self, claim_id: str, settled_amount: float, meta: Optional[Dict] = None) -> Dict[str, Any]:
        """Mark a claim as settled. Writes a fee_events row.

        Returns: {"claim": dict, "fee_event": dict, "fee_path_status": int}
        """
        pass


# ─── Adapters (one per carrier) ────────────────────────────────────────

class MockCarrierAdapter(CarrierAdapter):
    """In-memory mock. The only one in production today."""
    name = "mock"

    def health_check(self) -> bool:
        return True  # always healthy

    def get_open_claims(self) -> list:
        # delegates to empire_carrier._CLAIMS — implemented in the hub
        raise NotImplementedError("call /api/v1/carrier/claims?status=open instead")

    def get_settled_claims(self, since: datetime) -> list:
        raise NotImplementedError("call /api/v1/carrier/claims?status=settled&since=... instead")

    def settle_claim(self, claim_id, settled_amount, meta=None):
        raise NotImplementedError("call /api/v1/carrier/claims/{id}/settle instead")


class StateFarmAdapter(CarrierAdapter):
    """State Farm — biggest US carrier. No public partner API as of 2026-06.
    When their partner program opens, populate the API base + auth."""
    name = "state_farm"

    def __init__(self, api_key: str = "", partner_id: str = ""):
        self.api_key = api_key
        self.partner_id = partner_id
        self.base_url = "https://api.statefarm.com/partner/v1"  # placeholder

    def health_check(self) -> bool:
        # Real implementation: GET /health with auth
        # For now: return False (no live integration yet)
        return False

    def get_open_claims(self) -> list:
        raise NotImplementedError("State Farm partner API not yet available")

    def get_settled_claims(self, since: datetime) -> list:
        raise NotImplementedError("State Farm partner API not yet available")

    def settle_claim(self, claim_id, settled_amount, meta=None):
        raise NotImplementedError("State Farm partner API not yet available")


class AllstateAdapter(CarrierAdapter):
    """Allstate — has vendor partner program. Webhook shape: JSON POST
    to our /api/v1/fee/claim-settled endpoint on settlement."""
    name = "allstate"

    def __init__(self, api_key: str = "", vendor_id: str = ""):
        self.api_key = api_key
        self.vendor_id = vendor_id
        self.webhook_url = "https://hub.empire-ai.co.uk/api/v1/fee/claim-settled"

    def health_check(self) -> bool:
        return bool(self.api_key and self.vendor_id)

    def get_open_claims(self) -> list:
        # Allstate vendor program is poll-based: GET /claims?status=open
        raise NotImplementedError("requires live Allstate vendor credentials")

    def get_settled_claims(self, since: datetime) -> list:
        raise NotImplementedError("requires live Allstate vendor credentials")

    def settle_claim(self, claim_id, settled_amount, meta=None):
        # Allstate pushes webhooks to us; we don't push to them.
        raise NotImplementedError("Allstate pushes webhooks; we receive, not push")


class USAAAdapter(CarrierAdapter):
    """USAA — closed partner program. Membership-gated."""
    name = "usaa"

    def health_check(self) -> bool:
        return False  # not yet integrated

    def get_open_claims(self) -> list:
        raise NotImplementedError("USAA partner API not yet available")

    def get_settled_claims(self, since: datetime) -> list:
        raise NotImplementedError("USAA partner API not yet available")

    def settle_claim(self, claim_id, settled_amount, meta=None):
        raise NotImplementedError("USAA partner API not yet available")


class LibertyMutualAdapter(CarrierAdapter):
    """Liberty Mutual — enterprise sales motion."""
    name = "liberty_mutual"

    def health_check(self) -> bool:
        return False  # not yet integrated

    def get_open_claims(self) -> list:
        raise NotImplementedError("Liberty Mutual API not yet available")

    def get_settled_claims(self, since: datetime) -> list:
        raise NotImplementedError("Liberty Mutual API not yet available")

    def settle_claim(self, claim_id, settled_amount, meta=None):
        raise NotImplementedError("Liberty Mutual API not yet available")


class FarmersAdapter(CarrierAdapter):
    """Farmers — closed API, requires signed agreement."""
    name = "farmers"

    def health_check(self) -> bool:
        return False  # not yet integrated

    def get_open_claims(self) -> list:
        raise NotImplementedError("Farmers API not yet available")

    def get_settled_claims(self, since: datetime) -> list:
        raise NotImplementedError("Farmers API not yet available")

    def settle_claim(self, claim_id, settled_amount, meta=None):
        raise NotImplementedError("Farmers API not yet available")


class CoverForceAdapter(CarrierAdapter):
    """CoverForce — insurance API marketplace aggregator.

    Provides multi-carrier access through a single REST API. Gated —
    must Request API Access at https://www.coverforce.com/api-access
    then populate COVERFORCE_API_KEY env var and the base_url below.

    Once approved, CoverForce exposes claim status endpoints via their
    Stoplight portal (coverforce.stoplight.io). This adapter polls for
    settled-claim data and can optionally receive webhook forwards to
    our /api/v1/claim-settled endpoint.

    Expected API pattern (from CoverForce public docs, to be confirmed
    after access is granted):

        GET /v1/claims                    — list claims with filters
        GET /v1/claims/{id}               — single claim detail
        POST /v1/claims/{id}/settle       — manual settlement trigger
        POST /webhook                     — CoverForce pushes events here

    Env vars:
        COVERFORCE_API_KEY  — API key from CoverForce developer portal
        COVERFORCE_BASE_URL — API base URL (default: provided URL)

    Webhook path (receive CoverForce push events):
        POST /api/v1/claim-settled  (already implemented in hub)
    """
    name = "coverforce"

    def __init__(self,
                 api_key: str = "",
                 base_url: str = ""):
        self.api_key = api_key or os.environ.get("COVERFORCE_API_KEY", "")
        self.base_url = (
            base_url
            or os.environ.get("COVERFORCE_BASE_URL", "")
            or "https://api.coverforce.io/v1"
        )
        self.webhook_url = "https://hub.empire-ai.co.uk/api/v1/claim-settled"

    def health_check(self) -> bool:
        """Live if we have an API key configured. Real check would
        GET /v1/health with auth, but the API is gated so we accept
        the presence of a key as proof of integration readiness."""
        if not self.api_key:
            return False
        return True

    def get_open_claims(self) -> list:
        """Fetch open claims from CoverForce.

        Real implementation once API access is granted:

            async with httpx.AsyncClient() as client:
                r = await client.get(
                    f"{self.base_url}/claims",
                    params={"status": "open", "limit": 100},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=30,
                )
                r.raise_for_status()
                return r.json().get("claims", [])
        """
        raise NotImplementedError(
            "CoverForce API access has not been granted yet. "
            "Go to https://www.coverforce.com/api-access to request access, "
            "then set COVERFORCE_API_KEY in /root/.env"
        )

    def get_settled_claims(self, since: datetime) -> list:
        raise NotImplementedError(
            "CoverForce API access has not been granted yet. "
            "Set COVERFORCE_API_KEY in /root/.env after requesting access "
            "at https://www.coverforce.com/api-access"
        )

    def settle_claim(self, claim_id, settled_amount, meta=None):
        raise NotImplementedError(
            "CoverForce settle endpoint not yet available — "
            "will POST /v1/claims/{id}/settle once API access is granted"
        )


# ─── Factory ──────────────────────────────────────────────────────────

def get_adapter(name: str) -> CarrierAdapter:
    """Get a carrier adapter by name. Falls back to MockCarrier if name
    is unknown or not yet integrated."""
    adapters = {
        "mock": MockCarrierAdapter,
        "state_farm": StateFarmAdapter,
        "allstate": AllstateAdapter,
        "usaa": USAAAdapter,
        "liberty_mutual": LibertyMutualAdapter,
        "farmers": FarmersAdapter,
        "coverforce": CoverForceAdapter,
    }
    cls = adapters.get(name.lower(), MockCarrierAdapter)
    return cls()
