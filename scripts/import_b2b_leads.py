"""Import b2b_leads_export.csv into b2b_leads table with auto product-fit tagging.

Usage: python3 scripts/import_b2b_leads.py [--dry-run]
"""

import csv, os, sys, json, argparse
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
from supabase import create_client


# ── Product-fit mapping: niche → recommended Empire Suite products ──
NICHE_PRODUCT_FIT = {
    "HR & Staffing": [
        "inbound_router",      # Route inbound calls to staffing desks
        "lead_score",           # Score candidate quality
        "strike_campaigns",     # Outbound recruitment campaigns
    ],
    "Managed IT": [
        "data_vault",           # Secure data management
        "compliant",            # Compliance monitoring
        "buyer_spy",            # Competitive intel on IT providers
    ],
    "Merchant Services": [
        "buyer_spy",            # Competitive rate intel
        "lead_score",           # Score merchant quality
        "forecast",             # Revenue forecasting for processing
    ],
}


def load_env():
    env = {}
    with open('/root/.env') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def parse_csv(filepath):
    """Parse the CSV and return cleaned row dicts."""
    rows = []
    with open(filepath, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Skip completely empty rows
            if not row.get('Company', '').strip():
                continue

            niche = row.get('SubNiche', '').strip()

            rows.append({
                'company_name': row.get('Company', '').strip()[:255],
                'email': row.get('Email', '').strip().lower()[:255],
                'phone': row.get('Phone', '').strip().replace('(', '').replace(')', '').replace('-', ' ').replace(' ', ''),
                'address': row.get('Address', '').strip()[:500],
                'city': row.get('City', '').strip()[:100],
                'state': row.get('State', '').strip().upper()[:2],
                'metro': row.get('Metro', '').strip()[:100],
                'niche': niche,
                'website': row.get('Website', '').strip()[:500],
                'lead_score': int(row.get('Score', 0) or 0),
                'urgency': int(row.get('Urgency', 0) or 0),
                'product_fit': NICHE_PRODUCT_FIT.get(niche, []),
                'source': 'b2b_leads_export',
                'source_created_at': row.get('Created', '').strip(),
                'status': 'new',
            })

    return rows


def deduplicate(rows):
    """Remove duplicate emails, keeping highest lead_score."""
    seen = {}
    for row in rows:
        email = row['email']
        # Skip placeholder/undeliverable emails
        if not email or '@' not in email or '@2x.' in email or email.startswith('mask-'):
            continue
        if email not in seen or row['lead_score'] > seen[email]['lead_score']:
            seen[email] = row
    return list(seen.values())


def main():
    parser = argparse.ArgumentParser(description='Import B2B leads from CSV into Supabase')
    parser.add_argument('--dry-run', action='store_true', help='Parse and report without inserting')
    parser.add_argument('--csv', default='/root/empire-v49/b2b_leads_export.csv', help='Path to CSV file')
    parser.add_argument('--batch-size', type=int, default=100, help='Rows per insert batch')
    args = parser.parse_args()

    # ── Load env and connect ──────────────────────────────────────
    env = load_env()
    sb = create_client(env.get('SUPABASE_URL', ''), env.get('SUPABASE_SERVICE_KEY', ''))

    # ── Parse and clean ───────────────────────────────────────────
    print(f'Reading: {args.csv}')
    rows = parse_csv(args.csv)
    print(f'  Parsed: {len(rows)} rows')

    rows = deduplicate(rows)
    print(f'  After dedup: {len(rows)} rows')

    # ── Stats ─────────────────────────────────────────────────────
    niche_counts = Counter(r['niche'] for r in rows)
    state_counts = Counter(r['state'] for r in rows)
    product_counts = Counter()
    for r in rows:
        for p in r['product_fit']:
            product_counts[p] += 1

    print(f'\nNiches:')
    for niche, count in niche_counts.most_common():
        products = NICHE_PRODUCT_FIT.get(niche, [])
        print(f'  {count:4d}  {niche:<25s}  → {", ".join(products[:3])}')

    print(f'\nProduct fits:')
    for product, count in product_counts.most_common():
        print(f'  {count:4d}  {product}')

    print(f'\nStates:')
    for state, count in state_counts.most_common():
        print(f'  {count:4d}  {state}')

    if args.dry_run:
        print(f'\nDRY RUN — no data inserted. {len(rows)} rows ready.')
        return

    # ── Verify table exists ───────────────────────────────────────
    try:
        sb.table('b2b_leads').select('id', count='exact').limit(0).execute()
        print(f'\nb2b_leads table exists. Ready to insert.')
    except Exception as e:
        print(f'\nERROR: b2b_leads table does not exist or is inaccessible.')
        print(f'  Run the migration first: migrations/20260622_b2b_leads_table.sql')
        print(f'  Error: {str(e)[:200]}')
        sys.exit(1)

    # ── Insert into Supabase ──────────────────────────────────────
    print(f'\nInserting {len(rows)} rows in batches of {args.batch_size}...')
    inserted = 0
    errors = 0

    for i in range(0, len(rows), args.batch_size):
        batch = rows[i:i + args.batch_size]
        try:
            r = sb.table('b2b_leads').insert(batch).execute()
            count = len(r.data) if r.data else 0
            inserted += count
            print(f'  Batch {i // args.batch_size + 1}: {count} rows (total: {inserted})')
        except Exception as e:
            err_str = str(e)
            if 'duplicate' in err_str.lower() or 'unique' in err_str.lower():
                # Already imported — safe to skip
                skipped = len(batch)
                print(f'  Batch {i // args.batch_size + 1}: SKIP {skipped} rows (already imported)')
            else:
                errors += len(batch)
                print(f'  Batch {i // args.batch_size + 1}: ERROR — {err_str[:120]}')

    print(f'\nDone: {inserted} inserted, {errors} errors')

    # ── Verify ────────────────────────────────────────────────────
    try:
        r = sb.table('b2b_leads').select('id', count='exact').execute()
        print(f'\nVerification: {r.count} total rows in b2b_leads')
        r2 = sb.table('b2b_leads').select('niche', count='exact').execute()
        niche_verify = Counter()
        for row in (r2.data or []):
            niche_verify[row['niche']] += 1
        for niche, count in niche_verify.most_common():
            print(f'  {count:4d}  {niche}')
    except Exception as e:
        print(f'Verification query failed: {e}')


if __name__ == '__main__':
    main()
