#!/bin/bash
# YouTube Shorts — daily at 09:00 UTC
# Generates and renders one faceless YouTube Short for Empire AI's channel.
# Pipeline: topic selection → Deepgram TTS → WhisperX alignment → ASS captions
#   → FFmpeg 1080×1920 vertical video
# Dry-run by default (no YouTube upload).
set -e
cd /root/empire-v49
set -a; source /root/.env; set +a

# Pull a random hook from CONTENT_PILLARS (source of truth in youtube_shorts_agent.py)
TOPIC=$(python3 -c "
from bots.youtube_shorts_agent import CONTENT_PILLARS
import random, itertools
hooks = list(itertools.chain.from_iterable(p['hooks'] for p in CONTENT_PILLARS))
print(random.choice(hooks))
")

STARTED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
echo "[$STARTED_AT] youtube-shorts submitting: $TOPIC"

# Submit through Buffy Buffer queue (manages concurrency, prevents overload)
# Deepgram is the default TTS provider (set in buffy_buffer.py and render_short.py)
RESULT=$(/usr/bin/python3 -m bots.buffy_buffer submit \
    --topic "$TOPIC" \
    --source cron \
    --priority 5 \
    2>&1)

echo "[$STARTED_AT] buffy response: $RESULT"

# Extract job ID for tracking
JOB_ID=$(echo "$RESULT" | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d.get('id','unknown')[:8])" 2>/dev/null || echo "unknown")
echo "[$STARTED_AT] youtube-shorts submitted → buffy job $JOB_ID (will render when capacity opens)"
