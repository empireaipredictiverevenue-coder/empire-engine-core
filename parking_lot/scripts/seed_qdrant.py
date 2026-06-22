#!/usr/bin/env python3
"""
EMPIRE AI · SEED QDRANT COLLECTIONS
=====================================
Populates the 3 Qdrant collections from existing data sources:

  - skills:    Scans brain_vault/skills/*.md + skills/marketingskills/*.md
  - leads:     Queries Supabase contractors, radar_targets, and buyers tables
  - documents: Reads autoresearch results.tsv files + outreach_log from Supabase

Usage:
    python3 scripts/seed_qdrant.py                    # seed all collections
    python3 scripts/seed_qdrant.py --only skills       # seed only skills
    python3 scripts/seed_qdrant.py --dry-run           # dry run (count only)
    python3 scripts/seed_qdrant.py --force             # re-index even if exists

Requires:
    - .env at /root/.env with SUPABASE_URL, SUPABASE_SERVICE_KEY
    - Qdrant running at localhost:6333
"""

import os
import sys
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path("/root/empire-v49").resolve()))

try:
    from dotenv import load_dotenv
    for env_file in ("/root/.env", "/root/.hermes/.env"):
        try:
            load_dotenv(env_file)
        except Exception:
            pass
except Exception:
    pass

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [seed_qdrant] %(message)s",
)
log = logging.getLogger("seed_qdrant")

# Lazy imports
_sb = None


def _uuid5(s: str) -> str:
    """Generate a deterministic UUID v5 from a string."""
    import uuid
    return str(uuid.uuid5(uuid.NAMESPACE_DNS, s))


def _supabase():
    global _sb
    if _sb is None:
        from supabase import create_client
        _sb = create_client(
            os.environ["SUPABASE_URL"],
            os.environ["SUPABASE_SERVICE_KEY"],
        )
    return _sb


# ── Skills ─────────────────────────────────────────────────────────────

def collect_vault_skills() -> list:
    """Scan brain_vault/skills/*.md for SKILL.md definitions."""
    vault_dir = Path("/root/empire-v49/brain_vault/skills")
    items = []
    if not vault_dir.exists():
        log.warning(f"vault skills dir not found: {vault_dir}")
        return items

    for fpath in sorted(vault_dir.glob("*.md")):
        slug = fpath.stem  # e.g. 'dev_browser'
        content = fpath.read_text()
        # Parse YAML frontmatter if present
        metadata = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                content_body = parts[2].strip()
                for line in frontmatter.strip().split("\n"):
                    if ":" in line:
                        key, val = line.split(":", 1)
                        metadata[key.strip()] = val.strip().strip('"').strip("'")
            else:
                content_body = content
        else:
            content_body = content

        skill_name = metadata.get("name", slug.replace("_", "-"))
        tags_raw = metadata.get("tags", "")
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.strip("[]").split(",") if t.strip()]
        else:
            tags = []

        items.append({
            "id": _uuid5(f"vault:{slug}"),
            "skill_name": skill_name,
            "content": content_body or content,
            "metadata": {
                "version": metadata.get("version", "1.0"),
                "tags": tags,
                "category": metadata.get("category", "vault"),
                "domain": metadata.get("type", "skill"),
                "source_file": str(fpath),
            },
        })

    log.info(f"[vault skills] collected {len(items)} items")
    return items


def collect_marketing_skills() -> list:
    """Scan skills/marketingskills/*.md for marketing skill definitions."""
    mkt_dir = Path("/root/empire-v49/skills/marketingskills")
    items = []
    if not mkt_dir.exists():
        log.warning(f"marketing skills dir not found: {mkt_dir}")
        return items

    for fpath in sorted(mkt_dir.glob("*.md")):
        slug = fpath.stem
        content = fpath.read_text()
        # Parse YAML frontmatter
        metadata = {}
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                frontmatter = parts[1]
                content_body = parts[2].strip()
                for line in frontmatter.strip().split("\n"):
                    if ":" in line:
                        key, val = line.split(":", 1)
                        metadata[key.strip()] = val.strip().strip('"').strip("'")
            else:
                content_body = content
        else:
            content_body = content

        skill_name = metadata.get("name", slug.replace("_", "-"))
        tags_raw = metadata.get("tags", "")
        if isinstance(tags_raw, str):
            tags = [t.strip() for t in tags_raw.strip("[]").split(",") if t.strip()]
        else:
            tags = []

        items.append({
            "id": _uuid5(f"marketing:{slug}"),
            "skill_name": skill_name,
            "content": content_body or content,
            "metadata": {
                "version": metadata.get("version", "1.0"),
                "tags": tags,
                "category": "marketing",
                "domain": metadata.get("type", "marketing_skill"),
                "source_file": str(fpath),
            },
        })

    log.info(f"[marketing skills] collected {len(items)} items")
    return items


# ── Leads ──────────────────────────────────────────────────────────────

def collect_contractors() -> list:
    """Query contractors from Supabase."""
    items = []
    try:
        sb = _supabase()
        page = sb.table("contractors").select("id, name, specialties, metro, niche, active, trust_score").limit(5000).execute()
        for row in (page.data or []):
            specialties_raw = row.get("specialties", "")
            if isinstance(specialties_raw, list):
                specialties_str = ", ".join(str(s) for s in specialties_raw)
            else:
                specialties_str = str(specialties_raw) if specialties_raw else ""
            desc = " ".join(filter(None, [
                row.get("name", ""),
                specialties_str,
                row.get("niche", ""),
            ]))
            items.append({
                "id": _uuid5(f"contractor:{row['id']}"),
                "name": row.get("name", row.get("id", "")),
                "description": desc or f"Contractor {row['id']}",
                "metadata": {
                    "metro": row.get("metro", ""),
                    "niche": row.get("niche", ""),
                    "status": "active" if row.get("active") else "inactive",
                    "score": row.get("trust_score", 0),
                    "source": "contractors",
                },
            })
        log.info(f"[contractors] collected {len(items)} items")
    except Exception as e:
        log.warning(f"[contractors] query failed: {e}")
    return items


def collect_radar_targets() -> list:
    """Query radar_targets from Supabase."""
    items = []
    try:
        sb = _supabase()
        page = sb.table("radar_targets").select("id, name, city, status, urgency_score, damage_severity").limit(5000).execute()
        for row in (page.data or []):
            desc = " ".join(filter(None, [
                row.get("name", ""),
                f"in {row.get('city', '')}" if row.get("city") else "",
                f"severity: {row.get('damage_severity', '')}" if row.get("damage_severity") else "",
            ]))
            items.append({
                "id": _uuid5(f"radar:{row['id']}"),
                "name": row.get("name", row.get("id", "")),
                "description": desc or f"Radar target {row['id']}",
                "metadata": {
                    "city": row.get("city", ""),
                    "status": row.get("status", "active"),
                    "score": row.get("urgency_score", 0),
                    "source": "radar_targets",
                },
            })
        log.info(f"[radar_targets] collected {len(items)} items")
    except Exception as e:
        log.warning(f"[radar_targets] query failed: {e}")
    return items


# ── Documents ──────────────────────────────────────────────────────────

def collect_autoresearch_results() -> list:
    """Read autoresearch results.tsv files."""
    autoresearch_dir = Path("/root/empire-v49/integrations/autoresearch")
    items = []
    if not autoresearch_dir.exists():
        return items

    # Search for results.tsv in all subdirs
    for tsv_path in autoresearch_dir.rglob("results.tsv"):
        target_name = tsv_path.parent.name
        try:
            with open(tsv_path) as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("timestamp"):
                        continue
                    parts = line.split("\t")
            raw_id = f"autoresearch:{target_name}:{parts[0] if len(parts) > 0 else line[:40]}"
            items.append({
                "id": _uuid5(raw_id),
                        "title": f"Autoresearch result — {target_name}",
                        "content": line,
                        "doc_type": "autoresearch_result",
                        "metadata": {
                            "source": f"autoresearch/{target_name}",
                            "tags": [target_name, "autoresearch"],
                        },
                    })
            log.info(f"[autoresearch] {tsv_path}: {len([l for l in open(tsv_path) if l.strip() and not l.startswith('timestamp')])} rows read")
        except Exception as e:
            log.warning(f"[autoresearch] failed to read {tsv_path}: {e}")

    log.info(f"[autoresearch] collected {len(items)} items total")
    return items


def collect_outreach_log() -> list:
    """Query recent outreach_log from Supabase."""
    items = []
    try:
        sb = _supabase()
        page = sb.table("outreach_log").select("id, body_preview, sent_at, sequence, channel, response_received_at").limit(2000).execute()
        for row in (page.data or []):
            content = row.get("body_preview") or "(no body)"
            items.append({
                "id": _uuid5(f"outreach:{row['id']}"),
                "title": f"Outreach — {row.get('sequence', '?')} via {row.get('channel', '?')}",
                "content": content[:2000],
                "doc_type": "outreach_email",
                "metadata": {
                    "source": "outreach_log",
                    "sequence": row.get("sequence", ""),
                    "tags": [row.get("channel", ""), row.get("sequence", "")],
                    "created_at": (row.get("sent_at") or "")[:10],
                },
            })
        log.info(f"[outreach_log] collected {len(items)} items")
    except Exception as e:
        log.warning(f"[outreach_log] query failed: {e}")
    return items


# ── Main seeding logic ─────────────────────────────────────────────────

async def seed_skills(store, force: bool = False) -> dict:
    """Seed the skills collection from vault + marketing skill files."""
    from integrations.qdrant import bulk_upsert_skills

    all_items = collect_vault_skills() + collect_marketing_skills()
    if not all_items:
        return {"indexed": 0, "failed": 0, "total": 0}

    result = await bulk_upsert_skills(all_items)
    result["total"] = len(all_items)
    return result


async def seed_leads(store, force: bool = False) -> dict:
    """Seed the leads collection from contractors + radar_targets."""
    from integrations.qdrant import bulk_upsert_leads

    all_items = collect_contractors() + collect_radar_targets()
    if not all_items:
        return {"indexed": 0, "failed": 0, "total": 0}

    result = await bulk_upsert_leads(all_items)
    result["total"] = len(all_items)
    return result


async def seed_documents(store, force: bool = False) -> dict:
    """Seed the documents collection from autoresearch results + outreach_log."""
    from integrations.qdrant import bulk_upsert_documents

    all_items = collect_autoresearch_results() + collect_outreach_log()
    if not all_items:
        return {"indexed": 0, "failed": 0, "total": 0}

    result = await bulk_upsert_documents(all_items)
    result["total"] = len(all_items)
    return result


async def main():
    parser = argparse.ArgumentParser(description="Seed Qdrant collections")
    parser.add_argument("--only", choices=["skills", "leads", "documents"], help="Only seed this collection")
    parser.add_argument("--dry-run", action="store_true", help="Count only, don't actually index")
    parser.add_argument("--force", action="store_true", help="Re-index even if points already exist")
    args = parser.parse_args()

    from integrations.qdrant import ensure_collections

    # Ensure collections exist
    ok = await ensure_collections()
    if not ok:
        log.error("Failed to ensure Qdrant collections. Is Qdrant running?")
        sys.exit(1)

    log.info("Qdrant collections ready")

    if args.dry_run:
        log.info("=== DRY RUN — counting items ===")
        if not args.only or args.only == "skills":
            vault = collect_vault_skills()
            mkt = collect_marketing_skills()
            log.info(f"  skills: {len(vault) + len(mkt)} items ({len(vault)} vault + {len(mkt)} marketing)")
        if not args.only or args.only == "leads":
            leads = collect_contractors()
            radar = collect_radar_targets()
            log.info(f"  leads: {len(leads) + len(radar)} items ({len(leads)} contractors + {len(radar)} radar)")
        if not args.only or args.only == "documents":
            auto = collect_autoresearch_results()
            ol = collect_outreach_log()
            log.info(f"  documents: {len(auto) + len(ol)} items ({len(auto)} autoresearch + {len(ol)} outreach)")
        log.info("Dry run complete — no data indexed")
        return

    # Seed each collection
    results = {}

    if not args.only or args.only == "skills":
        log.info("=== Seeding skills ===")
        results["skills"] = await seed_skills(None, force=args.force)
        log.info(f"  → {results['skills'].get('indexed', 0)} indexed, {results['skills'].get('failed', 0)} failed / {results['skills'].get('total', 0)} total")

    if not args.only or args.only == "leads":
        log.info("=== Seeding leads ===")
        results["leads"] = await seed_leads(None, force=args.force)
        log.info(f"  → {results['leads'].get('indexed', 0)} indexed, {results['leads'].get('failed', 0)} failed / {results['leads'].get('total', 0)} total")

    if not args.only or args.only == "documents":
        log.info("=== Seeding documents ===")
        results["documents"] = await seed_documents(None, force=args.force)
        log.info(f"  → {results['documents'].get('indexed', 0)} indexed, {results['documents'].get('failed', 0)} failed / {results['documents'].get('total', 0)} total")

    total_indexed = sum(r.get("indexed", 0) for r in results.values())
    total_failed = sum(r.get("failed", 0) for r in results.values())
    log.info(f"=== Done — {total_indexed} indexed, {total_failed} failed ===")

    # Print summary as JSON
    print(json.dumps({
        "status": "complete",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "results": results,
        "total_indexed": total_indexed,
        "total_failed": total_failed,
    }, indent=2))


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
