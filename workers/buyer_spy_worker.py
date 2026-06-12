"""
EMPIRE V49 · DIRECT BUYER SPY WORKER
=====================================
Scans long-duration aggregator-pool calls to extract direct end-buyer brand
names via local Ollama. Runs as a standalone daemon or cron batch job.

Usage:
  python3 workers/buyer_spy_worker.py          # single pass
  python3 workers/buyer_spy_worker.py --loop   # continuous monitoring loop
"""

import os
import json
import sqlite3
import http.client
import logging
import sys
import time
from pathlib import Path

log = logging.getLogger("empire.spy.worker")

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"

_OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "localhost")
_OLLAMA_PORT = int(os.environ.get("OLLAMA_PORT", "11434"))
_OLLAMA_MODEL = os.environ.get("OLLAMA_SPY_MODEL", "llama3:8b")
_LOOP_INTERVAL = int(os.environ.get("SPY_WORKER_INTERVAL_SEC", "300"))


def consult_local_spy_matrix(transcript: str) -> dict:
    """
    Queries local Ollama to isolate corporate names from intake audio transcripts.
    """
    conn = http.client.HTTPConnection(_OLLAMA_HOST, _OLLAMA_PORT, timeout=20)
    headers = {"Content-Type": "application/json"}

    system_rules = (
        "You are an intake auditor tracking corporate entities. Analyze the following telephone text "
        "and isolate the commercial brand name mentioned by the answering sales representative. "
        "Return a JSON object containing exactly one key: 'extracted_brand_identity'."
    )

    payload = {
        "model": _OLLAMA_MODEL,
        "messages": [
            {"role": "system", "content": system_rules},
            {"role": "user", "content": transcript},
        ],
        "stream": False,
        "format": "json",
    }

    try:
        conn.request("POST", "/api/chat", json.dumps(payload), headers)
        res = conn.getresponse()
        raw = json.loads(res.read().decode())
        content = raw.get("message", {}).get("content", "{}")
        return json.loads(content)
    except Exception as e:
        log.warning(f"[spy] Ollama call failed: {e}")
        return {"extracted_brand_identity": "UNKNOWN_AGGREGATOR"}
    finally:
        conn.close()


def audit_aggregator_streams() -> int:
    """
    Loops through unverified aggregator calls to locate direct end-buyers.
    Returns the number of calls analyzed.
    """
    if not DB_PATH.exists():
        log.warning(f"[spy] DB not found at {DB_PATH}")
        return 0

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Grab long-duration calls assigned to generic network pools
    cursor.execute('''
        SELECT call_id, niche_category, sub_niche_vertical
        FROM call_logs
        WHERE assigned_buyer_id = 'aggregator_pool'
          AND call_duration_seconds >= 60
    ''')

    target_calls = cursor.fetchall()
    log.info(f"[spy] Found {len(target_calls)} long-form network calls to analyze")

    for call in target_calls:
        # Mock transcript — in production this comes from the telephony hook
        mock_transcript = (
            "Thank you for dialing National Choice Care Group, "
            "my code is agent 402. How can I pull up your claim?"
        )

        extracted_data = consult_local_spy_matrix(mock_transcript)
        found_brand = extracted_data.get("extracted_brand_identity", "UNKNOWN_AGGREGATOR")

        log.info(
            f"[spy] Call {call['call_id']}: "
            f"Extracted End-Buyer -> {found_brand.upper()}"
        )
        log.info(
            f"[spy] PITCH: 'We own the search placement driving these calls. "
            f"Cut the middleman network.' -> {found_brand}"
        )

    conn.close()
    return len(target_calls)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stdout,
    )

    loop_mode = "--loop" in sys.argv

    if loop_mode:
        log.info(f"[spy] Worker started in loop mode (interval={_LOOP_INTERVAL}s)")
        while True:
            count = audit_aggregator_streams()
            log.info(f"[spy] Cycle complete — {count} calls analyzed")
            time.sleep(_LOOP_INTERVAL)
    else:
        count = audit_aggregator_streams()
        log.info(f"[spy] Single pass complete — {count} calls analyzed")

    return 0


if __name__ == "__main__":
    sys.exit(main())
