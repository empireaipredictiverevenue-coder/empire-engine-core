#!/bin/bash
# EMPIRE V49 · Ranking Prediction Monitor
# ========================================
# Logs ranking-stats endpoint every hour to a CSV file.
# After a week, compare rate=3 vs rate=5 cost projections.
#
# Cron: 0 * * * * cd /root/empire-v49 && bash scripts/monitor_ranking_prediction.sh
#
# Output file: logs/ranking_monitor.csv
# Columns: timestamp, total_events, predictions_fired, sample_rate,
#          sample_pct, actual_pct, cost_rate_3_weekly, cost_rate_5_weekly,
#          cost_delta_weekly, cost_delta_pct

LOG_DIR="/root/empire-v49/logs"
LOG_FILE="$LOG_DIR/ranking_monitor.csv"
STATS_ENDPOINT="http://localhost:8001/api/seo/ranking-stats"

mkdir -p "$LOG_DIR"

# Initialize CSV with header if file doesn't exist
if [ ! -f "$LOG_FILE" ]; then
    echo "timestamp,total_events,predictions_fired,sample_rate,sample_pct,actual_pct,groq_model,cost_per_prediction,cost_rate_3_weekly,cost_rate_5_weekly,cost_delta_weekly,cost_delta_pct" > "$LOG_FILE"
fi

# Fetch stats
RESPONSE=$(curl -s --max-time 5 "$STATS_ENDPOINT" 2>/dev/null)

if [ -z "$RESPONSE" ]; then
    echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),ERROR: endpoint unreachable" >> "$LOG_FILE"
    exit 1
fi

# Parse and append CSV row
python3 -c "
import json, sys
try:
    d = json.loads('''$RESPONSE''')
    row = [
        d.get('total_events', '?'),
        d.get('predictions_fired', '?'),
        d.get('sample_rate', '?'),
        d.get('sample_pct', '?'),
        d.get('actual_pct', '?'),
        d.get('groq_model', '?'),
        d.get('cost_per_prediction', '?'),
        d.get('cost_rate_3_weekly', '?'),
        d.get('cost_rate_5_weekly', '?'),
        d.get('cost_delta_weekly', '?'),
        d.get('cost_delta_pct', '?'),
    ]
    row_str = ','.join(str(x) for x in row)
    with open('$LOG_FILE', 'a') as f:
        f.write(f'$(date -u +%Y-%m-%dT%H:%M:%SZ),{row_str}\n')
except Exception as e:
    with open('$LOG_FILE', 'a') as f:
        f.write(f'$(date -u +%Y-%m-%dT%H:%M:%SZ),PARSE_ERROR:{e}\n')
" 2>/dev/null

# Cleanup: keep only last 720 entries (30 days of hourly data)
tail -n 720 "$LOG_FILE" > "$LOG_FILE.tmp" 2>/dev/null && mv "$LOG_FILE.tmp" "$LOG_FILE" 2>/dev/null
