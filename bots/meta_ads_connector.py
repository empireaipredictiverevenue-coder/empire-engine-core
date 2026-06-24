"""
EMPIRE V49 · META ADS CONNECTOR
================================
Real Meta (Facebook/Instagram) Ads API integration via REST.

Fetches live campaign performance data from Meta Marketing API and
returns it in the format empire_traffic_ads_agent.py expects.

REQUIRED CREDENTIALS (set in /root/.env):
  META_ACCESS_TOKEN          — long-lived auth credential with ads_read scope
  META_AD_ACCOUNT_ID         — ad account ID (format: act_123456789)

SETUP STEPS (human):
  1. Go to https://developers.facebook.com/
  2. Create an app, add "Marketing API" product
  3. Generate a System User auth credential with ads_read permission
  4. Go to Business Settings → System Users → Generate Token
  5. Set the env vars above and restart the traffic-specialist

GRACEFUL DEGRADATION:
  If any credential is missing, all methods return None.
  The traffic_ads_agent falls back to call_logs → buyers → static.

USAGE:
  from bots.meta_ads_connector import MetaAdsConnector
  conn = MetaAdsConnector()
  data = conn.get_campaign_performance()  # returns list of dicts or None
"""

import os
import json
import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

log = logging.getLogger("empire.meta_ads")

META_API_VERSION = "v21.0"
META_API_BASE = f"https://graph.facebook.com/{META_API_VERSION}"


class MetaAdsConnector:
    """Connects to Meta (Facebook/Instagram) Ads API and fetches campaign data."""

    def __init__(self):
        self.access_token = os.getenv("META_ACCESS_TOKEN", "").strip()
        self.ad_account_id = os.environ.get("META_AD_ACCOUNT_ID", "").strip()

    @property
    def configured(self) -> bool:
        """True if all required credentials are present."""
        return bool(self.access_token and self.ad_account_id)

    async def get_campaign_performance(self, days: int = 30) -> Optional[list[dict]]:
        """
        Fetch campaign performance data from Meta Marketing API.

        Returns a list of dicts compatible with empire_traffic_ads_agent
        platform format, or None if not configured / API error.
        """
        if not self.configured:
            return None

        # Fields to fetch with proper nested structure for insights
        fields = (
            "id,name,status,objective,daily_budget,"
            "insights.date_preset(last_30d)"
            "{impressions,clicks,spend,cpc,cpm,ctr,"
            "actions,action_values,cost_per_action_type,"
            "reach,frequency}"
        )

        url = f"{META_API_BASE}/{self.ad_account_id}/campaigns"
        params = {
            "fields": fields,
            "limit": 50,
            "access_token": self.access_token,
            "filtering": json.dumps([
                {"field": "effective_status", "operator": "IN",
                 "value": ["ACTIVE", "PAUSED", "ARCHIVED"]}
            ]),
        }

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.get(url, params=params)
                if r.status_code >= 400:
                    log.warning(f"[meta-ads] API error {r.status_code}: {r.text[:200]}")
                    return None

                data = r.json()
                campaign_list = data.get("data", [])
                if not campaign_list:
                    log.info("[meta-ads] No campaign results returned")
                    return None

                platforms = []
                for campaign in campaign_list:
                    name = campaign.get("name", "Unknown")
                    status = (campaign.get("status", "")).lower()
                    objective = campaign.get("objective", "UNKNOWN")

                    insights = campaign.get("insights", {})
                    if isinstance(insights, list) and insights:
                        insights = insights[0]
                    elif not isinstance(insights, dict):
                        insights = {}

                    spend = float(insights.get("spend", 0) or 0)
                    impressions = int(insights.get("impressions", 0) or 0)
                    clicks = int(insights.get("clicks", 0) or 0)
                    cpc = float(insights.get("cpc", 0) or 0)
                    ctr = float(insights.get("ctr", 0) or 0)

                    # Extract conversions (purchase or lead)
                    conversions = 0
                    conv_value = 0.0
                    actions = insights.get("actions", []) or []
                    action_values = insights.get("action_values", []) or []
                    for a in actions:
                        atype = a.get("action_type", "")
                        if atype in ("purchase", "lead", "offsite_conversion.fb_pixel_purchase"):
                            conversions += int(a.get("value", 0) or 0)
                    for av in action_values:
                        if av.get("action_type") in ("purchase", "offsite_conversion.fb_pixel_purchase"):
                            conv_value += float(av.get("value", 0) or 0)

                    cpa = spend / max(conversions, 1) if conversions else None
                    roas = round(conv_value / max(spend, 1), 2) if spend > 0 and conv_value > 0 else None

                    # Icon by objective
                    icons = {
                        "CONVERSIONS": "🎯", "TRAFFIC": "📘", "REACH": "👁️",
                        "VIDEO_VIEWS": "🎬", "LEAD_GENERATION": "📋",
                        "ENGAGEMENT": "💬", "APP_INSTALLS": "📱",
                    }

                    # Estimate monthly budget from daily
                    daily_budget = int(campaign.get("daily_budget", 0) or 0) / 100  # cents → dollars
                    monthly_estimate = daily_budget * 30 if daily_budget else spend * 1.5

                    platforms.append({
                        "id": f"meta-{campaign.get('id', '?')}",
                        "name": f"Meta: {name}",
                        "type": "social",
                        "icon": icons.get(objective, "📘"),
                        "budget_monthly": round(monthly_estimate, 2),
                        "budget_spent": round(spend, 2),
                        "impressions": impressions,
                        "clicks": clicks,
                        "conversions": conversions,
                        "cost_per_click": round(cpc, 2),
                        "cost_per_acquisition": round(cpa, 2) if cpa else None,
                        "ctr": round(ctr, 2),
                        "revenue": round(conv_value, 2),
                        "roas": roas,
                        "status": "active" if status == "active" else status,
                        "source": "meta_ads_api",
                    })

                log.info(f"[meta-ads] Fetched {len(platforms)} campaigns")
                return platforms

        except Exception as e:
            log.warning(f"[meta-ads] fetch error: {e}")
            return None

    async def get_account_summary(self) -> Optional[dict]:
        """Get a summary of the Meta ad account."""
        if not self.configured:
            return None

        fields = "name,currency,account_status,amount_spent,balance"
        url = f"{META_API_BASE}/{self.ad_account_id}"
        params = {"fields": fields, "access_token": self.access_token}

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.get(url, params=params)
                if r.status_code >= 400:
                    return None
                data = r.json()

                return {
                    "account_name": data.get("name", "Unknown"),
                    "currency": data.get("currency", "USD"),
                    "status": data.get("account_status", 0),
                    "amount_spent": round(float(data.get("amount_spent", 0) or 0) / 100, 2),
                    "balance": round(float(data.get("balance", 0) or 0) / 100, 2),
                    "source": "meta_ads_api",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as e:
            log.warning(f"[meta-ads] account_summary error: {e}")
            return None


# ── SINGLETON ────────────────────────────────────────────────────────
_connector: Optional[MetaAdsConnector] = None


def get_meta_ads_connector() -> MetaAdsConnector:
    global _connector
    if _connector is None:
        _connector = MetaAdsConnector()
    return _connector


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    import sys

    if "--auth" in sys.argv:
        print("""
╔══════════════════════════════════════════════════════════╗
║  META ADS API — Setup Instructions                      ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  1. Go to Meta Business Suite:                           ║
║     https://business.facebook.com/settings              ║
║                                                          ║
║  2. Create a System User with ads_read permission:       ║
║     Users → System Users → Add                         ║
║     Assign to your ad account with "View performance"   ║
║                                                          ║
║  3. Generate a token:                                   ║
║     System Users → Generate New Token                   ║
║     Select your ad account, scope: ads_read             ║
║     Set to "Never expires"                              ║
║                                                          ║
║  4. Get your Ad Account ID:                             ║
║     Ads Manager → Account dropdown → ID                 ║
║     Format: act_123456789012345                        ║
║                                                          ║
║  5. Set these in /root/.env:                             ║
║     META_ACCESS_TOKEN=EAAxxxxx...                        ║
║     META_AD_ACCOUNT_ID=act_123456789012345               ║
║                                                          ║
║  6. Run --test to verify the connection                  ║
╚══════════════════════════════════════════════════════════╝
""")
    elif "--test" in sys.argv:
        async def _test():
            conn = get_meta_ads_connector()
            if not conn.configured:
                print("NOT CONFIGURED — missing credentials in /root/.env")
                print(f"  access_token: {'✓' if conn.access_token else '✗'}")
                print(f"  ad_account_id: {'✓' if conn.ad_account_id else '✗'}")
                return
            print(f"Configured — fetching campaigns...")
            campaigns = await conn.get_campaign_performance()
            if campaigns:
                print(json.dumps(campaigns, indent=2, default=str))
            else:
                print("No campaign data returned (API error or no campaigns)")
        asyncio.run(_test())
    else:
        conn = get_meta_ads_connector()
        print(f"Meta Ads Connector: {'CONFIGURED' if conn.configured else 'NOT CONFIGURED'}")
