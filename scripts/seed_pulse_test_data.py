"""
Seed call_logs with test data for pulse_rollup_hourly heatmap rendering.
Inserts ~120 rows spread across the last 7 days with varied dimensions.
"""
import os, random, uuid
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras
from psycopg2.extras import execute_values

psycopg2.extras.register_uuid()

load_dotenv('/root/.env')

# ── Config ──────────────────────────────────────────────────────────────
NOW = datetime.now(timezone.utc)
NICHES = [
    ("restoration", 30),
    ("Mass Tort Legal", 25),
    ("Roofing Restoration", 20),
    ("Flood Damage Restoration", 10),
    ("Hail Damage Repair", 8),
    ("Storm Damage Restoration", 5),
    ("Tornado Damage Repair", 2),
]
CHANNELS = [
    ("voice", 40),
    ("sms", 30),
    ("email", 15),
    ("web", 10),
    ("referral", 5),
]
CORRIDORS = [
    ("dallas", 30),
    ("houston", 25),
    ("austin", 20),
    ("san-antonio", 15),
    ("okc", 10),
]
CONTRACTORS = [
    uuid.UUID("a1000000-0000-0000-0000-000000000001"),
    uuid.UUID("b2000000-0000-0000-0000-000000000002"),
    uuid.UUID("c3000000-0000-0000-0000-000000000003"),
    uuid.UUID("d4000000-0000-0000-0000-000000000004"),
    uuid.UUID("e5000000-0000-0000-0000-000000000005"),
]
TOTAL_ROWS = 120

# ── Helpers ─────────────────────────────────────────────────────────────
def weighted_choice(items):
    """items: list of (value, weight)"""
    total = sum(w for _, w in items)
    r = random.uniform(0, total)
    cum = 0
    for val, w in items:
        cum += w
        if r <= cum:
            return val
    return items[-1][0]

def random_ts(minutes_ago_range):
    """Random timestamp between min and max minutes ago."""
    mins = random.randint(*minutes_ago_range)
    ts = NOW - timedelta(minutes=mins)
    # Round to nearest hour for clean hour_bucket grouping
    return ts.replace(minute=0, second=0, microsecond=0)

def gen_fee(niche):
    """Generate realistic fee_earned per niche."""
    base = {
        "restoration": (100, 500),
        "Mass Tort Legal": (200, 800),
        "Roofing Restoration": (150, 600),
        "Flood Damage Restoration": (120, 550),
        "Hail Damage Repair": (100, 400),
        "Storm Damage Restoration": (80, 450),
        "Tornado Damage Repair": (200, 700),
    }.get(niche, (50, 300))
    return round(random.uniform(*base), 2)

def gen_cost(niche):
    """Generate realistic cost_usd per call."""
    base = {
        "restoration": (10, 40),
        "Mass Tort Legal": (15, 60),
        "Roofing Restoration": (12, 45),
        "Flood Damage Restoration": (10, 35),
        "Hail Damage Repair": (8, 30),
        "Storm Damage Restoration": (10, 40),
        "Tornado Damage Repair": (15, 50),
    }.get(niche, (5, 25))
    return round(random.uniform(*base), 2)

# ── Generate rows ────────────────────────────────────────────────────────
random.seed(42)  # reproducible

rows = []
for i in range(TOTAL_ROWS):
    niche = weighted_choice(NICHES)
    channel = weighted_choice(CHANNELS)
    corridor = weighted_choice(CORRIDORS)
    contractor = random.choice(CONTRACTORS)
    fee = gen_fee(niche)
    cost = gen_cost(niche)
    is_billable = random.random() < 0.80  # 80% billable
    qualified = random.random() < 0.70  # 70% qualified

    # Spread across 7 days, with more data in last 48h for heatmap richness
    if i < 60:
        # Last 48 hours — dense heatmap
        minutes_ago = (1, 48 * 60)
    else:
        # Days 2-7 — sparser
        minutes_ago = (48 * 60 + 1, 7 * 24 * 60)

    created_at = NOW - timedelta(minutes=random.randint(*minutes_ago))
    # Round to hour for clean hour_bucket grouping
    created_at = created_at.replace(minute=0, second=0, microsecond=0)

    rows.append((
        niche, channel, corridor, contractor,
        fee, cost, is_billable, qualified,
        round(fee * 0.6, 2),  # payout_value = 60% of fee
        random.randint(30, 600),  # duration_seconds
        created_at,
    ))

print(f"Generated {len(rows)} seed rows")

# ── Insert into Supabase ─────────────────────────────────────────────────
project_ref = os.environ['SUPABASE_URL'].replace('https://','').replace('http://','').split('.')[0]
db = psycopg2.connect(
    host=f'db.{project_ref}.supabase.co', port=5432, user='postgres',
    password=os.environ.get('DB_PASSWORD') or os.environ['SUPABASE_SERVICE_KEY'],
    dbname='postgres', connect_timeout=10, sslmode='require'
)
db.autocommit = True
cur = db.cursor()

# Get existing count
cur.execute("SELECT count(*) FROM call_logs")
before = cur.fetchone()[0]
print(f"Existing call_logs rows: {before}")

# Insert in batch
sql = """
INSERT INTO call_logs (
    niche, channel, corridor, contractor_id,
    fee_earned, cost_usd, is_billable, qualified,
    payout_value, duration_seconds, created_at
) VALUES %s
"""
execute_values(cur, sql, rows, page_size=100)
print(f"Inserted {cur.rowcount} rows")

cur.execute("SELECT count(*) FROM call_logs")
after = cur.fetchone()[0]
print(f"Total call_logs rows: {after} (added {after - before})")

# ── Verify distribution ──────────────────────────────────────────────────
print("\n=== Niche distribution ===")
cur.execute("SELECT niche, count(*) FROM call_logs GROUP BY niche ORDER BY 2 DESC")
for r in cur.fetchall():
    print(f"  {r[0]:35s} {r[1]:4d}")

print("\n=== Channel distribution ===")
cur.execute("SELECT channel, count(*) FROM call_logs GROUP BY channel ORDER BY 2 DESC")
for r in cur.fetchall():
    print(f"  {r[0]:20s} {r[1]:4d}")

print("\n=== Corridor distribution ===")
cur.execute("SELECT corridor, count(*) FROM call_logs GROUP BY corridor ORDER BY 2 DESC")
for r in cur.fetchall():
    print(f"  {r[0]:20s} {r[1]:4d}")

print("\n=== Revenue summary ===")
cur.execute("""
    SELECT 
        count(*) as total,
        sum(fee_earned) as total_rev,
        sum(cost_usd) as total_cost,
        sum(fee_earned) - sum(cost_usd) as margin,
        count(*) FILTER (WHERE is_billable) as billable
    FROM call_logs
""")
r = cur.fetchone()
print(f"  Total: {r[0]}, Billable: {r[4]}")
print(f"  Revenue: ${r[1]:,.2f}, Cost: ${r[2]:,.2f}, Margin: ${r[3]:,.2f}")

cur.close()
db.close()
print("\n✅ Done — ready to refresh pulse_rollup_hourly")
