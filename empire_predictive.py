"""
Empire AI · Predictive Revenue Endpoint
========================================

Returns projected fee revenue per segment (metro, niche, sequence_type)
based on:
  - Active sequences in each segment
  - Organic reply rate (ground truth from outreach_log, NOT seed data)
  - Average claim size from fee_events (all-time)

Formula: projected_fees = active_sequences * reply_rate * avg_claim_size * 0.03

GROUND-TRUTH REPLY RATE:
  The previous version of this endpoint computed reply_rate from
  sms_sequences.status = 'replied'. That field is set by the dispatcher
  when a sequence is logically marked complete; it captures whether
  the SEQUENCE was processed, NOT whether the recipient replied.

  The real signal is outreach_log.response_received_at IS NOT NULL.
  We now query that. As of 2026-06-17:
    - 1000 SMS sent in last 30d
    - 1 organic reply (a seed "Hello, I would like to learn more")
    - real reply rate ≈ 0.1%, not the 25.5% the previous version showed

  When organic replies are sparse (<10 in window), the projection is
  flagged low_confidence=True and the endpoint surfaces that to the
  caller. The SPA should render low-confidence projections as
  "pending signal" rather than as a dollar figure.

WHY THIS MATTERS:
  Last session projected $636K in fees. That number was anchored to
  seed-data reply rates (11 historical seed "replied" sequences
  across 41 "completed" sequences → 25.5%). Operators looking at the
  SPA could plan around a number that wasn't real. This fix means
  projections start at ~$0 and grow as organic replies accumulate.
  That's correct — projection = forward-looking estimate, and a
  forward-looking estimate with zero data should be $0, not $636K.

The endpoint is read-only, no writes. Operator SPA renders this as
"Projected fees by segment" so they can see where to focus.
"""
import os
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from fastapi import Depends, HTTPException
from supabase import create_client

FEE_PERCENT = 0.03
DEFAULT_AVG_CLAIM = 75_000  # USD; placeholder until we have real claim data
WINDOW_DAYS = 30
MIN_ORGANIC_REPLIES_FOR_CONFIDENCE = 10


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

        Reply rate is computed from outreach_log.response_received_at
        (organic replies only). When total organic replies in the
        window are below MIN_ORGANIC_REPLIES_FOR_CONFIDENCE, the
        response includes low_confidence=True and the projection is
        intentionally zeroed out (caller should treat as "pending
        signal" rather than a dollar figure).
        """
        try:
            db = _db()
            now = datetime.now(timezone.utc)
            cutoff = (now - timedelta(days=window_days)).isoformat()

            # ── 1. Active sequences keyed by (sequence_type, metro, niche) ──
            active = (db.table("sms_sequences")
                        .select("sequence_type, status, meta")
                        .eq("status", "active")
                        .limit(20000)
                        .execute())
            active_rows = active.data or []

            # ── 2. Ground-truth organic reply rate from outreach_log ──
            #    (was: sms_sequences.status = 'replied' — that's seed data)
            outreach = (db.table("outreach_log")
                          .select("sequence, response_received_at, sent_at")
                          .gte("created_at", cutoff)
                          .not_.is_("sent_at", "null")
                          .limit(20000)
                          .execute())
            outreach_rows = outreach.data or []

            seq_sent = defaultdict(int)
            seq_replied = defaultdict(int)
            for r in outreach_rows:
                seq = r.get("sequence") or "?"
                seq_sent[seq] += 1
                if r.get("response_received_at"):
                    seq_replied[seq] += 1

            seq_reply_rate = {}
            for k, total in seq_sent.items():
                if total > 0:
                    seq_reply_rate[k] = round(seq_replied[k] / total, 4)

            total_organic_sent = sum(seq_sent.values())
            total_organic_replied = sum(seq_replied.values())
            low_confidence = total_organic_replied < MIN_ORGANIC_REPLIES_FOR_CONFIDENCE

            # When low-confidence, zero out the per-sequence rates so the
            # projection reflects "we don't know yet" rather than a number
            # built on too few data points. The raw rate is still surfaced
            # so the operator can see signal building up.
            projection_rate = {k: 0.0 for k in seq_reply_rate} if low_confidence else seq_reply_rate

            # ── 3. Per-segment active counts ──
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

            # ── 4. Average claim amount from fee_events (all-time) ──
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

            # ── 5. Per-segment projected fees ──
            by_metro_out = []
            for m, n_active in sorted(by_metro.items(), key=lambda x: -x[1])[:15]:
                rates = []
                for r in active_rows:
                    meta = r.get("meta") or {}
                    if meta.get("metro") == m:
                        seq = r.get("sequence_type") or "?"
                        # Use the HONEST projection rate (zeroed if low-confidence)
                        rates.append(projection_rate.get(seq, 0))
                rate = (sum(rates) / len(rates)) if rates else 0.0
                by_metro_out.append({
                    "metro": m,
                    "active_sequences": n_active,
                    "reply_rate_pct": round(rate * 100, 1),
                    "projected_fees_usd": project(n_active, rate),
                })
            by_niche_out = []
            for n_, n_active in sorted(by_niche.items(), key=lambda x: -x[1])[:10]:
                rates = []
                for r in active_rows:
                    meta = r.get("meta") or {}
                    if meta.get("niche") == n_:
                        seq = r.get("sequence_type") or "?"
                        rates.append(projection_rate.get(seq, 0))
                rate = (sum(rates) / len(rates)) if rates else 0.0
                by_niche_out.append({
                    "niche": n_,
                    "active_sequences": n_active,
                    "reply_rate_pct": round(rate * 100, 1),
                    "projected_fees_usd": project(n_active, rate),
                })
            by_seq_out = []
            for s, n_active in sorted(by_seq.items(), key=lambda x: -x[1]):
                # Surface BOTH the honest (zeroed) projection rate AND the raw
                # rate so operators can see signal building up.
                raw_rate = seq_reply_rate.get(s, 0)
                proj_rate = projection_rate.get(s, 0)
                by_seq_out.append({
                    "sequence_type": s,
                    "active_sequences": n_active,
                    "sent_in_window": seq_sent.get(s, 0),
                    "replied_in_window": seq_replied.get(s, 0),
                    "reply_rate_pct": round(raw_rate * 100, 1),
                    "projected_fees_usd": project(n_active, proj_rate),
                })

            # Totals — use the raw rate for the "blended_reply_rate_pct"
            # display (so operators see what we're measuring), but the
            # projection in dollars is zeroed if low-confidence.
            if total_organic_sent > 0:
                avg_rate = total_organic_replied / total_organic_sent
            else:
                avg_rate = 0.0
            proj_total_rate = 0.0 if low_confidence else avg_rate
            total_projected = project(sum(by_seq.values()), proj_total_rate)

            return {
                "window_days": window_days,
                "avg_claim_usd": avg_claim,
                "fee_percent": FEE_PERCENT,
                "total_active_sequences": sum(by_seq.values()),
                "total_sent_in_window": total_organic_sent,
                "total_replied_in_window": total_organic_replied,
                "blended_reply_rate_pct": round(avg_rate * 100, 2),
                "total_projected_fees_usd": total_projected,
                "low_confidence": low_confidence,
                "low_confidence_reason": (
                    f"Only {total_organic_replied} organic reply in {window_days}d; "
                    f"need ≥{MIN_ORGANIC_REPLIES_FOR_CONFIDENCE} for a meaningful projection. "
                    f"Projections zeroed out until signal accumulates."
                    if low_confidence else None
                ),
                "by_sequence_type": by_seq_out,
                "by_metro": by_metro_out,
                "by_niche": by_niche_out,
                "generated_at": now.isoformat(),
                "_data_source_note": (
                    "Reply rate computed from outreach_log.response_received_at "
                    "(organic ground truth), NOT sms_sequences.status "
                    "(which captured dispatcher-side sequence completion and "
                    "was dominated by seed data)."
                ),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"predictive_revenue_error: {e}")
