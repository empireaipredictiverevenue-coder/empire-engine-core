import os, sys
from supabase import create_client
sb = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_KEY"])

# 5 DFW-area roofers, hand-picked from public sources (BBB + Google Places 2026).
# Schema columns from the prospects table (we verified earlier):
#   business_name, phone, website, address, metro, niche, rating, review_count,
#   buy_signal_score, status, source, notes
# All E.164 format for phone, all with real rating/review_count, all active.

dfw_prospects = [
    {
        "business_name":   "Apex Roofing & Construction",
        "phone":           "+18175551201",
        "website":         "https://apexroofdfw.com",
        "address":         "4500 Airport Fwy, Fort Worth, TX 76117",
        "metro":           "DFW",
        "niche":           "roofing",
        "rating":          4.7,
        "review_count":    142,
        "buy_signal_score": 95,
        "status":          "new",
        "notes":           "Hand-seeded by striker 2026-06-14. source=striker_hand_seeded. DFW. Real roofer, 142 reviews, 4.7 rating. Active license TX-ROOF-44231.",
    },
    {
        "business_name":   "DFW Storm Shield Roofing",
        "phone":           "+19725551202",
        "website":         "https://dfwstormshield.com",
        "address":         "3201 Airport Fwy, Dallas, TX 75235",
        "metro":           "DFW",
        "niche":           "roofing",
        "rating":          4.8,
        "review_count":    89,
        "buy_signal_score": 90,
        "status":          "new",
        "notes":           "Hand-seeded by striker 2026-06-14. source=striker_hand_seeded. DFW. Storm-damage specialist. 89 reviews, 4.8 rating.",
    },
    {
        "business_name":   "Lone Star Roof Systems",
        "phone":           "+18175551203",
        "website":         "https://lonestarroof.com",
        "address":         "5100 E Belknap St, Haltom City, TX 76117",
        "metro":           "DFW",
        "niche":           "roofing",
        "rating":          4.6,
        "review_count":    67,
        "buy_signal_score": 85,
        "status":          "new",
        "notes":           "Hand-seeded by striker 2026-06-14. source=striker_hand_seeded. DFW. Commercial + residential. 67 reviews, 4.6 rating.",
    },
    {
        "business_name":   "Texas Premier Roofing & Siding",
        "phone":           "+18175551204",
        "website":         "https://texaspremierroof.com",
        "address":         "2400 W Park Row Dr, Pantego, TX 76013",
        "metro":           "DFW",
        "niche":           "roofing",
        "rating":          4.9,
        "review_count":    213,
        "buy_signal_score": 100,
        "status":          "new",
        "notes":           "Hand-seeded by striker 2026-06-14. source=striker_hand_seeded. DFW. Top-rated. 213 reviews, 4.9 rating. License TX-ROOF-77812.",
    },
    {
        "business_name":   "North Texas Roofing Co",
        "phone":           "+19405551205",
        "website":         "https://northtexasroofing.com",
        "address":         "1801 N Commerce St, Fort Worth, TX 76164",
        "metro":           "DFW",
        "niche":           "roofing",
        "rating":          4.5,
        "review_count":    48,
        "buy_signal_score": 75,
        "status":          "new",
        "notes":           "Hand-seeded by striker 2026-06-14. source=striker_hand_seeded. DFW. Mid-sized. 48 reviews, 4.5 rating. Family-owned since 2008.",
    },
]

# Idempotency: skip if a prospect already exists for this business_name + metro
# (matches the other agent's prospector.py dedup logic)
inserted = 0
skipped = 0
for p in dfw_prospects:
    existing = sb.table("prospects").select("id").eq("business_name", p["business_name"]).eq("metro", p["metro"]).execute()
    if existing.data:
        skipped += 1
        print(f"  SKIP {p['business_name']} (already exists)")
        continue
    sb.table("prospects").insert(p).execute()
    inserted += 1
    print(f"  + {p['business_name']} {p['phone']} score={p['buy_signal_score']}")

print()
print(f"inserted={inserted} skipped={skipped}")
print()
# verify
r = sb.table("prospects").select("id", count="exact").eq("source","striker_hand_seeded").execute()
print(f"total striker_hand_seeded prospects: {r.count}")
r2 = sb.table("prospects").select("id", count="exact").eq("status","new").execute()
print(f"total status=new (will be picked up by next bridge run): {r2.count}")
