"""
EMPIRE V49 · BRAIN LEARNING (Threshold Auto-Tuning)
=====================================================
Nightly job. Reads outcomes from the last 90 days. Computes optimal
thresholds per metro/severity/asset-band. Writes new config that the
brain reads at runtime.

THE PROBLEM IT SOLVES
─────────────────────
Today, BRAIN_MIN_URGENCY = 7 is a hardcoded constant. But:
  - Maybe in Dallas, urgency-7 leads settle 30% of the time (good)
  - Maybe in Houston, urgency-7 leads settle 8% of the time (bad ROI)
  - Maybe high-asset Mobile hail leads settle even at urgency-5

This module computes those answers from real data and writes them to
brain_config. Brain reads from brain_config at runtime instead of hardcoded.


HOW IT WORKS
────────────
Nightly:
  1. Pull all brain_memory rows with outcomes from last 90 days
  2. Group by (city, severity, asset_band, urgency_band)
  3. For each bucket, compute:
       - n: count of leads
       - win_rate: settled / total
       - avg_fee: average settled fee
       - expected_value: win_rate × avg_fee
  4. For each (city, severity, asset_band), find the urgency floor where
     expected_value drops below a minimum threshold ($500 default)
  5. Write per-bucket urgency floors to brain_config
  6. Brain at runtime: looks up its floor for THIS lead's bucket


SCHEMA
──────
    CREATE TABLE IF NOT EXISTS brain_config (
      id              uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      created_at      timestamptz NOT NULL DEFAULT now(),
      updated_at      timestamptz NOT NULL DEFAULT now(),
      city            text NOT NULL,
      severity        text NOT NULL,
      asset_band      text NOT NULL,
      urgency_floor   int NOT NULL,
      sample_size     int NOT NULL,
      win_rate        numeric(5,4),
      avg_fee         numeric(12,2),
      expected_value  numeric(12,2),
      updated_by      text DEFAULT 'auto_tuner',
      UNIQUE (city, severity, asset_band)
    );


WIRE-UP IN hub.py
─────────────────
    from empire_brain_learning import BrainLearning

    brain_learning = BrainLearning(get_db=get_db)

    # In startup, kick the nightly task:
    asyncio.create_task(brain_learning.nightly_tune_loop())

    # In the brain decision path, look up the current floor:
    floor = await brain_learning.get_urgency_floor(
        city=p["city"],
        severity=severity,
        asset_value=asset_val_num,
    )
    # ... then use `floor` instead of the hardcoded BRAIN_MIN_URGENCY
"""

import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Callable, Optional


log = logging.getLogger("empire.brain.learning")


# Asset bands match brain_memory._build_context_text
ASSET_BANDS = [
    ("unknown",       0,        500_000),
    ("sub-500K",      0,        500_000),
    ("mid-six-fig",   500_000,  1_000_000),
    ("low-million",   1_000_000, 5_000_000),
    ("mid-million",   5_000_000, 25_000_000),
    ("large-asset",   25_000_000, None),
]

# Defaults if a bucket has no data
DEFAULT_URGENCY_FLOOR = 7
MIN_EXPECTED_VALUE_USD = 500   # below this, brain says NO_GO regardless of urgency
MIN_SAMPLES_FOR_TUNING = 10    # need this many outcomes before we tune a bucket


def asset_to_band(asset_value: float) -> str:
    """Convert raw asset value to a band name."""
    if asset_value <= 0:
        return "unknown"
    if asset_value < 500_000:
        return "sub-500K"
    if asset_value < 1_000_000:
        return "mid-six-fig"
    if asset_value < 5_000_000:
        return "low-million"
    if asset_value < 25_000_000:
        return "mid-million"
    return "large-asset"


class BrainLearning:
    def __init__(self, *, get_db: Callable):
        self.get_db = get_db
        self.stats = {
            "tune_runs":         0,
            "buckets_tuned":     0,
            "last_tune_at":      None,
            "last_error":        None,
        }
        # In-memory cache of brain_config so we don't hit the DB on every brain call
        self._cache: dict[tuple[str, str, str], dict] = {}
        self._cache_at: Optional[datetime] = None
        self._cache_ttl = timedelta(minutes=15)

    # ── PUBLIC: GET URGENCY FLOOR FOR A LEAD ────────────────────────────
    async def get_urgency_floor(
        self,
        *,
        city: str,
        severity: str,
        asset_value: float,
    ) -> int:
        """
        Look up the tuned urgency floor for this bucket. If no tuned value
        exists, returns DEFAULT_URGENCY_FLOOR.
        """
        band = asset_to_band(asset_value)
        await self._maybe_refresh_cache()
        cfg = self._cache.get((city, severity, band))
        if cfg:
            return int(cfg.get("urgency_floor", DEFAULT_URGENCY_FLOOR))
        return DEFAULT_URGENCY_FLOOR

    # ── PUBLIC: TUNE NOW (callable on-demand from operator dashboard) ───
    async def tune_now(self, lookback_days: int = 90) -> dict:
        """Run the tuning logic once. Returns a summary."""
        try:
            db = self.get_db()
        except Exception as e:
            return {"ok": False, "error": str(e)}

        since = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).isoformat()

        try:
            res = db.table("brain_memory").select(
                "city, severity, asset_value, urgency, outcome, actual_fee"
            ) \
                .not_.is_("outcome", "null") \
                .neq("outcome", "pending") \
                .gte("created_at", since) \
                .execute()
            rows = res.data or []
        except Exception as e:
            log.error(f"[brain.learning] memory query failed: {e}")
            return {"ok": False, "error": str(e)}

        if len(rows) < MIN_SAMPLES_FOR_TUNING:
            return {
                "ok":      True,
                "tuned":   0,
                "skipped": "insufficient_data",
                "rows":    len(rows),
            }

        # Group by (city, severity, asset_band)
        buckets: dict[tuple[str, str, str], list[dict]] = {}
        for row in rows:
            city = row.get("city") or "Unknown"
            severity = row.get("severity") or "unknown"
            band = asset_to_band(float(row.get("asset_value") or 0))
            buckets.setdefault((city, severity, band), []).append(row)

        # For each bucket, find the optimal urgency floor
        tuned_count = 0
        for (city, severity, band), bucket_rows in buckets.items():
            if len(bucket_rows) < MIN_SAMPLES_FOR_TUNING:
                continue

            # Sweep urgency floors from 1 to 10
            best = None
            for floor in range(1, 11):
                qualifying = [r for r in bucket_rows if (r.get("urgency") or 0) >= floor]
                if len(qualifying) < 3:
                    continue
                settled = [r for r in qualifying if r.get("outcome") == "settled"]
                win_rate = len(settled) / len(qualifying)
                avg_fee = (sum(float(r.get("actual_fee") or 0) for r in settled) / len(settled)) if settled else 0
                expected_value = win_rate * avg_fee

                if expected_value >= MIN_EXPECTED_VALUE_USD:
                    candidate = {
                        "urgency_floor":  floor,
                        "sample_size":    len(qualifying),
                        "win_rate":       round(win_rate, 4),
                        "avg_fee":        round(avg_fee, 2),
                        "expected_value": round(expected_value, 2),
                    }
                    # We want the LOWEST floor where EV stays above the minimum
                    if best is None:
                        best = candidate
                    # Don't break — record but keep checking higher floors
                    # If a higher floor has noticeably better win_rate
                    # at non-trivial volume, prefer it
                    elif (candidate["win_rate"] > best["win_rate"] * 1.3
                          and candidate["sample_size"] >= 5):
                        best = candidate

            if best:
                # Upsert into brain_config
                try:
                    db.table("brain_config").upsert({
                        "city":           city,
                        "severity":       severity,
                        "asset_band":     band,
                        "urgency_floor":  best["urgency_floor"],
                        "sample_size":    best["sample_size"],
                        "win_rate":       best["win_rate"],
                        "avg_fee":        best["avg_fee"],
                        "expected_value": best["expected_value"],
                        "updated_at":     datetime.now(timezone.utc).isoformat(),
                    }, on_conflict="city,severity,asset_band").execute()
                    tuned_count += 1
                except Exception as e:
                    log.error(f"[brain.learning] upsert failed for {city}/{severity}/{band}: {e}")

        self.stats["tune_runs"]      += 1
        self.stats["buckets_tuned"]   = tuned_count
        self.stats["last_tune_at"]    = datetime.now(timezone.utc).isoformat()

        # Invalidate the cache so next get_urgency_floor() rebuilds it
        self._cache.clear()
        self._cache_at = None

        log.info(f"[brain.learning] tune complete · {tuned_count} buckets updated · {len(rows)} outcomes analyzed")
        return {
            "ok":        True,
            "tuned":     tuned_count,
            "buckets":   len(buckets),
            "rows":      len(rows),
        }

    # ── BACKGROUND TASK: NIGHTLY TUNE LOOP ──────────────────────────────
    async def nightly_tune_loop(self):
        """Forever loop. Tunes once per night (24h tick)."""
        log.info("[brain.learning] Nightly tuner ONLINE · 24h tick")
        while True:
            try:
                await self.tune_now(lookback_days=90)
            except Exception as e:
                log.error(f"[brain.learning] tune cycle error: {e}")
                self.stats["last_error"] = str(e)
            await asyncio.sleep(24 * 3600)  # 24 hours

    # ── INTERNAL: CACHE REFRESH ──────────────────────────────────────────
    async def _maybe_refresh_cache(self):
        now = datetime.now(timezone.utc)
        if self._cache_at and (now - self._cache_at) < self._cache_ttl:
            return
        try:
            db = self.get_db()
            res = db.table("brain_config").select("*").execute()
            self._cache = {}
            for row in (res.data or []):
                key = (row["city"], row["severity"], row["asset_band"])
                self._cache[key] = row
            self._cache_at = now
        except Exception as e:
            log.debug(f"[brain.learning] cache refresh failed: {e}")
