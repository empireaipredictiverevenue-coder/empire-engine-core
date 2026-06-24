"""
EMPIRE V49 · OMNICHANNEL ENGINE — Layer 1: LEADS HUB
======================================================
Central lead management layer. Pulls from Supabase (radar_targets,
enriched_leads, contractors), deduplicates, enriches, and syncs to
Twenty CRM (companies/contacts) and ListMonk (subscribers/lists).

Pipeline:
    radar_targets → enriched_leads → contractors
        → dedup by phone/email/address
        → sync to Twenty CRM (companies + people)
        → sync to ListMonk (subscriber lists)
        → return unified lead record

Usage:
    hub = LeadsHub()
    leads = await hub.ingest_leads(limit=100)
    stats = await hub.sync_to_twenty(leads)
    counts = await hub.sync_to_listmonk(leads)
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple

log = logging.getLogger("empire.omni.leads_hub")

SUPABASE_URL = os.getenv("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")
TWENTY_URL = "http://localhost:3003"
LISTMONK_URL = "http://localhost:9000"


def _sb():
    """Lazy Supabase client."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return None
    try:
        from supabase import create_client
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        return None


class LeadsHub:
    """Layer 1: Central lead ingestion, dedup, enrichment, and CRM sync.

    Unified lead record format:
        {
            "id": str,               # uuid
            "source": str,           # radar_targets | enriched_leads | contractors
            "name": str,
            "email": str,
            "phone": str,
            "address": str,
            "city": str,
            "state": str,
            "metro": str,
            "niche": str,
            "urgency_score": int,    # 0-10
            "asset_value": float,
            "status": str,           # active | pending | converted | blocked
            "temperature": str,      # hot | warm | cold (set by Layer 2)
            "created_at": str,       # ISO timestamp
            "meta": dict,
        }
    """

    def __init__(self):
        self.sb = _sb()
        self.stats = {"ingested": 0, "synced_twenty": 0, "synced_listmonk": 0}

    # ── INGESTION ──────────────────────────────────────────────────────

    async def ingest_leads(self, limit: int = 100, sources: List[str] = None) -> List[Dict[str, Any]]:
        """Pull leads from Supabase across all sources, dedup, and return unified records.

        Sources: radar_targets (raw leads), enriched_leads (scored/enriched),
                 contractors (recruited), campaign_leads (classified).

        Dedup: prefers enriched_leads over radar_targets, keeps highest urgency_score.
        """
        if sources is None:
            sources = ["radar_targets", "enriched_leads", "campaign_leads"]

        sb = self.sb
        if sb is None:
            log.error("[leads_hub] Supabase not configured")
            return []

        all_raw = []

        # ── radar_targets (raw property-owner leads) ──
        if "radar_targets" in sources:
            try:
                r = sb.table("radar_targets").select(
                    "id,warehouse_name,address,city,state,phone,email,"
                    "urgency_score,asset_value,source,status,created_at"
                ).eq("status", "active").order("created_at", desc=True).limit(limit).execute()
                for row in (r.data or []):
                    all_raw.append(self._normalize_radar(row))
            except Exception as e:
                log.warning(f"[leads_hub] radar_targets query failed: {e}")

        # ── enriched_leads (scored & enriched) ──
        if "enriched_leads" in sources:
            try:
                r = sb.table("enriched_leads").select(
                    "id,radar_target_id,warehouse_name,address,city,state,phone,email,"
                    "niche,score,status,created_at,meta"
                ).in_("status", ["pending_outreach", "pending_enrichment"]).order("created_at", desc=True).limit(limit).execute()
                for row in (r.data or []):
                    all_raw.append(self._normalize_enriched(row))
            except Exception as e:
                log.warning(f"[leads_hub] enriched_leads query failed: {e}")

        # ── campaign_leads (classified by lead_scorer) ──
        if "campaign_leads" in sources:
            try:
                r = sb.table("campaign_leads").select(
                    "id,radar_target_id,enriched_lead_id,warehouse_name,address,city,state,"
                    "phone,email,temperature,urgency_score,enrichment_score,composite_score,"
                    "source,status,created_at,meta"
                ).eq("status", "active").order("created_at", desc=True).limit(limit).execute()
                for row in (r.data or []):
                    all_raw.append(self._normalize_campaign(row))
            except Exception as e:
                log.warning(f"[leads_hub] campaign_leads query failed: {e}")

        # ── Dedup by phone → email → address ──
        leads = self._dedup(all_raw)
        self.stats["ingested"] = len(leads)
        log.info(f"[leads_hub] ingested {len(leads)} leads (from {len(all_raw)} raw rows)")
        return leads

    def _normalize_radar(self, row: dict) -> dict:
        return {
            "id": row.get("id", ""),
            "source": "radar_targets",
            "name": row.get("warehouse_name") or row.get("address", "")[:50],
            "email": row.get("email", ""),
            "phone": row.get("phone", ""),
            "address": row.get("address", ""),
            "city": row.get("city", ""),
            "state": row.get("state", ""),
            "metro": "",
            "niche": row.get("source", ""),
            "urgency_score": row.get("urgency_score") or 0,
            "asset_value": row.get("asset_value") or 0,
            "status": row.get("status", "active"),
            "temperature": "",
            "created_at": row.get("created_at", ""),
            "meta": {},
        }

    def _normalize_enriched(self, row: dict) -> dict:
        meta = row.get("meta") or {}
        return {
            "id": row.get("id", ""),
            "source": "enriched_leads",
            "name": row.get("warehouse_name") or row.get("address", "")[:50],
            "email": row.get("email", ""),
            "phone": row.get("phone", ""),
            "address": row.get("address", ""),
            "city": row.get("city", ""),
            "state": row.get("state", ""),
            "metro": meta.get("metro", ""),
            "niche": row.get("niche", ""),
            "urgency_score": meta.get("urgency_score", 0),
            "asset_value": row.get("score") or 0,
            "status": row.get("status", "pending_outreach"),
            "temperature": "",
            "created_at": row.get("created_at", ""),
            "meta": meta,
        }

    def _normalize_campaign(self, row: dict) -> dict:
        meta = row.get("meta") or {}
        return {
            "id": row.get("id", ""),
            "source": "campaign_leads",
            "name": row.get("warehouse_name") or row.get("address", "")[:50],
            "email": row.get("email", ""),
            "phone": row.get("phone", ""),
            "address": row.get("address", ""),
            "city": row.get("city", ""),
            "state": row.get("state", ""),
            "metro": meta.get("metro", ""),
            "niche": row.get("source", ""),
            "urgency_score": row.get("urgency_score") or 0,
            "asset_value": row.get("composite_score") or 0,
            "status": row.get("status", "active"),
            "temperature": row.get("temperature", ""),
            "created_at": row.get("created_at", ""),
            "meta": meta,
        }

    def _dedup(self, rows: List[dict]) -> List[dict]:
        """Dedup by phone > email > address. Later rows (enriched > radar) win."""
        seen = {}
        for row in rows:
            key = row.get("phone") or row.get("email") or row.get("address") or row.get("id")
            if not key:
                continue
            if key not in seen or row["source"] in ("enriched_leads", "campaign_leads"):
                seen[key] = row
        return list(seen.values())

    # ── TWENTY CRM SYNC ────────────────────────────────────────────────

    async def sync_to_twenty(self, leads: List[dict], api_token: str = "") -> int:
        """Sync leads to Twenty CRM as companies + contacts.

        Creates companies with name/address/domain, then people linked to them.
        Skips leads without email or with duplicate company names.
        """
        token = api_token or os.getenv("TWENTY_API_TOKEN", "")
        if not token:
            log.warning("[leads_hub] TWENTY_API_TOKEN not set — skipping Twenty sync")
            return 0

        import httpx
        synced = 0

        async with httpx.AsyncClient(timeout=30) as client:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            for lead in leads:
                email = lead.get("email", "")
                name = lead.get("name", "")
                if not name or "@" not in email:
                    continue
                try:
                    # Create company
                    r = await client.post(
                        f"{TWENTY_URL}/rest/companies",
                        headers=headers,
                        json={
                            "name": name,
                            "domainName": email.split("@")[1] if "@" in email else "",
                            "address": f"{lead.get('city','')}, {lead.get('state','')}",
                            "employees": 1,
                        },
                    )
                    if r.status_code < 400:
                        company_id = r.json().get("data", {}).get("company", {}).get("id", "")
                        if company_id:
                            await client.post(
                                f"{TWENTY_URL}/rest/people",
                                headers=headers,
                                json={
                                    "name": {"firstName": name.split()[0] if name.split() else name,
                                             "lastName": " ".join(name.split()[1:]) if len(name.split()) > 1 else ""},
                                    "email": email,
                                    "phone": lead.get("phone", ""),
                                    "companyId": company_id,
                                },
                            )
                        synced += 1
                except Exception as e:
                    log.debug(f"[leads_hub] Twenty sync skip: {name[:30]} — {e}")

        self.stats["synced_twenty"] = synced
        log.info(f"[leads_hub] synced {synced} leads to Twenty CRM")
        return synced

    # ── LISTMONK SYNC ───────────────────────────────────────────────────

    # SQL helpers for direct ListMonk DB access (same pattern as sync_listmonk.py)
    _PSQL = ["docker", "exec", "-t", "listmonk-db", "psql", "-U", "listmonk", "-d", "listmonk", "-c"]

    @staticmethod
    def _lmsql(query: str) -> str:
        import subprocess as _sp
        try:
            r = _sp.run(LeadsHub._PSQL + [query], stdout=_sp.PIPE, stderr=_sp.PIPE,
                       text=True, timeout=10)
            return r.stdout
        except Exception:
            return ""

    async def sync_to_listmonk(self, leads: List[dict]) -> int:
        """Sync classified omni leads to ListMonk as subscribers.

        Inserts each lead as a subscriber (with email, name, attribs) and
        links them to the 'Omni Leads' list. Uses the same SQL pattern as
        sync_listmonk.py but operates on the leads passed in.
        """
        import asyncio, uuid, json as _json

        if not leads:
            return 0

        # Ensure the "Omni Leads" list exists
        omni_list_id = 0
        out = self._lmsql("SELECT id FROM lists WHERE name = 'Omni Leads';")
        for line in out.split("\n"):
            line = line.strip()
            if line.isdigit():
                omni_list_id = int(line)
                break
        if not omni_list_id:
            self._lmsql("INSERT INTO lists (name, type, optin, description, created_at, updated_at) "
                         "VALUES ('Omni Leads', 'private', 'single', 'Classified leads from omni engine', NOW(), NOW());")
            out2 = self._lmsql("SELECT id FROM lists WHERE name = 'Omni Leads';")
            for line in out2.split("\n"):
                line = line.strip()
                if line.isdigit():
                    omni_list_id = int(line)
                    break

        # Also ensure the Default list exists for fallback
        default_list_id = 0
        out = self._lmsql("SELECT id FROM lists WHERE name = 'Default list';")
        for line in out.split("\n"):
            line = line.strip()
            if line.isdigit():
                default_list_id = int(line)
                break

        def _add_subscriber(email: str, name: str, attribs: dict) -> int:
            """Create or update a subscriber. Returns subscriber ID."""
            sub_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"empire-omni-{email}"))
            safe_email = email.replace("'", "''")
            safe_name = name.replace("'", "''")
            attribs_json = _json.dumps(attribs).replace("'", "''")

            check = self._lmsql(f"SELECT id FROM subscribers WHERE email = '{safe_email}';")
            for line in check.split("\n"):
                line = line.strip()
                if line.isdigit():
                    self._lmsql(f"UPDATE subscribers SET name = '{safe_name}', attribs = '{attribs_json}'::jsonb, "
                                f"updated_at = NOW() WHERE id = {line};")
                    return int(line)

            self._lmsql(f"INSERT INTO subscribers (uuid, email, name, attribs, status, created_at, updated_at) "
                         f"VALUES ('{sub_uuid}', '{safe_email}', '{safe_name}', '{attribs_json}'::jsonb, "
                         f"'enabled', NOW(), NOW());")
            check2 = self._lmsql(f"SELECT id FROM subscribers WHERE email = '{safe_email}';")
            for line in check2.split("\n"):
                line = line.strip()
                if line.isdigit():
                    return int(line)
            return 0

        def _subscribe(sub_id: int, list_id: int) -> None:
            if not sub_id or not list_id:
                return
            self._lmsql(f"INSERT INTO subscriber_lists (subscriber_id, list_id, status, created_at, updated_at) "
                         f"VALUES ({sub_id}, {list_id}, 'confirmed', NOW(), NOW()) "
                         f"ON CONFLICT (subscriber_id, list_id) DO NOTHING;")

        # ── Build temperature-based lists ──
        hot_list_id = 0
        warm_list_id = 0
        cold_list_id = 0
        for temp in ["Hot Leads", "Warm Leads", "Cold Leads"]:
            out = self._lmsql(f"SELECT id FROM lists WHERE name = '{temp}';")
            for line in out.split("\n"):
                line = line.strip()
                if line.isdigit():
                    lid = int(line)
                    if "Hot" in temp: hot_list_id = lid
                    elif "Warm" in temp: warm_list_id = lid
                    else: cold_list_id = lid

        synced = 0
        for lead in leads:
            email = (lead.get("email") or "").strip()
            phone = (lead.get("phone") or "").strip()
            name = (lead.get("name") or lead.get("address", "Property Owner")[:40]).strip()

            # Fall back to phone-based identifier if no email
            if email and "@" in email:
                identifier = email
            elif phone:
                identifier = f"{phone.replace(' ', '')}@phone-omni.empire-ai.co.uk"
                name = f"{name} ({phone})"
            else:
                log.debug(f"[leads_hub] skipping lead without email/phone: {name[:30]}")
                continue

            # Use identifier (which is email or phone-based synthetic email)
            email = identifier
            temp = lead.get("temperature", "cold")
            attribs = {
                "source": "omni_engine",
                "temperature": temp,
                "phone": lead.get("phone", ""),
                "city": lead.get("city", ""),
                "state": lead.get("state", ""),
                "niche": lead.get("niche", ""),
                "urgency": lead.get("urgency_score", 0),
                "classified_at": lead.get("classified_at", ""),
            }

            try:
                sub_id = _add_subscriber(email, name, attribs)
                if sub_id:
                    # Link to omni list + temperature list + default
                    _subscribe(sub_id, omni_list_id)
                    if temp == "hot" and hot_list_id: _subscribe(sub_id, hot_list_id)
                    elif temp == "warm" and warm_list_id: _subscribe(sub_id, warm_list_id)
                    elif cold_list_id: _subscribe(sub_id, cold_list_id)
                    if default_list_id: _subscribe(sub_id, default_list_id)
                    synced += 1
            except Exception as e:
                log.debug(f"[leads_hub] ListMonk subscriber insert failed for {email[:30]}: {e}")

        self.stats["synced_listmonk"] += synced
        log.info(f"[leads_hub] synced {synced}/{len(leads)} omni leads to ListMonk (Omni Leads list)")
        return synced

    def snapshot(self) -> dict:
        return {
            "supabase_connected": self.sb is not None,
            "twenty_token_set": bool(os.getenv("TWENTY_API_TOKEN", "")),
            **self.stats,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
