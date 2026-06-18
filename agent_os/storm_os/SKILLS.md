# STORM ORCHESTRATOR · Skills Registry

## Registered Skills

### 1. `storm.nws.poll`
Poll the NWS API for active alerts in Texas zones.
- Input: zones (optional list, defaults to all TX zones)
- Output: list of active alerts with severity, urgency, area
- Frequency: every 300s (configurable via STORM_POLL_INTERVAL_SEC)

### 2. `storm.alert.process`
Process a raw NWS alert into a structured strike event.
- Input: raw_alert dict
- Output: processed alert with geo-bounding box, severity score, lane match
- Depends on: storm.nws.poll

### 3. `storm.lane.match`
Match a processed alert against active metro lanes.
- Input: processed_alert
- Output: list of matched lane IDs with intersection area
- Depends on: storm.alert.process

### 4. `storm.status.report`
Generate a current status report — active alerts, recent strikes, coverage.
- Input: none
- Output: status dict with alert count, lane coverage, last poll time

### 5. `storm.fake_alert.inject`
Inject a synthetic alert for testing purposes.
- Input: city, state, severity, event_type
- Output: fake alert injected into processing pipeline
- Destructive: YES (test only)

## Dependencies
- `storm.nws.poll` → `storm.alert.process` → `storm.lane.match`
- `storm.status.report` → `storm.nws.poll` (reads last poll state)
