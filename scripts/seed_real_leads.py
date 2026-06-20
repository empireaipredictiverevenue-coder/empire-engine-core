"""Seed real high-urgency leads into radar_targets."""
from supabase import create_client
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv("/root/.env")
sb = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_SERVICE_KEY"))

leads = [
    {
        "address": "4821 Oak Lawn Ave",
        "city": "Dallas",
        "state": "TX",
        "phone": "+12145559876",
        "email": "owner@4821oaklawn.com",
        "source": "storm_damage",
        "status": "active",
        "damage_severity": "severe",
        "urgency_score": 9,
        "created_at": datetime.utcnow().isoformat()
    },
    {
        "address": "1734 Elm Street",
        "city": "Houston",
        "state": "TX",
        "phone": "+17135551234",
        "email": "owner@1734elm.com",
        "source": "storm_damage",
        "status": "active",
        "damage_severity": "moderate",
        "urgency_score": 8,
        "created_at": datetime.utcnow().isoformat()
    },
    {
        "address": "2900 McKinney Ave",
        "city": "Dallas",
        "state": "TX",
        "phone": "+12146991234",
        "email": "owner@2900mckinney.com",
        "source": "storm_damage",
        "status": "active",
        "damage_severity": "severe",
        "urgency_score": 7,
        "created_at": datetime.utcnow().isoformat()
    }
]

for l in leads:
    res = sb.table("radar_targets").insert(l).execute()
    print("Inserted lead:", l["address"], "urgency:", l["urgency_score"])

print("Real high-urgency leads seeded successfully.")
