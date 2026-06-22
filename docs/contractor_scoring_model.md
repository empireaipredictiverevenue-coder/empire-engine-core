# Contractor Decision-Maker Scoring Model

## Purpose
Score contractor prospects by likelihood to:
1. Self-onboard to Empire AI
2. Close their first deal
3. Become a high-value recurring partner

## Scoring Dimensions (0-100 each, weighted)

### 1. Niche Fit (Weight: 25%)
| Criteria | Score | Notes |
|----------|-------|-------|
| Roofing | 100 | Core niche, highest claim volume |
| Restoration | 90 | Water/fire/mold, strong second niche |
| General Contractor | 70 | Broad, but slower to convert |
| Public Adjuster | 85 | Direct claims pipeline |
| HVAC | 60 | Adjacent, lower claim value |
| Solar | 40 | Different insurance model |
| Other | 20 | Low match |

### 2. Service Area Fit (Weight: 20%)
| Criteria | Score | Notes |
|----------|-------|-------|
| Dallas-Fort Worth | 100 | Highest storm frequency in TX |
| Houston | 95 | Hurricane/ flood zone |
| San Antonio | 80 | Secondary market |
| Austin | 75 | Growing, less storm exposure |
| Other Texas | 60 | Expanding coverage |
| Out of state | 0 | Not yet supported |

### 3. Digital Presence (Weight: 15%)
| Criteria | Score |
|----------|-------|
| Has website + Google Business + reviews | 100 |
| Has website + Google Business | 75 |
| Has website only | 50 |
| Google Business only | 40 |
| No online presence | 10 |

### 4. Company Size Signal (Weight: 15%)
| Criteria | Score | Indicator |
|----------|-------|-----------|
| 10-50 employees | 100 | Established but growing |
| 5-9 employees | 80 | Small but operational |
| 1-4 employees | 60 | Solo operator |
| 50+ employees | 70 | May have existing lead sources |

### 5. Engagement Readiness (Weight: 15%)
| Criteria | Score | Indicator |
|----------|-------|-----------|
| Has website with "Get a Quote" | 100 | Lead-ready |
| Active social media (last 30d) | 75 | Marketing-aware |
| Has Google Reviews (10+) | 60 | Established reputation |
| Has email on website | 50 | Contactable |
| No contact info | 0 | Hard to reach |

### 6. Competitive Signal (Weight: 10%)
| Criteria | Points |
|----------|--------|
| No "financing available" on site | +20 |
| No "insurance claim specialist" mention | +15 |
| No "free inspection" offer | +15 |
| Outdated website (no updates in 6mo) | +10 |
| Uses competitor lead gen service | -30 |

## Composite Score Calculation

```
Total Score = Σ(weight_i × score_i) / Σ(weight_i)

Score Range:
  80-100:  Hot prospect — prioritize outreach
  60-79:   Warm — nurture sequence
  40-59:   Lukewarm — lower priority
  0-39:    Cold — deprioritize
```

## Automated Scoring
Score can be computed from existing enriched_leads data:
- `meta.niche` → Niche Fit
- `city` / `state` → Service Area Fit
- `meta.raw.website`, `meta.raw.google_business` → Digital Presence
- `meta.employee_count` → Company Size
- `asset_value` / `estimated_claim_value` → Deal potential (bonus signal)

## Next: Implementation
- Add `contractor_score` column to `enriched_leads` or `contractors` table
- Add scoring function to `empire_enricher_ai.py`
- Wire into dispatch prioritization in `empire_matching.py`
