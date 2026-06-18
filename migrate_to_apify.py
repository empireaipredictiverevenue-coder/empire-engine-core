"""
Empire AI · Apify Migration & Test Script
=========================================
Run this on July 10th 2026 to switch from Google Places to Apify.

Usage:
    python3 migrate_to_apify.py --test          # Run small test (3 niches, 2 metros)
    python3 migrate_to_apify.py --full          # Full 30+ lanes (use with caution)
    python3 migrate_to_apify.py --compare       # Compare cost/quality vs old Google version

Prerequisites:
    - APIFY_API_TOKEN in .env
    - b2b_lead_scraper_apify.py already created
"""

import os
import sys
import argparse
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

def test_run():
    print("=== TEST RUN (July 10th validation) ===")
    cmd = "python3 b2b_lead_scraper_apify.py --niches Commercial Roofing,Commercial Solar --metros Dallas,Fort Worth --max 20"
    print(f"Running: {cmd}")
    os.system(cmd)
    print("Test complete. Check radar_targets for new Apify-sourced rows.")

def full_run():
    print("=== FULL RUN (30+ lanes) ===")
    cmd = "python3 b2b_lead_scraper_apify.py"
    print(f"Running: {cmd}")
    os.system(cmd)

def compare_cost():
    print("=== COST COMPARISON ===")
    print("Google Places: ~£8-15 per 1,000 leads (already cost £154)")
    print("Apify:         ~£2-6 per 1,000 leads")
    print("Expected monthly savings at scale: 60-70%")
    print("Recommendation: Run test on July 10th, then switch fully.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--full", action="store_true")
    parser.add_argument("--compare", action="store_true")
    args = parser.parse_args()

    if args.test:
        test_run()
    elif args.full:
        full_run()
    elif args.compare:
        compare_cost()
    else:
        print("Usage: python3 migrate_to_apify.py --test | --full | --compare")
