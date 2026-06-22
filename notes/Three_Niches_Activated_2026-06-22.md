---
tags: [niches, multi-vertical, mass-tort, legal, hvac, insurance, 2026-06-22]
---

# Three New Niches Activated (2026-06-22)

**Status:** All three wired end-to-end. Most paths inherit the storm funnel
infrastructure (BBB scrape → score → prospector_bridge → contractors →
dispatch). The mass_tort path is separate (FDA recall → classifier → vonage dial).

## 1. Mass Tort + Legal

**Code:** existed, never activated. mass_tort_scout.py, mass_tort_bridge.py,
recall_classifier.py, legal_call_quality_gate.py, seed_legal_lane_buyers.py.

**What it does:** every 4h, fetches the latest FDA enforcement actions across
device/drug/food endpoints, classifies each into one of 5 legal sub-niches,
dials the matching buyer via Vonage (after passing the quality gate).

**Cron:** `15 */4 * * *` mass_tort_bridge.py.

**Buyers state (DB):**
- Apex Mass Tort Group — phone=+12142277528, **active**, dials fire
- Class Action, Consumer Product, Medical Device, Pharma Liability —
  placeholder rows, phone=None, is_active=False. **Need real numbers from
  the vonage dashboard to activate.**

**Verified live:** bridge run shows 4 recalls, 0 calls initiated (correctly
skips the 4 placeholder rows). Bridge logic is sound; just blocked on
provisioning.

**Next step (you):** provision 4 vonage numbers, one per legal sub-niche,
update `destination_phone` for each. Then 1-3 calls/day per active buyer
start firing automatically.

## 2. HVAC

**Code:** fully inherited from the storm funnel. Same BBB scraper, same
scoring, same prospector_bridge, same dispatch. The only HVAC-specific
asset is `bots/hvac_system.py` (a thin extension).

**What it does:** BBB scrape → 14 real HVAC businesses in Houston saved →
scored (30 base + 25 web + 25 phone + 15 BBB bonus = 95) → 11 bridged to
contractors table. From here, dispatch follows the same path as roofing.

**Cron:** already running (bgb_prospector nightly 03:30 covers 54 metros × 5
niches, HVAC is one of the 5). No new crons needed.

**Verified live:** Houston HVAC → 14 saved, 11 bridged, 2 dup-phone
skipped, 1 no-phone skipped. 11 fresh contractors in the table.

**Landing page:** generated dynamically via the landing_matrix API
(POST /api/v6/landing/render). Same engine as roofing, niche parameter
drives copy.

**Next step (you):** provision a vonage number for the HVAC buyer lane
(`destination_phone` in the `buyers` table, sub_niche='HVAC'). Until then
the 11 new contractors are in the table but no outreach fires.

## 3. Debt Consolidation / Life Insurance / Medicare / Final Expense

**Code:** partly existed. NICHES list in prospector.py had all 4 sub-niches
but no buyers were seeded. Wrote `scripts/seed_insurance_buyers.py` to fill
the gap. Idempotent dedup on (niche, buyer_name).

**What it does:** prospector BBB-scrape is wired for all 4 sub-niches.
Buyers table has placeholder rows for each. Outreach fires the moment a
buyer has a real destination_phone.

**Buyers state (DB after seed):**
- Debt Consolidation Lead Buyer #1 — placeholder
- Life Insurance Lead Buyer #1 — placeholder
- Medicare Advantage Lead Buyer #1 — placeholder
- Final Expense Lead Buyer #1 — placeholder

All 4 active=False until destination_phone is set. Same provisioning
problem as legal.

**Verified live:** NYC debt-consolidation → 14 saved. Scoring + bridge
ready when buyers are activated.

## Common thread — what's blocking real cash

All 3 niches are *discoverable* (BBB scraper pulls real businesses into
prospects) and *connectable* (prospector_bridge moves them to contractors).
The gap is **buyer provisioning**: 4 legal + 4 insurance + 1 HVAC vonage
numbers needed, then outreach fires automatically.

The plumbing is done. The 9 phone numbers are the only manual step
between today and 3 live vertical revenue streams.

## File diff

- `scripts/seed_insurance_buyers.py` (new, 2.9KB)
- crontab — 1 new entry (mass_tort_bridge 15 */4 * * *)

## What ships automatically when vonage numbers are set

- Legal lane: 4 buyers × ~1-3 calls/day = up to 12 outbound dials/day
- HVAC: 11 contractors in DB; once a buyer is provisioned, contractor_outreach
  cron enrolls them in the SMS sequence
- Insurance/Finance: 4 buyers waiting; same flow

## Related

- [[Sessions/2026-06-22_payment_and_recovery]] — storm funnel
- [[Fee_Attention_System_2026-06-22]] — fee recovery loop
- [[Brain_MiniMax_Live_2026-06-22]] — brain that makes decisions across all 3
- [[Obsidian_RAG_2026-06-22]] — brain reads this kind of note before deciding