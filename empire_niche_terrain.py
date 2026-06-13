"""
EMPIRE V49 · NICHE SOCIAL TERRAIN
==================================
Learns where each niche's audience hangs out — the platforms, communities,
forums, and social spaces they inhabit. Maps the social terrain per niche,
monitors those spaces for activity patterns, and extracts habit intelligence
so the Predictive Cloud knows where to be and when.

NICHE SOCIAL TERRAIN MAP (pre-seeded + self-learning):
  - For each niche: list of communities (platform, url, audience_size, activity_level)
  - Per community: engagement metrics, best posting times, content angles
  - Habit traits: peak activity hours, day-of-week patterns, sentiment baseline

Usage:
  terrain = NicheTerrain()
  map = terrain.get_terrain_map("Roofing Restoration")
  habits = terrain.get_habits("Mass Tort")
  intel = terrain.terrain_intel("commercial_roofing")
"""
import logging
import sqlite3
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any

log = logging.getLogger("empire.niche_terrain")

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "data" / "storm_alerts.sqlite"

# ═════════════════════════════════════════════════════════════════════════
# PRE-SEEDED NICHE SOCIAL TERRAIN
# ═════════════════════════════════════════════════════════════════════════
# Each niche maps to communities where its audience hangs out.
# Each community: {platform, name, url, audience_size (est.), activity_level,
#                  best_times (when to post), content_angles (what resonates)}
# This is the initial seed — the LLM discovery engine expands it.

SEED_TERRAIN: Dict[str, List[Dict]] = {
    "Roofing Restoration": [
        {"platform": "Nextdoor", "name": "Nextdoor Neighborhood Groups",
         "url": "nextdoor.com", "audience_size": "high",
         "activity_level": "daily", "best_times": ["7-9am", "6-8pm"],
         "content_angles": ["emergency response", "insurance claims help", "neighbor referrals"],
         "niche_relevance": 0.95, "discovered_at": None},
        {"platform": "Angi / HomeAdvisor", "name": "Angi Pro Community",
         "url": "angi.com", "audience_size": "high",
         "activity_level": "daily", "best_times": ["8-10am", "12-2pm"],
         "content_angles": ["contractor reviews", "cost estimates", "project timelines"],
         "niche_relevance": 0.90, "discovered_at": None},
        {"platform": "Facebook Groups", "name": "Roofing Contractors Network",
         "url": "facebook.com/groups/roofing", "audience_size": "medium",
         "activity_level": "weekly", "best_times": ["6-8pm weekdays"],
         "content_angles": ["technique discussions", "material reviews", "business tips"],
         "niche_relevance": 0.85, "discovered_at": None},
        {"platform": "Forum", "name": "RoofingTalk / ContractorTalk",
         "url": "roofingtalk.com", "audience_size": "medium",
         "activity_level": "daily", "best_times": ["9-11am", "2-4pm"],
         "content_angles": ["code questions", "product recommendations", "storm damage"],
         "niche_relevance": 0.88, "discovered_at": None},
        {"platform": "LinkedIn", "name": "Commercial Roofing Professionals",
         "url": "linkedin.com/groups/commercial-roofing", "audience_size": "medium",
         "activity_level": "weekly", "best_times": ["7-9am", "12-1pm weekdays"],
         "content_angles": ["industry trends", "certifications", "case studies"],
         "niche_relevance": 0.80, "discovered_at": None},
        {"platform": "Google Business", "name": "Google Maps / Business Profile",
         "url": "business.google.com", "audience_size": "very_high",
         "activity_level": "continuous", "best_times": ["8am-8pm"],
         "content_angles": ["service listings", "review responses", "Q&A"],
         "niche_relevance": 0.92, "discovered_at": None},
        {"platform": "YouTube", "name": "Roofing Restoration Channels",
         "url": "youtube.com", "audience_size": "high",
         "activity_level": "weekly", "best_times": ["evenings", "weekends"],
         "content_angles": ["repair tutorials", "before/after", "insurance explainers"],
         "niche_relevance": 0.75, "discovered_at": None},
        {"platform": "Reddit", "name": "r/Roofing, r/HomeImprovement, r/CommercialRealEstate",
         "url": "reddit.com/r/roofing", "audience_size": "medium",
         "activity_level": "daily", "best_times": ["10am-2pm", "7-10pm"],
         "content_angles": ["advice threads", "cost discussions", "contractor recommendations"],
         "niche_relevance": 0.82, "discovered_at": None},
    ],
    "Mass Tort": [
        {"platform": "Reddit", "name": "r/legaladvice, r/MassTort, r/ClassAction",
         "url": "reddit.com/r/legaladvice", "audience_size": "high",
         "activity_level": "daily", "best_times": ["9am-4pm", "8-11pm"],
         "content_angles": ["case discussions", "settlement questions", "attorney referrals"],
         "niche_relevance": 0.92, "discovered_at": None},
        {"platform": "Facebook Groups", "name": "Mass Tort Support Groups / Class Action Info",
         "url": "facebook.com", "audience_size": "very_high",
         "activity_level": "daily", "best_times": ["8-10am", "6-9pm"],
         "content_angles": ["personal stories", "settlement timelines", "eligibility questions"],
         "niche_relevance": 0.90, "discovered_at": None},
        {"platform": "Forum", "name": "Top Class Actions Forum",
         "url": "topclassactions.com", "audience_size": "high",
         "activity_level": "daily", "best_times": ["9am-5pm"],
         "content_angles": ["new filings", "claim deadlines", "settlement updates"],
         "niche_relevance": 0.88, "discovered_at": None},
        {"platform": "Legal Directories", "name": "Lawyer Referral Services / LegalMatch",
         "url": "lawyers.com", "audience_size": "medium",
         "activity_level": "weekly", "best_times": ["9am-5pm weekdays"],
         "content_angles": ["attorney profiles", "case reviews", "consultation booking"],
         "niche_relevance": 0.85, "discovered_at": None},
        {"platform": "TikTok", "name": "LegalTok / Mass Tort Explainers",
         "url": "tiktok.com", "audience_size": "very_high",
         "activity_level": "daily", "best_times": ["6-9pm", "weekends"],
         "content_angles": ["quick legal explainers", "case updates", "settlement amounts"],
         "niche_relevance": 0.82, "discovered_at": None},
        {"platform": "YouTube", "name": "Mass Tort Attorney Channels",
         "url": "youtube.com", "audience_size": "high",
         "activity_level": "weekly", "best_times": ["evenings", "weekends"],
         "content_angles": ["case deep-dives", "interview victims", "settlement breakdowns"],
         "niche_relevance": 0.80, "discovered_at": None},
        {"platform": "LinkedIn", "name": "Mass Tort / Personal Injury Legal Network",
         "url": "linkedin.com", "audience_size": "medium",
         "activity_level": "weekly", "best_times": ["7-9am", "12-1pm weekdays"],
         "content_angles": ["industry analysis", "verdicts", "legal trends"],
         "niche_relevance": 0.75, "discovered_at": None},
    ],
    "Tornado Damage Repair": [
        {"platform": "Nextdoor", "name": "Nextdoor Storm Recovery Groups",
         "url": "nextdoor.com", "audience_size": "high",
         "activity_level": "spike_after_event", "best_times": ["immediate_aftermath", "7-9am", "6-8pm"],
         "content_angles": ["safety alerts", "contractor recommendations", "FEMA guidance"],
         "niche_relevance": 0.95, "discovered_at": None},
        {"platform": "Facebook Groups", "name": "Tornado Recovery & Support Groups",
         "url": "facebook.com", "audience_size": "very_high",
         "activity_level": "spike_after_event", "best_times": ["immediate_aftermath", "all_hours"],
         "content_angles": ["damage reports", "help coordination", "resource sharing"],
         "niche_relevance": 0.92, "discovered_at": None},
        {"platform": "Reddit", "name": "r/tornado, r/weather, r/StormDamage",
         "url": "reddit.com/r/tornado", "audience_size": "medium",
         "activity_level": "spike_after_event", "best_times": ["during_event", "days_after"],
         "content_angles": ["damage photos", "insurance questions", "recovery timelines"],
         "niche_relevance": 0.88, "discovered_at": None},
        {"platform": "News/Social", "name": "Local News Facebook Pages / Citizen App",
         "url": "facebook.com/localnews", "audience_size": "high",
         "activity_level": "spike_after_event", "best_times": ["event+72h"],
         "content_angles": ["recovery resources", "contractor warnings", "community meetings"],
         "niche_relevance": 0.85, "discovered_at": None},
    ],
    "Flood Damage Restoration": [
        {"platform": "Facebook Groups", "name": "Flood Recovery & Support Groups",
         "url": "facebook.com", "audience_size": "very_high",
         "activity_level": "spike_after_event", "best_times": ["during_event", "days_after"],
         "content_angles": ["water damage tips", "mold prevention", "FEMA claims"],
         "niche_relevance": 0.93, "discovered_at": None},
        {"platform": "Nextdoor", "name": "Flood-Affected Neighborhood Groups",
         "url": "nextdoor.com", "audience_size": "high",
         "activity_level": "spike_after_event", "best_times": ["7-9am", "6-8pm"],
         "content_angles": ["drainage issues", "contractor referrals", "insurance help"],
         "niche_relevance": 0.90, "discovered_at": None},
        {"platform": "Reddit", "name": "r/Flood, r/HomeImprovement, r/Insurance",
         "url": "reddit.com/r/flood", "audience_size": "medium",
         "activity_level": "spike_after_event", "best_times": ["10am-2pm", "7-10pm"],
         "content_angles": ["claim questions", "restoration advice", "contractor reviews"],
         "niche_relevance": 0.82, "discovered_at": None},
        {"platform": "FEMA/NFIP", "name": "FEMA Disaster Assistance / NFIP Resources",
         "url": "fema.gov", "audience_size": "high",
         "activity_level": "spike_after_event", "best_times": ["event_declaration+2weeks"],
         "content_angles": ["aid applications", "appeal processes", "documentation"],
         "niche_relevance": 0.88, "discovered_at": None},
    ],
    "Hurricane Damage Restoration": [
        {"platform": "Facebook Groups", "name": "Hurricane Recovery Networks",
         "url": "facebook.com", "audience_size": "very_high",
         "activity_level": "spike_before_and_after", "best_times": ["pre_landfall", "evacuation", "return"],
         "content_angles": ["preparation checklists", "damage assessments", "contractor vetting"],
         "niche_relevance": 0.94, "discovered_at": None},
        {"platform": "Nextdoor", "name": "Coastal Neighborhood Groups",
         "url": "nextdoor.com", "audience_size": "high",
         "activity_level": "spike_before_and_after", "best_times": ["pre_landfall+48h", "return+72h"],
         "content_angles": ["evacuation info", "property checks", "restoration leads"],
         "niche_relevance": 0.92, "discovered_at": None},
        {"platform": "Reddit", "name": "r/Hurricane, r/TropicalWeather, r/Insurance",
         "url": "reddit.com/r/hurricane", "audience_size": "medium",
         "activity_level": "spike_during_season", "best_times": ["cone_release", "landfall+24h"],
         "content_angles": ["tracking discussions", "damage reports", "claim strategies"],
         "niche_relevance": 0.85, "discovered_at": None},
        {"platform": "WhatsApp/Telegram", "name": "Community Emergency Alert Groups",
         "url": "whatsapp.com", "audience_size": "very_high",
         "activity_level": "spike_during_event", "best_times": ["during_emergency"],
         "content_angles": ["real-time updates", "resource coordination", "neighbor help"],
         "niche_relevance": 0.87, "discovered_at": None},
    ],
    "Hail Damage Repair": [
        {"platform": "Nextdoor", "name": "Hail-Affected Neighborhood Groups",
         "url": "nextdoor.com", "audience_size": "high",
         "activity_level": "spike_after_event", "best_times": ["post_storm+24h", "7-9am"],
         "content_angles": ["damage reports", "contractor recommendations", "insurance tips"],
         "niche_relevance": 0.93, "discovered_at": None},
        {"platform": "Facebook Groups", "name": "Local Community Pages (hail events)",
         "url": "facebook.com", "audience_size": "high",
         "activity_level": "spike_after_event", "best_times": ["post_event_days"],
         "content_angles": ["damage photos", "referral requests", "claim help"],
         "niche_relevance": 0.88, "discovered_at": None},
        {"platform": "Reddit", "name": "r/Insurance, r/Roofing, local city subreddits",
         "url": "reddit.com", "audience_size": "medium",
         "activity_level": "spike_after_event", "best_times": ["event+24-72h"],
         "content_angles": ["claim questions", "contractor reviews", "damage assessment"],
         "niche_relevance": 0.80, "discovered_at": None},
    ],
    "Commercial Property": [
        {"platform": "LinkedIn", "name": "CRE (Commercial Real Estate) Groups",
         "url": "linkedin.com/groups/cre", "audience_size": "high",
         "activity_level": "daily", "best_times": ["7-9am", "12-1pm weekdays"],
         "content_angles": ["property management", "facility maintenance", "roofing ROI"],
         "niche_relevance": 0.92, "discovered_at": None},
        {"platform": "Forum", "name": "Building Owners & Managers Association (BOMA)",
         "url": "boma.org", "audience_size": "medium",
         "activity_level": "weekly", "best_times": ["weekday_mornings"],
         "content_angles": ["industry standards", "property insurance", "vendor management"],
         "niche_relevance": 0.88, "discovered_at": None},
        {"platform": "Industry Publications", "name": "GlobeSt / REBusinessOnline Comments",
         "url": "globest.com", "audience_size": "medium",
         "activity_level": "daily", "best_times": ["9-11am"],
         "content_angles": ["market trends", "property values", "investment strategy"],
         "niche_relevance": 0.85, "discovered_at": None},
        {"platform": "Nextdoor Business", "name": "Nextdoor Business Pages",
         "url": "nextdoor.com", "audience_size": "medium",
         "activity_level": "weekly", "best_times": ["8-10am"],
         "content_angles": ["local business networking", "service recommendations"],
         "niche_relevance": 0.78, "discovered_at": None},
        {"platform": "Facebook Groups", "name": "Commercial Property Owners Network",
         "url": "facebook.com/groups/commercial-property", "audience_size": "medium",
         "activity_level": "weekly", "best_times": ["evenings", "weekends"],
         "content_angles": ["tenant management", "roofing decisions", "cost saving"],
         "niche_relevance": 0.80, "discovered_at": None},
    ],
    "Legal Intake": [
        {"platform": "Google Ads / Search", "name": "Google Personal Injury / Mass Tort Queries",
         "url": "google.com", "audience_size": "very_high",
         "activity_level": "continuous", "best_times": ["9am-5pm weekdays"],
         "content_angles": ["lawyer near me", "case evaluation", "settlement calculator"],
         "niche_relevance": 0.95, "discovered_at": None},
        {"platform": "Reddit", "name": "r/legaladvice, r/AskALawyer, r/ClassAction",
         "url": "reddit.com/r/legaladvice", "audience_size": "very_high",
         "activity_level": "daily", "best_times": ["9am-4pm", "8-11pm"],
         "content_angles": ["free advice", "case questions", "firm recommendations"],
         "niche_relevance": 0.90, "discovered_at": None},
        {"platform": "Facebook Groups", "name": "Legal Help / Class Action Groups",
         "url": "facebook.com", "audience_size": "high",
         "activity_level": "daily", "best_times": ["8-10am", "6-9pm"],
         "content_angles": ["personal stories", "settlement questions", "lawyer searches"],
         "niche_relevance": 0.87, "discovered_at": None},
        {"platform": "Legal Directories", "name": "Avvo / Justia / Lawyers.com",
         "url": "avvo.com", "audience_size": "high",
         "activity_level": "daily", "best_times": ["9am-8pm"],
         "content_angles": ["attorney profiles", "client reviews", "case types"],
         "niche_relevance": 0.88, "discovered_at": None},
        {"platform": "TikTok", "name": "LegalTok — Personal Injury + Mass Tort",
         "url": "tiktok.com", "audience_size": "very_high",
         "activity_level": "daily", "best_times": ["6-10pm", "weekends"],
         "content_angles": ["quick legal tips", "settlement reveal", "case eligibility"],
         "niche_relevance": 0.83, "discovered_at": None},
    ],
    "Consumer CPA": [
        {"platform": "Facebook Groups", "name": "Small Business Accounting & Tax Groups",
         "url": "facebook.com/groups/tax", "audience_size": "high",
         "activity_level": "daily", "best_times": ["8-10am", "6-8pm"],
         "content_angles": ["tax questions", "deduction tips", "software recommendations"],
         "niche_relevance": 0.90, "discovered_at": None},
        {"platform": "LinkedIn", "name": "CPA / Accounting Professionals",
         "url": "linkedin.com/groups/cpa", "audience_size": "medium",
         "activity_level": "weekdays", "best_times": ["7-9am", "12-1pm"],
         "content_angles": ["tax law changes", "practice management", "client acquisition"],
         "niche_relevance": 0.88, "discovered_at": None},
        {"platform": "Reddit", "name": "r/tax, r/Accounting, r/smallbusiness",
         "url": "reddit.com/r/tax", "audience_size": "high",
         "activity_level": "daily", "best_times": ["9am-5pm", "tax_season_spike"],
         "content_angles": ["tax questions", "IRS help", "bookkeeping advice"],
         "niche_relevance": 0.85, "discovered_at": None},
        {"platform": "Nextdoor", "name": "Local Business Networking Groups",
         "url": "nextdoor.com", "audience_size": "medium",
         "activity_level": "weekly", "best_times": ["8-10am"],
         "content_angles": ["local referrals", "business resources", "service recommendations"],
         "niche_relevance": 0.75, "discovered_at": None},
        {"platform": "Forum", "name": "CPA Practice Advisor / TaxProTalk",
         "url": "cpatalk.com", "audience_size": "medium",
         "activity_level": "weekly", "best_times": ["9-11am", "2-4pm"],
         "content_angles": ["software reviews", "IRS updates", "client management"],
         "niche_relevance": 0.82, "discovered_at": None},
    ],
    "Local SEO & HVAC": [
        {"platform": "Nextdoor", "name": "Local Neighborhood Groups",
         "url": "nextdoor.com", "audience_size": "very_high",
         "activity_level": "daily", "best_times": ["7-9am", "6-8pm"],
         "content_angles": ["service recommendations", "emergency needs", "local reviews"],
         "niche_relevance": 0.93, "discovered_at": None},
        {"platform": "Google Business", "name": "Google Maps / Local Search",
         "url": "business.google.com", "audience_size": "very_high",
         "activity_level": "continuous", "best_times": ["8am-8pm"],
         "content_angles": ["near me searches", "service area", "review generation"],
         "niche_relevance": 0.95, "discovered_at": None},
        {"platform": "Facebook Groups", "name": "Local Community / Town Pages",
         "url": "facebook.com", "audience_size": "high",
         "activity_level": "daily", "best_times": ["6-9pm"],
         "content_angles": ["local recommendations", "service questions", "community engagement"],
         "niche_relevance": 0.88, "discovered_at": None},
        {"platform": "Angi / HomeAdvisor", "name": "HVAC & Home Services",
         "url": "angi.com", "audience_size": "high",
         "activity_level": "daily", "best_times": ["8-10am", "12-2pm"],
         "content_angles": ["service requests", "cost guides", "contractor matching"],
         "niche_relevance": 0.90, "discovered_at": None},
        {"platform": "Reddit", "name": "r/HVAC, r/homeowners, local city subreddits",
         "url": "reddit.com/r/hvac", "audience_size": "medium",
         "activity_level": "daily", "best_times": ["10am-2pm", "7-10pm"],
         "content_angles": ["repair advice", "unit recommendations", "contractor reviews"],
         "niche_relevance": 0.82, "discovered_at": None},
    ],
}

# ── NICHE ALIAS MAP (normalize variant names) ────────────────────────
_NICHE_ALIASES = {
    "roofing": "Roofing Restoration",
    "roofing restoration": "Roofing Restoration",
    "tornado": "Tornado Damage Repair",
    "tornado damage": "Tornado Damage Repair",
    "hurricane": "Hurricane Damage Restoration",
    "hurricane damage": "Hurricane Damage Restoration",
    "hail": "Hail Damage Repair",
    "hail damage": "Hail Damage Repair",
    "flood": "Flood Damage Restoration",
    "flood damage": "Flood Damage Restoration",
    "storm": "Storm Damage Restoration",
    "storm damage": "Storm Damage Restoration",
    "mass tort": "Mass Tort",
    "legal": "Legal Intake",
    "legal intake": "Legal Intake",
    "commercial": "Commercial Property",
    "commercial property": "Commercial Property",
    "cpa": "Consumer CPA",
    "consumer cpa": "Consumer CPA",
    "hvac": "Local SEO & HVAC",
    "local seo": "Local SEO & HVAC",
    "local seo & hvac": "Local SEO & HVAC",
}

# ── DEFAULT TRAITS (when no observations exist yet) ──────────────────
_DEFAULT_HABIT_TRAITS = {
    "peak_activity_hours": ["9-11am", "2-4pm", "7-9pm"],
    "peak_days": ["Tuesday", "Wednesday", "Thursday"],
    "engagement_style": "informational",  # informational, emotional, urgent
    "decision_cycle_hours": 72,
    "content_preferences": ["how-to", "cost_info", "case_studies"],
    "sentiment_baseline": "neutral",
    "response_expected_within_hours": 24,
    "mobile_first": True,
    "best_platforms": [],
}


class NicheTerrain:
    """Maps, monitors, and learns the social terrain for each niche.
    Answers: Where does this niche's audience hang out? When are they active?
    What content do they engage with? What's the sentiment baseline?"""

    def __init__(self):
        self._terrain: Dict[str, List[Dict]] = {}
        self._habits: Dict[str, Dict] = {}
        self._observations: List[Dict] = []
        self._stats = {
            "communities_mapped": 0,
            "observations_recorded": 0,
            "discovery_runs": 0,
            "niches_tracked": 0,
        }
        self._load_terrain()

    # ── INIT ─────────────────────────────────────────────────────────

    def _load_terrain(self):
        """Load the pre-seeded terrain and any persisted observations from DB."""
        self._terrain = {}
        for niche, communities in SEED_TERRAIN.items():
            self._terrain[niche] = [dict(c) for c in communities]
        self._stats["communities_mapped"] = sum(len(c) for c in self._terrain.values())
        self._stats["niches_tracked"] = len(self._terrain)
        self._load_from_db()

    def _load_from_db(self):
        """Load persisted observations and habit traits from SQLite."""
        conn = self._get_conn()
        try:
            # Load observations
            cursor = conn.execute(
                "SELECT niche, platform, community_name, observation_type, content, "
                "engagement_count, sentiment, observed_at "
                "FROM social_observations ORDER BY observed_at DESC LIMIT 1000"
            )
            for row in cursor.fetchall():
                self._observations.append({
                    "niche": row[0],
                    "platform": row[1],
                    "community_name": row[2],
                    "observation_type": row[3],
                    "content": row[4],
                    "engagement_count": row[5],
                    "sentiment": row[6],
                    "observed_at": row[7],
                })
            self._stats["observations_recorded"] = len(self._observations)

            # Load habit traits
            cursor = conn.execute(
                "SELECT niche, trait_key, trait_value, confidence, learned_at "
                "FROM niche_habit_traits ORDER BY niche, trait_key"
            )
            for row in cursor.fetchall():
                niche = row[0]
                if niche not in self._habits:
                    self._habits[niche] = dict(_DEFAULT_HABIT_TRAITS)
                key = row[1]
                try:
                    val = json.loads(row[2])
                except (json.JSONDecodeError, TypeError):
                    val = row[2]
                self._habits[niche][key] = val
        except sqlite3.OperationalError:
            # Tables might not exist yet
            pass
        finally:
            conn.close()

    def _get_conn(self):
        return sqlite3.connect(str(DB_PATH))

    # ── NICHE RESOLUTION ─────────────────────────────────────────────

    def _resolve_niche(self, niche: str) -> Optional[str]:
        """Normalize a niche name to its canonical form."""
        key = niche.lower().strip()
        return _NICHE_ALIASES.get(key, niche if niche in self._terrain else None)

    def _ensure_niche(self, niche: str) -> str:
        """Resolve and register a niche if it doesn't exist yet."""
        resolved = self._resolve_niche(niche)
        if resolved:
            return resolved
        # Register a new niche
        self._terrain[niche] = []
        self._stats["niches_tracked"] = len(self._terrain)
        log.info(f"[niche_terrain] registered new niche: {niche}")
        return niche

    # ── TERRAIN MAP ──────────────────────────────────────────────────

    def get_terrain_map(self, niche: Optional[str] = None) -> Dict:
        """Return the terrain map for one niche or all niches.
        Each community includes its current engagement metrics and best posting intel."""
        if niche:
            resolved = self._ensure_niche(niche)
            communities = self._terrain.get(resolved, [])
            habits = self._habits.get(resolved, dict(_DEFAULT_HABIT_TRAITS))
            return {
                "niche": resolved,
                "communities": communities,
                "community_count": len(communities),
                "habits": habits,
                "last_updated": datetime.now(timezone.utc).isoformat(),
            }

        # Return all niches
        result = {}
        for n, communities in self._terrain.items():
            result[n] = {
                "communities": communities,
                "community_count": len(communities),
                "habits": self._habits.get(n, dict(_DEFAULT_HABIT_TRAITS)),
            }
        return result

    # ── HABITS ───────────────────────────────────────────────────────

    def get_habits(self, niche: Optional[str] = None) -> Dict:
        """Return learned habit traits for a niche or all niches."""
        if niche:
            resolved = self._ensure_niche(niche)
            return self._habits.get(resolved, dict(_DEFAULT_HABIT_TRAITS))
        return dict(self._habits)

    def _update_habit_trait(self, niche: str, key: str, value: Any, confidence: float = 0.5):
        """Persist a learned habit trait to memory and DB."""
        if niche not in self._habits:
            self._habits[niche] = dict(_DEFAULT_HABIT_TRAITS)
        self._habits[niche][key] = value

        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT OR REPLACE INTO niche_habit_traits
                   (niche, trait_key, trait_value, confidence, learned_at, source)
                   VALUES (?, ?, ?, ?, ?, 'observation')""",
                (niche, key, json.dumps(value) if not isinstance(value, str) else value,
                 confidence, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Table may not exist yet
        finally:
            conn.close()

    # ── LLM DISCOVERY ────────────────────────────────────────────────

    async def discover_terrain(self, niche: str, depth: str = "standard") -> Dict:
        """Use local Ollama to discover the social terrain for a niche.
        Returns communities where this niche's audience hangs out, with
        platform, URL, audience estimates, and content angle recommendations.

        Args:
            niche: Target niche to discover communities for
            depth: 'quick' (top 5-8), 'standard' (10-15), 'deep' (20+)
        """
        resolved = self._ensure_niche(niche)
        if not resolved:
            resolved = niche

        import httpx
        limit_map = {"quick": 8, "standard": 14, "deep": 25}
        max_communities = limit_map.get(depth, 14)

        # Build prompt with existing knowledge as context
        existing = self._terrain.get(resolved, [])
        existing_context = ""
        if existing:
            existing_context = "Already known communities:\n"
            for c in existing:
                existing_context += f"  - {c['platform']}: {c['name']} ({c.get('url', '')})\n"

        system = (
            "You are a social terrain analyst. For a given niche/market, identify "
            "the online platforms, communities, forums, groups, and social spaces "
            "where that niche's audience actively hangs out.\n\n"
            "For EACH community return:\n"
            "  platform: the platform name (Reddit, Facebook Groups, LinkedIn, TikTok, "
            "           Nextdoor, YouTube, Discord, Forum, Industry Site, WhatsApp, etc.)\n"
            "  name: specific community/group/page name\n"
            "  url: the URL or domain\n"
            "  audience_size: estimate (very_high, high, medium, low, niche)\n"
            "  activity_level: daily, weekly, monthly, spike_after_event\n"
            "  best_times: when the audience is most active (list of time slots)\n"
            "  content_angles: what type of content resonates there (list)\n"
            "  niche_relevance: 0.0-1.0 how relevant this community is for outreach\n\n"
            "Return ONLY valid JSON: { \"communities\": [...] }\n"
            f"Max {max_communities} communities. Prioritize communities with HIGH "
            "active engagement, not just large follower counts."
        )

        prompt = (
            f"Niche: {resolved}\n"
            f"{existing_context}"
            f"Research where {resolved} prospects and decision-makers hang out online. "
            f"Focus on platforms where they ASK QUESTIONS, SEEK RECOMMENDATIONS, "
            f"and DISCUSS THEIR NEEDS — these are the highest-intent spaces.\n"
            f"Return JSON only."
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "http://localhost:11434/api/chat",
                    headers={"Content-Type": "application/json"},
                    json={
                        "model": "llama3:8b",
                        "messages": [
                            {"role": "system", "content": system},
                            {"role": "user", "content": prompt},
                        ],
                        "stream": False,
                        "temperature": 0.4,
                    },
                )
                if response.status_code < 300:
                    data = response.json()
                    content = data.get("message", {}).get("content", "{}")
                    # Parse JSON from response
                    import re
                    json_match = re.search(r'\{.*\}', content, re.DOTALL)
                    if json_match:
                        parsed = json.loads(json_match.group())
                        communities = parsed.get("communities", [])
                        if communities:
                            # Merge with existing (deduplicate by URL pattern)
                            existing_urls = {c.get("url", "") for c in existing}
                            for c in communities:
                                url = c.get("url", "")
                                if url and url not in existing_urls:
                                    c["discovered_at"] = datetime.now(timezone.utc).isoformat()
                                    if resolved not in self._terrain:
                                        self._terrain[resolved] = []
                                    self._terrain[resolved].append(c)
                                    existing_urls.add(url)
                            self._stats["communities_mapped"] = sum(
                                len(c) for c in self._terrain.values()
                            )

                            log.info(
                                f"[niche_terrain] discovered {len(communities)} communities "
                                f"for '{resolved}': {[c.get('name','?')[:30] for c in communities[:5]]}"
                            )
                            self._stats["discovery_runs"] += 1
                            return {
                                "ok": True,
                                "niche": resolved,
                                "new_communities": len(communities),
                                "total_mapped": self._stats["communities_mapped"],
                                "communities": communities,
                                "depth": depth,
                            }
        except Exception as e:
            log.warning(f"[niche_terrain] discovery failed for '{resolved}': {e}")

        return {
            "ok": False,
            "niche": resolved,
            "error": "Discovery failed or returned no communities",
        }

    # ── RECORD OBSERVATION ───────────────────────────────────────────

    def record_observation(self, niche: str, platform: str, community_name: str,
                           observation_type: str, content: str,
                           engagement_count: int = 0, sentiment: str = "neutral") -> bool:
        """Record a social observation from monitoring a community.
        This feeds the habit learning engine over time."""
        resolved = self._ensure_niche(niche)
        conn = self._get_conn()
        try:
            conn.execute(
                """INSERT INTO social_observations
                   (niche, platform, community_name, observation_type, content,
                    engagement_count, sentiment, observed_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (resolved, platform, community_name, observation_type, content,
                 engagement_count, sentiment, datetime.now(timezone.utc).isoformat()),
            )
            conn.commit()
            self._observations.append({
                "niche": resolved,
                "platform": platform,
                "community_name": community_name,
                "observation_type": observation_type,
                "content": content,
                "engagement_count": engagement_count,
                "sentiment": sentiment,
                "observed_at": datetime.now(timezone.utc).isoformat(),
            })
            self._stats["observations_recorded"] = len(self._observations)
            return True
        except sqlite3.OperationalError as e:
            log.debug(f"[niche_terrain] observation failed: {e}")
            return False
        finally:
            conn.close()

    # ── HABIT LEARNING ENGINE ────────────────────────────────────────

    def _learn_from_observations(self, niche: str):
        """Analyze observations for a niche and update habit traits.
        Looks at engagement patterns, sentiment, content types, and timing.
        Called periodically by the background scan loop and on-demand."""
        niche_obs = [o for o in self._observations if o["niche"] == niche]
        if len(niche_obs) < 5:
            return  # Need minimum data

        # Extract peak hours from observation timestamps
        from collections import Counter
        hour_counts = Counter()
        day_counts = Counter()
        sentiments = []
        total_engagement = 0

        for obs in niche_obs:
            try:
                ts = datetime.fromisoformat(obs["observed_at"])
                hour_counts[ts.hour] += 1
                day_counts[ts.strftime("%A")] += 1
                sentiments.append(obs.get("sentiment", "neutral"))
                total_engagement += obs.get("engagement_count", 0)
            except (ValueError, TypeError):
                pass

        # Update habits
        if hour_counts:
            peak_hours = [f"{h}-{h+1}:00" for h, _ in hour_counts.most_common(3)]
            self._update_habit_trait(niche, "peak_activity_hours", peak_hours,
                                     confidence=min(len(niche_obs) / 50, 1.0))

        if day_counts:
            peak_days = [d for d, _ in day_counts.most_common(3)]
            self._update_habit_trait(niche, "peak_days", peak_days,
                                     confidence=min(len(niche_obs) / 50, 1.0))

        if sentiments:
            pos = sentiments.count("positive")
            neg = sentiments.count("negative")
            neu = sentiments.count("neutral")
            total = len(sentiments)
            if total > 0:
                baseline = "positive" if pos > neg + neu else (
                    "negative" if neg > pos + neu else "neutral"
                )
                self._update_habit_trait(niche, "sentiment_baseline", baseline,
                                         confidence=min(total / 30, 1.0))

        log.debug(f"[niche_terrain] learned habits for '{niche}' from {len(niche_obs)} observations")

    def learn_all_habits(self):
        """Run habit learning across all niches with enough data."""
        niches_with_data = set(o["niche"] for o in self._observations)
        for n in niches_with_data:
            self._learn_from_observations(n)
        return {"niches_analyzed": len(niches_with_data)}

    # ── TERRAIN INTEL ────────────────────────────────────────────────

    def terrain_intel(self, niche: Optional[str] = None) -> Dict:
        """Consolidated intelligence report: where to be, when, and with what.
        This is the actionable output that feeds the routing/brain systems."""
        if niche:
            resolved = self._ensure_niche(niche)
            if not resolved:
                return {"niche": niche, "error": "Unknown niche", "deploy_plan": []}

            communities = self._terrain.get(resolved, [])
            habits = self._habits.get(resolved, dict(_DEFAULT_HABIT_TRAITS))

            # Rank communities by niche_relevance
            ranked = sorted(communities, key=lambda c: c.get("niche_relevance", 0.5), reverse=True)

            # Build deploy recommendations
            top_platforms = []
            for c in ranked[:5]:
                top_platforms.append({
                    "platform": c["platform"],
                    "name": c["name"],
                    "niche_relevance": c.get("niche_relevance", 0.5),
                    "best_times": c.get("best_times", []),
                    "content_angles": c.get("content_angles", []),
                })

            return {
                "niche": resolved,
                "deploy_priority": top_platforms,
                "habits": habits,
                "total_communities": len(communities),
                "observation_count": sum(1 for o in self._observations if o["niche"] == resolved),
            }

        # All niches
        return {
            niche: self.terrain_intel(niche)
            for niche in self._terrain
        }

    # ── SNAPSHOT ─────────────────────────────────────────────────────

    def snapshot(self) -> Dict:
        """Full system snapshot for the SPA / monitoring."""
        return {
            "stats": dict(self._stats),
            "niches": list(self._terrain.keys()),
            "total_communities": self._stats["communities_mapped"],
            "total_observations": self._stats["observations_recorded"],
            "habits_learned": len(self._habits),
        }

    # ── BACKGROUND SCAN HELPER ───────────────────────────────────────

    async def scan_cycle(self):
        """One cycle of the background terrain scanner.
        1. Pick niches with fewest observations
        2. Try LLM discovery if communities are sparse
        3. Learn habits from accumulated observations
        """
        # Find niches that could use more community discovery
        for niche, communities in self._terrain.items():
            if len(communities) < 5:
                log.info(f"[niche_terrain] sparse terrain for '{niche}' ({len(communities)} communities) — discovering")
                await self.discover_terrain(niche, depth="quick")

        # Learn habits from accumulated observations
        result = self.learn_all_habits()
        if result["niches_analyzed"] > 0:
            log.info(f"[niche_terrain] scan cycle: learned habits for {result['niches_analyzed']} niches")

        return result
