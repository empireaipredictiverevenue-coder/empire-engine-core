"""
Empire AI · Predictive Revenue Endpoint
========================================

Returns projected fee revenue per segment (metro, niche, sequence_type)
based on:
  - Active sequences in each segment
  - Historical reply rate
  - Average claim size (placeholder for now — see TODO)

Formula: projected_fees = active_sequences * reply_rate * avg_claim_size * 0.03

Where:
  - active_sequences: count of sms_sequences WHERE status='active' IN segment
  - reply_rate: replied / (replied + completed) for that segment over the
    last 30 days (or all-time if <10 replies)
  - avg_claim_size: per-segment average from fee_events; falls back to
    the all-time average if no per-segment data

The endpoint is read-only, no writes. Operator SPA renders this as
"Projected fees by segment" so they can see where to focus.
"""
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from fastapi import Depends, HTTPException
from supabase import create_client

FEE_PERCENT = 0.03
DEFAULT_AVG_CLAIM = 75_000  # USD; placeholders until we have real claim data
WINDOW_DAYS = 30


def register_predictive_routes(app, *, require_auth, get_db=None):
    def _db():
        if get_db is not None:
            return get_db()
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    @app.get("/api/v1/predictive/revenue")
    async def predictive_revenue(
        window_days: int = WINDOW_DAYS,
        auth: bool = Depends(require_auth),
    ):
        """Projected fees per segment (metro / niche / sequence_type).
        Three response sections: by_metro, by_niche, by_sequence_type.
        Plus a totals block.
        """
        try:
            db = _db()
            now = datetime.now(timezone.utc)
            cutoff = (now - timedelta(days=window_days)).isoformat()

            # active_sequences keyed by (sequence_type, metro, niche)
            # We need to read the meta JSONB to extract metro + niche.
            active = (db.table("sms_sequences")
                        .select("sequence_type, status, meta")
                        .eq("status", "active")
                        .limit(20000)
                        .execute())
            active_rows = active.data or []

            # historical reply rate per sequence_type, last N days
            hist = (db.table("sms_sequences")
                      .select("sequence_type, status, created_at")
                      .gte("created_at", cutoff)
                      .limit(20000)
                      .execute())
            hist_rows = hist.data or []

            # per-segment reply rate
            seq_total = defaultdict(int)
            seq_replied = defaultdict(int)
            for r in hist_rows:
                k = r.get("sequence_type") or "?"
                st = r.get("status") or "?"
                if st in ("replied", "completed", "opted_out", "failed"):
                    seq_total[k] += 1
                if st == "replied":
                    seq_replied[k] += 1
            seq_reply_rate = {}
            for k, total in seq_total.items():
                rate = seq_replied[k] / total if total > 0 else 0
                seq_reply_rate[k] = round(rate, 4)

            # per-segment active counts
            by_metro = defaultdict(int)
            by_niche = defaultdict(int)
            by_seq = defaultdict(int)
            for r in active_rows:
                seq = r.get("sequence_type") or "?"
                meta = r.get("meta") or {}
                m = meta.get("metro") or "?"
                n = meta.get("niche") or "?"
                by_seq[seq] += 1
                by_metro[m] += 1
                by_niche[n] += 1

            # average claim amount from fee_events (all-time)
            fees = (db.table("fee_events")
                      .select("claim_amount")
                      .limit(1000)
                      .execute())
            fees_rows = fees.data or []
            avg_claim = DEFAULT_AVG_CLAIM
            if fees_rows:
                amounts = [float(r.get("claim_amount") or 0) for r in fees_rows if r.get("claim_amount")]
                if amounts:
                    avg_claim = round(sum(amounts) / len(amounts))

            def project(n_active, rate):
                return round(n_active * rate * avg_claim * FEE_PERCENT, 2)

            # per-segment projected fees
            by_metro_out = []
            for m, n_active in sorted(by_metro.items(), key=lambda x: -x[1])[:15]:
                # use the metro's most-common sequence reply rate
                rate = 0.0
                rates = []
                for r in active_rows:
                    meta = r.get("meta") or {}
                    if meta.get("metro") == m:
                        seq = r.get("sequence_type") or "?"
                        rates.append(seq_reply_rate.get(seq, 0))
                if rates:
                    rate = sum(rates) / len(rates)
                by_metro_out.append({
                    "metro": m,
                    "active_sequences": n_active,
                    "reply_rate_pct": round(rate * 100, 1),
                    "projected_fees_usd": project(n_active, rate),
                })
            by_niche_out = []
            for n_, n_active in sorted(by_niche.items(), key=lambda x: -x[1])[:10]:
                rate = 0.0
                rates = []
                for r in active_rows:
                    meta = r.get("meta") or {}
                    if meta.get("niche") == n_:
                        seq = r.get("sequence_type") or "?"
                        rates.append(seq_reply_rate.get(seq, 0))
                if rates:
                    rate = sum(rates) / len(rates)
                by_niche_out.append({
                    "niche": n_,
                    "active_sequences": n_active,
                    "reply_rate_pct": round(rate * 100, 1),
                    "projected_fees_usd": project(n_active, rate),
                })
            by_seq_out = []
            for s, n_active in sorted(by_seq.items(), key=lambda x: -x[1]):
                rate = seq_reply_rate.get(s, 0)
                by_seq_out.append({
                    "sequence_type": s,
                    "active_sequences": n_active,
                    "reply_rate_pct": round(rate * 100, 1),
                    "projected_fees_usd": project(n_active, rate),
                })
            # totals
            total_active = sum(by_seq.values())
            avg_rate = 0.0
            if seq_total:
                total_replies = sum(seq_replied.values())
                total_terminal = sum(seq_total.values())
                if total_terminal > 0:
                    avg_rate = total_replies / total_terminal
            total_projected = project(total_active, avg_rate)
            return {
                "window_days": window_days,
                "avg_claim_usd": avg_claim,
                "fee_percent": FEE_PERCENT,
                "total_active_sequences": total_active,
                "blended_reply_rate_pct": round(avg_rate * 100, 1),
                "total_projected_fees_usd": total_projected,
                "by_sequence_type": by_seq_out,
                "by_metro": by_metro_out,
                "by_niche": by_niche_out,
                "generated_at": now.isoformat(),
            }
        except Exception as e:
            raise HTTPException(500, str(e))
