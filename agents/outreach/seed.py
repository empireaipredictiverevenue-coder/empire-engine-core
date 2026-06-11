"""
Empire AI · Predictive Revenue
Outreach Agent — Seed Helpers
================================

Two scripts to drop the FIRST real entries into supabase so the
dispatcher cron (not built yet) has something to act on when it's
wired up. Both are idempotent (upsert by primary key) so re-running
is safe.

  seed_lead.py        — insert a real storm lead into radar_targets
  seed_contractor.py  — insert a real contractor into the contractors table

Until you have at least one of each, the dispatch loop has nothing
to dispatch TO. Per STARTING_POINT.md, these are the two boxes
"Recruit 1 real contractor" and "Pipeline has scraped at least 100
real URLs" ultimately feed.

Usage:
    python3 -m agents.outreach.seed_lead \\
        --address "123 Main St" \\
        --city "Wichita" \\
        --state "KS" \\
        --phone "+13165551234" \\
        --urgency 9 \\
        --event "severe hail"

    python3 -m agents.outreach.seed_contractor \\
        --business "Acme Roofing" \\
        --contact-name "Jane Smith" \\
        --phone "+13165555678" \\
        --state "KS"
"""
import os
import sys
import json
import argparse
import logging
from pathlib import Path

# Make sure /root/empire-v49/ is on sys.path so we can import local modules.
REPO = Path(__file__).resolve().parents[2]  # /root/empire-v49
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

try:
    from dotenv import load_dotenv
    load_dotenv(REPO.parent / ".env")  # /root/.env
except ImportError:
    pass  # cron env will provide these

from supabase import create_client

log = logging.getLogger("empire.outreach.seed")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    if not url or not key:
        log.error("SUPABASE_URL / SUPABASE_SERVICE_KEY missing — set in /root/.env")
        sys.exit(2)
    return create_client(url, key)


# ─────────────────────────────────────────────────────────────────────
# Lead seeder
# ─────────────────────────────────────────────────────────────────────

def seed_lead(
    address: str,
    city: str,
    state: str,
    phone: str,
    urgency: int,
    event: str,
    severity: str = "Severe",
    lat: float | None = None,
    lon: float | None = None,
    tcpa_consent: bool = True,  # default True for first real test leads
) -> dict:
    """Insert or update a storm lead in radar_targets. Returns the row."""
    if urgency < 0 or urgency > 10:
        raise ValueError("urgency must be 0-10")
    sb = _sb()
    # radar_targets schema (from REVENUE_FLOW.md): address, phone, location,
    # status, damage_severity, urgency_score. We pass through phone so the
    # dispatcher has a real number to call.
    row = {
        "address":         f"{address}, {city}, {state}",
        "phone":           phone,
        "damage_severity": severity.lower(),
        "urgency_score":   urgency,
        "status":          "active",
        "meta": {
            "event":        event,
            "city":         city,
            "state":        state,
            "tcpa_consent": tcpa_consent,
            "source":       "manual_seed",
        },
    }
    if lat is not None and lon is not None:
        # PostGIS point literal: 'POINT(lon lat)' (note order)
        row["location"] = f"POINT({lon} {lat})"

    # Upsert by (address) — the most stable unique-ish key we have.
    # If the table has a real unique constraint, switch to that.
    r = sb.table("radar_targets").upsert(row, on_conflict="address").execute()
    out = r.data[0] if r.data else row
    log.info(f"seeded lead: id={out.get('id')} address={out.get('address')} urgency={urgency}")
    return out


def main_lead():
    p = argparse.ArgumentParser(description="Seed a storm lead into radar_targets")
    p.add_argument("--address", required=True)
    p.add_argument("--city", required=True)
    p.add_argument("--state", required=True, help="2-letter state code, e.g. KS")
    p.add_argument("--phone", required=True, help="E.164 format, e.g. +13165551234")
    p.add_argument("--urgency", type=int, required=True, help="0-10")
    p.add_argument("--event", required=True, help='e.g. "severe hail", "tornado"')
    p.add_argument("--severity", default="Severe", choices=["Moderate", "Severe", "Extreme", "Catastrophic"])
    p.add_argument("--lat", type=float, default=None)
    p.add_argument("--lon", type=float, default=None)
    p.add_argument("--no-consent", action="store_true", help="set tcpa_consent=False")
    args = p.parse_args()
    out = seed_lead(
        address=args.address, city=args.city, state=args.state, phone=args.phone,
        urgency=args.urgency, event=args.event, severity=args.severity,
        lat=args.lat, lon=args.lon, tcpa_consent=not args.no_consent,
    )
    print(json.dumps(out, indent=2, default=str))


# ─────────────────────────────────────────────────────────────────────
# Contractor seeder
# ─────────────────────────────────────────────────────────────────────

def seed_contractor(
    business: str,
    contact_name: str,
    phone: str,
    state: str,
    email: str = "",
    trade: str = "roofing",
    tcpa_consent: bool = True,
) -> dict:
    """Insert or update a contractor in the contractors table.

    The contractors schema is read from the live table. We upsert on
    business_name; if the schema differs, the dispatcher (when built)
    will skip the row with a logged warning. That's fine for the seed
    step — this gets you a row, not a guaranteed working dispatch.
    """
    sb = _sb()
    row = {
        "business_name":  business,
        "contact_name":   contact_name,
        "phone":          phone,
        "state":          state,
        "email":          email or None,
        "trade":          trade,
        "status":         "prospect",   # recruiter sequence will flip to 'active'
        "tcpa_consent":   tcpa_consent,
        "meta": {
            "source": "manual_seed",
        },
    }
    r = sb.table("contractors").upsert(row, on_conflict="business_name").execute()
    out = r.data[0] if r.data else row
    log.info(f"seeded contractor: id={out.get('id')} business={business}")
    return out


def main_contractor():
    p = argparse.ArgumentParser(description="Seed a contractor into the contractors table")
    p.add_argument("--business", required=True)
    p.add_argument("--contact-name", required=True)
    p.add_argument("--phone", required=True, help="E.164 format")
    p.add_argument("--state", required=True, help="2-letter state code")
    p.add_argument("--email", default="")
    p.add_argument("--trade", default="roofing")
    p.add_argument("--no-consent", action="store_true")
    args = p.parse_args()
    out = seed_contractor(
        business=args.business, contact_name=args.contact_name, phone=args.phone,
        state=args.state, email=args.email, trade=args.trade,
        tcpa_consent=not args.no_consent,
    )
    print(json.dumps(out, indent=2, default=str))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "contractor":
        sys.argv.pop(1)
        main_contractor()
    else:
        main_lead()
