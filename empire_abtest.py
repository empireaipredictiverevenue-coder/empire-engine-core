"""
Empire AI · A/B Test Results Endpoint
======================================

Returns the current A/B cohort reply-rate comparison between
storm_strike (new short copy) and storm_strike_v2 (longer scarcity copy).
Also provides a variant-trend endpoint for dispatch SMS A/B test variants
(A, B, C) — conversion rate over time per variant.
"""
import os
import re
import logging
from datetime import datetime, timezone, timedelta
from collections import defaultdict
from fastapi import Depends, HTTPException, Query

from supabase import create_client

log = logging.getLogger("empire.abtest")


def register_ab_test_routes(app, *, require_auth, get_db=None):
    def _db():
        if get_db is not None:
            return get_db()
        return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    @app.get("/api/v1/ab-test/variant-trend")
    async def ab_test_variant_trend(
        days: int = Query(30, ge=7, le=90),
        auth: bool = Depends(require_auth),
    ):
        """Return daily conversion rate per SMS variant (A, B, C) from dispatch SMS.

        Queries sms_log for outbound dispatch SMS with sms_variant set, then
        matches each phone to subsequent inbound YES replies. Groups by date
        and variant to produce a time-series trend.

        Returns:
          - series: [{date, sent_a, replied_a, rate_a, sent_b, replied_b, rate_b, ...}]
          - variants: list of variant labels found
          - totals: {variant: {sent, replied, rate}}
        """
        db = _db()
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        try:
            # 1. Fetch outbound dispatch SMS with sms_variant set
            out_r = db.table("sms_log").select(
                "phone, sms_variant, created_at"
            ).eq("direction", "outbound").gte("created_at", cutoff).not_.is_("sms_variant", "null").limit(2000).execute()
            outbound = out_r.data or []

            if not outbound:
                return {"series": [], "variants": [], "totals": {}, "days": days}

            # 2. Collect unique phones that received variant SMS
            variant_phones: dict[str, set] = defaultdict(set)
            # Bucket by date + variant
            daily_sent: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
            daily_phones: dict[str, dict[str, set]] = defaultdict(lambda: defaultdict(set))

            for row in outbound:
                v = (row.get("sms_variant") or "").strip().upper()
                if v not in ("A", "B", "C"):
                    continue
                phone = (row.get("phone") or "").strip()
                if not phone:
                    continue
                created = row.get("created_at") or ""
                day = str(created)[:10] if created else ""
                if not day:
                    continue

                variant_phones[v].add(phone)
                daily_sent[day][v] += 1
                daily_phones[day][v].add(phone)

            # 3. Fetch inbound YES replies from those variant phones
            all_variant_phones = set()
            for phones in variant_phones.values():
                all_variant_phones.update(phones)

            if not all_variant_phones:
                return {"series": [], "variants": ["A", "B", "C"], "totals": {}, "days": days}

            # Fetch inbound SMS from variant phones (in the same date window)
            # PostgREST can't do IN with 1000+ phones, so we batch
            phone_list = list(all_variant_phones)
            batch_size = 500
            all_inbound = []
            for i in range(0, len(phone_list), batch_size):
                batch = phone_list[i:i + batch_size]
                try:
                    in_r = db.table("sms_log").select(
                        "phone, body, created_at"
                    ).eq("direction", "inbound").in_("phone", batch).gte("created_at", cutoff).limit(2000).execute()
                    all_inbound.extend(in_r.data or [])
                except Exception as e:
                    log.debug(f"[variant-trend] batch inbound query failed: {e}")

            # 4. Classify inbound as YES replies
            # Match against known YES patterns
            _yes_pattern = re.compile(r"\b(YES|YEAH|SURE|SEND|GO AHEAD)\b", re.IGNORECASE)
            _no_pattern = re.compile(r"\b(NO|STOP|UNSUBSCRIBE|CANCEL|DON'T|NOT)\b", re.IGNORECASE)

            # phone → list of (created_at, is_yes) — inbound replies
            # We want earliest YES reply after the outbound SMS
            inbound_by_phone: dict[str, list[tuple[str, bool]]] = defaultdict(list)
            for row in all_inbound:
                phone = (row.get("phone") or "").strip()
                body = (row.get("body") or "").strip()
                created = row.get("created_at") or ""
                if not phone or not body or not created:
                    continue
                # Explicit NO/STOP overrides YES pattern
                if _no_pattern.search(body):
                    inbound_by_phone[phone].append((created, False))
                elif _yes_pattern.search(body):
                    inbound_by_phone[phone].append((created, True))

            # 5. For each day+variant, count how many phones converted (replied YES)
            # A phone converts if they replied YES on or after the outbound dispatch date
            daily_replied: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

            for day, var_phones in daily_phones.items():
                for v, phones in var_phones.items():
                    converted = 0
                    for phone in phones:
                        replies = inbound_by_phone.get(phone, [])
                        # Find first YES reply on or after this day
                        for reply_date, is_yes in replies:
                            if is_yes and str(reply_date)[:10] >= day:
                                converted += 1
                                break
                    daily_replied[day][v] = converted

            # 6. Build response
            all_dates = sorted(set(daily_sent.keys()) | set(daily_replied.keys()))
            variants_found = sorted(set(v for vs in daily_sent.values() for v in vs))

            # Totals
            totals: dict[str, dict] = {}
            for v in variants_found:
                total_sent = sum(daily_sent[d].get(v, 0) for d in all_dates)
                total_replied = sum(daily_replied[d].get(v, 0) for d in all_dates)
                totals[v] = {
                    "sent": total_sent,
                    "replied": total_replied,
                    "rate": round((total_replied / total_sent * 100), 1) if total_sent > 0 else 0,
                }

            series = []
            for date in all_dates:
                entry = {"date": date}
                for v in variants_found:
                    sent = daily_sent[date].get(v, 0)
                    replied = daily_replied[date].get(v, 0)
                    entry[f"sent_{v}"] = sent
                    entry[f"replied_{v}"] = replied
                    entry[f"rate_{v}"] = round((replied / sent * 100), 1) if sent > 0 else None
                series.append(entry)

            return {
                "series": series,
                "variants": variants_found,
                "totals": totals,
                "days": days,
                "window_days": days,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }

        except Exception as e:
            log.error(f"[variant-trend] query failed: {e}")
            raise HTTPException(500, str(e))

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
