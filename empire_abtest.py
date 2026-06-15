"""
Empire AI · A/B Test Results Endpoint
======================================

Returns the current A/B cohort reply-rate comparison between
storm_strike (new short copy) and storm_strike_v2 (longer scarcity copy).
"""
import os
from datetime import datetime, timezone, timedelta
from fastapi import Depends, HTTPException

from supabase import create_client


def register_ab_test_routes(app, *, require_auth, get_db=None):
    def _db():
        if get_db is not None:
            return get_db()
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    @app.get("/api/v1/ab-test/results")
    async def ab_test_results(
        cohort_a: str = "storm_strike",
        cohort_b: str = "storm_strike_v2",
        days: int = 7,
        auth: bool = Depends(require_auth),
    ):
        """Compare reply-rate between two sequence_types (cohorts) over N days.

        Returns: {
            "cohort_a": {"name", "sent", "terminal", "replied", "completed", "active", "reply_rate_pct"},
            "cohort_b": {...},
            "winner": "a" | "b" | "tie" | "no_data",
            "uplift_pct": float | None,
            "n_replies": int,
        }
        """
        try:
            db = _db()
            cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
            result = {}
            for label, seq in [("a", cohort_a), ("b", cohort_b)]:
                r = db.table("sms_sequences").select("status,created_at").eq("sequence_type", seq).gte("created_at", cutoff).execute()
                rows = r.data or []
                replied = sum(1 for x in rows if x.get("status") == "replied")
                completed = sum(1 for x in rows if x.get("status") == "completed")
                opted_out = sum(1 for x in rows if x.get("status") == "opted_out")
                failed = sum(1 for x in rows if x.get("status") == "failed")
                active = sum(1 for x in rows if x.get("status") == "active")
                terminal = replied + completed + opted_out + failed
                rate = round((replied / terminal * 100), 2) if terminal > 0 else None
                result[f"cohort_{label}"] = {
                    "name": seq,
                    "sent": len(rows),
                    "terminal": terminal,
                    "replied": replied,
                    "completed": completed,
                    "active": active,
                    "opted_out": opted_out,
                    "failed": failed,
                    "reply_rate_pct": rate,
                }
            a = result["cohort_a"]
            b = result["cohort_b"]
            if a["reply_rate_pct"] is None and b["reply_rate_pct"] is None:
                winner = "no_data"
            elif a["reply_rate_pct"] is None:
                winner = "b"
            elif b["reply_rate_pct"] is None:
                winner = "a"
            elif abs(a["reply_rate_pct"] - b["reply_rate_pct"]) < 1.0:
                winner = "tie"
            elif a["reply_rate_pct"] > b["reply_rate_pct"]:
                winner = "a"
            else:
                winner = "b"
            uplift = None
            if a["reply_rate_pct"] is not None and b["reply_rate_pct"] is not None and b["reply_rate_pct"] > 0:
                uplift = round((a["reply_rate_pct"] - b["reply_rate_pct"]) / b["reply_rate_pct"] * 100, 1)
            n_replies = (a["replied"] or 0) + (b["replied"] or 0)
            return {
                **result,
                "winner": winner,
                "uplift_pct": uplift,
                "n_replies": n_replies,
                "window_days": days,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            raise HTTPException(500, str(e))
