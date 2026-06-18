# Lead Evaluation Criteria

> *How the brain evaluates leads for storm-strike outreach.*

## Signal Weighting

When evaluating a lead, weight these signals in order:

1. **Storm severity** (primary) — Severe/Extreme: strong GO signal.
   Moderate: requires other signals to confirm. Minor: NO_GO unless extreme
   asset value.

2. **Geographic match** (primary) — Does the lead's city/county fall within
   the NWS alert polygon? If not, NO_GO regardless of other signals.

3. **Asset value** (secondary) — Higher asset value correlates with higher
   claim potential. Buckets: sub-500K (low), mid-six-fig, low-million,
   mid-million, large-asset (25M+).

4. **Contact availability** (secondary) — Phone + email is ideal. Phone
   only is acceptable. Email only is weak. Neither is NO_GO.

5. **Commercial status** (tertiary) — Warehouses, distribution centers,
   manufacturing, retail. Residential properties should generally NO_GO
   unless the storm is extreme.

## GO Conditions

A GO decision requires:
  - Storm severity >= Moderate
  - Geographic match confirmed
  - At least one working contact channel
  - Asset value >= $500K (or high urgency override)
  - Memory check: similar past leads didn't consistently NO_GO

## NO_GO Conditions

Automatic NO_GO triggers:
  - Storm is Minor only
  - No geographic overlap
  - No contact channels available
  - Property is clearly residential
  - Already processed (in _processed_alerts dedup set)
  - Memory check: similar leads with outcomes consistently denied

## Confidence Calibration

| Confidence | Meaning | Action |
|---|---|---|
| 0.8-1.0 | Strong signals, past precedent | Aggressive outreach |
| 0.6-0.8 | Good signals, some uncertainty | Standard outreach |
| 0.4-0.6 | Weak signals, default NO_GO | Re-evaluate with more data |
| <0.4 | Insufficient evidence | NO_GO |
