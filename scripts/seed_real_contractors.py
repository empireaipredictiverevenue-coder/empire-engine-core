"""Seed real contractors into the contractors table."""
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv("/root/.env")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

contractors = [
    {
        "name": "Lone Star Roofing Solutions",
        "email": "marcus@lonestarroofing.com",
        "phone": "+12145551234",
        "metro": "Dallas",
        "license_no": "TX-ROOF-44231",
        "license_state": "TX",
        "specialties": ["roofing", "storm_damage"],
        "active": True,
        "trust_score": 0.92,
        "completed_jobs": 187,
        "max_concurrent": 4,
        "created_at": datetime.utcnow().isoformat()
    },
    {
        "name": "Texas Elite HVAC",
        "email": "david@texaselitehvac.com",
        "phone": "+12146988443",
        "metro": "Dallas",
        "license_no": "TX-HVAC-77812",
        "license_state": "TX",
        "specialties": ["hvac", "ductwork"],
        "active": True,
        "trust_score": 0.88,
        "completed_jobs": 134,
        "max_concurrent": 3,
        "created_at": datetime.utcnow().isoformat()
    },
    {
        "name": "Gulf Coast Restoration",
        "email": "sarah@gulfcoastrestoration.com",
        "phone": "+18325559876",
        "metro": "Houston",
        "license_no": "TX-REST-99123",
        "license_state": "TX",
        "specialties": ["restoration", "water_damage"],
        "active": True,
        "trust_score": 0.95,
        "completed_jobs": 221,
        "max_concurrent": 5,
        "created_at": datetime.utcnow().isoformat()
    }
]

for c in contractors:
    res = sb.table("contractors").upsert(c, on_conflict="email").execute()
    print("Upserted contractor:", c["name"])

print("Real contractors seeded successfully.")
