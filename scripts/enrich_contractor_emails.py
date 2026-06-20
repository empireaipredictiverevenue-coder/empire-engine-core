"""
EMPIRE V49 · CONTRACTOR EMAIL ENRICHER
=======================================
One-time enrichment script that populates real email addresses for
contractors with placeholder emails (@prospector.placeholder).

Strategies (in priority order):
  1. PHONE MATCH — Cross-reference contractor phone numbers against
     enriched_leads and radar_targets tables for real emails
  2. NAME PATTERN — For contractors with business-style names, generate
     likely email patterns (info@, contact@, hello@)
  3. REPORT — List what couldn't be enriched for manual followup

Usage:
    python3 scripts/enrich_contractor_emails.py          # dry-run
    python3 scripts/enrich_contractor_emails.py --apply  # write to DB
"""

import os
import re
import sys
import json
import time
import subprocess
import logging
from datetime import datetime
from collections import defaultdict
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env")
except ImportError:
    pass

from supabase import create_client

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
log = logging.getLogger("enrich")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
sb = create_client(SUPABASE_URL, SUPABASE_KEY)


# ── EMAIL EXTRACTION HELPERS ─────────────────────────────────────────

def _is_valid_email(email: str) -> bool:
    """Check if a string looks like a real, deliverable email."""
    if not email or not isinstance(email, str):
        return False
    email = email.strip()
    if not email:
        return False
    # Must have @ and a domain
    if "@" not in email:
        return False
    local, domain = email.rsplit("@", 1)
    if not local or not domain:
        return False
    if "." not in domain:
        return False
    # Filter known placeholders and garbage
    bad = {"prospector.placeholder", "example.com", "domain.com", "email.com",
           "test.com", "mail.com", "user.com", "yourcompany.com"}
    if domain.lower() in bad:
        return False
    # Filter image files and non-email patterns
    if domain.lower().endswith((".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp")):
        return False
    # Must have at least 3 chars in local part (e.g. "a@b.co" is too short)
    if len(local) < 2:
        return False
    return True


def _generate_email_patterns(name: str) -> list:
    """Generate likely email patterns from a business name.
    Returns list of (pattern_type, email) tuples.
    """
    if not name or name == "Unknown":
        return []

    # Clean the name — remove common suffixes and normalize
    clean = name.strip()
    clean = re.sub(r'\b(LLC|INC|CORP|CORPORATION|LTD|LIMITED|CO|COMPANY|SERVICES|SOLUTIONS|GROUP|PRO|PROS)\b\.?$', '', clean, flags=re.IGNORECASE)
    clean = clean.strip()
    if not clean:
        return []

    # Build domain from name
    domain_part = clean.lower()
    domain_part = re.sub(r'[^a-z0-9]', '', domain_part)
    if not domain_part or len(domain_part) < 3:
        return []

    # Use `info@` as the best guess — most businesses use this
    return [(f"info@{domain_part}.com", f"info@{domain_part}.com")]


# ── STRATEGY 1: PHONE MATCH ──────────────────────────────────────────

def match_by_phone(contractors: list[dict]) -> dict:
    """Cross-reference contractor phones against enriched_leads and
    radar_targets. Returns dict mapping contractor_id -> email."""
    matched = {}

    phones = [c["phone"] for c in contractors if c.get("phone")]
    if not phones:
        return matched

    log.info(f"Searching enriched_leads for {len(phones)} phone numbers...")

    # Batch queries to avoid URL length limits
    batch_size = 50
    for i in range(0, len(phones), batch_size):
        batch = phones[i:i + batch_size]
        try:
            r = sb.table("enriched_leads").select("phone,email,warehouse_name") \
                .in_("phone", batch).execute()
            for row in (r.data or []):
                email = (row.get("email") or "").strip()
                if not _is_valid_email(email):
                    continue
                phone = row.get("phone", "")
                # Find the contractor with this phone
                for c in contractors:
                    if c["phone"] == phone and c["id"] not in matched:
                        matched[c["id"]] = {
                            "email": email,
                            "source": "enriched_leads",
                            "warehouse_name": row.get("warehouse_name", ""),
                        }
                        break
        except Exception as e:
            log.warning(f"enriched_leads batch query failed: {e}")

    log.info(f"Phone match found: {len(matched)} emails")

    # Also check radar_targets for any additional matches
    unmatched = [c for c in contractors if c["id"] not in matched and c.get("phone")]
    if unmatched:
        unmatched_phones = list(set(c["phone"] for c in unmatched))
        log.info(f"Searching radar_targets for {len(unmatched_phones)} remaining phones...")
        for i in range(0, len(unmatched_phones), batch_size):
            batch = unmatched_phones[i:i + batch_size]
            try:
                r = sb.table("radar_targets").select("phone,email,warehouse_name") \
                    .in_("phone", batch).execute()
                for row in (r.data or []):
                    email = (row.get("email") or "").strip()
                    if not _is_valid_email(email):
                        continue
                    phone = row.get("phone", "")
                    for c in unmatched:
                        if c["phone"] == phone and c["id"] not in matched:
                            matched[c["id"]] = {
                                "email": email,
                                "source": "radar_targets",
                                "warehouse_name": row.get("warehouse_name", ""),
                            }
                            break
            except Exception as e:
                log.warning(f"radar_targets batch query failed: {e}")

        log.info(f"Total phone matches (enriched_leads + radar_targets): {len(matched)}")

    return matched


# ── STRATEGY 2: NAME PATTERN ─────────────────────────────────────────

def generate_name_patterns(contractors: list[dict], already_matched: set) -> dict:
    """Generate guessable email patterns for contractors with business names.
    Returns dict mapping contractor_id -> list of (pattern_type, email)."""
    generated = {}

    for c in contractors:
        if c["id"] in already_matched:
            continue
        name = c.get("name", "")
        patterns = _generate_email_patterns(name)
        if patterns:
            generated[c["id"]] = {
                "name": name,
                "patterns": patterns,
            }

    log.info(f"Name patterns generated for: {len(generated)} contractors")
    return generated


# ── MAIN ENRICHMENT ──────────────────────────────────────────────────

def enrich(dry_run: bool = True) -> dict:
    """Run the full enrichment pipeline.

    Args:
        dry_run: If True, only report what would be done. If False, write to DB.

    Returns:
        dict with enrichment results
    """
    log.info(f"{'DRY RUN' if dry_run else 'APPLY'} — Enriching contractor emails")

    # ── Fetch all contractors with placeholder emails ────────────────
    r = sb.table("contractors").select("id,name,email,phone,metro,specialties,active") \
        .limit(2000).execute()
    all_contractors = r.data or []

    placeholder = [
        c for c in all_contractors
        if c.get("email") and "prospector.placeholder" in str(c.get("email", ""))
    ]

    log.info(f"Total contractors: {len(all_contractors)}")
    log.info(f"With placeholder emails: {len(placeholder)}")

    # ── Strategy 1: Phone match ──────────────────────────────────────
    phone_matched = match_by_phone(placeholder)
    matched_ids = set(phone_matched.keys())

    # ── Strategy 2: Name patterns ────────────────────────────────────
    name_patterns = generate_name_patterns(placeholder, matched_ids)

    # ── Apply updates ───────────────────────────────────────────────
    updates = []
    errors = []

    for c in placeholder:
        cid = c["id"]
        name = c.get("name", "Unknown")

        if cid in phone_matched:
            # Use the phone-matched email (best quality)
            match = phone_matched[cid]
            updates.append({
                "id": cid,
                "name": name,
                "old_email": c["email"],
                "new_email": match["email"],
                "source": match["source"],
                "quality": "high",
            })

        elif cid in name_patterns:
            # Use the first generated pattern as best guess
            patterns = name_patterns[cid]["patterns"]
            best = patterns[0]  # info@business.com
            updates.append({
                "id": cid,
                "name": name,
                "old_email": c["email"],
                "new_email": best[1],
                "source": f"name_pattern:{best[0]}",
                "quality": "guess",
            })

    # ── Write to DB (if not dry-run) ─────────────────────────────────
    if not dry_run:
        log.info(f"Writing {len(updates)} email updates to contractors table...")
        # First pass: write emails + quality flags via concurrent batches
        written = 0
        for i in range(0, len(updates), 50):
            batch = updates[i:i + 50]
            for u in batch:
                try:
                    # Update email + stamp quality marker in meta
                    cur = sb.table("contractors").select("meta").eq("id", u["id"]).limit(1).execute()
                    existing_meta = cur.data[0].get("meta", {}) if cur.data else {}
                    if not isinstance(existing_meta, dict):
                        existing_meta = {}
                    existing_meta["email_quality"] = u["quality"]  # "high" or "guess"
                    existing_meta["original_email_source"] = u["source"]
                    
                    sb.table("contractors").update({
                        "email": u["new_email"],
                        "meta": existing_meta,
                    }).eq("id", u["id"]).execute()
                    written += 1
                except Exception as e:
                    errors.append({"id": u["id"], "error": str(e)[:80]})
            log.info(f"  Wrote {written}/{len(updates)}...")
            time.sleep(0.25)  # gentle throttle
        log.info(f"Done — {written} updated, {len(errors)} errors")
    else:
        log.info(f"DRY RUN — would update {len(updates)} contractors")

    # ── Summary ──────────────────────────────────────────────────────
    high_quality = sum(1 for u in updates if u["quality"] == "high")
    guesses = sum(1 for u in updates if u["quality"] == "guess")
    total_with_real = len(set(c.get("email") for c in all_contractors
                               if c.get("email") and "placeholder" not in str(c.get("email", ""))))
    # After enrichment
    total_after = total_with_real + high_quality + guesses

    # Contractors that still couldn't be enriched
    enriched_ids = set(u["id"] for u in updates)
    still_placeholder = [c for c in placeholder if c["id"] not in enriched_ids]
    no_name_contractors = [
        c for c in still_placeholder
        if not c.get("name") or c["name"] == "Unknown" or not c["name"].strip()
    ]
    unreachable = [
        c for c in still_placeholder
        if c not in no_name_contractors
    ]

    print()
    print("=" * 60)
    print(f"  CONTRACTOR EMAIL ENRICHMENT {'(DRY RUN)' if dry_run else '(APPLIED)'}")
    print("=" * 60)
    print(f"  Total contractors with placeholders:  {len(placeholder)}")
    print(f"  Phone-matched (high quality):         {high_quality}")
    print(f"  Name-pattern generated (guess):        {guesses}")
    print(f"  Total enriched:                        {len(updates)}")
    print(f"  Already had real emails:               {total_with_real}")
    print(f"  After enrichment:                      {total_after}")
    print(f"  Still placeholder (no name):           {len(no_name_contractors)}")
    print(f"  Still placeholder (unreachable):       {len(unreachable)}")
    print()

    if updates:
        print("  SAMPLE UPDATES:")
        for u in updates[:10]:
            qual = "✓" if u["quality"] == "high" else "?"
            print(f"    {qual} {u['name'][:30]:30s} {u['old_email'][:30]:30s} → {u['new_email'][:35]}")
        if len(updates) > 10:
            print(f"    ... and {len(updates) - 10} more")

    return {
        "dry_run": dry_run,
        "total_placeholder": len(placeholder),
        "phone_matched": len(phone_matched),
        "name_patterns": len(name_patterns),
        "total_enriched": len(updates),
        "high_quality": high_quality,
        "guesses": guesses,
        "still_placeholder_no_name": len(no_name_contractors),
        "still_placeholder_unreachable": len(unreachable),
        "errors": len(errors),
        "sample_updates": updates[:10] if updates else [],
    }


if __name__ == "__main__":
    dry_run = "--apply" not in sys.argv
    run_agent_reach = "--agent-reach" in sys.argv
    result = enrich(dry_run=dry_run)
    print(f"\n{'DRY RUN' if result['dry_run'] else 'APPLIED'} — use {'--apply' if result['dry_run'] else '(already applied)'} to {'write' if result['dry_run'] else 're-run'}")

    # ── Chain Agent-Reach intel enrichment ─────────────────────────
    if run_agent_reach:
        print("\n" + "=" * 60)
        print("  CHAINING: Agent-Reach multi-source intel enrichment")
        print("=" * 60)
        script = str(Path(__file__).resolve().parent / "enrich_contractor_agent_reach.py")
        cmd = [sys.executable, script]
        if not dry_run:
            cmd.append("--apply")
        print(f"  Running: {' '.join(cmd)}")
        subprocess.run(cmd)
