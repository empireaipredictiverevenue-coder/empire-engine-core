"""
EMPIRE V49 · PAIN POINTS LIBRARY
=================================
Niche-specific pain point profiles that the AI Closer uses during call scripts,
SMS/email nurture, and the SI Strategy Evolution genome.

Each niche has a catalog of pain points. Each pain point has:
  - A label/name (e.g. "Claim Denial Nightmare")
  - A hook phrase (spoken on calls, e.g. "Insurance denied your roof claim?")
  - A resolution promise (e.g. "We specialize in overturning denials")
  - Proof points (data/statistics to back the claim)
  - A weight (conversion effectiveness, 0.0-1.0, learned over time)

The PainPointLibrary tracks which pain points convert best per niche
and feeds that data into:
  1. empire_ai_closer._build_live_script() — inject top 1-2 pain points
  2. empire_si_strategy.StrategyEvolution — pain point weights as genome traits
  3. SPA Pain Points tab — analytics dashboard
  4. CSV/Excel export endpoint

Usage:
  from empire_pain_points import PainPointLibrary
  ppl = PainPointLibrary(get_db=get_db)
  script = ppl.inject_pain_points(niche, base_script)
  ppl.record_outcome(niche, pain_point_id, success)
"""

import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timezone

log = logging.getLogger("empire.pain_points")


# ── PAIN POINT CATALOG PER NICHE ────────────────────────────────────
# Each pain point: {id, label, hook, resolution, proof, weight (default)}
PAIN_POINTS_CATALOG: Dict[str, List[Dict[str, Any]]] = {
    "Roofing Restoration": [
        {
            "id": "roof_denial",
            "label": "Claim Denial Nightmare",
            "hook": "Did your insurance deny or lowball your roof claim?",
            "resolution": "We specialize in overturning denied claims — our contractors work directly with adjusters and get approvals 87% of the time.",
            "proof": "3,200+ denied claims overturned in 2025. Average settlement increase: 2.4x.",
            "weight": 0.65,
        },
        {
            "id": "roof_leak",
            "label": "Leaking Into Operations",
            "hook": "Is water getting into your building and disrupting operations?",
            "resolution": "We can have a tarp crew out same-day to stop the damage. Full restoration follows within 72 hours.",
            "proof": "Average response time: 4.2 hours. 98% satisfaction on emergency response.",
            "weight": 0.60,
        },
        {
            "id": "roof_out_of_pocket",
            "label": "Out-of-Pocket Fear",
            "hook": "Worried about what this will cost you out-of-pocket?",
            "resolution": "Most of our commercial clients pay $0 out-of-pocket. We handle the insurance coordination from start to finish.",
            "proof": "94% of commercial claims resolved with zero client out-of-pocket cost.",
            "weight": 0.55,
        },
        {
            "id": "roof_bad_contractor",
            "label": "Bad Contractor Burn",
            "hook": "Burnt by a previous contractor who did shoddy work or disappeared?",
            "resolution": "We're licensed, bonded, and insured in 18 states with a 5-year workmanship warranty on every job.",
            "proof": "Zero unresolved complaints with BBB. 4.8★ average across 1,400+ reviews.",
            "weight": 0.50,
        },
        {
            "id": "roof_business_interruption",
            "label": "Business Interruption",
            "hook": "How much revenue are you losing every day that roof stays damaged?",
            "resolution": "Our commercial crews work weekends and after-hours to minimize your downtime.",
            "proof": "Average job completion: 40% faster than industry standard for commercial properties.",
            "weight": 0.58,
        },
    ],
    "Tornado Damage Repair": [
        {
            "id": "tornado_total_loss",
            "label": "Total Loss Uncertainty",
            "hook": "Are you worried the adjuster will call it a total loss and you'll be stuck?",
            "resolution": "Our forensic engineers counter insurer reports with data-backed assessments. We fight for full replacement value.",
            "proof": "83% of initial 'total loss' assessments were reversed on appeal with our documentation.",
            "weight": 0.62,
        },
        {
            "id": "tornado_fema_delay",
            "label": "FEMA / SBA Delay",
            "hook": "FEMA or SBA loan taking too long while your property deteriorates?",
            "resolution": "We can begin emergency stabilization now and work with your SBA loan timeline for full restoration.",
            "proof": "Emergency tarp/tarp stabilization available within 6 hours of dispatch.",
            "weight": 0.55,
        },
        {
            "id": "tornado_debris",
            "label": "Debris & Safety Hazard",
            "hook": "Is debris making your property unsafe for employees or customers?",
            "resolution": "We deploy debris removal teams alongside structural assessment. Get your property back to safe condition fast.",
            "proof": "Full-service storm response: debris → tarp → structural → restoration in one contract.",
            "weight": 0.52,
        },
    ],
    "Hurricane Damage Restoration": [
        {
            "id": "hurricane_flood_mold",
            "label": "Mold & Flood Damage",
            "hook": "Water has been sitting — are you worried about mold spreading through the building?",
            "resolution": "Our water extraction and mold remediation teams are IICRC-certified. We stop mold before it spreads.",
            "proof": "Industrial dehumidification reduces moisture to safe levels within 48 hours. Mold remediation certified.",
            "weight": 0.60,
        },
        {
            "id": "hurricane_multiple_damage",
            "label": "Multi-System Damage Overwhelm",
            "hook": "Roof damage plus flooding plus structural — dealing with multiple claims is overwhelming, isn't it?",
            "resolution": "One point of contact handles your entire restoration. Roof, water, structural — we coordinate it all.",
            "proof": "Single-source restoration reduces claim resolution time by 35% vs. hiring separate contractors.",
            "weight": 0.58,
        },
        {
            "id": "hurricane_vacant",
            "label": "Vacant Property Risk",
            "hook": "Is your property sitting vacant and becoming a target for looters or squatters?",
            "resolution": "We can secure the property today — board-up, fencing, and security monitoring included in our emergency package.",
            "proof": "24/7 emergency board-up and security deployment across Gulf and Atlantic states.",
            "weight": 0.50,
        },
    ],
    "Hail Damage Repair": [
        {
            "id": "hail_hidden_damage",
            "label": "Hidden Damage",
            "hook": "Hail damage isn't always visible — are you sure your adjuster caught everything?",
            "resolution": "Our infrared drone scans catch subsurface damage that visual inspections miss. We document everything for your claim.",
            "proof": "47% of hail damage claims had additional damages discovered through infrared scanning.",
            "weight": 0.63,
        },
        {
            "id": "hail_cosmetic_denial",
            "label": "Cosmetic Denial",
            "hook": "Did your adjuster say the damage is 'just cosmetic' and not covered?",
            "resolution": "We provide certified engineering reports proving functional impairment. 'Cosmetic' doesn't mean 'harmless.'",
            "proof": "71% of 'cosmetic' denials were successfully appealed with our engineering documentation.",
            "weight": 0.59,
        },
        {
            "id": "hail_multiple_structures",
            "label": "Multiple Structure Fatigue",
            "hook": "Managing repairs across multiple buildings or units is a logistical nightmare, isn't it?",
            "resolution": "Our commercial team handles multi-structure projects as a single coordinated operation — same crew, same standards.",
            "proof": "Largest single project: 47 buildings restored across 12 weeks with zero safety incidents.",
            "weight": 0.48,
        },
    ],
    "Flood Damage Restoration": [
        {
            "id": "flood_excluded",
            "label": "Flood Exclusion Fear",
            "hook": "Standard insurance doesn't cover floods — are you staring at a six-figure repair bill?",
            "resolution": "We navigate FEMA, NFIP, and supplemental coverage options. Most clients recover 70-90% of costs through combined programs.",
            "proof": "$48M in flood restoration claims managed in 2025. Average client recovery rate: 82%.",
            "weight": 0.61,
        },
        {
            "id": "flood_contamination",
            "label": "Contamination Hazard",
            "hook": "Floodwater carries sewage, chemicals, and biohazards — your building needs more than just drying out.",
            "resolution": "Our HazMat-certified teams handle Category 3 water damage with full decontamination protocols.",
            "proof": "IICRC-certified in Category 3 (black water) remediation. OSHA-compliant protocols.",
            "weight": 0.54,
        },
        {
            "id": "flood_equipment_loss",
            "label": "Equipment & Inventory Loss",
            "hook": "How much equipment and inventory did you lose to the flooding?",
            "resolution": "We document and value every asset for your claim — machinery, inventory, IT equipment — nothing gets missed.",
            "proof": "Average additional recovery from undocumented assets: $127K per commercial flood claim.",
            "weight": 0.53,
        },
    ],
    "Storm Damage Restoration": [
        {
            "id": "storm_urgent",
            "label": "Urgency — Storm Window Closing",
            "hook": "Storm repair windows close fast — insurance deadlines, contractor availability, material shortages. Are you on top of all three?",
            "resolution": "We pre-reserve materials and crews the moment a storm is forecast in your area. You're first in line.",
            "proof": "Pre-positioned crews and materials in 8 storm-prone regions. Average dispatch: 3 hours post-storm.",
            "weight": 0.57,
        },
        {
            "id": "storm_compliance",
            "label": "Code Compliance Risk",
            "hook": "Did you know storm repairs often trigger mandatory building code upgrades that insurance might fight?",
            "resolution": "We identify all code-triggered upgrades upfront and include them in the claim — your insurer can't say 'we didn't know.'",
            "proof": "$14M in code-upgrade costs recovered for commercial clients in 2025.",
            "weight": 0.50,
        },
        {
            "id": "storm_liability",
            "label": "Liability Exposure",
            "hook": "Every day that damage sits unrepaired, your liability exposure grows — slip-and-fall, structural failure, tenant complaints.",
            "resolution": "We carry $10M in general liability and can begin mitigation today. Protect yourself from lawsuits.",
            "proof": "Fully insured — $10M GL, $5M umbrella, Workers' Comp in all operating states.",
            "weight": 0.52,
        },
    ],
    "Legal Intake": [
        {
            "id": "legal_missed_deadline",
            "label": "Statute of Limitations",
            "hook": "Every day you wait, evidence deteriorates and legal deadlines tick closer. Are you sure you haven't already passed a critical filing date?",
            "resolution": "We connect you with a vetted attorney within 24 hours who will evaluate your case and file immediately if deadlines are imminent.",
            "proof": "1,800+ attorney placements in 2025. Average time-to-call: 3.2 hours after intake.",
            "weight": 0.58,
        },
        {
            "id": "legal_no_win_no_fee",
            "label": "No Win, No Fee",
            "hook": "Worried about legal fees? Most of our partner attorneys work on contingency — you don't pay unless you win.",
            "resolution": "We only match you with contingency-fee attorneys. Zero upfront cost. Zero risk.",
            "proof": "94% of matched cases accepted on contingency. Average settlement: $185K.",
            "weight": 0.52,
        },
    ],
}

# Default pain points for any niche not in the catalog
_DEFAULT_PAIN_POINTS = [
    {
        "id": "default_cost",
        "label": "Cost Uncertainty",
        "hook": "Are you worried about what this is going to cost?",
        "resolution": "We offer transparent pricing and will work with your budget to find a solution.",
        "proof": "Competitive rates with proven results.",
        "weight": 0.50,
    },
    {
        "id": "default_timeline",
        "label": "Timeline Pressure",
        "hook": "Concerned about how long repairs will take?",
        "resolution": "We prioritize rapid response — our crews are ready to deploy immediately.",
        "proof": "Industry-leading response times with quality guarantees.",
        "weight": 0.48,
    },
]


class PainPointLibrary:
    """
    Manages pain point profiles, tracks conversion effectiveness per niche,
    and injects the best-performing pain points into closer scripts.
    """

    def __init__(self, get_db: Optional[Callable] = None):
        self.get_db = get_db
        # Per-niche pain point catalog with dynamic weights
        self._catalog: Dict[str, Dict[str, Dict]] = {}
        # Outcome tracking: (niche, pp_id) -> {attempts, successes, last_success_ts}
        self._outcomes: Dict[tuple, Dict] = {}
        self._init_catalog()

    def _init_catalog(self):
        """Seed the catalog from static definitions with mutable weights."""
        for niche, points in PAIN_POINTS_CATALOG.items():
            self._catalog[niche] = {}
            for pp in points:
                self._catalog[niche][pp["id"]] = dict(pp)
        # Load any stored weights from DB
        self._load_from_db()

    def _load_from_db(self):
        """Load persisted pain point weights from pain_points_pool table."""
        if not self.get_db:
            return
        try:
            db = self.get_db()
            rows = db.table("pain_points_pool").select("*").execute()
            for row in (rows.data or []):
                niche = row.get("niche", "")
                pp_id = row.get("pain_point_id", "")
                if niche in self._catalog and pp_id in self._catalog[niche]:
                    self._catalog[niche][pp_id]["weight"] = float(row.get("weight", 0.5))
                # Restore outcome tracking
                self._outcomes[(niche, pp_id)] = {
                    "attempts": int(row.get("attempts", 0)),
                    "successes": int(row.get("successes", 0)),
                    "last_success_ts": row.get("last_success_ts"),
                }
        except Exception as e:
            log.debug(f"[pain_points] DB load skipped: {e}")

    def _persist_outcome(self, niche: str, pp_id: str):
        """Write outcome data back to pain_points_pool."""
        if not self.get_db:
            return
        try:
            key = (niche, pp_id)
            outcomes = self._outcomes.get(key, {"attempts": 0, "successes": 0})
            weight = self._catalog.get(niche, {}).get(pp_id, {}).get("weight", 0.5)
            db = self.get_db()
            db.table("pain_points_pool").upsert({
                "niche": niche,
                "pain_point_id": pp_id,
                "label": self._catalog.get(niche, {}).get(pp_id, {}).get("label", pp_id),
                "weight": weight,
                "attempts": outcomes["attempts"],
                "successes": outcomes["successes"],
                "last_success_ts": outcomes.get("last_success_ts"),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }, on_conflict="niche,pain_point_id").execute()
        except Exception as e:
            log.debug(f"[pain_points] persist failed: {e}")

    # ── GET PAIN POINTS FOR NICHE ───────────────────────────────────
    def get_pain_points(self, niche: str) -> List[Dict]:
        """Return pain points for a niche, sorted by weight (highest first)."""
        if niche in self._catalog:
            points = list(self._catalog[niche].values())
        else:
            points = list(_DEFAULT_PAIN_POINTS)
        return sorted(points, key=lambda p: p.get("weight", 0), reverse=True)

    # ── GET TOP PAIN POINT ──────────────────────────────────────────
    def get_top_pain_point(self, niche: str) -> Optional[Dict]:
        """Return the single highest-weight pain point for a niche."""
        points = self.get_pain_points(niche)
        return points[0] if points else None

    # ── INJECT PAIN POINTS INTO SCRIPT ─────────────────────────────
    def inject_pain_points(self, niche: str, base_script: str, max_points: int = 2) -> str:
        """
        Inject the top 1-2 pain point hooks into a closer call script.
        Inserts after the greeting/opener, before the call-to-action.
        """
        top = self.get_pain_points(niche)[:max_points]
        if not top:
            return base_script

        # Build pain point injection
        injections = []
        for pp in top:
            injections.append(f"{pp['hook']} {pp['resolution']}")

        injection_text = " " + " ".join(injections)

        # Inject after the first sentence boundary
        parts = base_script.split(". ", 1)
        if len(parts) == 2:
            return parts[0] + "." + injection_text + ". " + parts[1]
        return base_script + injection_text

    # ── GET PAIN POINTS FOR SCRIPT ──────────────────────────────────
    def get_script_pain_points(self, niche: str, max_points: int = 2) -> List[str]:
        """Return top pain point IDs to use in a script (for logging)."""
        return [p["id"] for p in self.get_pain_points(niche)[:max_points]]

    # ── RECORD OUTCOME ─────────────────────────────────────────────
    def record_outcome(self, niche: str, pain_point_ids: List[str], success: bool):
        """
        Record which pain points were used and whether the call/nurture succeeded.
        Adjusts weights using exponential moving average.
        Auto-creates entries for unseen pain points so the system learns from new niches.
        """
        if not pain_point_ids:
            return

        for pp_id in pain_point_ids:
            # Auto-create niche catalog entry if unseen
            if niche not in self._catalog:
                self._catalog[niche] = {}
                log.info(f"[pain_points] auto-created niche catalog entry: {niche}")

            if pp_id not in self._catalog[niche]:
                # Auto-register unknown pain point with default weight
                self._catalog[niche][pp_id] = {
                    "id": pp_id,
                    "label": pp_id.replace("_", " ").title(),
                    "hook": "",
                    "resolution": "",
                    "proof": "",
                    "weight": 0.5,
                }
                log.debug(f"[pain_points] auto-registered unknown pain point: {niche}/{pp_id}")

            key = (niche, pp_id)
            if key not in self._outcomes:
                self._outcomes[key] = {"attempts": 0, "successes": 0}

            self._outcomes[key]["attempts"] += 1
            if success:
                self._outcomes[key]["successes"] += 1
                self._outcomes[key]["last_success_ts"] = datetime.now(timezone.utc).isoformat()

            # Update weight via EMA (alpha=0.2)
            alpha = 0.2
            target = self._outcomes[key]["successes"] / self._outcomes[key]["attempts"]
            current = self._catalog[niche][pp_id]["weight"]
            self._catalog[niche][pp_id]["weight"] = round(current * (1 - alpha) + target * alpha, 3)

            self._persist_outcome(niche, pp_id)

    # ── SNAPSHOT ────────────────────────────────────────────────────
    def snapshot(self) -> Dict:
        """Return full pain point library state for the SPA / analytics."""
        by_niche = {}
        for niche, points in self._catalog.items():
            entries = []
            for pp_id, pp in points.items():
                outcomes = self._outcomes.get((niche, pp_id), {"attempts": 0, "successes": 0})
                attempts = outcomes["attempts"]
                successes = outcomes["successes"]
                entries.append({
                    "id": pp_id,
                    "label": pp["label"],
                    "hook": pp["hook"],
                    "resolution": pp["resolution"],
                    "proof": pp["proof"],
                    "weight": pp["weight"],
                    "attempts": attempts,
                    "successes": successes,
                    "conversion_rate": round(successes / attempts, 3) if attempts > 0 else 0,
                    "last_success_ts": outcomes.get("last_success_ts"),
                })
            entries.sort(key=lambda e: e["weight"], reverse=True)
            by_niche[niche] = {
                "total_attempts": sum(e["attempts"] for e in entries),
                "total_successes": sum(e["successes"] for e in entries),
                "pain_points": entries,
            }
        return {
            "niches": len(by_niche),
            "total_pain_points": sum(len(v["pain_points"]) for v in by_niche.values()),
            "by_niche": by_niche,
        }

    # ── GENOME RELEVANCE ────────────────────────────────────────────
    def get_genome_traits(self, niche: str) -> Dict[str, float]:
        """
        Return pain point weights as genome traits for SI Strategy Evolution.
        Keys are prefixed with 'pp_' to distinguish from other genome traits.
        """
        points = self.get_pain_points(niche)
        traits = {}
        for pp in points:
            traits[f"pp_{pp['id']}"] = pp["weight"]
        return traits

    # ── EXPORT ──────────────────────────────────────────────────────
    def export_csv(self) -> str:
        """Export pain points data as CSV string."""
        import csv, io
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Niche", "Pain Point ID", "Label", "Weight", "Attempts",
                          "Successes", "Conversion Rate", "Hook", "Resolution", "Proof"])
        for niche, points in self._catalog.items():
            for pp_id, pp in points.items():
                outcomes = self._outcomes.get((niche, pp_id), {"attempts": 0, "successes": 0})
                attempts = outcomes["attempts"]
                successes = outcomes["successes"]
                writer.writerow([
                    niche, pp_id, pp["label"], pp["weight"], attempts,
                    successes, round(successes / attempts, 3) if attempts > 0 else 0,
                    pp["hook"], pp["resolution"], pp["proof"],
                ])
        return output.getvalue()

    def export_excel_data(self) -> List[Dict]:
        """Export pain points data as list of dicts for Excel generation."""
        rows = []
        for niche, points in self._catalog.items():
            for pp_id, pp in points.items():
                outcomes = self._outcomes.get((niche, pp_id), {"attempts": 0, "successes": 0})
                rows.append({
                    "niche": niche,
                    "pain_point_id": pp_id,
                    "label": pp["label"],
                    "weight": pp["weight"],
                    "attempts": outcomes["attempts"],
                    "successes": outcomes["successes"],
                    "conversion_rate": round(outcomes["successes"] / outcomes["attempts"], 3)
                                       if outcomes["attempts"] > 0 else 0,
                    "hook": pp["hook"],
                    "resolution": pp["resolution"],
                    "proof": pp["proof"],
                })
        return rows
