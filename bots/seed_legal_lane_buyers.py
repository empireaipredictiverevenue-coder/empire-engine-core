"""
EMPIRE V49 · LEGAL LANE BUYER SEEDER (5 sub_niches, idempotent)
===============================================================
Seeds the 5 legal lane buyers (one per sub_niche) into the buyers
table. Idempotent: re-runnable from boot, cron, or any agent.

Sub_niches (mirrors mesh_orchestrator.LANES 16-20):
  16  Pharma Liability
  17  Medical Device
  18  Consumer Product
  19  Class Action
  20  Mass Tort  (Apex Mass Tort Group, the canonical buyer)

Dedup guard:
  - Match on (buyer_name, niche) to respect the DB's unique
    constraint and prevent cross-niche collisions (e.g. Apex Mass
    Tort Group previously had rows in both "Legal" and "Mass Tort
    Legal" niches).
  - If an active row with the same (buyer_name, niche) exists,
    UPDATE it in place with the current config.
  - If no active row exists but an INACTIVE one does (e.g. from
    a previous run that was deactivated), reactivate it and
    update the config.
  - If no row exists at all, INSERT.

Placeholder numbers:
  - destination_phone is None on every row by default. The
    seeder does NOT make up numbers. Real vonage numbers must
    be provisioned per buyer from the vonage dashboard and set
    via --set-phones or a follow-up script.

Patched 2026-06-12 (step 4 of mass-tort lane-sort plan):
  - Replaces the previous bots/seed_mass_tort_buyer.py (which
    seeded only the Apex row and had the weak dedup).
  - Seeds all 5 sub_niches.
  - Real firm names (buyer_name) are placeholders. Replace
    when the firm identity is sourced.
"""

import argparse
import os
import sys


# Manual .env loader (sniper_env may not have python-dotenv).
ENV_PATH = "/root/.env"
if os.path.exists(ENV_PATH):
    with open(ENV_PATH) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _v = _line.split("=", 1)
            _v = _v.strip()
            if (_v.startswith('"') and _v.endswith('"')) or (_v.startswith("'") and _v.endswith("'")):
                _v = _v[1:-1]
            os.environ[_k.strip()] = _v


from supabase import create_client


# ── LANE → BUYER CONFIG ────────────────────────────────────────────────
# Each entry maps a legal lane to its buyer record. Numbers are
# None by default. Use --set-phones to populate them, or UPDATE
# the row directly from the dashboard.
LEGAL_LANES = {
    "Pharma Liability": {
        "lane_id": 16,
        "buyer_name": "PENDING - Pharma Buyer #1",
        "area_code_intent": "732 (NJ)",
        "destination_phone": None,
        "state_coverage": ["NJ", "NY", "PA", "CT"],
        "base_payout": 400.00,
        "notes": "Stub 2026-06-12. Real firm + contact to be sourced.",
    },
    "Medical Device": {
        "lane_id": 17,
        "buyer_name": "PENDING - Medical Device Buyer #1",
        "area_code_intent": "800 (toll-free)",
        "destination_phone": None,
        "state_coverage": ["MN", "MA", "CA"],
        "base_payout": 400.00,
        "notes": "Stub 2026-06-12. Real firm + contact to be sourced.",
    },
    "Consumer Product": {
        "lane_id": 18,
        "buyer_name": "PENDING - Consumer Product Buyer #1",
        "area_code_intent": "310 (LA, CA)",
        "destination_phone": None,
        "state_coverage": ["CA", "OR", "WA"],
        "base_payout": 400.00,
        "notes": "Stub 2026-06-12. Real firm + contact to be sourced.",
    },
    "Class Action": {
        "lane_id": 19,
        "buyer_name": "PENDING - Class Action Buyer #1",
        "area_code_intent": "212 (NYC)",
        "destination_phone": None,
        "state_coverage": ["NY", "NJ", "MA", "IL"],
        "base_payout": 500.00,
        "notes": "Stub 2026-06-12. Real firm + contact to be sourced.",
    },
    "Mass Tort": {
        "lane_id": 20,
        "buyer_name": "Apex Mass Tort Group",
        "area_code_intent": "214 (Dallas, TX)",
        "destination_phone": None,  # Will be the user's existing 214 vonage number.
        "state_coverage": ["TX", "NY", "FL", "CA", "IL"],
        "base_payout": 400.00,
        "notes": "Canonical legal/Mass Tort buyer. Number to be sourced from existing vonage dashboard.",
    },
}


def _buyer_payload(sub_niche: str, cfg: dict) -> dict:
    """Build the row payload for insert/update."""
    return {
        "buyer_name": cfg["buyer_name"],
        "niche": "Legal",
        "sub_niche": sub_niche,
        "destination_phone": cfg["destination_phone"],
        "is_active": True,
        "status": "ACTIVE",
        "state_coverage": cfg["state_coverage"],
        "base_payout": cfg["base_payout"],
        "fee_rate": 0.03,
        "per_call_fee": 0,
        "monthly_retainer": 0,
        "daily_cap": 50,
        "hours_open": 8,
        "hours_close": 20,
        "calls_today": 0,
        "calls_accepted": 0,
        "calls_offered": 0,
        "notes": cfg["notes"],
    }


def _find_existing(sb, buyer_name: str, niche: str = "Legal") -> dict | None:
    """
    Strong dedup: find by buyer_name + niche. Prefers the active row;
    falls back to the newest inactive row only if no active row exists.

    Filters by niche to prevent cross-niche collisions — e.g. Apex Mass
    Tort Group previously had rows in both "Legal" and "Mass Tort Legal"
    niches. Without the niche filter, the seeder would find the wrong
    row and try to update it with niche="Legal", violating the
    (buyer_name, niche) unique constraint.
    """
    # First try: active row with this buyer_name + niche
    res = (
        sb.table("buyers")
        .select("id, is_active")
        .eq("buyer_name", buyer_name)
        .eq("niche", niche)
        .eq("is_active", True)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    if res.data:
        return res.data[0]
    # Fallback: newest row with this buyer_name + niche (any status)
    res = (
        sb.table("buyers")
        .select("id, is_active")
        .eq("buyer_name", buyer_name)
        .eq("niche", niche)
        .order("created_at", desc=True)
        .limit(1)
        .execute()
    )
    return res.data[0] if res.data else None


def _upsert(sb, sub_niche: str, cfg: dict, *, dry_run: bool = False) -> str:
    """Upsert one buyer. Returns an action label for the run report."""
    payload = _buyer_payload(sub_niche, cfg)
    existing = _find_existing(sb, cfg["buyer_name"])

    if dry_run:
        if existing:
            return f"[DRY] {sub_niche:<20} UPDATE  {cfg['buyer_name']} (id={existing['id']})"
        return f"[DRY] {sub_niche:<20} INSERT  {cfg['buyer_name']}"

    if existing:
        # Update in place; if it was inactive, this reactivates it.
        sb.table("buyers").update(payload).eq("id", existing["id"]).execute()
        action = "REACTIVATED+UPDATE" if not existing["is_active"] else "UPDATE"
        return f"{sub_niche:<20} {action:<18} {cfg['buyer_name']} (id={existing['id']})"
    else:
        sb.table("buyers").insert(payload).execute()
        return f"{sub_niche:<20} {'INSERT':<18} {cfg['buyer_name']}"


def _set_phone(sb, sub_niche: str, phone: str) -> str:
    """Set destination_phone for the active buyer with this sub_niche."""
    res = (
        sb.table("buyers")
        .select("id, buyer_name")
        .eq("niche", "Legal")
        .eq("sub_niche", sub_niche)
        .eq("is_active", True)
        .execute()
    )
    if not res.data:
        return f"{sub_niche:<20} NO ACTIVE BUYER (run --seed first)"
    row = res.data[0]
    sb.table("buyers").update({"destination_phone": phone}).eq("id", row["id"]).execute()
    return f"{sub_niche:<20} PHONE SET     {row['buyer_name']} = {phone}"


# ── MAIN ───────────────────────────────────────────────────────────────
def main() -> int:
    p = argparse.ArgumentParser(description="Seed the 5 legal lane buyers")
    p.add_argument("--seed", action="store_true",
                   help="Run the upsert pass (default action)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show what --seed would do without making changes")
    p.add_argument("--set-phones", action="store_true",
                   help="Interactively set destination_phone for each lane")
    args = p.parse_args()

    if not os.environ.get("SUPABASE_URL") or not os.environ.get("SUPABASE_SERVICE_KEY"):
        print("[ERROR] SUPABASE_URL and SUPABASE_SERVICE_KEY required")
        return 1
    sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

    if args.set_phones:
        print("=== Set destination_phone per lane ===")
        for sub_niche, cfg in LEGAL_LANES.items():
            intent = cfg["area_code_intent"]
            current = "(none)"
            existing = _find_existing(sb, cfg["buyer_name"])
            if existing:
                res = sb.table("buyers").select("destination_phone").eq("id", existing["id"]).execute()
                if res.data and res.data[0].get("destination_phone"):
                    current = res.data[0]["destination_phone"]
            print(f"\n[{sub_niche}] area_code_intent: {intent}")
            print(f"  current phone: {current}")
            phone = input("  new phone (or Enter to skip): ").strip()
            if phone:
                print(" ", _set_phone(sb, sub_niche, phone))
            else:
                print(f"  {sub_niche:<20} SKIPPED")
        return 0

    # Default: --seed (or --dry-run)
    print("=== Upserting 5 legal lane buyers ===")
    for sub_niche, cfg in LEGAL_LANES.items():
        print(" ", _upsert(sb, sub_niche, cfg, dry_run=args.dry_run))

    # Verify
    if not args.dry_run:
        res = (
            sb.table("buyers")
            .select("buyer_name, sub_niche, destination_phone, is_active")
            .eq("niche", "Legal")
            .eq("is_active", True)
            .order("sub_niche")
            .execute()
        )
        print(f"\n=== Verification: {len(res.data)} active Legal buyers ===")
        for r in res.data:
            phone = r["destination_phone"] or "(no phone yet)"
            print(f"  {r['sub_niche']:<20} {r['buyer_name']:<40} phone={phone}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
