# lead_scorer

I am the lead scorer. I score enriched_leads on urgency × asset_value
× likelihood so the lead_converter can prioritize high-value targets.

## Status
Scaffolded. Not yet wired.

## Planned behavior
- Read enriched_leads WHERE status='pending_enrichment' or similar
- Score on: storm urgency (1-10), property asset_value (USD), lead age
- Update lead.score (numeric, 0-100)
- The lead_converter then orders by score desc

## Tables I will touch
- enriched_leads (update score column)
- agent_activity (logging)

## Why I'm not live yet
The asset_value field is empty for most leads (the pipeline doesn't
populate it). Without it, scoring is a guess. Either:
1. Wire a property valuation API (Zillow, CoreLogic, etc.) in lead_enricher
2. Approximate from metro (DFW = high, Wichita = medium, etc.)
3. Use the existing urgency from radar_targets as the sole signal

The path forward is (1) — but requires an API key + agreement.
