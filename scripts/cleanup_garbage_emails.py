#!/usr/bin/env python3
"""
EMPIRE V49 · GARBAGE EMAIL CLEANUP
====================================
Scans email_sequences and radar_targets for invalid emails (image files,
placeholder domains, garbage patterns). Reports what was found and optionally
deletes/quarantines them.

Gmail spam filters penalize the sender domain when mail is sent to obviously
invalid addresses like shadow@2x.png or you@community.com. Removing these
from the pipeline is critical for deliverability.

Usage:
    python3 scripts/cleanup_garbage_emails.py              # dry-run (default)
    python3 scripts/cleanup_garbage_emails.py --apply      # actually delete
    python3 scripts/cleanup_garbage_emails.py --status     # show current counts
"""

import os, sys, json
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv(REPO.parent / ".env")
from supabase import create_client

from bots.email_validator import is_valid_email, describe_rejection


def _sb():
    url = os.getenv("SUPABASE_URL", "")
    key = os.getenv("SUPABASE_SERVICE_KEY", "")
    return create_client(url, key)


def show_status(sb):
    """Show current counts of garbage emails across tables."""
    tables = ["email_sequences", "radar_targets"]
    for table in tables:
        try:
            r = sb.table(table).select("email").limit(5000).execute()
            rows = r.data or []
            total = len(rows)
            garbage = [row for row in rows if not is_valid_email(row.get("email", ""), strict=True)]
            print(f"{table:25s}: {total:5d} total, {len(garbage):5d} garbage ({len(garbage)/max(total,1)*100:.1f}%)")
            if garbage:
                reasons = {}
                for g in garbage[:20]:
                    email = g.get("email", "")[:50]
                    reason = describe_rejection(email) or "unknown"
                    reasons.setdefault(reason, []).append(email)
                for reason, examples in sorted(reasons.items()):
                    print(f"    {reason}: {examples[:3]}")
        except Exception as e:
            print(f"{table:25s}: error - {e}")


def cleanup(sb, dry_run=True):
    """Find and optionally delete/quarantine garbage emails.

    Does NOT delete radar_targets rows — only clears their email field
    so the lead itself isn't lost, just the bad email.
    """
    results = {"email_sequences_deleted": 0, "radar_targets_cleared": 0, "errors": []}

    # ── 1. email_sequences: delete garbage entries entirely ──────
    try:
        r = sb.table("email_sequences").select("id, email").limit(5000).execute()
        for row in (r.data or []):
            email = row.get("email", "")
            if not is_valid_email(email, strict=True):
                reason = describe_rejection(email) or "unknown"
                if dry_run:
                    print(f"  [DRY-RUN] Would DELETE email_sequences id={row['id'][:8]} email={email[:40]} ({reason})")
                    results["email_sequences_deleted"] += 1
                else:
                    try:
                        sb.table("email_sequences").delete().eq("id", row["id"]).execute()
                        results["email_sequences_deleted"] += 1
                        print(f"  ✓ DELETED email_sequences id={row['id'][:8]} email={email[:40]} ({reason})")
                    except Exception as e:
                        results["errors"].append(f"delete {row['id']}: {e}")
    except Exception as e:
        results["errors"].append(f"email_sequences scan: {e}")

    # ── 2. radar_targets: clear email field, don't delete the row ──
    try:
        r = sb.table("radar_targets").select("id, email").limit(5000).execute()
        for row in (r.data or []):
            email = row.get("email", "")
            if email and not is_valid_email(email, strict=True):
                reason = describe_rejection(email) or "unknown"
                if dry_run:
                    print(f"  [DRY-RUN] Would CLEAR email for radar_targets id={row['id'][:8]} email={email[:40]} ({reason})")
                    results["radar_targets_cleared"] += 1
                else:
                    try:
                        sb.table("radar_targets").update({"email": ""}).eq("id", row["id"]).execute()
                        results["radar_targets_cleared"] += 1
                        print(f"  ✓ CLEARED email for radar_targets id={row['id'][:8]} email={email[:40]} ({reason})")
                    except Exception as e:
                        results["errors"].append(f"clear {row['id']}: {e}")
    except Exception as e:
        results["errors"].append(f"radar_targets scan: {e}")

    return results


def main():
    import argparse
    p = argparse.ArgumentParser(description="Clean up garbage emails from the pipeline")
    p.add_argument("--apply", action="store_true", help="Actually delete/clear (default: dry-run)")
    p.add_argument("--status", action="store_true", help="Show current garbage email counts and exit")
    args = p.parse_args()

    sb = _sb()

    if args.status:
        print("=" * 60)
        print("  GARBAGE EMAIL STATUS")
        print("=" * 60)
        show_status(sb)
        return

    print("=" * 60)
    print(f"  GARBAGE EMAIL CLEANUP {'(DRY RUN)' if not args.apply else '(APPLY)'}")
    print("=" * 60)
    results = cleanup(sb, dry_run=not args.apply)
    print()
    print(f"  email_sequences deleted:   {results['email_sequences_deleted']}")
    print(f"  radar_targets emails cleared: {results['radar_targets_cleared']}")
    if results["errors"]:
        print(f"  Errors: {len(results['errors'])}")
        for e in results["errors"][:5]:
            print(f"    {e}")
    if not args.apply:
        print(f"\n  DRY-RUN — run with --apply to execute")


if __name__ == "__main__":
    main()
