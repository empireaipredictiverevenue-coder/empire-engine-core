import json
from datetime import datetime
from cost_analytics import CostAnalytics
from quantitative import QuantitativeTracker

print(f"=== Elite Scraper v2 Report — {datetime.utcnow().isoformat()} ===\n")

cost = CostAnalytics()
quant = QuantitativeTracker()

print("Cost per Lead by Source:")
for source, data in cost.summary().items():
    print(f"  {source}: ${data[cost_per_lead]}")

print("\nSource Performance:")
for source, data in quant.summary().items():
    print(f"  {source}: score={data[score]:.1f}, leads={data[leads]}, converted={data[converted]}")

print("\nReport complete.")
