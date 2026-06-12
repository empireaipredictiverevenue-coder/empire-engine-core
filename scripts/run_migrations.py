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
    """Split SQL content into individual statements, respecting:
       - single-quoted strings ('...') with '' escapes
       - double-quoted identifiers ("...") with "" escapes
       - dollar-quoted blocks ($tag$...$tag$ or $$...$$)
       - line comments (-- ... to end of line)
       - block comments (/* ... */)
       - balanced parentheses (only top-level ; splits)
    """
    statements = []
    current = []
    paren_depth = 0
    i = 0
    n = len(content)
    in_single = False   # '...'
    in_double = False   # "..."
    in_dollar = False   # $tag$ ... $tag$
    dollar_tag = None   # e.g. "$$" or "$func$"
    in_line_comment = False
    in_block_comment = False

    def emit():
        stmt = ''.join(current).strip()
        current.clear()
        if not stmt or stmt == ';':
            return
        # Drop pure-comment lines; keep lines that have SQL on them
        lines = stmt.split('\n')
        kept = [ln for ln in lines if ln.strip() and not ln.strip().startswith('--')]
        clean = '\n'.join(kept).strip()
        if clean and clean != ';':
            statements.append(clean)

    while i < n:
        ch = content[i]
        nxt = content[i + 1] if i + 1 < n else ''

        # Line comment: -- to end of line
        if in_line_comment:
            current.append(ch)
            if ch == '\n':
                in_line_comment = False
            i += 1
            continue

        # Block comment: /* ... */
        if in_block_comment:
            current.append(ch)
            if ch == '*' and nxt == '/':
                current.append(nxt)
                in_block_comment = False
                i += 2
                continue
            i += 1
            continue

        # Inside a dollar-quoted block: look for the matching close tag
        if in_dollar:
            current.append(ch)
            if ch == '$' and content[i:i + len(dollar_tag)] == dollar_tag:
                # Append remaining tag chars and close
                tag_len = len(dollar_tag)
                current.extend(list(dollar_tag[1:]))
                in_dollar = False
                dollar_tag = None
                i += tag_len  # '$' already counted, advance past rest of tag
                continue
            i += 1
            continue

        # Inside a single-quoted string: '' is an escape
        if in_single:
            current.append(ch)
            if ch == "'" and nxt == "'":
                current.append(nxt)
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue

        # Inside a double-quoted identifier: "" is an escape
        if in_double:
            current.append(ch)
            if ch == '"' and nxt == '"':
                current.append(nxt)
                i += 2
                continue
            if ch == '"':
                in_double = False
            i += 1
            continue

        # Not in any string/comment. Look for openings.
        if ch == '-' and nxt == '-':
            current.append(ch)
            current.append(nxt)
            in_line_comment = True
            i += 2
            continue

        if ch == '/' and nxt == '*':
            current.append(ch)
            current.append(nxt)
            in_block_comment = True
            i += 2
            continue

        if ch == "'":
            current.append(ch)
            in_single = True
            i += 1
            continue

        if ch == '"':
            current.append(ch)
            in_double = True
            i += 1
            continue

        # Dollar-quote open: read $tag$ where tag is [A-Za-z0-9_]* (or empty)
        if ch == '$':
            j = i + 1
            tag_chars = []
            while j < n and (content[j].isalnum() or content[j] == '_'):
                tag_chars.append(content[j])
                j += 1
            if j < n and content[j] == '$':
                # Real dollar-quote opener
                current.append(ch)
                current.extend(tag_chars)
                current.append('$')
                in_dollar = True
                dollar_tag = '$' + ''.join(tag_chars) + '$'
                i = j + 1
                continue
            # Not a dollar-quote opener (e.g. $1 parameter) — treat as normal char
            current.append(ch)
            i += 1
            continue

        # Parentheses
        if ch == '(':
            paren_depth += 1
        elif ch == ')':
            paren_depth -= 1

        current.append(ch)

        # Statement terminator (top-level ; outside any quote/comment/parens)
        if ch == ';' and paren_depth == 0:
            emit()
            i += 1
            continue

        i += 1

    # Trailing statement without semicolon
    if current:
        emit()

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
    password = os.environ.get("DB_PASSWORD") or SUPABASE_SERVICE_KEY
    return psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=password,
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
