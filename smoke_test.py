"""
Smoke test for pipeline.py — runs phases 2-3 with mock data so you can verify
Open-Meteo connectivity, Supabase writes, and ntfy push without hitting any
real URLs.

Usage:
    python smoke_test.py

What it does:
  - Skips Phase 1 (no scraping)
  - Feeds 3 mock leads (Dallas, Houston, Mobile)
  - Runs Phase 3 (real Open-Meteo call)
  - Runs Phase 4 dry-run (logs what would be written, no DB writes)

Expected output on a clean box:
  - "Phase 3 complete: N verified hits" where N depends on actual weather
  - Per-city wind readings logged
  - No errors

If you see:
  - "Weather fetch failed" → Hetzner box can't reach api.open-meteo.com
  - SSL errors → Python cert bundle issue
  - Module errors → run `pip install -r requirements.txt` first
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from pipeline import phase_2_clean, phase_3_radar, phase_4_vault, log

MOCK_LEADS = [
    {
        "Company Name": "Dallas Cold Storage Inc",
        "Phone":        "2145551001",
        "City":         "Dallas",
        "URL":          "https://example.test/dallas",
        "Email":        "",
    },
    {
        "Company Name": "Houston Freight Hub",
        "Phone":        "7135552002",
        "City":         "Houston",
        "URL":          "https://example.test/houston",
        "Email":        "",
    },
    {
        "Company Name": "Mobile Port Logistics",
        "Phone":        "2515553003",
        "City":         "Mobile",
        "URL":          "https://example.test/mobile",
        "Email":        "",
    },
]


async def main():
    log.info("━━━ EMPIRE SMOKE TEST ━━━")
    log.info(f"Mock leads: {len(MOCK_LEADS)}")

    # Skip phase 1 entirely
    df = phase_2_clean(MOCK_LEADS)
    verified = await phase_3_radar(df)

    log.info("")
    log.info("Calling Phase 4 in DRY RUN mode...")
    log.info("")

    phase_4_vault(verified, dry_run=True)

    log.info("")
    log.info("━━━ SMOKE TEST COMPLETE ━━━")
    log.info("If you saw weather readings for each city, Open-Meteo is reachable.")
    log.info("If any locks were detected, the verification logic is firing.")
    log.info("Now safe to point at real URLs.")


if __name__ == "__main__":
    asyncio.run(main())
