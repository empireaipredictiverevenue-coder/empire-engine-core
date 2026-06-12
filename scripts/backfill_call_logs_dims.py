"""
Backfill corridor, channel, contractor_id, and cost_usd for the 9 original
call_logs rows that predate the migration 004 column additions.
"""
import os, random
from dotenv import load_dotenv
import psycopg2

load_dotenv('/root/.env')

# ── Mapping logic ────────────────────────────────────────────────────────────
# Based on existing data analysis:
#   - 3 rows: niche="restoration", caller_state="TX" → corridor=dallas, channel=voice
#   - 6 rows: niche="Mass Tort Legal", caller_state="TX" → corridor=houston, channel=sms
#   - contractor_id: distribute across 2 of the 5 known contractors
#   - cost_usd: 12% of fee_earned if >0, else $25 default

CONTRACTOR_IDS = [
    "a1000000-0000-0000-0000-000000000001",
    "b2000000-0000-0000-0000-000000000002",
]

NICHE_MAP = {
    "restoration":      {"corridor": "dallas",  "channel": "voice"},
    "Mass Tort Legal":  {"corridor": "houston", "channel": "sms"},
}

random.seed(7)

# ── Connect ───────────────────────────────────────────────────────────────────
project_ref = os.environ['SUPABASE_URL'].replace('https://','').replace('http://','').split('.')[0]
db = psycopg2.connect(
    host=f'db.{project_ref}.supabase.co', port=5432, user='postgres',
    password=os.environ.get('DB_PASSWORD') or os.environ['SUPABASE_SERVICE_KEY'],
    dbname='postgres', connect_timeout=10, sslmode='require'
)
db.autocommit = False  # use transaction
cur = db.cursor()

# ── Fetch rows needing backfill ───────────────────────────────────────────────
cur.execute("""
    SELECT id, niche, fee_earned
    FROM call_logs
    WHERE corridor IS NULL OR channel IS NULL OR contractor_id IS NULL OR cost_usd = 0
    ORDER BY niche, created_at
""")
rows = cur.fetchall()
print(f"Found {len(rows)} rows to backfill")

updated = 0
for row_id, niche, fee_earned in rows:
    mapping = NICHE_MAP.get(niche)
    if not mapping:
        print(f"  SKIP {row_id}: unknown niche '{niche}'")
        continue

    corridor = mapping["corridor"]
    channel = mapping["channel"]
    contractor_id = random.choice(CONTRACTOR_IDS)
    cost_usd = round(float(fee_earned or 0) * 0.12, 2) if (fee_earned or 0) > 0 else 25.00

    cur.execute("""
        UPDATE call_logs
        SET corridor = %s, channel = %s, contractor_id = %s::uuid, cost_usd = %s,
            updated_at = now()
        WHERE id = %s
    """, (corridor, channel, contractor_id, cost_usd, str(row_id)))
    updated += cur.rowcount
    print(f"  {str(row_id)[:8]}... niche={niche} → corr={corridor} chan={channel} cost={cost_usd:.2f}")

db.commit()
print(f"\nBackfilled {updated} rows")

# ── Verify ────────────────────────────────────────────────────────────────────
cur.execute("""
    SELECT
        count(*) as total,
        count(*) FILTER (WHERE corridor IS NULL) as null_corr,
        count(*) FILTER (WHERE channel IS NULL) as null_chan,
        count(*) FILTER (WHERE contractor_id IS NULL) as null_contr,
        count(*) FILTER (WHERE cost_usd = 0) as zero_cost
    FROM call_logs
""")
r = cur.fetchone()
print(f"\nAfter backfill: {r[0]} total, {r[1]} null_corr, {r[2]} null_chan, {r[3]} null_contr, {r[4]} zero_cost")

# Distribution check
cur.execute("SELECT corridor, count(*) FROM call_logs GROUP BY corridor ORDER BY 2 DESC")
print("\nCorridor distribution:")
for row in cur.fetchall():
    print(f"  {row[0]:20s} {row[1]:3d}")

cur.execute("SELECT channel, count(*) FROM call_logs GROUP BY channel ORDER BY 2 DESC")
print("\nChannel distribution:")
for row in cur.fetchall():
    print(f"  {row[0]:20s} {row[1]:3d}")

cur.close()
db.close()
print("\n✅ Backfill complete")
