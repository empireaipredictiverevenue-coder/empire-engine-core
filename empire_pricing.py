"""
EMPIRE V49 · PRICING PAGE + CPL PRICING ENGINE
=================================================
Standalone public pricing page served at /pricing.
Also contains the CPL_BENCHMARKS data structure and CPLPricingEngine
for per-vertical pricing strategy — CPL lookups, model recommendations,
ROI estimates, and margin calculations across all 32 lanes.
"""

import math
from typing import Dict, List, Optional, Tuple

from empire_tokens import empire_head


# ═════════════════════════════════════════════════════════════════════════
# CPL BENCHMARKS — Full Spectrum Data (from VERTICALS.md research)
# ═════════════════════════════════════════════════════════════════════════

CPL_BENCHMARKS: Dict[str, Dict] = {
    "Home Services": {
        "icon": "🏠",
        "best_model": "both",
        "volume": "highest",
        "sub_niches": {
            "Roofing":                  {"ppl": (162, 228), "ppc": (11, 258),  "best": "both",  "trigger": "Storm/hail, emergency",       "notes": "Google LSA delivers 30-50% lower CPL"},
            "HVAC":                     {"ppl": (51, 149),  "ppc": (10, 150),  "best": "both",  "trigger": "Weather extremes, seasonal",   "notes": "78% hire first responder"},
            "Plumbing":                 {"ppl": (57, 183),  "ppc": (14, 150),  "best": "ppc",   "trigger": "Emergency, burst pipe",         "notes": "Speed is highest-leverage metric"},
            "Electrical":               {"ppl": (35, 150),  "ppc": (20, 80),   "best": "both",  "trigger": "Emergency/renovation",           "notes": ""},
            "Water Damage Restoration": {"ppl": (40, 150),  "ppc": (40, 200),  "best": "ppc",   "trigger": "Flood/burst → immediate",       "notes": "Avg response time: ~47h"},
            "Mold Remediation":         {"ppl": (20, 80),   "ppc": (30, 120),  "best": "both",  "trigger": "Secondary to water damage",      "notes": ""},
            "Solar Installation":       {"ppl": (100, 300), "ppc": (50, 300),  "best": "ppl",   "trigger": "Policy-driven, IRA",             "notes": "Long consideration cycle"},
            "Pest Control":             {"ppl": (20, 60),   "ppc": (20, 108),  "best": "both",  "trigger": "Seasonal, recurring",            "notes": "Recurring revenue model"},
            "Bath Remodeling":          {"ppl": (50, 120),  "ppc": (19, 120),  "best": "both",  "trigger": "Renovation cycle",               "notes": ""},
            "Window Repair/Install":    {"ppl": (40, 80),   "ppc": (11, 108),  "best": "both",  "trigger": "Seasonal",                      "notes": ""},
            "Home Security":            {"ppl": (20, 60),   "ppc": (25, 80),   "best": "ppl",   "trigger": "Subscription, high LTV",         "notes": "Recurring revenue model"},
        },
    },
    "Legal": {
        "icon": "⚖️",
        "best_model": "both",
        "volume": "high_value",
        "sub_niches": {
            "Personal Injury":         {"ppl": (250, 600), "ppc": (150, 400), "best": "both", "trigger": "Highest competition",           "notes": "Highest CPL; PI keywords >$200/click"},
            "Mass Tort":               {"ppl": (150, 350), "ppc": (100, 300), "best": "ppl",  "trigger": "Lower per-lead, high volume",    "notes": "FDA recall-driven"},
            "Workers Comp":            {"ppl": (150, 400), "ppc": (50, 150),  "best": "both", "trigger": "Highly dependent on local mkt",   "notes": "88% of legal search = phone call"},
            "Medical Malpractice":     {"ppl": (300, 700), "ppc": (200, 500), "best": "both", "trigger": "Most expensive legal sub-niche",  "notes": ""},
            "Criminal Defense":        {"ppl": (75, 185),  "ppc": (75, 200),  "best": "ppc",  "trigger": "Localized, urgent",              "notes": ""},
            "Family Law":              {"ppl": (75, 200),  "ppc": (30, 80),   "best": "both", "trigger": "Higher volume, lower margin",      "notes": "Divorce, custody"},
            "Class Action":            {"ppl": (100, 300), "ppc": (80, 250),  "best": "ppl",  "trigger": "FDA recall-driven",              "notes": ""},
            "Bankruptcy/Debt":         {"ppl": (25, 75),   "ppc": (40, 100),  "best": "both", "trigger": "Tied to economic cycles",          "notes": ""},
            "Business Litigation":     {"ppl": (50, 200),  "ppc": (50, 150),  "best": "ppl",  "trigger": "Contract disputes, IP",           "notes": "B2B"},
            "Social Security Disab":   {"ppl": (25, 60),   "ppc": (30, 80),   "best": "both", "trigger": "Steady demand",                   "notes": ""},
        },
    },
    "Insurance": {
        "icon": "🏥",
        "best_model": "both",
        "volume": "high",
        "sub_niches": {
            "Medicare Advantage":  {"ppl": (35, 85),   "ppc": (55, 110), "best": "both", "trigger": "AEP (Oct-Dec)",             "notes": "Exclusive leads close 10-20%"},
            "Medicare Supplement": {"ppl": (40, 95),   "ppc": (60, 120), "best": "both", "trigger": "Year-round",                "notes": ""},
            "Final Expense":       {"ppl": (15, 40),   "ppc": (25, 55),  "best": "ppc",  "trigger": "Year-round, senior demo",    "notes": ""},
            "Life Insurance":      {"ppl": (30, 80),   "ppc": (50, 120), "best": "both", "trigger": "Year-round",                "notes": ""},
            "ACA/Health":          {"ppl": (25, 65),   "ppc": (40, 90),  "best": "both", "trigger": "OEP (Nov-Jan)",             "notes": "Costs spike 15-30% during OEP"},
            "Auto Insurance":      {"ppl": (35, 85),   "ppc": (20, 50),  "best": "ppl",  "trigger": "Rate-shopping, year-round",  "notes": ""},
            "Commercial Insurance":{"ppl": (15, 40),   "ppc": (20, 60),  "best": "both", "trigger": "Year-round",                "notes": "B2B"},
        },
    },
    "Financial Services": {
        "icon": "💰",
        "best_model": "both",
        "volume": "medium",
        "sub_niches": {
            "Debt Consolidation":    {"ppl": (150, 400), "ppc": (50, 150),  "best": "both", "trigger": "Economic distress",           "notes": "Blended CPL often >$450"},
            "Debt Settlement":       {"ppl": (100, 300), "ppc": (30, 80),   "best": "both", "trigger": "Growing vertical",           "notes": ""},
            "Mortgage Refinance":    {"ppl": (250, 600), "ppc": (60, 150),  "best": "ppl",  "trigger": "Rate-driven",               "notes": "BANT-qualified 30-50% more"},
            "Business Loans/MCA":    {"ppl": (300, 800), "ppc": (75, 300),  "best": "both", "trigger": "Small business",             "notes": "Highest CPL in financial"},
            "Credit Repair":         {"ppl": (100, 300), "ppc": (30, 80),   "best": "both", "trigger": "Growing vertical",           "notes": ""},
            "Tax Resolution":        {"ppl": (100, 350), "ppc": (40, 100),  "best": "both", "trigger": "Tax season",                 "notes": ""},
            "Personal Loans":        {"ppl": (15, 50),   "ppc": (20, 40),   "best": "both", "trigger": "Year-round",                "notes": ""},
        },
    },
    "Healthcare": {
        "icon": "🏥",
        "best_model": "both",
        "volume": "medium",
        "sub_niches": {
            "Addiction Treatment":   {"ppl": (200, 500), "ppc": (150, 500), "best": "ppc",  "trigger": "Avg patient LTV: $78k+",     "notes": "Justifies extremely high CPLs"},
            "Mental Health":         {"ppl": (140, 380), "ppc": (100, 300), "best": "both", "trigger": "Growing, destigmatized",      "notes": "88% behavioral health = phone call"},
            "Assisted Living":       {"ppl": (75, 250),  "ppc": (100, 300), "best": "ppc",  "trigger": "Sales cycle: 3-6 months",     "notes": "Senior demographic"},
            "Home Health Care":      {"ppl": (50, 150),  "ppc": (60, 200),  "best": "both", "trigger": "Senior demographic",          "notes": ""},
            "Medical Alert Systems": {"ppl": (25, 100),  "ppc": (40, 150),  "best": "both", "trigger": "Recurring sub, ~$37/mo avg",   "notes": ""},
            "Dental (Cosmetic)":     {"ppl": (20, 60),   "ppc": (25, 60),   "best": "both", "trigger": "Elective",                    "notes": ""},
        },
    },
    "Senior Care": {
        "icon": "👴",
        "best_model": "ppc",
        "volume": "growing",
        "sub_niches": {
            "Assisted Living":  {"ppl": (75, 250),  "ppc": (100, 300), "best": "ppc", "trigger": "Sales cycle: 3-6 months",  "notes": "Senior demographic"},
            "Home Health":      {"ppl": (50, 150),  "ppc": (60, 200),  "best": "ppc", "trigger": "Senior demographic",       "notes": ""},
            "Medical Alert Sys":{"ppl": (25, 100),  "ppc": (40, 150),  "best": "both","trigger": "Recurring sub",            "notes": "~$37/mo avg"},
        },
    },
    "Education": {
        "icon": "📚",
        "best_model": "both",
        "volume": "medium",
        "sub_niches": {
            "CDL/Truck Driving":     {"ppl": (40, 120),  "ppc": (30, 80),   "best": "both", "trigger": "Labor shortage",           "notes": "Phone leads convert 3-10x higher"},
            "Nursing Certifications":{"ppl": (80, 200),  "ppc": (50, 120),  "best": "both", "trigger": "Healthcare demand",        "notes": "Optimal LTV:CAC = 3:1"},
            "HVAC/R Trade School":   {"ppl": (15, 40),   "ppc": (15, 35),   "best": "both", "trigger": "Skilled trades",            "notes": ""},
            "IT Certifications":     {"ppl": (60, 180),  "ppc": (40, 100),  "best": "ppl",  "trigger": "Cybersecurity, cloud",     "notes": ""},
            "Online Degree Programs":{"ppl": (100, 250), "ppc": (60, 150),  "best": "ppl",  "trigger": "Long decision cycle",      "notes": ""},
        },
    },
    "Business Services": {
        "icon": "🏢",
        "best_model": "ppl",
        "volume": "medium",
        "sub_niches": {
            "Managed IT":           {"ppl": (30, 100),  "ppc": (25, 60),   "best": "ppl", "trigger": "Cybersecurity, cloud",     "notes": "Fastest-growing B2B"},
            "Merchant Services":    {"ppl": (20, 60),   "ppc": (20, 50),   "best": "both", "trigger": "Small business",           "notes": ""},
            "HR & Staffing":        {"ppl": (20, 80),   "ppc": (20, 60),   "best": "ppl", "trigger": "Recurring need",           "notes": ""},
            "Payroll Services":     {"ppl": (15, 40),   "ppc": (15, 40),   "best": "ppl", "trigger": "Year-round",               "notes": ""},
            "Cybersecurity":        {"ppl": (40, 150),  "ppc": (30, 80),   "best": "ppl", "trigger": "Growing vertical",         "notes": ""},
            "VoIP/Business Phone":  {"ppl": (15, 40),   "ppc": (15, 40),   "best": "both", "trigger": "Year-round",               "notes": ""},
            "Incorporation":        {"ppl": (20, 50),   "ppc": (20, 45),   "best": "ppl", "trigger": "Entrepreneur cycle",       "notes": ""},
        },
    },
    "Consumer CPA": {
        "icon": "📊",
        "best_model": "ppl",
        "volume": "medium",
        "sub_niches": {
            "Consumer CPA": {"ppl": (15, 50), "ppc": (10, 40), "best": "ppl", "trigger": "Year-round", "notes": ""},
        },
    },
    "SEO": {
        "icon": "🔍",
        "best_model": "service",
        "volume": "enabler",
        "notes": "SEO is an enabler for all verticals — ROI measured in organic traffic cost avoidance ($0.50-$3/visitor vs $2-$50+/click for paid)",
        "sub_niches": {
            "Local SEO":     {"ppl": (None, None), "ppc": (None, None), "best": "service", "trigger": "GMB optimization",         "notes": "Service-based pricing"},
            "E-commerce SEO":{"ppl": (None, None), "ppc": (None, None), "best": "service", "trigger": "Product feeds, categories", "notes": "Service-based pricing"},
            "Technical SEO": {"ppl": (None, None), "ppc": (None, None), "best": "service", "trigger": "Core Web Vitals, speed",    "notes": "Service-based pricing"},
        },
    },
    "Roofing Restoration": {
        "icon": "🏠",
        "best_model": "both",
        "volume": "highest",
        "notes": "Storm-triggered vertical with immediate urgency; speed is the highest-leverage metric",
        "sub_niches": {
            "Roofing Restoration":{"ppl": (162, 228), "ppc": (11, 258), "best": "both", "trigger": "Storm/hail, emergency", "notes": "78% hire first responder"},
        },
    },
    "Commercial Roofing": {
        "icon": "🏭",
        "best_model": "both",
        "volume": "medium",
        "notes": "B2B sale focused on commercial/industrial flat roofing. Longer sales cycle, higher ticket than residential.",
        "sub_niches": {
            "Commercial Roofing": {"ppl": (100, 350), "ppc": (50, 200), "best": "both", "trigger": "Storm damage, building age, energy efficiency", "notes": "Higher ticket than residential; multi-sqft flat roof"},
        },
    },
    "Commercial Solar": {
        "icon": "☀️",
        "best_model": "ppl",
        "volume": "growing",
        "notes": "B2B solar for commercial/industrial properties. Policy-driven (IRA, tax credits). Longer consideration cycle.",
        "sub_niches": {
            "Commercial Solar": {"ppl": (150, 400), "ppc": (75, 250), "best": "ppl", "trigger": "IRA/tax credits, energy cost reduction, ESG mandates", "notes": "B2B decision cycle; higher ticket than residential"},
        },
    },
    "Debt Relief": {
        "icon": "🛡️",
        "best_model": "both",
        "volume": "high",
        "notes": "Covers debt settlement, consolidation, and credit repair. Economic distress drives demand.",
        "sub_niches": {
            "Debt Relief": {"ppl": (100, 350), "ppc": (30, 150), "best": "both", "trigger": "Economic distress, interest rate environment", "notes": "Blended CPL tracks Debt Settlement $100-300 + Debt Consolidation $150-400"},
        },
    },
}

# Lane-to-niche mapping (mirrors mesh_orchestrator.py)
_LANE_NICHE_MAP: Dict[int, Dict[str, str]] = {
    0:  {"niche": "Roofing Restoration", "sub_niche": "Roofing Restoration", "strategy": "AGGRESSIVE_STRIKE"},
    1:  {"niche": "Roofing Restoration", "sub_niche": "Roofing Restoration", "strategy": "AGGRESSIVE_STRIKE"},
    2:  {"niche": "Roofing Restoration", "sub_niche": "Roofing Restoration", "strategy": "AGGRESSIVE_STRIKE"},
    3:  {"niche": "Roofing Restoration", "sub_niche": "Roofing Restoration", "strategy": "AGGRESSIVE_STRIKE"},
    4:  {"niche": "Roofing Restoration", "sub_niche": "Roofing Restoration", "strategy": "AGGRESSIVE_STRIKE"},
    5:  {"niche": "HVAC", "sub_niche": "HVAC", "strategy": "UGLY_BANNER"},
    6:  {"niche": "HVAC", "sub_niche": "HVAC", "strategy": "UGLY_BANNER"},
    7:  {"niche": "SEO", "sub_niche": "Local SEO", "strategy": "STANDARD"},
    8:  {"niche": "SEO", "sub_niche": "E-commerce SEO", "strategy": "STANDARD"},
    9:  {"niche": "SEO", "sub_niche": "Technical SEO", "strategy": "STANDARD"},
    10: {"niche": "Legal", "sub_niche": "Personal Injury", "strategy": "RECALL_SNIPER"},
    11: {"niche": "Legal", "sub_niche": "Mass Tort", "strategy": "RECALL_SNIPER"},
    12: {"niche": "Legal", "sub_niche": "Class Action", "strategy": "RECALL_SNIPER"},
    13: {"niche": "Legal", "sub_niche": "Workers Comp", "strategy": "RECALL_SNIPER"},
    14: {"niche": "Legal", "sub_niche": "Medical Malpractice", "strategy": "RECALL_SNIPER"},
    15: {"niche": "Insurance", "sub_niche": "Medicare Advantage", "strategy": "INSURANCE_STRIKE"},
    16: {"niche": "Insurance", "sub_niche": "Life Insurance", "strategy": "INSURANCE_STRIKE"},
    17: {"niche": "Insurance", "sub_niche": "Final Expense", "strategy": "INSURANCE_STRIKE"},
    18: {"niche": "Financial Services", "sub_niche": "Debt Consolidation", "strategy": "FINANCIAL_STRIKE"},
    19: {"niche": "Financial Services", "sub_niche": "Business Loans/MCA", "strategy": "FINANCIAL_STRIKE"},
    20: {"niche": "Consumer CPA", "sub_niche": "Consumer CPA", "strategy": "FINANCIAL_STRIKE"},
    21: {"niche": "Consumer CPA", "sub_niche": "Consumer CPA", "strategy": "FINANCIAL_STRIKE"},
    22: {"niche": "Senior Care", "sub_niche": "Assisted Living", "strategy": "SENIOR_STRIKE"},
    23: {"niche": "Senior Care", "sub_niche": "Home Health", "strategy": "SENIOR_STRIKE"},
    24: {"niche": "Healthcare", "sub_niche": "Addiction Treatment", "strategy": "HEALTH_STRIKE"},
    25: {"niche": "Education", "sub_niche": "CDL/Truck Driving", "strategy": "STANDARD"},
    26: {"niche": "Education", "sub_niche": "Nursing Certifications", "strategy": "STANDARD"},
    27: {"niche": "Healthcare", "sub_niche": "Mental Health", "strategy": "HEALTH_STRIKE"},
    28: {"niche": "Healthcare", "sub_niche": "Medical Alert Systems", "strategy": "HEALTH_STRIKE"},    29: {"niche": "Business Services",   "sub_niche": "Managed IT", "strategy": "BIZ_STRIKE"},
    30: {"niche": "Business Services",   "sub_niche": "Merchant Services", "strategy": "BIZ_STRIKE"},
    31: {"niche": "Business Services",   "sub_niche": "HR & Staffing", "strategy": "BIZ_STRIKE"},
    32: {"niche": "Financial Services",  "sub_niche": "Mortgage Refinance", "strategy": "FINANCIAL_STRIKE"},
    33: {"niche": "Financial Services",  "sub_niche": "Debt Settlement", "strategy": "FINANCIAL_STRIKE"},
    34: {"niche": "Home Services",       "sub_niche": "Solar Installation", "strategy": "AGGRESSIVE_STRIKE"},
    35: {"niche": "Home Services",       "sub_niche": "Plumbing", "strategy": "UGLY_BANNER"},
    36: {"niche": "Home Services",       "sub_niche": "Water Damage Restoration", "strategy": "AGGRESSIVE_STRIKE"},
    37: {"niche": "Home Services",       "sub_niche": "Plumbing", "strategy": "AGGRESSIVE_STRIKE"},
    38: {"niche": "Commercial Roofing",    "sub_niche": "Commercial Roofing", "strategy": "AGGRESSIVE_STRIKE"},
    39: {"niche": "Commercial Solar",      "sub_niche": "Commercial Solar",   "strategy": "AGGRESSIVE_STRIKE"},
    40: {"niche": "Debt Relief",           "sub_niche": "Debt Relief",        "strategy": "FINANCIAL_STRIKE"},
}


# ═════════════════════════════════════════════════════════════════════════
# CPL PRICING ENGINE
# ═════════════════════════════════════════════════════════════════════════

class CPLPricingEngine:
    """
    Per-vertical CPL pricing strategy engine.

    Query CPL benchmarks, recommend optimal pricing models (PPL vs PPC),
    calculate ROI estimates, and generate per-lane pricing data.

    Can operate standalone (no DB, no external deps) for the pricing page,
    or be wired with actual lane outcome data for dynamic margin estimates.
    """

    @staticmethod
    def list_niches() -> List[str]:
        """Return all available niche names."""
        return sorted(CPL_BENCHMARKS.keys())

    @staticmethod
    def get_niche(niche: str) -> Optional[Dict]:
        """Return the full CPL benchmark data for a niche."""
        return CPL_BENCHMARKS.get(niche)

    @staticmethod
    def get_sub_niche(niche: str, sub_niche: str) -> Optional[Dict]:
        """Return CPL data for a specific sub-niche within a niche."""
        n = CPL_BENCHMARKS.get(niche)
        if not n:
            return None
        return n.get("sub_niches", {}).get(sub_niche)

    @staticmethod
    def find_sub_niche(query: str) -> Optional[Tuple[str, str, Dict]]:
        """Search all niches for a sub-niche matching `query` (case-insensitive).
        Returns (niche_name, sub_niche_name, data) or None.
        """
        if not query:
            return None
        q = query.lower()
        for niche_name, niche_data in CPL_BENCHMARKS.items():
            for sn_name, sn_data in niche_data.get("sub_niches", {}).items():
                if q in sn_name.lower():
                    return (niche_name, sn_name, sn_data)
        return None

    @staticmethod
    def cpl_range(sub_niche_data: Dict, model: str = "ppl") -> Tuple[Optional[float], Optional[float]]:
        """Get the CPL range (low, high) for a sub-niche by model type."""
        key = "ppl" if model in ("ppl", "PPL") else "ppc"
        pair = sub_niche_data.get(key, (None, None))
        if pair and pair[0] is None and pair[1] is None:
            return (None, None)
        return pair if isinstance(pair, (tuple, list)) and len(pair) == 2 else (None, None)

    @staticmethod
    def recommend_model(niche: str, sub_niche: Optional[str] = None) -> Dict:
        """
        Recommend the optimal pricing model (PPL vs PPC) for a niche/sub-niche.

        Returns a dict with the recommendation, reasoning, and CPL ranges for both models.
        """
        niche_data = CPL_BENCHMARKS.get(niche)
        if not niche_data:
            return {"niche": niche, "error": "niche not found"}

        if sub_niche and sub_niche in niche_data.get("sub_niches", {}):
            sn = niche_data["sub_niches"][sub_niche]
            best = sn.get("best", niche_data.get("best_model", "both"))
            ppl_range = CPLPricingEngine.cpl_range(sn, "ppl")
            ppc_range = CPLPricingEngine.cpl_range(sn, "ppc")
            return {
                "niche": niche,
                "sub_niche": sub_niche,
                "recommended": best,
                "reasoning": {
                    "ppl": f"PPL: ${ppl_range[0]}-${ppl_range[1]}" if ppl_range[0] else "N/A",
                    "ppc": f"PPC: ${ppc_range[0]}-${ppc_range[1]}" if ppc_range[0] else "N/A",
                },
                "cpl_ranges": {
                    "ppl": {"low": ppl_range[0], "high": ppl_range[1]},
                    "ppc": {"low": ppc_range[0], "high": ppc_range[1]},
                },
                "trigger": sn.get("trigger", ""),
                "notes": sn.get("notes", ""),
            }

        # Niche-level recommendation
        best = niche_data.get("best_model", "both")
        return {
            "niche": niche,
            "sub_niche": None,
            "recommended": best,
            "reasoning": {
                "ppl": "Form-fill leads for top-of-funnel volume",
                "ppc": "Live inbound calls for bottom-of-funnel conversion",
            },
            "trigger": niche_data.get("notes", ""),
            "volume": niche_data.get("volume", ""),
        }

    @staticmethod
    def roi_estimate(
        niche: str,
        sub_niche: Optional[str] = None,
        monthly_volume: int = 100,
        sell_price_per_lead: Optional[float] = None,
        model: str = "ppl",
    ) -> Dict:
        """
        Estimate ROI for a vertical given monthly volume.

        Calculates:
          - Cost per lead (midpoint of CPL range)
          - Monthly acquisition cost (CPL × volume)
          - Monthly revenue (sell_price × volume × close_rate)
          - Gross margin
          - ROI percentage
          - Breakeven volume

        Args:
            niche: Vertical name
            sub_niche: Specific sub-niche (optional)
            monthly_volume: Expected leads per month
            sell_price_per_lead: What you sell the lead for (defaults to 2.5x CPL)
            model: "ppl" or "ppc"

        Returns dict with all estimates.
        """
        sn_data = None
        if sub_niche:
            sn_data = CPLPricingEngine.get_sub_niche(niche, sub_niche)
        if not sn_data:
            # Fall back to first sub-niche in the niche
            niche_data = CPL_BENCHMARKS.get(niche)
            if niche_data and niche_data.get("sub_niches"):
                first_sn = list(niche_data["sub_niches"].keys())[0]
                sn_data = niche_data["sub_niches"][first_sn]
                sub_niche = first_sn

        if not sn_data:
            return {"niche": niche, "error": "No pricing data available"}

        ppl = sn_data.get("ppl", (None, None))
        ppc = sn_data.get("ppc", (None, None))

        if model in ("ppl", "PPL"):
            cpl_mid = ((ppl[0] or 0) + (ppl[1] or 0)) / 2 if ppl[0] and ppl[1] else None
        else:
            cpl_mid = ((ppc[0] or 0) + (ppc[1] or 0)) / 2 if ppc[0] and ppc[1] else None

        if not cpl_mid or cpl_mid <= 0:
            return {"niche": niche, "sub_niche": sub_niche, "error": "Could not determine CPL"}

        # Default sell price: 2.5x CPL (industry standard markup)
        if sell_price_per_lead is None:
            sell_price_per_lead = round(cpl_mid * 2.5, 2)

        # Conservative close rate for this model
        close_rate = 0.15 if model == "ppl" else 0.30  # PPL 5-15%, PPC 20-40%

        monthly_acquisition_cost = cpl_mid * monthly_volume
        monthly_revenue = sell_price_per_lead * monthly_volume * close_rate
        gross_margin = monthly_revenue - monthly_acquisition_cost
        roi_pct = (gross_margin / monthly_acquisition_cost * 100) if monthly_acquisition_cost > 0 else 0
        breakeven_volume = int(math.ceil(monthly_acquisition_cost / max(sell_price_per_lead * close_rate, 0.01)))

        return {
            "niche": niche,
            "sub_niche": sub_niche,
            "model": model,
            "cpl_midpoint": round(cpl_mid, 2),
            "cpl_range": {
                "low": round(ppl[0], 2) if ppl[0] else None,
                "high": round(ppl[1], 2) if ppl[1] else None,
            } if model == "ppl" else {
                "low": round(ppc[0], 2) if ppc[0] else None,
                "high": round(ppc[1], 2) if ppc[1] else None,
            },
            "sell_price_per_lead": sell_price_per_lead,
            "close_rate": close_rate,
            "monthly_volume": monthly_volume,
            "monthly_acquisition_cost": round(monthly_acquisition_cost, 2),
            "monthly_revenue": round(monthly_revenue, 2),
            "gross_margin": round(gross_margin, 2),
            "roi_percentage": round(roi_pct, 1),
            "breakeven_volume": breakeven_volume,
        }

    @staticmethod
    def suggest_sell_price(niche: str, sub_niche: str, target_margin_pct: float = 60.0,
                          model: str = "ppl") -> Dict:
        """
        Suggest an optimal sell price per lead given a target margin.

        Formula: sell_price = CPL_mid / (1 - target_margin/100)

        Returns the suggested price and the margin at that price.
        """
        sn_data = CPLPricingEngine.get_sub_niche(niche, sub_niche)
        if not sn_data:
            return {"error": f"No data for {niche}/{sub_niche}"}

        pair = sn_data.get(model, (None, None))
        cpl_mid = ((pair[0] or 0) + (pair[1] or 0)) / 2 if pair[0] and pair[1] else None
        if not cpl_mid or cpl_mid <= 0:
            return {"niche": niche, "sub_niche": sub_niche, "error": f"No {model} data"}

        margin_dec = target_margin_pct / 100.0
        suggested = round(cpl_mid / (1 - margin_dec), 2) if margin_dec < 1 else 0
        actual_margin = round((1 - cpl_mid / suggested) * 100, 1) if suggested > 0 else 0

        # Industry benchmark markup
        markup_multiple = round(suggested / cpl_mid, 2) if cpl_mid > 0 else 0

        return {
            "niche": niche,
            "sub_niche": sub_niche,
            "model": model,
            "cpl_midpoint": round(cpl_mid, 2),
            "target_margin_pct": target_margin_pct,
            "suggested_sell_price": suggested,
            "actual_margin_pct": actual_margin,
            "markup_multiple": markup_multiple,
            "formula": f"${cpl_mid:.2f} / (1 - {margin_dec:.2f}) = ${suggested:.2f}",
        }

    @staticmethod
    def lane_pricing(model: str = "ppl", monthly_volume: int = 100) -> Dict:
        """
        Generate per-lane pricing data for all 32 lanes.

        Maps each lane to its CPL benchmark and computes pricing estimates.
        Useful for the pricing page, API, and automated lane pricing strategies.
        """
        lanes = []
        for lane_id in range(41):
            lm = _LANE_NICHE_MAP.get(lane_id)
            if not lm:
                continue

            niche = lm["niche"]
            sub_niche = lm["sub_niche"]

            # Try exact sub-niche match, then find by search
            sn_data = CPLPricingEngine.get_sub_niche(niche, sub_niche)
            if not sn_data:
                found = CPLPricingEngine.find_sub_niche(sub_niche)
                if found:
                    _, _, sn_data = found

            if not sn_data:
                lanes.append({
                    "lane_id": lane_id,
                    "niche": niche,
                    "sub_niche": sub_niche,
                    "strategy": lm["strategy"],
                    "cpl_available": False,
                })
                continue

            ppl_range = CPLPricingEngine.cpl_range(sn_data, "ppl")

            # SEO/service lanes have None CPL values — mark as unavailable
            if ppl_range == (None, None):
                lanes.append({
                    "lane_id": lane_id,
                    "niche": niche,
                    "sub_niche": sub_niche,
                    "strategy": lm["strategy"],
                    "cpl_available": False,
                })
                continue
            ppc_range = CPLPricingEngine.cpl_range(sn_data, "ppc")

            best_model = sn_data.get("best", CPL_BENCHMARKS.get(niche, {}).get("best_model", "both"))

            # ROI estimate at default volume
            roi = CPLPricingEngine.roi_estimate(
                niche, sub_niche, monthly_volume=monthly_volume, model=model
            ) if best_model != "service" else {}

            suggest = CPLPricingEngine.suggest_sell_price(
                niche, sub_niche, target_margin_pct=60.0, model=model
            ) if best_model != "service" else {}

            lanes.append({
                "lane_id": lane_id,
                "niche": niche,
                "sub_niche": sub_niche,
                "strategy": lm["strategy"],
                "best_model": best_model,
                "cpl_available": True,
                "ppc_ready": (best_model in ("ppc", "both")) and (
                    "storm" in (sn_data.get("trigger", "") or "").lower()
                    or "roofing" in niche.lower()
                    or ("emergency" in (sn_data.get("trigger", "") or "").lower() and best_model == "ppc")
                    or "flood" in (sn_data.get("trigger", "") or "").lower()
                    or "burst" in (sn_data.get("trigger", "") or "").lower()
                ),
                "cpl": {
                    "ppl": {"low": ppl_range[0], "high": ppl_range[1]},
                    "ppc": {"low": ppc_range[0], "high": ppc_range[1]},
                },
                "roi": roi,
                "suggested_pricing": suggest,
                "trigger": sn_data.get("trigger", ""),
                "notes": sn_data.get("notes", ""),
            })

        return {
            "total_lanes": len(lanes),
            "model": model,
            "monthly_volume": monthly_volume,
            "lanes": lanes,
        }

    @staticmethod
    def margin_calculator(
        niche: str,
        sub_niche: str,
        sell_price: float,
        monthly_volume: int = 100,
        model: str = "ppl",
    ) -> Dict:
        """
        Calculate margin and profit at a given sell price and volume.

        Given a specific sell price (e.g. what a Strike Pack subscriber pays per lead),
        calculate the margin, profit, and ROI for the Empire platform.
        """
        sn_data = CPLPricingEngine.get_sub_niche(niche, sub_niche)
        if not sn_data:
            return {"error": f"No data for {niche}/{sub_niche}"}

        pair = sn_data.get(model, (None, None))
        cpl_mid = ((pair[0] or 0) + (pair[1] or 0)) / 2 if pair[0] and pair[1] else None
        if not cpl_mid or cpl_mid <= 0:
            return {"error": f"No {model} data for {niche}/{sub_niche}"}

        # Platform math
        acquisition_monthly = cpl_mid * monthly_volume
        revenue_monthly = sell_price * monthly_volume
        gross_profit = revenue_monthly - acquisition_monthly
        margin_pct = (gross_profit / revenue_monthly * 100) if revenue_monthly > 0 else 0
        roi_pct = (gross_profit / acquisition_monthly * 100) if acquisition_monthly > 0 else 0
        markup = sell_price / cpl_mid if cpl_mid > 0 else 0

        # Annual projections
        annual_revenue = revenue_monthly * 12
        annual_profit = gross_profit * 12

        return {
            "niche": niche,
            "sub_niche": sub_niche,
            "model": model,
            "cpl_midpoint": round(cpl_mid, 2),
            "sell_price": sell_price,
            "markup_multiple": round(markup, 2),
            "monthly_volume": monthly_volume,
            "monthly_acquisition_cost": round(acquisition_monthly, 2),
            "monthly_revenue": round(revenue_monthly, 2),
            "monthly_gross_profit": round(gross_profit, 2),
            "margin_pct": round(margin_pct, 1),
            "roi_pct": round(roi_pct, 1),
            "annual_revenue": round(annual_revenue, 2),
            "annual_profit": round(annual_profit, 2),
        }

    @staticmethod
    def summary() -> Dict:
        """Return a summary of all niches with key stats."""
        summary_data = {}
        for niche_name, niche_data in CPL_BENCHMARKS.items():
            sub_count = len(niche_data.get("sub_niches", {}))
            ppl_avg = 0
            ppc_avg = 0
            count = 0
            for sn_name, sn_data in niche_data.get("sub_niches", {}).items():
                ppl = sn_data.get("ppl", (None, None))
                ppc = sn_data.get("ppc", (None, None))
                if ppl[0] and ppl[1]:
                    ppl_avg += (ppl[0] + ppl[1]) / 2
                    ppc_avg += (ppc[0] + ppc[1]) / 2 if ppc[0] and ppc[1] else 0
                    count += 1

            avg_ppl = round(ppl_avg / count, 2) if count > 0 else None
            avg_ppc = round(ppc_avg / count, 2) if count > 0 else None

            summary_data[niche_name] = {
                "icon": niche_data.get("icon", ""),
                "sub_niche_count": sub_count,
                "best_model": niche_data.get("best_model", "both"),
                "volume": niche_data.get("volume", ""),
                "avg_cpl_ppl": avg_ppl,
                "avg_cpl_ppc": avg_ppc,
            }
        return summary_data


# ── Convenience alias for imports ────────────────────────────────────────
cpl_engine = CPLPricingEngine()


# ═════════════════════════════════════════════════════════════════════════
# PRICING PAGE HTML — unchanged from before
# ═════════════════════════════════════════════════════════════════════════

def _suite_product_cards(products: list) -> str:
    """Render dynamic HTML product cards from product_metadata data."""
    if not products:
        return ''
    cards = []
    for p in products:
        tier = p.get("tier", "")
        name = p.get("display_name") or p.get("product_name") or tier
        desc = p.get("description", "")
        price = p.get("monthly_price_usd", 0) or 0
        features = p.get("features", [])
        if not isinstance(features, list):
            features = []
        badges = " ".join(f'<span class="pr-bdg pr-bdg-cyan">{f}</span>' for f in features[:3])
        cards.append(f'''    <div class="pr-card">
      <div class="pr-card-topline"></div>
      <div class="pr-card-header">
        <div class="pr-card-name">{name}</div>
        <div class="pr-card-desc">{desc[:80]}</div>
      </div>
      <div class="pr-card-badges">{badges}</div>
      <div class="pr-card-features">
        {chr(10).join(f'        <li>{f}</li>' for f in features[:6])}
      </div>
      <div class="pr-card-price">${price:,.0f}<span class="pr-card-price-sub">/mo</span></div>
      <a href="/crypto/checkout/{tier}" class="pr-card-cta">Subscribe with USDC</a>
    </div>''')
    return '<div class="pr-prods">\n' + "\n".join(cards) + '\n    </div>'






FALLBACK_SUITE_HTML = '''<!-- SECTION 1: SUITE PRODUCTS                                          -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-section">
    <div class="pr-section-h">
      <span class="pr-section-num">01</span>
      <span class="pr-section-title">Suite Products</span>
      <span class="pr-section-sub">SaaS subscription · per-feature</span>
    </div>

    <div class="pr-prods">

      <!-- Product 1: Inbound Router -->
      <div class="pr-card" style="animation-delay: 0.05s">
        <div class="pr-card-icon"><i class="ti ti-phone-incoming"></i></div>
        <div class="pr-card-name">Inbound Router</div>
        <div class="pr-card-desc">
          Traffic control &amp; intelligent routing for inbound leads.
          Parse intent, score urgency, and dispatch to the right channel.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg teal">Router SaaS</span>
          <span class="pr-bdg cyan">API</span>
        </div>
        <ul class="pr-card-features">
          <li>Real-time call triage with AI intent parsing</li>
          <li>Multi-channel dispatch (voice, SMS, email)</li>
          <li>Urgency scoring &amp; priority queuing</li>
          <li>Per-call usage metering</li>
        </ul>
        <div class="pr-card-price">$499 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $0.25 per routed call</div>
        <a href="/crypto/checkout/ROUTER_SaaS" class="pr-card-cta">Subscribe with USDC</a>
      </div>

      <!-- Product 2: Data Vault -->
      <div class="pr-card" style="animation-delay: 0.10s">
        <div class="pr-card-icon"><i class="ti ti-database"></i></div>
        <div class="pr-card-name">Data Vault</div>
        <div class="pr-card-desc">
          Secure data retention &amp; asset storage with configurable
          retention policies, encryption, and compliance logging.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg teal">Data Enterprise</span>
          <span class="pr-bdg amber">HIPAA-ready</span>
        </div>
        <ul class="pr-card-features">
          <li>Configurable retention policies (30-365 days)</li>
          <li>AES-256 encryption at rest &amp; in transit</li>
          <li>Full audit trail with compliance reporting</li>
          <li>Automated archival &amp; purge workflows</li>
        </ul>
        <div class="pr-card-price">$799 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $0.02 per stored record/mo</div>
        <a href="/crypto/checkout/DATA_ENTERPRISE" class="pr-card-cta">Subscribe with USDC</a>
      </div>

      <!-- Product 3: Buyer Spy AI -->
      <div class="pr-card" style="animation-delay: 0.15s">
        <div class="pr-card-icon"><i class="ti ti-eye"></i></div>
        <div class="pr-card-name">Buyer Spy AI</div>
        <div class="pr-card-desc">
          Network bypass &amp; buyer intelligence. Analyze transcripts,
          map buyer networks, and uncover hidden buying signals.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg teal">Spy Data</span>
          <span class="pr-bdg cyan">AI-powered</span>
        </div>
        <ul class="pr-card-features">
          <li>Deep transcript analysis with SI entity extraction</li>
          <li>Buyer network mapping &amp; relationship scoring</li>
          <li>Real-time buying signal detection</li>
          <li>API access for custom integrations</li>
        </ul>
        <div class="pr-card-price">$1,499 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $5 per analysis</div>
        <a href="/crypto/checkout/SPY_DATA" class="pr-card-cta">Subscribe with USDC</a>
      </div>

    </div>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  '''

def pricing_page(products: list = None) -> str:
    pricing_css = """
    /* ── PAGE SPECIFIC ──────────────────────────────────────────────── */
    .pr-wrap {
      max-width: 1200px;
      margin: 0 auto;
      padding: 48px 32px 80px;
      position: relative;
      z-index: 1;
    }
    .pr-header {
      text-align: center;
      margin-bottom: 56px;
      animation: empire-fade-up 0.6s var(--ease-out-empire) both;
    }
    .pr-eyebrow {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--signal-teal);
      letter-spacing: 0.32em;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    .pr-title {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 44px;
      letter-spacing: -0.04em;
      color: var(--empire-white);
      line-height: 1.1;
      margin-bottom: 16px;
    }
    .pr-title em {
      font-style: italic;
      font-weight: 700;
      color: var(--signal-teal);
    }
    .pr-sub {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      max-width: 640px;
      margin: 0 auto;
      line-height: 1.7;
    }
    .pr-nav {
      display: flex;
      justify-content: center;
      gap: 8px;
      margin-bottom: 48px;
      flex-wrap: wrap;
    }
    .pr-nav-btn {
      padding: 8px 18px;
      font-family: var(--font-mono);
      font-size: 9px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      border: 1px solid var(--empire-border);
      background: transparent;
      color: var(--empire-mist);
      cursor: pointer;
      border-radius: var(--radius-pill);
      transition: all 0.2s var(--ease-snap);
    }
    .pr-nav-btn:hover {
      color: var(--empire-white);
      border-color: var(--empire-border-hi);
    }
    .pr-nav-btn.active {
      color: var(--signal-teal);
      border-color: var(--signal-teal-soft);
      background: var(--signal-teal-soft);
    }

    /* ── SECTION ────────────────────────────────────────────────────── */
    .pr-section {
      margin-bottom: 64px;
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .pr-section:last-child { margin-bottom: 0; }
    .pr-section-h {
      display: flex;
      align-items: baseline;
      gap: 16px;
      margin-bottom: 28px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--empire-divider);
    }
    .pr-section-num {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--signal-teal);
      letter-spacing: 0.12em;
    }
    .pr-section-title {
      font-weight: 500;
      font-size: 20px;
      letter-spacing: -0.02em;
      color: var(--empire-white);
    }
    .pr-section-sub {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.14em;
      text-transform: uppercase;
      margin-left: auto;
    }

    /* ── PRODUCT CARDS (3-column) ───────────────────────────────────── */
    .pr-prods {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 16px;
    }
    .pr-card {
      background: var(--empire-surface);
      border: 1px solid var(--empire-border);
      padding: 28px 24px;
      position: relative;
      overflow: hidden;
      transition: all 0.25s var(--ease-snap);
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .pr-card:hover {
      border-color: var(--signal-teal-soft);
      transform: translateY(-2px);
      box-shadow: 0 8px 32px rgba(0,0,0,0.3);
    }
    .pr-card::before {
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 2px;
      background: linear-gradient(90deg, var(--signal-teal), var(--strike-cyan));
      opacity: 0.6;
    }
    .pr-card-icon {
      width: 36px;
      height: 36px;
      border-radius: var(--radius-sm);
      background: var(--signal-teal-soft);
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 16px;
      font-size: 18px;
      color: var(--signal-teal);
    }
    .pr-card-name {
      font-weight: 600;
      font-size: 17px;
      color: var(--empire-white);
      margin-bottom: 8px;
      letter-spacing: -0.01em;
    }
    .pr-card-desc {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.6;
      margin-bottom: 18px;
    }
    .pr-card-badges {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      margin-bottom: 16px;
    }
    .pr-bdg {
      display: inline-block;
      padding: 3px 8px;
      font-family: var(--font-mono);
      font-size: 8px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      border-radius: var(--radius-xs);
      border: 1px solid;
    }
    .pr-bdg.teal  { color: var(--signal-teal); border-color: rgba(68,229,184,0.25); background: var(--signal-teal-soft); }
    .pr-bdg.cyan  { color: var(--strike-cyan); border-color: rgba(90,200,250,0.25); background: var(--strike-cyan-soft); }
    .pr-bdg.amber { color: var(--status-amber); border-color: rgba(245,166,35,0.25); background: var(--status-amber-soft); }
    .pr-bdg.muted { color: var(--empire-fog); border-color: var(--empire-divider); }
    .pr-card-features {
      list-style: none;
      padding: 0;
      margin: 0 0 20px;
    }
    .pr-card-features li {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-silver);
      padding: 5px 0;
      border-bottom: 1px solid var(--empire-divider);
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .pr-card-features li:last-child { border-bottom: none; }
    .pr-card-features li::before {
      content: '→';
      color: var(--signal-teal);
      font-weight: 700;
      flex-shrink: 0;
    }
    .pr-card-price {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 32px;
      color: var(--signal-teal);
      line-height: 1;
      margin-bottom: 4px;
    }
    .pr-card-price small {
      font-size: 14px;
      color: var(--empire-mist);
      font-weight: 400;
    }
    .pr-card-price-sub {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      margin-bottom: 18px;
    }
    .pr-card-cta {
      display: inline-block;
      padding: 10px 22px;
      background: transparent;
      border: 1px solid var(--signal-teal);
      color: var(--signal-teal);
      font-family: var(--font-mono);
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      cursor: pointer;
      transition: all 0.2s var(--ease-snap);
      text-decoration: none;
      font-weight: 600;
    }
    .pr-card-cta:hover {
      background: var(--signal-teal);
      color: var(--empire-black);
    }

    /* ── TIER TABLE ─────────────────────────────────────────────────── */
    .pr-tier-table {
      width: 100%;
      border-collapse: collapse;
      background: var(--empire-surface);
      border: 1px solid var(--empire-border);
      margin-bottom: 24px;
    }
    .pr-tier-table thead th {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-mist);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      text-align: left;
      padding: 14px 16px;
      border-bottom: 1px solid var(--empire-divider);
      background: var(--empire-elevated);
      font-weight: 500;
    }
    .pr-tier-table thead th:first-child { border-radius: 0; }
    .pr-tier-table tbody td {
      padding: 14px 16px;
      border-bottom: 1px solid var(--empire-divider);
      font-size: 12px;
      color: var(--empire-silver);
      vertical-align: top;
    }
    .pr-tier-table tbody tr:last-child td { border-bottom: none; }
    .pr-tier-table tbody tr:hover { background: var(--empire-elevated); }
    .pr-tier-name {
      font-weight: 600;
      color: var(--empire-white);
      font-size: 13px;
    }
    .pr-tier-price {
      font-family: var(--font-mono);
      color: var(--signal-teal);
      font-weight: 500;
    }
    .pr-tier-features {
      font-size: 11px;
      line-height: 1.6;
    }
    .pr-tier-bdg {
      display: inline-block;
      font-family: var(--font-mono);
      font-size: 8px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 2px 7px;
      border-radius: var(--radius-xs);
      border: 1px solid;
      margin-left: 6px;
      vertical-align: middle;
    }
    .pr-tier-bdg.popular {
      color: var(--signal-teal);
      border-color: var(--signal-teal-soft);
      background: var(--signal-teal-soft);
    }
    .pr-tier-bdg.enterprise {
      color: var(--strike-cyan);
      border-color: rgba(90,200,250,0.2);
      background: var(--strike-cyan-soft);
    }

    /* ── STRIKE PACKS GRID ──────────────────────────────────────────── */
    .pr-packs {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 14px;
    }
    .pr-pack {
      background: var(--empire-surface);
      border: 1px solid var(--empire-divider);
      padding: 22px 20px;
      text-align: center;
      transition: all 0.2s var(--ease-snap);
      animation: empire-fade-up 0.5s var(--ease-out-empire) both;
    }
    .pr-pack:hover {
      border-color: var(--strike-cyan-soft);
      transform: translateY(-1px);
    }
    .pr-pack-tier {
      font-family: var(--font-mono);
      font-size: 8px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    .pr-pack-tier.standard   { color: var(--empire-mist); }
    .pr-pack-tier.combo      { color: var(--strike-cyan); }
    .pr-pack-tier.whale      { color: var(--signal-teal); }
    .pr-pack-tier.enterprise { color: var(--status-amber); }
    .pr-pack-name {
      font-weight: 600;
      font-size: 15px;
      color: var(--empire-white);
      margin-bottom: 6px;
    }
    .pr-pack-desc {
      font-size: 11px;
      color: var(--empire-mist);
      line-height: 1.5;
      margin-bottom: 14px;
    }
    .pr-pack-price {
      font-family: var(--font-display);
      font-weight: 200;
      font-size: 28px;
      color: var(--strike-cyan);
      line-height: 1;
      margin-bottom: 2px;
    }
    .pr-pack-price small {
      font-size: 12px;
      color: var(--empire-fog);
    }
    .pr-pack-ppl {
      font-family: var(--font-mono);
      font-size: 10px;
      color: var(--empire-fog);
      margin-bottom: 12px;
    }
    .pr-pack-lanes {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--empire-mist);
      margin-bottom: 12px;
    }
    .pr-pack-channels {
      display: flex;
      gap: 4px;
      justify-content: center;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }
    .pr-pack-channel {
      font-family: var(--font-mono);
      font-size: 7px;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      padding: 2px 6px;
      border-radius: 2px;
      border: 1px solid var(--empire-divider);
      color: var(--empire-fog);
    }

    /* ── FAQ / NOTE ─────────────────────────────────────────────────── */
    .pr-note {
      margin-top: 48px;
      padding: 24px;
      background: var(--empire-surface);
      border: 1px solid var(--empire-border);
      border-left: 3px solid var(--signal-teal);
    }
    .pr-note-title {
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--signal-teal);
      letter-spacing: 0.18em;
      text-transform: uppercase;
      margin-bottom: 10px;
    }
    .pr-note-body {
      font-size: 12px;
      color: var(--empire-mist);
      line-height: 1.7;
      max-width: 720px;
    }
    .pr-note-body a {
      color: var(--signal-teal);
      text-decoration: none;
    }
    .pr-note-body a:hover {
      text-decoration: underline;
    }

    /* ── RESPONSIVE ─────────────────────────────────────────────────── */
    @media (max-width: 900px) {
      .pr-prods { grid-template-columns: 1fr; }
      .pr-packs { grid-template-columns: repeat(2, 1fr); }
      .pr-title { font-size: 32px; }
      .pr-wrap { padding: 32px 20px 60px; }
    }
    @media (max-width: 540px) {
      .pr-packs { grid-template-columns: 1fr; }
    }

    /* ── FOOTER ─────────────────────────────────────────────────────── */
    .pr-foot {
      margin-top: 64px;
      padding-top: 24px;
      border-top: 1px solid var(--empire-divider);
      text-align: center;
      font-family: var(--font-mono);
      font-size: 9px;
      color: var(--empire-fog);
      letter-spacing: 0.24em;
      text-transform: uppercase;
    }
    .pr-foot a {
      color: var(--empire-mist);
      text-decoration: none;
      transition: color 0.2s;
    }
    .pr-foot a:hover { color: var(--signal-teal); }
    .pr-foot .sep {
      padding: 0 8px;
      color: var(--empire-shadow);
    }
    """

    head = empire_head(
        title="Empire AI · Pricing & Products",
        extra=pricing_css,
    )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body>

<div class="pr-wrap">

  <!-- HERO -->
  <div class="pr-header">
    <div class="pr-eyebrow">Products & Pricing</div>
    <h1 class="pr-title">Autonomous <em>Revenue</em> Engine</h1>
    <p class="pr-sub">
      Six integrated products powering a closed-loop revenue machine —
      from lead generation and AI-powered outreach to settlement tracking and predictive analytics.
    </p>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  {_suite_product_cards(products) if products else FALLBACK_SUITE_HTML}<!-- SECTION 2: SUITE TIERS                                              -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-section">
    <div class="pr-section-h">
      <span class="pr-section-num">02</span>
      <span class="pr-section-title">Suite Tiers</span>
      <span class="pr-section-sub">All-Access bundles</span>
    </div>

    <table class="pr-tier-table">
      <thead>
        <tr>
          <th>Tier</th>
          <th>Monthly</th>
          <th>Products</th>
          <th>Features</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td><span class="pr-tier-name">Router SaaS</span></td>
          <td class="pr-tier-price">$499/mo</td>
          <td><span class="pr-bdg teal">Inbound Router</span></td>
          <td class="pr-tier-features">Up to 500 routed calls/mo · email dispatch · basic analytics</td>
        </tr>
        <tr>
          <td><span class="pr-tier-name">Data Enterprise</span> <span class="pr-tier-bdg popular">Popular</span></td>
          <td class="pr-tier-price">$799/mo</td>
          <td><span class="pr-bdg teal">Data Vault</span></td>
          <td class="pr-tier-features">50K stored records · 90-day retention · compliance audit log</td>
        </tr>
        <tr>
          <td><span class="pr-tier-name">Spy Data</span></td>
          <td class="pr-tier-price">$1,499/mo</td>
          <td><span class="pr-bdg teal">Buyer Spy AI</span></td>
          <td class="pr-tier-features">100 analyses/mo · network mapping · API access</td>
        </tr>
        <tr>
          <td><span class="pr-tier-name">All Access</span> <span class="pr-tier-bdg enterprise">Best Value</span></td>
          <td class="pr-tier-price">$2,499/mo</td>
          <td><span class="pr-bdg teal">All 3 Products</span></td>
          <td class="pr-tier-features">Everything included · priority support · custom SLA · dedicated onboarding</td>
        </tr>
      </tbody>
    </table>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  <!-- SECTION 3: ADVANCED PRODUCTS                                       -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-section">
    <div class="pr-section-h">
      <span class="pr-section-num">03</span>
      <span class="pr-section-title">Advanced Products</span>
      <span class="pr-section-sub">Enterprise-grade</span>
    </div>

    <div class="pr-prods">

      <!-- Product 4: Omni Bridge -->
      <div class="pr-card" style="animation-delay: 0.05s">
        <div class="pr-card-icon"><i class="ti ti-bridge"></i></div>
        <div class="pr-card-name">Omni Bridge</div>
        <div class="pr-card-desc">
          End-to-end voice-to-social pipeline. Deepgram STT → AI analysis →
          Zernio social distribution. Close the loop from call to content.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg cyan">Premium</span>
          <span class="pr-bdg amber">Add-on</span>
        </div>
        <ul class="pr-card-features">
          <li>Real-time Deepgram speech-to-text</li>
          <li>AI-powered content extraction &amp; summarization</li>
          <li>Auto-publish to Zernio social network</li>
          <li>Analytics dashboard with engagement tracking</li>
        </ul>
        <div class="pr-card-price">$999 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $0.10 per audio minute processed</div>
        <a href="/crypto/checkout/OMNI_BRIDGE" class="pr-card-cta">Subscribe with USDC</a>
      </div>

      <!-- Product 5: Agent Orchestrator -->
      <div class="pr-card" style="animation-delay: 0.10s">
        <div class="pr-card-icon"><i class="ti ti-robot"></i></div>
        <div class="pr-card-name">Agent Orchestrator</div>
        <div class="pr-card-desc">
          Spawn and manage autonomous AI agents. Define goals, monitor
          execution, and scale your workforce programmatically.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg cyan">Premium</span>
          <span class="pr-bdg muted">API-first</span>
        </div>
        <ul class="pr-card-features">
          <li>Declarative agent goal definitions</li>
          <li>Parallel agent execution with dependency resolution</li>
          <li>Step-by-step execution tracing &amp; replay</li>
          <li>Custom tool integration via plugin API</li>
        </ul>
        <div class="pr-card-price">$1,999 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $0.50 per agent-step executed</div>
        <a href="/crypto/checkout/AGENT_ORCHESTRATOR" class="pr-card-cta">Subscribe with USDC</a>
      </div>

      <!-- Product 6: B2B Pro -->
      <div class="pr-card" style="animation-delay: 0.15s">
        <div class="pr-card-icon"><i class="ti ti-building"></i></div>
        <div class="pr-card-name">B2B Pro</div>
        <div class="pr-card-desc">
          Enterprise B2B intelligence — property data, lead marketplace,
          contractor prospecting, and competitive intelligence in one platform.
        </div>
        <div class="pr-card-badges">
          <span class="pr-bdg cyan">Premium</span>
          <span class="pr-bdg teal">Enterprise</span>
        </div>
        <ul class="pr-card-features">
          <li>Commercial property intelligence &amp; valuation</li>
          <li>Lead marketplace with verified buyer network</li>
          <li>Contractor prospecting &amp; trust scoring</li>
          <li>Competitive intelligence feeds</li>
        </ul>
        <div class="pr-card-price">$2,999 <small>/mo</small></div>
        <div class="pr-card-price-sub">+ $10 per lead purchased</div>
        <a href="/crypto/checkout/B2B_PRO" class="pr-card-cta">Subscribe with USDC</a>
      </div>

    </div>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  <!-- SECTION 4: STRIKE PACKS                                             -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-section">
    <div class="pr-section-h">
      <span class="pr-section-num">04</span>
      <span class="pr-section-title">Strike Packs</span>
      <span class="pr-section-sub">Per-lead subscriptions · 32 lanes</span>
    </div>

    <p class="pr-sub" style="text-align:left; margin:0 0 28px; font-size:11px;">
      Productized lead lanes targeting specific niches. Each Strike Pack covers a set of lanes
      with configurable daily/monthly caps and delivery channels. Pricing is monthly + per lead delivered.
    </p>

    <div class="pr-packs">

      <!-- Standard -->
      <div class="pr-pack" style="animation-delay: 0.05s">
        <div class="pr-pack-tier standard">Standard</div>
        <div class="pr-pack-name">Roofing Strike</div>
        <div class="pr-pack-desc">Storm-damaged roofing leads in high-risk corridors</div>
        <div class="pr-pack-price">$499 <small>/mo</small></div>
        <div class="pr-pack-ppl">+ $5 per lead</div>
        <div class="pr-pack-lanes">4 lanes · 150 leads/mo cap</div>
        <div class="pr-pack-channels">
          <span class="pr-pack-channel">Email</span>
          <span class="pr-pack-channel">SMS</span>
        </div>            <a href="/crypto/checkout/STRIKE_STANDARD" class="pr-card-cta" style="font-size:9px; padding:8px 16px;">Subscribe with USDC</a>
      </div>

      <!-- Combo -->
      <div class="pr-pack" style="animation-delay: 0.10s">
        <div class="pr-pack-tier combo">Combo</div>
        <div class="pr-pack-name">Property Strike</div>
        <div class="pr-pack-desc">Multi-niche property leads (roofing, siding, gutters, windows)</div>
        <div class="pr-pack-price">$999 <small>/mo</small></div>
        <div class="pr-pack-ppl">+ $8 per lead</div>
        <div class="pr-pack-lanes">8 lanes · 500 leads/mo cap</div>
        <div class="pr-pack-channels">
          <span class="pr-pack-channel">Email</span>
          <span class="pr-pack-channel">SMS</span>
          <span class="pr-pack-channel">Voice</span>
        </div>            <a href="/crypto/checkout/STRIKE_COMBO" class="pr-card-cta" style="font-size:9px; padding:8px 16px;">Subscribe with USDC</a>
      </div>

      <!-- Whale -->
      <div class="pr-pack" style="animation-delay: 0.15s">
        <div class="pr-pack-tier whale">Whale</div>
        <div class="pr-pack-name">Commercial Strike</div>
        <div class="pr-pack-desc">High-value commercial property leads with API delivery</div>
        <div class="pr-pack-price">$2,999 <small>/mo</small></div>
        <div class="pr-pack-ppl">+ $25 per lead</div>
        <div class="pr-pack-lanes">16 lanes · 2,000 leads/mo cap</div>
        <div class="pr-pack-channels">
          <span class="pr-pack-channel">Email</span>
          <span class="pr-pack-channel">SMS</span>
          <span class="pr-pack-channel">Voice</span>
          <span class="pr-pack-channel">API</span>
        </div>            <a href="/crypto/checkout/STRIKE_WHALE" class="pr-card-cta" style="font-size:9px; padding:8px 16px;">Subscribe with USDC</a>
      </div>

      <!-- Enterprise -->
      <div class="pr-pack" style="animation-delay: 0.20s">
        <div class="pr-pack-tier enterprise">Enterprise</div>
        <div class="pr-pack-name">Full Spectrum</div>
        <div class="pr-pack-desc">All 32 lanes · unlimited caps · dedicated support</div>
        <div class="pr-pack-price">$7,999 <small>/mo</small></div>
        <div class="pr-pack-ppl">+ $15 per lead</div>
        <div class="pr-pack-lanes">32 lanes · unlimited</div>
        <div class="pr-pack-channels">
          <span class="pr-pack-channel">Email</span>
          <span class="pr-pack-channel">SMS</span>
          <span class="pr-pack-channel">Voice</span>
          <span class="pr-pack-channel">API</span>
          <span class="pr-pack-channel">Webhook</span>
        </div>            <a href="/crypto/checkout/STRIKE_ENTERPRISE" class="pr-card-cta" style="font-size:9px; padding:8px 16px;">Subscribe with USDC</a>
      </div>

    </div>
  </div>

  <!-- ──────────────────────────────────────────────────────────────────── -->
  <!-- SECTION 5: ADDITIONAL NOTES                                        -->
  <!-- ──────────────────────────────────────────────────────────────────── -->
  <div class="pr-note">
    <div class="pr-note-title">Enterprise &amp; Custom Pricing</div>
    <div class="pr-note-body">
      Need custom lane assignments, dedicated SLA tiers (enhanced/premium), webhook delivery,
      or a private API key for programmatic access? All Strike Packs support these features
      out of the box. Contact us at <a href="mailto:ops@empire-ai.co.uk">ops@empire-ai.co.uk</a>
      or sign in to configure your subscription at <a href="/command">the command dashboard</a>.
    </div>
  </div>

  <div class="pr-note" style="margin-top:16px; border-left-color: var(--strike-cyan);">
    <div class="pr-note-title">Revenue Share Model</div>
    <div class="pr-note-body">
      In addition to subscription pricing, Empire AI charges a <strong style="color:var(--empire-white);">3% fee</strong>
      on settled insurance claims facilitated through the platform.
      This per-claim fee covers contractor dispatch, AI-powered negotiation,
      and compliance infrastructure. No settlement, no fee.
    </div>
  </div>

  <!-- FOOTER -->
  <div class="pr-foot">
    <a href="/">Empire AI</a>
    <span class="sep">·</span>
    <a href="/command">Command Dashboard</a>
    <span class="sep">·</span>
    <a href="mailto:ops@empire-ai.co.uk">Contact</a>
    <br>
    <span style="letter-spacing:0.12em; color:var(--empire-shadow); margin-top:8px; display:block;">
      All prices in USD · Subject to change · Enterprise agreements available
    </span>
  </div>

</div>

</body>
</html>"""
