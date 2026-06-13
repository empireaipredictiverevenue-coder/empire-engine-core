#!/usr/bin/env python3
"""
Seed bridge_sessions with test data for Bridge View dashboard testing.
Inserts ~15 sessions with realistic transcript data spread across the
last 48 hours, simulating operator voice commands.

Usage:
    python3 scripts/seed_bridge_sessions.py

Dependencies:
    pip install psycopg2-binary python-dotenv
"""

import os
import random
import uuid
import json
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
import psycopg2

load_dotenv("/root/.env")

NOW = datetime.now(timezone.utc)

# ── Sample operators ───────────────────────────────────────────────────
OPERATOR_IDS = [
    "2dc46865-d997-4ed3-b321-92b3c952e8bd",  # Empire Owner
]

# ── Sample command scripts ─────────────────────────────────────────────
SAMPLE_SESSIONS = [
    {
        "minutes_ago": (10, 30),
        "commands": [
            ("user", "show hot leads in Dallas"),
            ("assistant", "Top leads:\n**ABC Logistics** at 1234 Main St, Dallas — severity=Severe · $2,500,000\n**Fast Ship** at 567 Oak Ave, Dallas — severity=Extreme · $4,100,000\n**Metro Storage** at 890 Elm St, Dallas — severity=Severe · $1,800,000"),
            ("user", "call +12145551234"),
            ("assistant", "Call placed. Brain says GO with 85% confidence."),
            ("user", "system status"),
            ("assistant", "System online. 47 outbound calls, 23 inbound. 2 active calls. Memory=enabled."),
        ],
        "actions": 3,
    },
    {
        "minutes_ago": (60, 120),
        "commands": [
            ("user", "what's my revenue today?"),
            ("assistant", "Revenue pulse is strong. Check the Pulse tab for full breakdown."),
            ("user", "help"),
            ("assistant", "Try: 'call +12145551234', 'show hot leads in Dallas', 'what's my revenue?', 'system status', or 'approve payout <id>'."),
        ],
        "actions": 0,
    },
    {
        "minutes_ago": (180, 360),
        "commands": [
            ("user", "show hot leads in Houston"),
            ("assistant", "Top leads:\n**Gulf Logistics** at 100 Shipping Ln, Houston — severity=Extreme · $5,200,000\n**Bayou Warehouse** at 200 Canal St, Houston — severity=Severe · $3,100,000\n**Port Storage** at 300 Harbor Dr, Houston — severity=Moderate · $950,000"),
            ("user", "system status"),
            ("assistant", "System online. 42 outbound calls, 19 inbound. 0 active calls. Memory=enabled."),
            ("user", "call +18325551234"),
            ("assistant", "Brain declined — NO_GO. Call not placed."),
        ],
        "actions": 1,
    },
    {
        "minutes_ago": (400, 600),
        "commands": [
            ("user", "system status"),
            ("assistant", "System online. 38 outbound calls, 15 inbound. 1 active call. Memory=enabled."),
        ],
        "actions": 0,
    },
    {
        "minutes_ago": (700, 1000),
        "commands": [
            ("user", "show hot leads in Fort Worth"),
            ("assistant", "Top leads:\n**Cowtown Distribution** at 500 Stockyards Blvd, Fort Worth — severity=Severe · $3,400,000\n**Alliance Logistics** at 600 Trade Center Dr, Fort Worth — severity=Extreme · $6,100,000"),
            ("user", "call +18175551234"),
            ("assistant", "Call placed. Brain says GO with 92% confidence."),
        ],
        "actions": 2,
    },
    {
        "minutes_ago": (1000, 1440),
        "commands": [
            ("user", "help"),
            ("assistant", "Try: 'call +12145551234', 'show hot leads in Dallas', 'what's my revenue?', 'system status', or 'approve payout <id>'."),
            ("user", "show hot leads in San Antonio"),
            ("assistant", "Top leads:\n**Alamo Storage** at 700 Riverwalk, San Antonio — severity=Severe · $2,800,000\n**South TX Logistics** at 800 Commerce St, San Antonio — severity=Moderate · $1,200,000"),
            ("user", "system status"),
            ("assistant", "System online. 35 outbound calls, 12 inbound. 0 active calls. Memory=enabled."),
            ("user", "call +12105551234"),
            ("assistant", "Call placed. Brain says GO with 78% confidence."),
        ],
        "actions": 2,
    },
    {
        "minutes_ago": (1440, 2000),
        "commands": [
            ("user", "system status"),
            ("assistant", "System online. 31 outbound calls, 10 inbound. 0 active calls. Memory=enabled."),
        ],
        "actions": 0,
    },
    {
        "minutes_ago": (30, 60),
        "commands": [
            ("user", "what's my revenue today?"),
            ("assistant", "Revenue pulse is strong. Check the Pulse tab for full breakdown."),
            ("user", "show hot leads in Oklahoma City"),
            ("assistant", "Top leads:\n**Plains Logistics** at 1000 Frontier Ave, Oklahoma City — severity=Severe · $2,100,000\n**OKC Storage** at 1100 Industrial Blvd, Oklahoma City — severity=Moderate · $850,000"),
        ],
        "actions": 0,
    },
    {
        "minutes_ago": (2000, 2880),
        "commands": [
            ("user", "system status"),
            ("assistant", "System online. 25 outbound calls, 8 inbound. 0 active calls. Memory=enabled."),
            ("user", "call +14055551234"),
            ("assistant", "Brain declined — NO_GO. Call not placed."),
        ],
        "actions": 0,
    },
    {
        "minutes_ago": (5, 15),
        "commands": [
            ("user", "show hot leads in Austin"),
            ("assistant", "Top leads:\n**Tech Storage** at 200 Congress Ave, Austin — severity=Extreme · $4,500,000\n**Hill Country Logistics** at 300 Barton Springs, Austin — severity=Severe · $2,900,000"),
            ("user", "call +15125551234"),
            ("assistant", "Call placed. Brain says GO with 88% confidence."),
            ("user", "system status"),
            ("assistant", "System online. 48 outbound calls, 24 inbound. 1 active call. Memory=enabled."),
        ],
        "actions": 2,
    },
    {
        "minutes_ago": (120, 240),
        "commands": [
            ("user", "help"),
            ("assistant", "Try: 'call +12145551234', 'show hot leads in Dallas', 'what's my revenue?', 'system status', or 'approve payout <id>'."),
        ],
        "actions": 0,
    },
    {
        "minutes_ago": (500, 800),
        "commands": [
            ("user", "system status"),
            ("assistant", "System online. 28 outbound calls, 11 inbound. 0 active calls. Memory=enabled."),
            ("user", "call +19725551234"),
            ("assistant", "Call placed. Brain says GO with 82% confidence."),
            ("user", "show hot leads in Minneapolis"),
            ("assistant", "No leads found matching that criteria."),
        ],
        "actions": 1,
    },
    {
        "minutes_ago": (1500, 2500),
        "commands": [
            ("user", "system status"),
            ("assistant", "System online. 22 outbound calls, 6 inbound. 0 active calls. Memory=enabled."),
        ],
        "actions": 0,
    },
    {
        "minutes_ago": (40, 90),
        "commands": [
            ("user", "approve payout abc123"),
            ("assistant", "Approval requires a specific payout ID. Try 'approve payout abc123'."),
            ("user", "call +19145551234"),
            ("assistant", "Call placed. Brain says GO with 75% confidence."),
            ("user", "system status"),
            ("assistant", "System online. 45 outbound calls, 21 inbound. 2 active calls. Memory=enabled."),
        ],
        "actions": 1,
    },
    {
        "minutes_ago": (1200, 1800),
        "commands": [
            ("user", "show hot leads in Dallas"),
            ("assistant", "Top leads:\n**Dallas Logistics** at 1500 Commerce St, Dallas — severity=Severe · $3,800,000\n**Metro Storage** at 1600 Main St, Dallas — severity=Moderate · $1,100,000"),
            ("user", "system status"),
            ("assistant", "System online. 33 outbound calls, 13 inbound. 0 active calls. Memory=enabled."),
        ],
        "actions": 0,
    },
]


def build_transcript(commands):
    """Build a transcript array from (role, text) pairs with timestamps."""
    transcript = []
    base = NOW - timedelta(minutes=60)
    for i, (role, text) in enumerate(commands):
        transcript.append({
            "role": role,
            "text": text,
            "timestamp": (base + timedelta(seconds=i * 45)).isoformat(),
        })
    return transcript


# ── DB Connection ──────────────────────────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")
PROJECT_REF = SUPABASE_URL.replace("https://", "").replace("http://", "").split(".")[0]
DB_HOST = f"db.{PROJECT_REF}.supabase.co"
DB_PORT = 5432
DB_USER = "postgres"
DB_NAME = "postgres"
DB_PASSWORD = os.environ.get("DB_PASSWORD") or SUPABASE_SERVICE_KEY

print(f"Connecting to {DB_HOST}...")
conn = psycopg2.connect(
    host=DB_HOST, port=DB_PORT,
    user=DB_USER, password=DB_PASSWORD,
    dbname=DB_NAME, connect_timeout=10,
    sslmode="require",
)
conn.autocommit = True
cur = conn.cursor()

# ── Check existing count ──────────────────────────────────────────────
cur.execute("SELECT count(*) FROM bridge_sessions")
before = cur.fetchone()[0]
print(f"Existing bridge_sessions rows: {before}")

# ── Insert sessions ───────────────────────────────────────────────────
inserted = 0
for i, session_spec in enumerate(SAMPLE_SESSIONS):
    session_id = str(uuid.uuid4())
    op_id = OPERATOR_IDS[i % len(OPERATOR_IDS)]

    # Random start time within minutes_ago
    mins_ago = random.randint(*session_spec["minutes_ago"]) if isinstance(session_spec["minutes_ago"], tuple) else session_spec["minutes_ago"]
    created_at = (NOW - timedelta(minutes=mins_ago)).isoformat()

    # End time: 2-15 minutes after start
    duration_min = random.randint(2, 15)
    ended_at = (NOW - timedelta(minutes=mins_ago - duration_min)).isoformat()

    transcript = build_transcript(session_spec["commands"])
    commands_count = len([e for e in session_spec["commands"] if e[0] == "user"])
    actions_taken = session_spec["actions"]

    # Meta
    meta = json.dumps({
        "entry_point": "nav_click",
        "browser": "Chrome",
        "initial_command": session_spec["commands"][0][1][:60] if session_spec["commands"] else "",
    })

    try:
        cur.execute("""
            INSERT INTO bridge_sessions
                (id, created_at, ended_at, operator_id,
                 duration_sec, actions_taken, commands_count,
                 transcript, meta)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (
            session_id, created_at, ended_at, op_id,
            duration_min * 60, actions_taken, commands_count,
            json.dumps(transcript), meta,
        ))
        inserted += 1
    except Exception as e:
        print(f"  [{i}] Insert failed: {e}")

print(f"Inserted {inserted} sessions")

# ── Verify ─────────────────────────────────────────────────────────────
cur.execute("SELECT count(*) FROM bridge_sessions")
after = cur.fetchone()[0]
print(f"Total bridge_sessions rows: {after} (added {after - before})")

print("\n=== Distribution ===")
cur.execute("""
    SELECT
        count(*) as total,
        sum(commands_count) as total_commands,
        sum(actions_taken) as total_actions,
        avg(duration_sec)::int as avg_duration_sec,
        count(*) FILTER (WHERE ended_at IS NOT NULL) as completed,
        count(*) FILTER (WHERE ended_at IS NULL) as active
    FROM bridge_sessions
""")
r = cur.fetchone()
print(f"  Total sessions: {r[0]}")
print(f"  Total commands: {r[1]}")
print(f"  Total actions:  {r[2]}")
print(f"  Avg duration:   {r[3]}s")
print(f"  Completed:      {r[4]}")
print(f"  Active:         {r[5]}")

print("\n=== Recent sessions ===")
cur.execute("""
    SELECT id, created_at, commands_count, actions_taken, duration_sec
    FROM bridge_sessions
    ORDER BY created_at DESC
    LIMIT 5
""")
for r in cur.fetchall():
    print(f"  {r[0][:8]}... created={str(r[1])[:19]} cmds={r[2]} acts={r[3]} dur={r[4]}s")

cur.close()
conn.close()
print("\n✅ Done — bridge sessions seeded")
