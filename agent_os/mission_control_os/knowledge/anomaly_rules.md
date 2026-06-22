# Anomaly Detection Rules

## Cross-System Correlation Patterns

### Pattern 1: Funnel Blockage
- **Signal**: Brain NO-GO spikes + low revenue + high compliance blocks
- **Indicators**: `brain.no_go_24h > 5`, `revenue.total_24h < threshold`, `compliance.blocked_today > 10`
- **Likely Cause**: Compliance filter too aggressive or lead quality dropped
- **Severity**: Amber → Red if persists > 2 cycles

### Pattern 2: Revenue Drop
- **Signal**: Revenue 24h drops > 30% while brain GO rate stays flat
- **Indicators**: `revenue.total_24h < 0.7 * revenue.avg_7d`, `brain.go_rate > 0.4`
- **Likely Cause**: Pipeline conversion failure, buyer churn, or SMS delivery issue
- **Severity**: Red

### Pattern 3: Stale Agents
- **Signal**: AGI governor reports stale agents + IPC bus inactivity
- **Indicators**: `agi.stale_count > 3`, `ipc.recent_events < 5`
- **Likely Cause**: Agent kernel process crash or scheduler failure
- **Severity**: Red — requires immediate operator restart

### Pattern 4: Call Window Violation
- **Signal**: Compliance call_window closed but outbound calls being made
- **Indicators**: `compliance.call_window_open = false`, `brain.calls_24h > 0`
- **Likely Cause**: Dialer ignoring time window config
- **Severity**: Red — TCPA violation risk

### Pattern 5: Autoresearch Stagnation
- **Signal**: No improvement across any autoresearch target for > 7 days
- **Indicators**: All scratchpad latest_improvement > 7 days ago
- **Likely Cause**: Search space exhausted or scoring model needs recalibration
- **Severity**: Amber — human review recommended

## Severity Levels

| Severity | Action | Response Time |
|----------|--------|---------------|
| Green | None — log | N/A |
| Amber | Flag in dashboard | Next operator check |
| Red | Telegram alert | Immediate |
