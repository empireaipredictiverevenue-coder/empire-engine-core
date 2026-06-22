#!/usr/bin/env python3
"""Insert Sovereign AGI Matrix product_metadata rows into Supabase."""
import os, sys
sys.path.insert(0, '/root/empire-v49')
from supabase import create_client

env = {}
with open('/root/.env') as f:
    for line in f:
        line = line.strip()
        if '=' in line and not line.startswith('#'):
            k, v = line.split('=', 1)
            env[k.strip()] = v.strip().strip('"').strip("'")

sb = create_client(env.get('SUPABASE_URL', ''), env.get('SUPABASE_SERVICE_KEY', ''))

tiers = [
    {
        'tier': 'SOVEREIGN_STARTER', 'product_name': 'sovereign_agi_matrix',
        'display_name': 'Sovereign AGI Matrix \u00b7 Starter',
        'description': 'Fleet intelligence API \u2014 500 calls/month. Access strategy-decide (AGI Governor with self-awareness anomaly gate) and self-aware (full-system introspection: agent health, lane performance, revenue state, PM2 services). Powered by local Ollama inference.',
        'monthly_price_usd': 199.00, 'price_per_unit': '$0.50 per additional API call',
        'features': [{'label': 'API Calls', 'value': '500/month'}, {'label': 'Strategy-Decide', 'value': 'AGI Governor + anomaly gate'}, {'label': 'Self-Aware', 'value': 'Full-system snapshot'}, {'label': 'Inference Engine', 'value': 'Ollama (local)'}, {'label': 'REST API', 'value': 'Full access'}, {'label': 'JSON Reports', 'value': 'Structured output'}],
        'sort_order': 190, 'is_public': True, 'is_active': True,
    },
    {
        'tier': 'SOVEREIGN_GROWTH', 'product_name': 'sovereign_agi_matrix',
        'display_name': 'Sovereign AGI Matrix \u00b7 Growth',
        'description': 'Full fleet intelligence \u2014 2,500 calls/month across all 5 endpoints: strategy-decide, self-aware, niche-analyze (Bayesian win-rate prediction), regime-detect (KL divergence market shift detection), agi-optimize (LLM parameter tuning). 90-day historical analytics.',
        'monthly_price_usd': 499.00, 'price_per_unit': '$0.25 per additional API call',
        'features': [{'label': 'API Calls', 'value': '2,500/month'}, {'label': 'All 5 Endpoints', 'value': 'Full suite'}, {'label': 'Strategy-Decide', 'value': 'AGI Governor + self-awareness'}, {'label': 'Self-Aware', 'value': 'Full-system snapshot'}, {'label': 'Niche-Analyze', 'value': 'Bayesian + win-rate'}, {'label': 'Regime-Detect', 'value': 'KL divergence detection'}, {'label': 'AGI-Optimize', 'value': 'LLM weight tuning'}, {'label': 'Historical Analytics', 'value': '90-day retention'}, {'label': 'REST API', 'value': 'Full access'}],
        'sort_order': 191, 'is_public': True, 'is_active': True,
    },
    {
        'tier': 'SOVEREIGN_ENTERPRISE', 'product_name': 'sovereign_agi_matrix',
        'display_name': 'Sovereign AGI Matrix \u00b7 Enterprise',
        'description': 'Enterprise fleet intelligence \u2014 unlimited API calls across all 5 endpoints. Custom AGI Governor training (per-niche strategy calibration), white-label API branding, SLA-backed 99.9% uptime, dedicated support. Unlimited historical analytics.',
        'monthly_price_usd': 999.00, 'price_per_unit': 'Unlimited API calls',
        'features': [{'label': 'API Calls', 'value': 'Unlimited'}, {'label': 'All 5 Endpoints', 'value': 'Full suite'}, {'label': 'Strategy-Decide', 'value': 'AGI Governor + anomaly gate'}, {'label': 'Self-Aware', 'value': 'Full-system snapshot'}, {'label': 'Niche-Analyze', 'value': 'Bayesian + win-rate'}, {'label': 'Regime-Detect', 'value': 'KL divergence detection'}, {'label': 'AGI-Optimize', 'value': 'LLM weight tuning'}, {'label': 'Custom AGI Training', 'value': 'Per-niche calibration'}, {'label': 'White-Label API', 'value': 'Custom domain + branding'}, {'label': 'SLA', 'value': '99.9% uptime'}, {'label': 'Dedicated Support', 'value': 'Included'}, {'label': 'Historical Analytics', 'value': 'Unlimited retention'}],
        'sort_order': 192, 'is_public': True, 'is_active': True,
    },
]

for t in tiers:
    r = sb.table('product_metadata').upsert(t, on_conflict='tier').execute()
    print(f"  {t['tier']}: {'OK' if r.data else 'FAILED'}")

print("\nDemo subscriptions:")
demos = [
    ('demo_sovereign_starter', 'SOVEREIGN_STARTER', 199.00),
    ('demo_sovereign_growth', 'SOVEREIGN_GROWTH', 499.00),
    ('demo_sovereign_enterprise', 'SOVEREIGN_ENTERPRISE', 999.00),
]
for acct_id, tier_level, mrr in demos:
    try:
        sb.table('product_subscriptions').upsert({
            'customer_account_id': acct_id, 'tier_level': tier_level,
            'subscription_status': 'ACTIVE', 'monthly_recurring_revenue': mrr,
            'billing_anchor_day': 1, 'notes': f'Demo - Sovereign AGI Matrix',
        }, on_conflict='customer_account_id').execute()
        print(f"  {acct_id}: OK")
    except Exception as e:
        print(f"  {acct_id}: {str(e)[:80]}")

# Verify
r = sb.table('product_metadata').select('tier,display_name,monthly_price_usd,sort_order').eq('product_name','sovereign_agi_matrix').order('sort_order').execute()
print(f"\nSovereign AGI Matrix products: {len(r.data or [])}")
for row in (r.data or []):
    print(f"  {row['tier']:25s} | {row['display_name']:35s} | ${row['monthly_price_usd']:,.0f} | sort={row['sort_order']}")
