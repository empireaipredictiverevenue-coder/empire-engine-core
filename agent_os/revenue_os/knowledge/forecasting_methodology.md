# Revenue Forecasting Methodology

## Pipeline Stages & Conversion Rates
| Stage | Rate | Time to Next |
|---|---|---|
| Lead Scraped → Enriched | 85% | 5 min |
| Enriched → Contacted | 70% | 30 min |
| Contacted → Replied | 12% | 2-24 hrs |
| Replied → Dispatched | 45% | 1 hr |
| Dispatched → Settled | 3% | 30-90 days |

## Fee Structure
- Standard fee: 3% of settlement amount
- Minimum fee: $150 per claim
- Referral bounty: $50 per active contractor referred
- Payment terms: Net-15 after settlement

## Anomaly Detection Rules
- Missing fee: settlement exists but no fee recorded → alert within 24h
- Unusual fee amount: deviation > 2σ from lane average → flag for review
- Pipeline stall: no movement in a lane for > 48h → investigate
- Duplicate lead: same property appearing in 2+ lanes → dedup

## Reporting Schedule
- Hourly: pulse check (revenue last 24h, active lanes)
- Daily: full report at 07:00 UTC
- Weekly: narrative report with trends and recommendations
- Monthly: board-level summary with variance analysis
