# Storm Severity Reference

> *NWS storm severity classifications and their business impact.*

## Severity Levels

| Level | NWS Term | GO Signal | Notes |
|---|---|---|---|
| 1 | Minor | Very weak | Isolated thunderstorms, no damage expected |
| 2 | Moderate | Moderate | Possible wind/gusts, some hail potential |
| 3 | Severe | Strong | Valid warning issued, damaging winds, large hail |
| 4 | Extreme | Very strong | Tornado warning, catastrophic damage likely |

## By Storm Type

**Thunderstorm**: Most common. Severe = GO. Moderate = evaluate other signals.
**Tornado**: Extreme = immediate GO. Severe = strong GO if in path.
**Flash Flood**: Moderate/High = GO for low-lying warehouses.
**Winter Storm**: Usually Moderate. Evaluate asset value and region prep.
**Hurricane**: Always Extreme. GO for all targets in cone.
**Heat**: Usually Minor. NO_GO unless extreme heat + vulnerable assets.

## Regional Considerations

- **Dallas/Fort Worth**: High storm frequency. Brain is calibrated tighter
  (higher urgency floor) due to high volume of false positives.
- **Houston**: Hurricane + flood risk. Lower urgency floor for flood alerts.
- **Austin/San Antonio**: Less frequent severe storms. Standard thresholds.
- **Oklahoma/Tornado Alley**: Extreme tornado = immediate GO regardless
  of other signals.
