#!/usr/bin/env python3
"""
Run SQL migration files against Supabase PostgreSQL database.

Usage:
  python3 scripts/run_migrations.py                          # auto-discover via glob
  python3 scripts/run_migrations.py --list                   # show discovered migrations + order
  python3 scripts/run_migrations.py migrations/005_*.sql     # explicit file(s)

Migrations are auto-discovered from migrations/*.sql (sorted by filename)
when no arguments are passed. Adding a new 00N_*.sql file to migrations/
is enough to register it — no code changes needed. The --list flag
prints the discovered order + statement count + file size so operators
can spot misnamed or out-of-order files without reading the source.
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


def run_migrations(files):
    conn = None
    try:
        print(f"Connecting to {DB_HOST}:{DB_PORT} as {DB_USER}...")
        conn = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            user=DB_USER,
            password=SUPABASE_SERVICE_KEY,
            dbname=DB_NAME,
            connect_timeout=10,
            sslmode='require',
        )
        conn.autocommit = True
        cur = conn.cursor()
        print("Connected successfully!")
        
        for filepath in files:
            if not os.path.exists(filepath):
                print(f"\n❌ File not found: {filepath}")
                continue
            
            print(f"\n{'='*60}")
            print(f"Running: {filepath}")
            print(f"{'='*60}")
            
            with open(filepath, 'r') as f:
                content = f.read()
            
            statements = parse_sql_statements(content)
            print(f"Parsed {len(statements)} SQL statements")
            
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
