"""
EMPIRE V49 · GOOGLE ADS CONNECTOR
==================================
Real Google Ads API integration via REST (no SDK dependency).

Fetches live campaign performance data from Google Ads API and
returns it in the format empire_traffic_ads_agent.py expects.

REQUIRED CREDENTIALS (set in /root/.env):
  GOOGLE_ADS_DEVELOPER_TOKEN   — from Google Ads API center
  GOOGLE_ADS_CLIENT_ID         — OAuth2 client ID
  GOOGLE_ADS_CLIENT_SECRET     — OAuth2 client secret
  GOOGLE_ADS_REFRESH_TOKEN     — OAuth2 refresh token
  GOOGLE_ADS_LOGIN_CUSTOMER_ID — manager account ID (10 digits, no hyphens)
  GOOGLE_ADS_CUSTOMER_ID       — ad account ID to query (10 digits)

SETUP STEPS (human):
  1. Go to https://ads.google.com/ → Tools → API Center
  2. Apply for a Developer Token (test access is instant)
  3. Create OAuth2 credentials in Google Cloud Console
  4. Run: python3 bots/google_ads_connector.py --auth
     This opens a browser to complete the OAuth2 flow and saves the refresh token.
  5. Set the env vars above and restart the traffic-specialist

GRACEFUL DEGRADATION:
  If any credential is missing, all methods return None.
  The traffic_ads_agent falls back to call_logs → buyers → static.

USAGE:
  from bots.google_ads_connector import GoogleAdsConnector
  conn = GoogleAdsConnector()
  data = conn.get_campaign_performance()  # returns list of dicts or None
"""

import os
import json
import logging
import time
from datetime import datetime, timezone, timedelta
from typing import Optional

import httpx

log = logging.getLogger("empire.google_ads")


class GoogleAdsConnector:
    """Connects to Google Ads API and fetches campaign performance data."""

    def __init__(self):
        self.dev_token = os.environ.get("GOOGLE_ADS_DEVELOPER_TOKEN", "").strip()
        self.client_id = os.environ.get("GOOGLE_ADS_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("GOOGLE_ADS_CLIENT_SECRET", "").strip()
        self.refresh_token = os.environ.get("GOOGLE_ADS_REFRESH_TOKEN", "").strip()
        self.login_customer_id = os.environ.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID", "").strip()
        self.customer_id = os.environ.get("GOOGLE_ADS_CUSTOMER_ID", "").strip()
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0

    @property
    def configured(self) -> bool:
        """True if all required credentials are present."""
        return all([
            self.dev_token, self.client_id, self.client_secret,
            self.refresh_token, self.customer_id,
        ])

    async def _get_access_token(self) -> Optional[str]:
        """Get or refresh the OAuth2 access token."""
        now = time.time()
        if self._access_token and now < self._token_expiry - 60:
            return self._access_token

        if not self.client_id or not self.client_secret or not self.refresh_token:
            return None

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                r = await client.post(
                    "https://oauth2.googleapis.com/token",
                    data={
                        "client_id": self.client_id,
                        "client_secret": self.client_secret,
                        "refresh_token": self.refresh_token,
                        "grant_type": "refresh_token",
                    },
                )
                if r.status_code >= 300:
                    log.warning(f"[google-ads] token refresh failed: {r.status_code}")
                    return None
                data = r.json()
                self._access_token = data.get("access_token")
                self._token_expiry = now + data.get("expires_in", 3600)
                return self._access_token
        except Exception as e:
            log.warning(f"[google-ads] token refresh error: {e}")
            return None

    async def get_campaign_performance(self, days: int = 30) -> Optional[list[dict]]:
        """
        Fetch campaign performance data from Google Ads.

        Uses the Google Ads API v17 search endpoint. Returns a list of
        dicts compatible with empire_traffic_ads_agent platform format,
        or None if not configured / API error.
        """
        if not self.configured:
            return None

        token = await self._get_access_token()
        if not token:
            return None

        # Build GAQL query for campaign performance
        query = (
            "SELECT "
            "campaign.id, campaign.name, campaign.status, "
            "campaign.advertising_channel_type, "
            "metrics.impressions, metrics.clicks, metrics.cost_micros, "
            "metrics.conversions, metrics.conversions_value, "
            "metrics.average_cpc, metrics.cost_per_conversion "
            "FROM campaign "
            "WHERE campaign.status != 'REMOVED' "
            "AND segments.date DURING LAST_30_DAYS "
            "ORDER BY metrics.impressions DESC "
            "LIMIT 50"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "developer-token": self.dev_token,
            "Content-Type": "application/json",
        }
        if self.login_customer_id:
            headers["login-customer-id"] = self.login_customer_id

        url = (
            f"https://googleads.googleapis.com/v17/customers/"
            f"{self.customer_id}/googleAds:search"
        )

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, headers=headers, json={"query": query})
                if r.status_code >= 400:
                    log.warning(f"[google-ads] API error {r.status_code}: {r.text[:200]}")
                    return None

                data = r.json()
                results = data.get("results", [])
                if not results:
                    log.info("[google-ads] No campaign results returned")
                    return None

                platforms = []
                for row in results:
                    campaign = row.get("campaign", {})
                    metrics = row.get("metrics", {})

                    name = campaign.get("name", "Unknown")
                    status = campaign.get("status", "UNKNOWN").lower()
                    channel_type = campaign.get("advertisingChannelType", "SEARCH")

                    cost_micros = int(metrics.get("costMicros", 0) or 0)
                    cost = cost_micros / 1_000_000
                    impressions = int(metrics.get("impressions", 0) or 0)
                    clicks = int(metrics.get("clicks", 0) or 0)
                    conversions = int(float(metrics.get("conversions", 0) or 0))
                    conv_value = float(metrics.get("conversionsValue", 0) or 0)
                    avg_cpc = cost / max(clicks, 1)
                    cpa = cost / max(conversions, 1) if conversions else None
                    roas = round(conv_value / max(cost, 1), 2) if cost > 0 and conv_value > 0 else None

                    # Icon by channel type
                    icons = {
                        "SEARCH": "🔍", "DISPLAY": "🖼️", "VIDEO": "🎬",
                        "SHOPPING": "🛒", "PERFORMANCE_MAX": "🚀",
                    }

                    platforms.append({
                        "id": f"gads-{campaign.get('id', '?')}",
                        "name": f"Google: {name}",
                        "type": "ppc",
                        "icon": icons.get(channel_type, "🔍"),
                        "budget_monthly": round(cost * 1.2, 2),  # estimate
                        "budget_spent": round(cost, 2),
                        "impressions": impressions,
                        "clicks": clicks,
                        "conversions": conversions,
                        "cost_per_click": round(avg_cpc, 2),
                        "cost_per_acquisition": round(cpa, 2) if cpa else None,
                        "revenue": round(conv_value, 2),
                        "roas": roas,
                        "status": "active" if status == "enabled" else status,
                        "source": "google_ads_api",
                    })

                log.info(f"[google-ads] Fetched {len(platforms)} campaigns")
                return platforms

        except Exception as e:
            log.warning(f"[google-ads] fetch error: {e}")
            return None

    async def get_account_summary(self) -> Optional[dict]:
        """Get a summary of the Google Ads account."""
        if not self.configured:
            return None

        token = await self._get_access_token()
        if not token:
            return None

        query = (
            "SELECT "
            "customer.descriptive_name, customer.currency_code, "
            "metrics.impressions, metrics.clicks, metrics.cost_micros, "
            "metrics.conversions, metrics.conversions_value "
            "FROM customer "
            "WHERE segments.date DURING LAST_30_DAYS"
        )

        headers = {
            "Authorization": f"Bearer {token}",
            "developer-token": self.dev_token,
            "Content-Type": "application/json",
        }
        if self.login_customer_id:
            headers["login-customer-id"] = self.login_customer_id

        url = (
            f"https://googleads.googleapis.com/v17/customers/"
            f"{self.customer_id}/googleAds:search"
        )

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(url, headers=headers, json={"query": query})
                if r.status_code >= 400:
                    return None
                data = r.json()
                results = data.get("results", [])
                if not results:
                    return None

                row = results[0]
                customer = row.get("customer", {})
                metrics = row.get("metrics", {})
                cost = int(metrics.get("costMicros", 0) or 0) / 1_000_000

                return {
                    "account_name": customer.get("descriptiveName", "Unknown"),
                    "currency": customer.get("currencyCode", "USD"),
                    "impressions": int(metrics.get("impressions", 0) or 0),
                    "clicks": int(metrics.get("clicks", 0) or 0),
                    "cost": round(cost, 2),
                    "conversions": int(float(metrics.get("conversions", 0) or 0)),
                    "revenue": round(float(metrics.get("conversionsValue", 0) or 0), 2),
                    "source": "google_ads_api",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
        except Exception as e:
            log.warning(f"[google-ads] account_summary error: {e}")
            return None


# ── SINGLETON ────────────────────────────────────────────────────────
_connector: Optional[GoogleAdsConnector] = None


def get_google_ads_connector() -> GoogleAdsConnector:
    global _connector
    if _connector is None:
        _connector = GoogleAdsConnector()
    return _connector


# ── CLI ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import asyncio
    import sys

    if "--auth" in sys.argv:
        print("""
╔══════════════════════════════════════════════════════════╗
║  GOOGLE ADS API — OAuth2 Setup                          ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  1. Go to Google Cloud Console:                          ║
║     https://console.cloud.google.com/apis/credentials   ║
║                                                          ║
║  2. Create an OAuth2 Client ID (Desktop application)    ║
║     Set redirect URI: http://localhost:8080              ║
║                                                          ║
║  3. Enable the Google Ads API:                           ║
║     https://console.cloud.google.com/apis/library/      ║
║     googleads.googleapis.com                             ║
║                                                          ║
║  4. Get your Developer Token:                            ║
║     https://ads.google.com/aw/apicenter                  ║
║                                                          ║
║  5. Get your Customer ID (10 digits, e.g. 1234567890)   ║
║     From Google Ads → Account Settings                  ║
║                                                          ║
║  6. Set these in /root/.env:                             ║
║     GOOGLE_ADS_DEVELOPER_TOKEN=...                       ║
║     GOOGLE_ADS_CLIENT_ID=...                             ║
║     GOOGLE_ADS_CLIENT_SECRET=...                         ║
║     GOOGLE_ADS_REFRESH_TOKEN=...                         ║
║     GOOGLE_ADS_LOGIN_CUSTOMER_ID=... (manager account)   ║
║     GOOGLE_ADS_CUSTOMER_ID=... (ad account)              ║
║                                                          ║
║  7. Run --test to verify the connection                  ║
╚══════════════════════════════════════════════════════════╝
""")
    elif "--test" in sys.argv:
        async def _test():
            conn = get_google_ads_connector()
            if not conn.configured:
                print("NOT CONFIGURED — missing credentials in /root/.env")
                print(f"  dev_token: {'✓' if conn.dev_token else '✗'}")
                print(f"  client_id: {'✓' if conn.client_id else '✗'}")
                print(f"  client_secret: {'✓' if conn.client_secret else '✗'}")
                print(f"  refresh_token: {'✓' if conn.refresh_token else '✗'}")
                print(f"  customer_id: {'✓' if conn.customer_id else '✗'}")
                return
            print(f"Configured — fetching campaigns...")
            campaigns = await conn.get_campaign_performance()
            if campaigns:
                print(json.dumps(campaigns, indent=2, default=str))
            else:
                print("No campaign data returned (API error or no campaigns)")
        asyncio.run(_test())
    else:
        conn = get_google_ads_connector()
        print(f"Google Ads Connector: {'CONFIGURED' if conn.configured else 'NOT CONFIGURED'}")
