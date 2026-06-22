"""FEE SYSTEM GENOME — Empire AI (Unstoppable)"""
import os
import logging

from dotenv import load_dotenv
from supabase import create_client
from empire_product_core import EmpireProductCore

load_dotenv("/root/.env")

log = logging.getLogger("fee_system")

_sb = None

def _get_db():
    global _sb
    if _sb is None:
        _sb = create_client(
            os.environ.get("SUPABASE_URL", ""),
            os.environ.get("SUPABASE_SERVICE_KEY", ""),
        )
    return _sb

class FeeSystemGenome(EmpireProductGenome):
    def __init__(self):
        super().__init__("fee_system")

    def _product_specific_data(self):
        """Fetch real pending fee_events from Supabase instead of hardcoded test data."""
        try:
            sb = _get_db()
            r = sb.table("fee_events") \
                .select("id,claim_id,claim_amount,fee_amount,contractor_id,status") \
                .eq("status", "pending") \
                .order("created_at", desc=True) \
                .limit(100) \
                .execute()
            rows = r.data or []
            log.info(f"[fee_system] Loaded {len(rows)} pending fee_events")
            return [
                {
                    "claim_id": row.get("claim_id", ""),
                    "amount": float(row.get("claim_amount") or 0),
                    "fee": float(row.get("fee_amount") or 0),
                    "fee_event_id": row.get("id"),
                    "contractor_id": row.get("contractor_id"),
                }
                for row in rows
            ]
        except Exception as e:
            log.warning(f"[fee_system] Failed to load fee_events: {e}")
            return []

    def _product_specific_scoring(self, item):
        return 95

    def _product_specific_action(self, item):
        fee = item.get("fee", 0)
        claim = item.get("amount", 0)
        log.info(f"[fee] Claim={item.get('claim_id')} amount=${claim:,.0f} fee=${fee:,.0f}")
        self._predictive_integration(item)
