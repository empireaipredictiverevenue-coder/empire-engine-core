# forecaster.md — the predictive revenue engine

## What it is

`bots/predictive_revenue.py` is the 1168-line master revenue
forecaster. It answers: "given everything we know about the
funnel, the lanes, the buyers, and the close rates, what is
the projected revenue over the next 24h / 30d / 60d?" Output
goes to the operator SPA at `/command#forecaster` and to the
forecast product API (3 tiers: LITE $199, PRO $499,
ENTERPRISE $999).

## Data flow

```
Supabase tables
  → per_niche aggregation
  → lane mapping (32 lanes → 13 niches)
  → LLM narrative (Ollama llama3.2:3b, JSON output)
  → comprehensive_forecast()
  → SPA dashboard
```

## Inputs the predictor actually uses (post-2026-06-15 audit)

| table | rows | used for | data quality |
|---|---|---|---|
| `radar_targets` | 2141 | `pipeline_forecast()` | 99.8% null on `damage_severity` and `urgency_score` — predictor falls back to meta data |
| `call_logs` | 0 | `per_lane_forecast()` (per-lane call metrics) | empty; per-lane revenue is zero |
| `buyers` | 8 | `per_lane_forecast()` (per-lane buyer/retainer/payout) | OK |
| `payout_log` | 0 | MRR projection | empty; "niche" column doesn't exist; bug |
| `pipeline_health` | 94 | 7-day trend | OK, avg fee $104.65 |
| `brain_memory` | 40 | `get_close_rate()` fallback | 100% null on outcome (was unreliable, now backed up by sms_log) |
| **`sms_log`** | 1525 | **`get_close_rate()` primary** (commit 01a90c2) | **the new calibration source** |

## Inputs the predictor ignores (the audit gaps)

| table | rows | unused signal |
|---|---|---|
| `agent_activity` | 450 | which agents move the funnel |
| `dispatches` | 2 | leading indicator of revenue (60-day cycle) |
| `enriched_leads` | 201 | quality signal (phone validity, address) |
| `contractors` | 31 | network size + activity |
| `storm_forecasts` | 1 | upstream storm signal |
| `qc_events` | 1 | quality of work (tier-2 pings) |

These are wired-in-only-when-not-empty candidates. Wiring them
in today would just compute zeros. The audit script
(`scripts/audit_predictor.py`) tracks when each becomes
non-empty.

## Functions (8)

- `get_close_rate()` — probability a contacted lead becomes a
  settled-claim fee. **Source priority: sms_log → AGI
  calibration → brain_memory → 0.15 default.** Capped 0.05-0.6.
- `base_for(keyword)` — TCV estimate from damage keyword.
  Hard-coded BASE_VALUE table ($9k storm, $25k solar, $4k
  repair, $6k default). Should be calibrated from real
  settled-claim data once we have any.
- `score_lead(lead, close_rate)` — TCV × close_rate ×
  intent_norm × 0.03.
- `pipeline_forecast()` — daily sum across radar_targets.
  Writes to `pipeline_health` table.
- `get_lane_metrics()` — 32-lane × niche breakdown from
  call_logs/buyers/payout_log. Cached 30s.
- `per_lane_forecast()` — calls get_lane_metrics, sorts, adds
  health segment counts.
- `revenue_health_check()` — compares current 24h to 7d
  average, fires alerts.
- `lane_revenue_score(lane_id)` — 0-10 score for AGI Lane
  Engine prioritization.
- `generate_llm_narrative()` — feeds per_lane data to
  Ollama llama3.2:3b, returns CRO-style JSON.
- `comprehensive_forecast()` — master orchestrator; returns
  pipeline + per_lane + health + narrative + **sms_log_signal**
  + **calibration_diagnostics**.

## Calibration state (the truth about the forecast)

The predictor used to claim a 0.15 close rate. **Real reply
rate (per sms_log, 7-day window, 35 distinct phones): 0.0286.**
Capped at the 0.05 floor to prevent the model from collapsing.
**Net: the predictor was over-forecasting revenue by 3x.** The
audit + the fix (commit 01a90c2) closed this gap.

## How to invoke

```python
from bots.predictive_revenue import (
    get_close_rate,
    get_sms_log_signal,
    comprehensive_forecast,
)
print(get_close_rate())           # 0.05 (or higher, as real data grows)
print(get_sms_log_signal())       # {global_reply_rate, samples, sent_24h, ...}
print(comprehensive_forecast())   # full payload
```

## How to audit (re-run anytime)

```bash
set -a && . /root/.env && set +a
/usr/bin/python3 /root/empire-v49/scripts/audit_predictor.py
```

The script prints: row counts, freshness, null rates on key
columns, calibration state, and pipeline_health history.
**Re-run after any new agent or DB change** to spot new
calibration gaps.

## See also

- [`architecture.md`](architecture.md) — funnel shape
- [`dispatcher.md`](dispatcher.md) — where the data comes from
- [`qc.md`](qc.md) — the watcher that catches data-quality issues
- [`locked-directive.md`](locked-directive.md) — what the
  forecast should move toward (revenue, the #4 metric)

## log

- 2026-06-15: created (initial scaffold; closes the 3x
  over-forecast gap surfaced by the audit)
