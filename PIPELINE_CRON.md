EMPIRE PIPELINE · CRON SETUP
==============================

Once pipeline.py is on your Hetzner box and tested with smoke_test.py,
wire it to cron so it runs automatically.


───────────────────────────────────────────────────────────────────────────────
RECOMMENDED SCHEDULE
───────────────────────────────────────────────────────────────────────────────

Storm-season (Mar-Oct) → every 2 hours, 6 AM to 10 PM Texas time
Off-season (Nov-Feb)   → daily at 8 AM

The pipeline is idempotent (state cache handles dedup) so missed runs
don't matter. But you want frequent enough scans that you catch a storm
within 2-4 hours of it passing.


───────────────────────────────────────────────────────────────────────────────
ONE-TIME SETUP ON HETZNER
───────────────────────────────────────────────────────────────────────────────

1. SSH into the Hetzner box and create the pipeline working directory:

    sudo mkdir -p /opt/empire-pipeline
    sudo chown $USER:$USER /opt/empire-pipeline
    cd /opt/empire-pipeline

2. Drop these files in /opt/empire-pipeline/:
    pipeline.py
    smoke_test.py
    master_whales.txt    (your URL list)
    requirements.txt     (just the pipeline dependencies — see below)

3. Set up a dedicated venv (don't pollute system Python):

    python3 -m venv venv
    ./venv/bin/pip install -U pip
    ./venv/bin/pip install httpx beautifulsoup4 pandas supabase requests

4. Create an .env file with your secrets (chmod 600 it):

    cat > /opt/empire-pipeline/.env <<'EOF'
    EMPIRE_OUTPUT_PATH=/opt/empire-pipeline/data/verified_storm_targets.csv
    EMPIRE_STATE_FILE=/opt/empire-pipeline/data/.pipeline_state.json
    EMPIRE_CONCURRENCY=8
    EMPIRE_TIMEOUT=12

    SUPABASE_URL=https://YOUR-PROJECT.supabase.co
    SUPABASE_SERVICE_KEY=YOUR_SERVICE_KEY

    NTFY_TOPIC=empire_private_alerts
    NTFY_TOKEN=YOUR_NTFY_TOKEN
    EOF

    chmod 600 /opt/empire-pipeline/.env

5. Make the data directory:

    mkdir -p /opt/empire-pipeline/data
    mkdir -p /opt/empire-pipeline/logs

6. Run smoke test ONCE manually to verify everything works:

    cd /opt/empire-pipeline
    source .env && export $(cut -d= -f1 .env)
    ./venv/bin/python smoke_test.py

   Expect to see weather readings for Dallas, Houston, and Mobile.
   If errors, fix them BEFORE wiring cron.


───────────────────────────────────────────────────────────────────────────────
THE CRON ENTRY
───────────────────────────────────────────────────────────────────────────────

Open the cron table:
    crontab -e

Add this entry:

# Empire Pipeline · Storm Hunter · every 2 hours, 6 AM - 10 PM Central Time
# (Hetzner runs UTC; Central is UTC-6 standard / UTC-5 daylight, so 6am CT = 11/12 UTC)
0 11,13,15,17,19,21,23,1,3 * * * cd /opt/empire-pipeline && set -a && . ./.env && set +a && ./venv/bin/python pipeline.py --since-last >> logs/pipeline.log 2>&1

Save and exit. Cron is now armed.

Breakdown:
  - `0 11,13,15,17,19,21,23,1,3` = at minute 0 of those UTC hours
    (matches 6, 8, 10am, 12, 2, 4, 6, 8, 10pm Central Daylight Time)
  - `cd /opt/empire-pipeline`     = go to the working directory
  - `set -a && . ./.env && set +a`= load env vars from .env file
  - `./venv/bin/python ...`        = use the dedicated venv Python
  - `--since-last`                 = skip already-processed URLs
  - `>> logs/pipeline.log 2>&1`    = append output + errors to log


───────────────────────────────────────────────────────────────────────────────
LOG ROTATION (so logs don't fill the disk)
───────────────────────────────────────────────────────────────────────────────

Drop this in /etc/logrotate.d/empire-pipeline (sudo required):

    sudo tee /etc/logrotate.d/empire-pipeline <<'EOF'
    /opt/empire-pipeline/logs/*.log {
        daily
        rotate 14
        compress
        delaycompress
        missingok
        notifempty
        copytruncate
    }
    EOF


───────────────────────────────────────────────────────────────────────────────
FAILURE ALERTS — get notified when cron itself fails
───────────────────────────────────────────────────────────────────────────────

The pipeline already pushes ntfy on success. Add this wrapper so cron
also pings ntfy if the pipeline itself crashes:

Create /opt/empire-pipeline/run_safe.sh:

    #!/bin/bash
    set -e
    cd /opt/empire-pipeline
    set -a && . ./.env && set +a

    if ! ./venv/bin/python pipeline.py --since-last >> logs/pipeline.log 2>&1; then
        # Pipeline failed — alert via ntfy
        curl -s \
          -H "Title: 🚨 EMPIRE PIPELINE CRASHED" \
          -H "Priority: urgent" \
          -H "Tags: warning" \
          ${NTFY_TOKEN:+-H "Authorization: Bearer $NTFY_TOKEN"} \
          -d "Pipeline run failed at $(date -u). Check /opt/empire-pipeline/logs/pipeline.log" \
          "https://ntfy.sh/${NTFY_TOPIC}"
        exit 1
    fi

Then chmod +x it and update your cron entry to call run_safe.sh instead:

    0 11,13,15,17,19,21,23,1,3 * * * /opt/empire-pipeline/run_safe.sh


───────────────────────────────────────────────────────────────────────────────
VERIFY IT'S WORKING
───────────────────────────────────────────────────────────────────────────────

After cron has run once (wait for the next scheduled hour):

    tail -n 100 /opt/empire-pipeline/logs/pipeline.log

You should see a clean run with the four phase banners and a completion line.

If you see no log file, cron isn't firing. Check:
    sudo systemctl status cron
    grep CRON /var/log/syslog | tail -20


───────────────────────────────────────────────────────────────────────────────
WHAT'S NEXT — INTEGRATION WITH THE HUB
───────────────────────────────────────────────────────────────────────────────

Once leads land in Supabase radar_targets, they automatically appear in:
  - /view/scout       (Warp Scout radar feed)
  - /command          (Cinematic Command Deck · live corridor heatmap)
  - The Subconscious Mind loop in hub.py picks them up on next cycle
  - When NWS issues a real severe storm alert within 25mi, the Empire Brain
    auto-evaluates the lead for GO/NO_GO and (if MANUS_ENABLED=1) fires
    the Manus sniper on it

That's the full chain:
  pipeline scrapes → Supabase stores → subconscious watches → brain decides
  → manus fires → contractor dispatched → claim settles → calibration learns

Loop closed.
