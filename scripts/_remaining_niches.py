"""
Show remaining uncovered sub-niches after 36-lane expansion.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from empire_pricing import CPLPricingEngine, CPL_BENCHMARKS, _LANE_NICHE_MAP
from mesh_orchestrator import LANES

# What's already in the lane map
existing_pairs = set()
for v in _LANE_NICHE_MAP.values():
    existing_pairs.add((v["niche"], v["sub_niche"]))

# Also check mesh_orchestrator
for v in LANES.values():
    n = v["niche"]
    sn = v.get("sub_niche", "") or n
    existing_pairs.add((n, sn))

# Find uncovered sub-niches
uncovered = []
for niche_name, niche_data in sorted(CPL_BENCHMARKS.items()):
    if niche_data.get("best_model") == "service":
        continue
    for sn_name, sn_data in niche_data.get("sub_niches", {}).items():
        sn_lookup = sn_name if sn_name else niche_name
        if (niche_name, sn_lookup) in existing_pairs:
            continue
        # Also check if a variant of the sub-niche name exists
        found = False
        for (en, esn) in existing_pairs:
            if en == niche_name and (sn_name.lower() in esn.lower() or esn.lower() in sn_name.lower()):
                found = True
                break
        if found:
            continue

        ppl = sn_data.get("ppl", (None, None))
        ppc = sn_data.get("ppc", (None, None))
        best_cpl = max(ppl[0] or 0, ppc[0] or 0)
        best_model = sn_data.get("best", niche_data.get("best_model", "both"))
        trigger = sn_data.get("trigger", "")
        notes = sn_data.get("notes", "")
        vol = niche_data.get("volume", "medium")
        uncovered.append((best_cpl, niche_name, sn_name, best_model, trigger, vol, notes))

uncovered.sort(key=lambda x: x[0], reverse=True)

print("=" * 100)
print(f"REMAINING UNCOVERED SUB-NICHES (after 36-lane expansion) — {len(uncovered)} total")
print("=" * 100)
print(f"{'Rank':<5} {'CPL':>7} {'Niche':<24} {'Sub-Niche':<24} {'Model':<6} {'Vol':<10} {'Trigger'}")
print("-" * 100)

for i, (cpl, n, sn, model, trigger, vol, notes) in enumerate(uncovered):
    cpl_str = f"${cpl:.0f}" if cpl > 0 else "N/A"
    print(f"{i+1:<5} {cpl_str:>7} {n:<24} {sn:<24} {model:<6} {vol:<10} {trigger[:35]}")

print()
print("=" * 100)
print("PROPOSED NEXT EXPANSION (36→48 = 12 more lanes)")
print("=" * 100)
print()

# Group by tier
tier1 = uncovered[:4]
tier2 = uncovered[4:8]
tier3 = uncovered[8:12]

print("Tier 1 — Highest CPL (next 4):")
total_rev_t1 = 0
for i, (cpl, n, sn, model, trigger, vol, notes) in enumerate(tier1):
    roi = CPLPricingEngine.roi_estimate(n, sn, monthly_volume=500, model="ppl" if model in ("ppl","both") else "ppc")
    ar = roi.get("monthly_revenue", 0) * 12 if "error" not in roi else 0
    total_rev_t1 += ar
    print(f"  Lane {36+i}: {sn:<24s} ({n})  CPL=${cpl:.0f}  model={model}  est.${ar:,.0f}/yr")
print(f"  Total Tier 1 annual: ${total_rev_t1:,.0f}")
print()

print("Tier 2 — Mid CPL (next 4):")
total_rev_t2 = 0
for i, (cpl, n, sn, model, trigger, vol, notes) in enumerate(tier2):
    j = i + 4
    roi = CPLPricingEngine.roi_estimate(n, sn, monthly_volume=500, model="ppl" if model in ("ppl","both") else "ppc")
    ar = roi.get("monthly_revenue", 0) * 12 if "error" not in roi else 0
    total_rev_t2 += ar
    print(f"  Lane {40+j}: {sn:<24s} ({n})  CPL=${cpl:.0f}  model={model}  est.${ar:,.0f}/yr")
print(f"  Total Tier 2 annual: ${total_rev_t2:,.0f}")
print()

print("Tier 3 — Remaining high-volume (next 4):")
total_rev_t3 = 0
for i, (cpl, n, sn, model, trigger, vol, notes) in enumerate(tier3):
    k = i + 8
    roi = CPLPricingEngine.roi_estimate(n, sn, monthly_volume=500, model="ppl" if model in ("ppl","both") else "ppc")
    ar = roi.get("monthly_revenue", 0) * 12 if "error" not in roi else 0
    total_rev_t3 += ar
    print(f"  Lane {44+k}: {sn:<24s} ({n})  CPL=${cpl:.0f}  model={model}  est.${ar:,.0f}/yr")
print(f"  Total Tier 3 annual: ${total_rev_t3:,.0f}")

total_all = total_rev_t1 + total_rev_t2 + total_rev_t3
print(f"\nTotal estimated annual revenue from 12 new lanes: ${total_all:,.0f}")
print(f"Combined with existing 36 lanes, this completes full coverage of all major sub-niches.")
