#!/usr/bin/env python3
"""
Run SQL migration files against Supabase PostgreSQL database.

Usage:
  python3 scripts/run_migrations.py                          # auto-discover via glob
  python3 scripts/run_migrations.py --list                   # show discovered migrations + order
  python3 scripts/run_migrations.py --status                 # show applied vs pending vs drift
  python3 scripts/run_migrations.py migrations/005_*.sql     # explicit file(s)

Migrations are auto-discovered from migrations/*.sql (sorted by filename)
when no arguments are passed. Adding a new 00N_*.sql file to migrations/
is enough to register it — no code changes needed. The --list flag
prints the discovered order + statement count + file size so operators
can spot misnamed or out-of-order files without reading the source.

The --status flag queries the schema_migrations tracking table and shows
which discovered migrations have been applied (have a row), which are
pending (in glob but no row), and which are drift (in DB but not on disk).
A schema_migrations table is auto-created on first run; one INSERT per
applied file. Idempotent.
"""
import os, sys, re, glob

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

import psycopg2
from psycopg2 import sql

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_SERVICE_KEY = os.environ.get("SUPABASE_SERVICE_KEY", "")

# Extract project ref from URL
# https://owbeinlfcfdtwcwrttjy.supabase.co -> owbeinlfcfdtwcwrttjy
PROJECT_REF = SUPABASE_URL.replace("https://", "").replace("http://", "").split(".")[0]
DB_HOST = f"db.{PROJECT_REF}.supabase.co"
DB_PORT = 5432
DB_USER = "postgres"
DB_NAME = "postgres"

# Tracking table for --status. One row per applied migration filename.
MIGRATIONS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    filename   text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);
"""


def parse_sql_statements(content):
    """Split SQL content into individual statements, respecting semicolons in strings and blocks."""
    statements = []
    current = []
    paren_depth = 0
    in_string = False
    string_char = None

    for char in content:
        current.append(char)

        # Track string boundaries
        if char in ("'", '"') and (len(current) < 2 or current[-2] != '\\'):
            if not in_string:
                in_string = True
                string_char = char
            elif char == string_char:
                in_string = False
                string_char = None

        # Track parentheses (only outside strings)
        if not in_string:
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif char == ';' and paren_depth == 0:
                stmt = ''.join(current).strip()
                # Skip pure comments or empty statements
                if stmt and not stmt.startswith('--') and stmt != ';':
                    # Filter out pure comment lines from the statement
                    lines = stmt.split('\n')
                    filtered_lines = [l for l in lines if not l.strip().startswith('--')]
                    clean_stmt = '\n'.join(filtered_lines).strip()
                    if clean_stmt and clean_stmt != ';':
                        statements.append(clean_stmt)
                current = []

    # Handle trailing statement without semicolon
    remaining = ''.join(current).strip()
    if remaining and remaining != ';':
        lines = remaining.split('\n')
        filtered_lines = [l for l in lines if not l.strip().startswith('--')]
        clean = '\n'.join(filtered_lines).strip()
        if clean:
            statements.append(clean)

    return statements


def list_migrations():
    """Print all discovered migrations in execution order without running them.

    Used by --list to verify the glob picks up new migrations. Prints
    order + statement count + file size so operators can spot misnamed
    or out-of-order files. Does NOT make any DB calls.
    """
    files = sorted(glob.glob("migrations/*.sql"))
    if not files:
        print("No migrations found in migrations/*.sql")
        return
    print(f"Discovered {len(files)} migration(s) (in execution order):\n")
    for i, filepath in enumerate(files, 1):
        with open(filepath) as fh:
            content = fh.read()
        n = len(parse_sql_statements(content))
        size_kb = os.path.getsize(filepath) / 1024
        print(f"  {i:2}. {filepath}  ({n} statements, {size_kb:.1f} KB)")


def _connect():
    """Open a fresh psycopg2 connection. Caller closes."""
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=SUPABASE_SERVICE_KEY,
        dbname=DB_NAME,
        connect_timeout=10,
        sslmode='require',
    )


def _ensure_migrations_table(cur):
    """Idempotent: create the schema_migrations tracking table if missing."""
    cur.execute(MIGRATIONS_TABLE_DDL)
    print("✓ schema_migrations table ready")


def _fetch_applied(cur) -> dict:
    """Return {filename: applied_at_iso} for every row in schema_migrations."""
    cur.execute("SELECT filename, applied_at FROM schema_migrations")
    return {row[0]: row[1].isoformat() if row[1] else "" for row in cur.fetchall()}


def status_migrations():
    """Compare discovered migrations (on disk) to applied migrations (in DB).

    Three buckets:
      APPLIED  — filename in BOTH disk and DB
      PENDING  — filename on disk, NOT in DB (needs to be run)
      DRIFT    — filename in DB, NOT on disk (manually deleted or renamed)

    Makes a single connection to the DB to read schema_migrations.
    Does NOT execute any migration.
    """
    files = sorted(glob.glob("migrations/*.sql"))
    conn = None
    try:
        print(f"Connecting to {DB_HOST}...")
        conn = _connect()
        conn.autocommit = True
        cur = conn.cursor()
        _ensure_migrations_table(cur)
        applied = _fetch_applied(cur)
        on_disk = {os.path.basename(f): f for f in files}

        applied_basenames = set(applied.keys())
        on_disk_basenames = set(on_disk.keys())

        pending = sorted(on_disk_basenames - applied_basenames)
        drift   = sorted(applied_basenames - on_disk_basenames)
        ok      = sorted(on_disk_basenames & applied_basenames)

        print()
        print(f"On disk: {len(on_disk_basenames)}  |  Applied: {len(applied_basenames)}")
        print(f"  APPLIED: {len(ok)}")
        for fn in ok:
            ts = applied[fn][:19]  # trim microseconds + tz for compactness
            print(f"    ✓ {fn}  (applied {ts} UTC)")
        print(f"  PENDING: {len(pending)}  ← needs to be run")
        for fn in pending:
            print(f"    → {fn}")
        if drift:
            print(f"  DRIFT: {len(drift)}  (in DB but not on disk — file was deleted/renamed)")
            for fn in drift:
                print(f"    ⚠ {fn}  (recorded at {applied[fn][:19]})")
        print()
        if pending:
            print(f"Run: python3 scripts/run_migrations.py   (will apply {len(pending)} pending)")
        else:
            print("✓ All discovered migrations are applied. Nothing to do.")
        cur.close()
    except psycopg2.OperationalError as e:
        print(f"\n❌ Connection failed: {e}")
        print("Troubleshooting tips:")
        print("  1. The SERVICE_KEY may not be the DB password. Try setting DB_PASSWORD in /root/.env")
        print("  2. Check that the IP is allowed in Supabase Dashboard > Database > Settings")
        sys.exit(1)
    finally:
        if conn:
            conn.close()


def _record_migration(cur, filename: str):
    """Insert a row marking this migration as applied. Idempotent (ON CONFLICT)."""
    cur.execute(
        "INSERT INTO schema_migrations (filename) VALUES (%s) ON CONFLICT (filename) DO NOTHING",
        (filename,),
    )


def run_migrations(files):
    conn = None
    try:
        print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
        conn = _connect()
        conn.autocommit = True
        cur = conn.cursor()
        print("Connected successfully!")

        _ensure_migrations_table(cur)
        applied_already = _fetch_applied(cur)

        for filepath in files:
            if not os.path.exists(filepath):
                print(f"\n❌ File not found: {filepath}")
                continue

            basename = os.path.basename(filepath)
            if basename in applied_already:
                print(f"\n⏭  Skipping {basename}  (already applied {applied_already[basename][:19]})")
                continue

            print(f"\n{'='*60}")
            print(f"Running: {filepath}")
            print(f"{'='*60}")

            with open(filepath, 'r') as f:
                content = f.read()

            statements = parse_sql_statements(content)
            print(f"Parsed {len(statements)} SQL statements")

            file_failed = False
            for i, stmt in enumerate(statements, 1):
                # Get first line for display
                first_line = stmt.split('\n')[0][:80]
                print(f"  [{i}/{len(statements)}] {first_line}...")

                try:
                    cur.execute(stmt)
                    # Check if it's a SELECT and print results
                    if cur.description:
                        rows = cur.fetchall()
                        if rows:
                            for row in rows[:5]:
                                print(f"    → {row}")
                            if len(rows) > 5:
                                print(f"    → ... and {len(rows) - 5} more rows")
                except Exception as e:
                    # For CREATE TABLE IF NOT EXISTS and CREATE INDEX IF NOT EXISTS,
                    # errors about existing objects are fine
                    err_msg = str(e)
                    if 'already exists' in err_msg.lower():
                        print(f"    ✓ Already exists (skipped)")
                    elif 'does not exist' in err_msg.lower() and 'DROP' not in stmt.upper():
                        print(f"    ⚠ {err_msg[:120]}")
                    else:
                        print(f"    ❌ Error: {err_msg[:150]}")
                        file_failed = True

            if not file_failed:
                _record_migration(cur, basename)
                print(f"  📝 Recorded {basename} in schema_migrations")
            else:
                print(f"  ⚠  NOT recorded in schema_migrations (file had errors above)")

        cur.close()
        print(f"\n{'='*60}")
        print("All migrations complete!")

    except psycopg2.OperationalError as e:
        print(f"\n❌ Connection failed: {e}")
        print(f"\nTroubleshooting tips:")
        print(f"  1. The SERVICE_KEY may not be the DB password. Try setting DB_PASSWORD in /root/.env")
        print(f"  2. Check that the IP is allowed in Supabase Dashboard > Database > Settings")
        print(f"  3. The connection string format is: postgresql://postgres:[PASSWORD]@db.{PROJECT_REF}.supabase.co:5432/postgres")
        sys.exit(1)
    finally:
        if conn:
            conn.close()

if __name__ == "__main__":
    args = sys.argv[1:]

    # --list flag: print discovered migrations + order, then exit (no DB calls)
    if "--list" in args:
        list_migrations()
        sys.exit(0)

    # --status flag: compare discovered (on disk) to applied (in DB), then exit
    if "--status" in args:
        status_migrations()
        sys.exit(0)

    if args:
        # User passed explicit migration file(s)
        files = args
    else:
        # Auto-discover all .sql files in migrations/ (sorted by filename)
        files = sorted(glob.glob("migrations/*.sql"))
        if not files:
            print("No migrations found in migrations/*.sql")
            print("Either create some or pass explicit file paths.")
            sys.exit(1)

    run_migrations(files)
