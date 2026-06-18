# Contractor Scoring & Management

## Trust Score Calculation
Score = (completion_rate × 0.35) + (response_time_score × 0.25) + (quality_score × 0.25) + (volume_score × 0.15)

- completion_rate: % of dispatched jobs completed
- response_time_score: ≤ 30 min = 100, ≤ 2 hr = 75, ≤ 6 hr = 50, > 6 hr = 25
- quality_score: average of QC call scores (0-100)
- volume_score: 0 jobs = 0, 1-5 = 25, 6-20 = 50, 21-50 = 75, 50+ = 100

## Contractor Tiers
- **Platinum** (trust ≥ 90): Priority dispatch, higher-value leads
- **Gold** (trust 75-89): Standard dispatch
- **Silver** (trust 50-74): Limited dispatch, needs development
- **Bronze** (trust < 50): Suspended from dispatch, needs re-engagement

## Win-back Sequence
- Day 7: "Haven't seen any jobs come your way — wanted to check in"
- Day 14: "New storm activity in your area, leads coming soon"
- Day 30: "We miss having you on the team. Reply YES to reactivate"
- Day 60: Remove from active roster, mark as dormant
