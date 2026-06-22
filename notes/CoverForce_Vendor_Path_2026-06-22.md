---
tags: [coverforce, vendor, broker-park, 2026-06-22, decision]
---

# CoverForce API — Vendor Path (2026-06-22)

**Status:** Application form ready to submit. Vendor mode (not broker).
No state license, no E&O, no carrier appointments required for this path.

## Decision

Phil picked "vendor mode" for CoverForce (vs. "we are a digital
brokerage"). Reasons:
- Vendor route gets the API key in 1-2 weeks.
- Broker route requires state license (P&C Producer, 50 states, $5-15k
  first year for 5 states) + E&O + carrier appointments + 3-6 month timeline.
- Empire AI's actual current operation is lead-gen for restoration
  contractors (3% fee on settled claims). That's vendor, not broker.
- Broker path is parked until empire is actually binding 50+ policies/month.

## Form answers (drafted 2026-06-22)

| Field | Value |
|-------|-------|
| Company | Empire AI |
| Contact | Phil Livesley, Founder |
| Use case | "We operate a contractor dispatch network for residential and commercial restoration..." (full text in conversation) |
| Volume | 500-2,000 calls/month at launch, 10k+/month within 6 months |
| Target carriers | State Farm, Allstate, Liberty Mutual, USAA, Farmers |
| Integration | 2-3 weeks, webhook to empire-ai.co.uk/api/v1/claim-settled |
| Existing carrier relationships | None direct (we route through contractors) |
| Are you a digital brokerage? | No — we are a vendor to restoration contractors |
| GWP ($) | $0 — we do not write premium |

## Wire-up plan (when key arrives)

1. `echo 'COVERFORCE_API_KEY=...' >> /root/.env`
2. Implement `CoverForceAdapter` in `/root/empire-v49/carrier_adapters.py`
   per the existing interface contract.
3. Swap `empire_carrier.py` (mock) for the real adapter in
   `bots/mass_tort_bridge.py` and `/api/v1/claim-settled` flow.
4. First live test: pull 1 settled claim from coverforce, verify it
   flows through to fee_events, verify fee_events.status moves to "paid".

## Broker-licensing roadmap (PARKED)

Revisit when:
- Empire is binding 50+ policies/month, OR
- revenue from broker commissions > revenue from contractor fees

If/when: state-by-state P&C Producer License, 3-6 month build, $5-15k
first year for 5 states (FL, TX, CA, NY, IL). DRLP = Phil or hire.
E&O $1,500-$5,000/yr. Full roadmap notes go in this file when activated.

## Related

- [[Sessions/2026-06-22_payment_and_recovery]] — base fee pipeline
- [[Three_Niches_Activated_2026-06-22]] — verticals coverforce feeds into
- [[Brain_MiniMax_Live_2026-06-22]] — brain routes coverforce data through
  obsidian RAG before deciding