"""
EMPIRE V49 · RECALL CLASSIFIER + SCOUT
=======================================
Pulls the latest recall from each of the 3 FDA enforcement endpoints
(drug, device, food) and classifies each into one of the 5 legal
sub_niches:

  Pharma Liability  : Drugs endpoint recalls (any classification)
  Medical Device    : Devices endpoint recalls (any classification)
  Consumer Product  : Food endpoint recalls (food, supplement,
                      cosmetic-like products)
  Class Action      : Class I recalls with nationwide or worldwide
                      distribution patterns. These are the big
                      injurious ones plaintiff firms want to lead.
  Mass Tort         : Catch-all for everything else (Class II / III
                      with limited distribution, or unclassifiable
                      recall types). Apex Mass Tort Group is the
                      buyer for this lane.

Keyword overrides: a few common recall terms can flip a drug or food
recall to Class Action (e.g. "contamination" with "nationwide"
distribution, or "death" in reason_for_recall).

This is step 3 of the mass-tort lane-sort plan: route each recall to
exactly one legal sub_niche so the 5 legal buyers stop being
duplicate-routed.

Patched 2026-06-12: the original scout only hit /device/enforcement
and returned a single flat dict. The new version polls all 3
endpoints, classifies, and returns a list of classified recalls.
"""

import json
import urllib.request
import urllib.error
from typing import Optional


# ── CONFIG ──────────────────────────────────────────────────────────────
FDA_ENDPOINTS = {
    "Drugs":   "https://api.fda.gov/drug/enforcement.json?limit=5",
    "Devices": "https://api.fda.gov/device/enforcement.json?limit=5",
    "Food":    "https://api.fda.gov/food/enforcement.json?limit=5",
}

# Sub-niches → lane_ids in mesh_orchestrator.py. The lane_id is what
# the call router uses to pick the right buyer. Mapping lives here so
# the classifier is the single source of truth for "this recall goes
# to this buyer."
SUB_NICHE_TO_LANE = {
    "Pharma Liability": 16,
    "Medical Device":   17,
    "Consumer Product": 18,
    "Class Action":     19,
    "Mass Tort":        20,
}

# Terms in reason_for_recall that, combined with nationwide / worldwide
# distribution, escalate a recall to Class Action. These are the high-
# value keywords plaintiff firms search for.
CLASS_ACTION_KEYWORDS = (
    "death", "fatal", "fatality", "sepsis", "contamination",
    "infection", "bleed", "cardiac", "stroke", "aneurysm",
    "cancer", "carcinogen", "lead", "asbestos",
)


# ── FETCH ───────────────────────────────────────────────────────────────
def _fetch(endpoint: str) -> list[dict]:
    """Fetch the latest recalls from one FDA endpoint."""
    try:
        req = urllib.request.Request(
            endpoint,
            headers={
                "User-Agent": "(empire-v49-storm-scraper, ops@empire-ai.local)",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            if resp.status != 200:
                return []
            body = json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError, TimeoutError):
        return []
    return body.get("results", [])


# ── CLASSIFY ────────────────────────────────────────────────────────────
def _is_nationwide(distribution: str) -> bool:
    """Heuristic: distribution string contains 'US Nationwide' or
    'Nationwide' or 'Worldwide' or is over 1000 chars (proxy for
    wide distribution)."""
    if not distribution:
        return False
    d = distribution.lower()
    if "us nationwide" in d or "worldwide" in d or "nationwide" in d:
        return True
    # Long distribution_pattern strings usually mean 20+ states
    if len(distribution) > 1000:
        return True
    return False


def classify(recall: dict) -> str:
    """
    Classify a recall into one of the 5 legal sub_niches.

    Returns the sub_niche label. Falls back to 'Mass Tort' for
    unclassifiable inputs (the catch-all lane).
    """
    product_type = (recall.get("product_type") or "").strip()
    classification = (recall.get("classification") or "").strip()
    reason = (recall.get("reason_for_recall") or "").lower()
    distribution = recall.get("distribution_pattern") or ""

    # Class Action upgrade: high-severity + nationwide + serious reason
    if classification == "Class I" and _is_nationwide(distribution):
        if any(kw in reason for kw in CLASS_ACTION_KEYWORDS):
            return "Class Action"

    # Default by product_type
    if product_type == "Drugs":
        return "Pharma Liability"
    if product_type == "Devices":
        return "Medical Device"
    if product_type == "Food":
        return "Consumer Product"

    # Fallback: Class I with no product_type is unusual but possible
    if classification == "Class I":
        return "Class Action"

    # Anything else → Mass Tort (the Apex buyer lane)
    return "Mass Tort"


# ── PUBLIC API ──────────────────────────────────────────────────────────
def fetch_classified_recalls() -> list[dict]:
    """
    Poll all 3 FDA endpoints, classify each recall, return a list of
    {sub_niche, lane_id, event_id, product_type, classification,
    product_description, reason_for_recall, recalling_firm}.
    """
    out = []
    for product_type, endpoint in FDA_ENDPOINTS.items():
        recalls = _fetch(endpoint)
        for r in recalls:
            sub_niche = classify(r)
            out.append({
                "sub_niche": sub_niche,
                "lane_id": SUB_NICHE_TO_LANE[sub_niche],
                "event_id": r.get("event_id"),
                "product_type": r.get("product_type"),
                "classification": r.get("classification"),
                "product_description": (r.get("product_description") or "")[:200],
                "reason_for_recall": (r.get("reason_for_recall") or "")[:200],
                "recalling_firm": r.get("recalling_firm"),
                "recall_number": r.get("recall_number"),
            })
    return out


def fetch_one_per_sub_niche() -> list[dict]:
    """
    Convenience: return up to one recall per sub_niche (the first one
    found for each). The call router fires one call per sub_niche
    per cycle.
    """
    all_recalls = fetch_classified_recalls()
    seen_sub_niches = set()
    out = []
    for r in all_recalls:
        if r["sub_niche"] not in seen_sub_niches:
            out.append(r)
            seen_sub_niches.add(r["sub_niche"])
    return out


if __name__ == "__main__":
    recalls = fetch_classified_recalls()
    print(f"[CLASSIFIER] {len(recalls)} recalls fetched across 3 FDA endpoints")
    # Count by sub_niche
    from collections import Counter
    counts = Counter(r["sub_niche"] for r in recalls)
    print("[CLASSIFIER] By sub_niche:")
    for sn, n in sorted(counts.items()):
        print(f"  {sn:<20} {n}")
    print()
    print("[CLASSIFIER] One per sub_niche (the call set):")
    one_each = fetch_one_per_sub_niche()
    for r in one_each:
        print(f"  lane {r['lane_id']:<2} | {r['sub_niche']:<20} | "
              f"{r['classification']:<8} | {r['product_description'][:60]}")
