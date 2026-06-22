"""Appsmith · Empire AI Dashboard Bootstrapper
==============================================
One-shot script to set up the 4 Empire AI dashboards in Appsmith
via its REST API. Requires Appsmith running on localhost:3001 and
a valid session token (from browser login).

Usage:
  python3 scripts/bootstrap_appsmith.py --token <appsmith-session-token>

To get the token:
  1. Go to http://localhost:3001 and log in
  2. Open DevTools → Application → Cookies → copy SESSION cookie value
  3. Or: sign in via API and extract token

Dashboards created:
  1. Fee Collection Dashboard — fee_events table, payment status, amounts owed
  2. Contractor Management — contractors table, SMS history, metro filters
  3. Lead Pipeline Funnel — radar_targets → settled claims conversion funnel
  4. Agent Fleet Monitor — PM2 service status from /fleet-status API
"""

import argparse
import json
import os
import sys
import requests

APPSMITH_BASE = os.environ.get("APPSMITH_URL", "http://localhost:3001")


def get_supabase_creds():
    """Extract Supabase Postgres connection details from /root/.env."""
    env_path = "/root/.env"
    creds = {}
    with open(env_path) as f:
        for line in f:
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                k, v = k.strip(), v.strip().strip('"').strip("'")
                creds[k] = v

    supabase_url = creds.get("SUPABASE_URL", "")
    if "://" in supabase_url:
        host = supabase_url.split("://")[1].split("/")[0]
    else:
        host = "db.empire-ai.supabase.co"

    return {
        "host": host,
        "port": 6543,  # Supabase Postgres port (transaction pooler)
        "database": "postgres",
        "username": "postgres",
        "password": creds.get("DB_PASSWORD", ""),
    }


def api_request(token, method, path, data=None):
    """Make an authenticated Appsmith API request."""
    url = f"{APPSMITH_BASE}/api/v1/{path}"
    headers = {
        "Cookie": f"SESSION={token}",
        "Content-Type": "application/json",
    }
    if method == "GET":
        r = requests.get(url, headers=headers, timeout=10)
    elif method == "POST":
        r = requests.post(url, headers=headers, json=data, timeout=10)
    elif method == "PUT":
        r = requests.put(url, headers=headers, json=data, timeout=10)
    else:
        raise ValueError(f"Unknown method: {method}")
    return r


def create_datasource(token, name, db_config):
    """Create a PostgreSQL datasource in Appsmith."""
    print(f"  Creating datasource: {name}...")

    payload = {
        "name": name,
        "pluginId": "postgres-plugin",  # PostgreSQL plugin
        "datasourceConfiguration": {
            "endpoints": [
                {"host": db_config["host"], "port": db_config["port"]}
            ],
            "databaseName": db_config["database"],
            "authentication": {
                "authenticationType": "USERNAME_PASSWORD",
                "username": db_config["username"],
                "password": db_config["password"],
            },
            "connection": {"ssl": {"authType": "DEFAULT"}},
            "properties": [
                {"key": "sSLMode", "value": "require"},
            ],
        },
    }

    r = api_request(token, "POST", "datasources", payload)
    return r.json() if r.ok else r.text


# ── Dashboard query templates ──────────────────────────────────────────

DASHBOARD_QUERIES = {
    "fee_collection": {
        "pending_fees": """
            SELECT id, contractor_id, claim_id, fee_amount, claim_amount,
                   status, created_at
            FROM fee_events
            WHERE status != 'paid'
            ORDER BY fee_amount DESC
            LIMIT 50
        """,
        "fee_summary": """
            SELECT
                COUNT(*) as total_events,
                SUM(CASE WHEN status = 'paid' THEN 1 ELSE 0 END) as paid,
                SUM(CASE WHEN status = 'pending' THEN 1 ELSE 0 END) as pending,
                SUM(CASE WHEN status = 'overdue' THEN 1 ELSE 0 END) as overdue,
                SUM(fee_amount) as total_fees,
                SUM(claim_amount) as total_claims
            FROM fee_events
        """,
        "top_contractors_by_fee": """
            SELECT c.name, c.phone, SUM(fe.fee_amount) as total_owed,
                   COUNT(fe.id) as pending_count
            FROM fee_events fe
            JOIN contractors c ON c.id = fe.contractor_id
            WHERE fe.status != 'paid'
            GROUP BY c.id, c.name, c.phone
            ORDER BY total_owed DESC
            LIMIT 20
        """,
    },
    "contractor_management": {
        "all_contractors": """
            SELECT id, name, phone, email, metro, niche, status,
                   created_at, meta
            FROM contractors
            ORDER BY created_at DESC
            LIMIT 200
        """,
        "contractor_sms_history": """
            SELECT c.name, sms.direction, sms.body, sms.sent_at
            FROM sms_log sms
            JOIN contractors c ON c.phone = sms.to_phone
            WHERE c.id = {{ Table1.selectedRow.id }}
            ORDER BY sms.sent_at DESC
            LIMIT 50
        """,
        "contractors_by_metro": """
            SELECT metro, COUNT(*) as count,
                   COUNT(CASE WHEN status = 'active' THEN 1 END) as active
            FROM contractors
            GROUP BY metro
            ORDER BY count DESC
        """,
    },
    "pipeline_funnel": {
        "funnel_stages": """
            SELECT
                (SELECT COUNT(*) FROM radar_targets WHERE status = 'active') as radar_targets,
                (SELECT COUNT(*) FROM enriched_leads) as enriched_leads,
                (SELECT COUNT(*) FROM sms_log WHERE direction = 'outbound') as sms_sent,
                (SELECT COUNT(*) FROM sms_log WHERE direction = 'inbound' AND ai_classification = 'YES') as sms_replied_yes,
                (SELECT COUNT(*) FROM dispatches) as dispatched,
                (SELECT COUNT(*) FROM dispatches WHERE status = 'accepted') as accepted,
                (SELECT COUNT(*) FROM carrier_claims) as claims,
                (SELECT COUNT(*) FROM carrier_claims WHERE status = 'settled') as settled
        """,
        "daily_dispatches": """
            SELECT DATE(created_at) as date, COUNT(*) as count
            FROM dispatches
            WHERE created_at > NOW() - INTERVAL '30 days'
            GROUP BY DATE(created_at)
            ORDER BY date
        """,
        "revenue_by_niche": """
            SELECT
                COALESCE(c.niche, 'unknown') as niche,
                COUNT(d.id) as dispatches,
                SUM(CASE WHEN d.status = 'accepted' THEN 1 ELSE 0 END) as accepted,
                SUM(fe.fee_amount) as total_fees
            FROM dispatches d
            LEFT JOIN contractors c ON c.id = d.contractor_id
            LEFT JOIN fee_events fe ON fe.claim_id::text = d.id::text
            GROUP BY c.niche
            ORDER BY total_fees DESC NULLS LAST
        """,
    },
    "fleet_monitor": {
        # Fleet monitor uses REST API, not PostgreSQL
        "fleet_rest_api": "GET /api/v6/matrix/fleet-status",
    },
}


def main():
    parser = argparse.ArgumentParser(description="Bootstrap Appsmith dashboards")
    parser.add_argument("--token", required=True, help="Appsmith session cookie value")
    args = parser.parse_args()

    print("=" * 60)
    print("Empire AI · Appsmith Dashboard Bootstrapper")
    print("=" * 60)

    db_config = get_supabase_creds()
    print(f"\nDatabase: {db_config['host']}:{db_config['port']}")
    print(f"User: {db_config['username']}")

    # 1. Create datasource
    print("\n[1/5] Creating Supabase PostgreSQL datasource...")
    ds_result = create_datasource(args.token, "Empire Supabase", db_config)
    print(f"  Result: {json.dumps(ds_result, indent=2)[:300]}")

    # 2. List existing apps
    print("\n[2/5] Checking existing applications...")
    r = api_request(args.token, "GET", "applications")
    if r.ok:
        apps = r.json().get("data", [])
        print(f"  Found {len(apps)} existing apps")
        for app in apps:
            print(f"    - {app.get('name')} (id={app.get('id')})")

    # 3. Create the 4 dashboard applications
    dashboards = [
        ("Fee Collection", "fee_collection"),
        ("Contractor Management", "contractor_management"),
        ("Pipeline Funnel", "pipeline_funnel"),
        ("Fleet Monitor", "fleet_monitor"),
    ]

    created_apps = {}
    for name, key in dashboards:
        print(f"\n[3/5] Creating app: {name}...")
        r = api_request(args.token, "POST", "applications", {
            "name": name,
        })
        if r.ok:
            app = r.json().get("data", {})
            created_apps[key] = app
            print(f"  Created: id={app.get('id')}")
        else:
            print(f"  ERROR: {r.status_code} {r.text[:200]}")

    # 4. Print next steps
    print("\n" + "=" * 60)
    print("SETUP COMPLETE")
    print("=" * 60)
    print(f"\nGo to: {APPSMITH_BASE}")
    print(f"  → You'll see 4 new apps in your workspace\n")
    print("Next steps for each dashboard:")
    print()
    print("Fee Collection Dashboard:")
    print("  1. Open the app → Edit mode")
    print("  2. Add a Table widget → connect to 'pending_fees' query")
    print("  3. Add Stat widgets for: total_fees, pending count, paid count")
    print("  4. Query template:")
    for qname, qsql in DASHBOARD_QUERIES["fee_collection"].items():
        print(f"      {qname}:\n{qsql[:200]}...\n")

    print("Contractor Management:")
    print("  1. Table widget → 'all_contractors' query")
    print("  2. Add search/filter on metro, niche columns")
    print("  3. Drill-down: click a contractor → SMS history panel")
    print("  4. Bar chart: 'contractors_by_metro'\n")

    print("Pipeline Funnel:")
    print("  1. Funnel chart widget → 'funnel_stages' query")
    print("  2. Line chart: 'daily_dispatches' (30-day trend)")
    print("  3. Table: 'revenue_by_niche' (dispatches + fees per niche)\n")

    print("Fleet Monitor:")
    print("  1. REST API query → GET localhost:8001/api/v6/matrix/fleet-status")
    print("  2. Table widget → pm2_services array from response")
    print("  3. Stat widgets: total_services, online, stopped, overall signal")
    print("  4. Set auto-refresh to 30s\n")


if __name__ == "__main__":
    main()
