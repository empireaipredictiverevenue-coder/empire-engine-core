# REVENUE FORECASTER · Skills Registry

## Registered Skills

### 1. `revenue.forecast.monthly`
Generate a 30-day forward revenue forecast by lane.
- Input: days (default 30)
- Output: per-lane and total projected revenue, confidence intervals

### 2. `revenue.anomaly.detect`
Scan recent transactions for anomalies — missing fees, unusual patterns, pipeline stalls.
- Input: lookback_hours (default 24)
- Output: list of anomalies with severity and recommended action

### 3. `revenue.lane.breakdown`
Show per-lane revenue, fee, and settlement breakdown.
- Input: days (default 7), lane_id (optional)
- Output: structured breakdown with trends

### 4. `revenue.health.check`
Assess overall revenue health — pipeline velocity, fee velocity, lane health scores.
- Input: none
- Output: health score (0-100) with breakdown

### 5. `revenue.report.generate`
Generate a comprehensive revenue narrative report.
- Input: days (default 7)
- Output: executive summary, lane highlights, risks, actionable advice
