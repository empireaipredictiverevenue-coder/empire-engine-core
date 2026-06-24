"""
EMPIRE V49 · SEO CONTENT AGENT
===============================
Dedicated content generation agent that feeds the SEO Agent with
fully-formed, SEO-optimized content assets — from property landing
pages to neighborhood guides, storm risk assessments, and social
sharing snippets. All content is structured as JSON so any rendering
engine (SPA, landing matrix, email) can consume it directly.

CONTENT TYPES:
  1. landing_page     — Full property landing page structure (hero, features, neighborhood, CTA)
  2. property_desc    — SEO-optimized property description (250-500 words)
  3. neighborhood     — Neighborhood/community guide content
  4. storm_risk       — Storm risk assessment + damage description for a property
  5. social_og        — Open Graph / social sharing metadata
  6. email_content    — Email outreach content for property owners
"""

import os
import sys
import json
import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

sys.path.insert(0, "/root/empire-v49")

try:
    from dotenv import load_dotenv
    load_dotenv("/root/.env", override=True)
except ImportError:
    pass

from supabase import create_client

log = logging.getLogger("seo.content")
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY", "")

_sb = None


def _get_sb():
    global _sb
    if _sb is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            log.error("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
            sys.exit(1)
        _sb = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _sb


from bots._llm import llm_json as _ollama_json


# ── CONTENT AGENT ────────────────────────────────────────────────────
class ContentAgent:
    """
    Full-scale content generation agent that produces SEO-optimized,
    conversion-focused content for real estate landing pages, property
    descriptions, neighborhood guides, storm risk assessments, and
    social sharing assets.

    Capabilities:
      - generate_landing_page(address, metro, niche, research_package)
      - generate_property_description(property_data, niche)
      - generate_neighborhood_guide(neighborhood_data)
      - generate_storm_risk_content(storm_data, property_data)
      - generate_social_og(address, metro, niche, content_data)
      - generate_email_content(property_data, storm_data, niche)
      - bulk_generate_for_research(research_package)
      - performance_snapshot()
    """

    CONTENT_TYPES = ["landing_page", "property_desc", "neighborhood", "storm_risk", "social_og", "email_content"]

    def __init__(self):
        self.stats = {
            "content_runs": 0,
            "landing_pages": 0,
            "property_descs": 0,
            "neighborhood_guides": 0,
            "storm_risk_pieces": 0,
            "social_og_pieces": 0,
            "email_pieces": 0,
            "errors": 0,
        }
        self._cache: Dict[str, dict] = {}

    # ── LANDING PAGE ───────────────────────────────────────────────
    async def generate_landing_page(
        self,
        address: str = "",
        metro: str = "",
        niche: str = "Roofing Restoration",
        property_data: Optional[Dict] = None,
        neighborhood_data: Optional[Dict] = None,
        storm_data: Optional[Dict] = None,
        style: str = "cinematic",
    ) -> Dict:
        """
        Generate a complete landing page content structure for a property.
        Returns structured JSON that a renderer can turn into HTML.

        Styles:
          - "cinematic": video-heavy hero, dramatic typography
          - "modern": clean grid, minimal design
          - "classic": detail-first, trust badges, long-form
        """
        cache_key = f"landing:{address}|{metro}|{niche}|{style}"
        if cache_key in self._cache:
            return dict(self._cache[cache_key])

        prop_summary = ""
        if property_data:
            prop_summary = (
                f"Property type: {property_data.get('property_type', 'Commercial')}, "
                f"Year built: {property_data.get('year_built', 'N/A')}, "
                f"Sqft: {property_data.get('sqft', 'N/A')}, "
                f"Estimated value: ${property_data.get('estimated_value', 0):,}, "
                f"Roof: {property_data.get('roof_type', 'Unknown')}"
            )

        hood_summary = ""
        if neighborhood_data:
            hood_summary = (
                f"Walk score: {neighborhood_data.get('walk_score', 'N/A')}, "
                f"School rating: {neighborhood_data.get('school_rating', 'N/A')}/10, "
                f"Median home: ${neighborhood_data.get('median_home_value', 0):,}"
            )

        storm_summary = ""
        if storm_data:
            storm_summary = (
                f"Events last 5yr: {storm_data.get('total_events_last_5yr', 'N/A')}, "
                f"Risk level: {storm_data.get('risk_level', 'unknown')}, "
                f"Most common: {storm_data.get('most_common_event', 'N/A')}"
            )

        style_guide = {
            "cinematic": "Dramatic full-bleed hero, large typography, parallax-ready sections, "
                         "CTA that floats over the hero. Dark theme with accent colors.",
            "modern": "Clean card-based layout, lots of whitespace, subtle animations, "
                      "mobile-first. Light theme.",
            "classic": "Detail-dense layout, trust badges, testimonials, long-form content. "
                       "Professional navy/blue theme.",
        }.get(style, "Modern single-column layout with bold hero and clear CTAs.")

        system = f"""You are a world-class real estate / property landing page copywriter.
Generate a complete landing page content structure for a commercial property.
Style: {style_guide}

Return ONLY JSON with this structure:
{{
  "style": "{style}",
  "hero": {{
    "headline": "powerful headline (max 12 words)",
    "subheadline": "supporting line (max 20 words)",
    "cta_text": "button text (3-5 words)",
    "trust_badge": "optional trust metric (e.g. '500+ Properties Protected')"
  }},
  "property_section": {{
    "headline": "section headline",
    "features": [
      {{"icon": "briefcase|hard-hat|ruler|sun|shield|map-pin", "label": "Feature label", "value": "Feature description"}}
    ],
    "description": "2-3 sentence persuasive description"
  }},
  "neighborhood_section": {{
    "headline": "neighborhood headline",
    "highlights": ["highlight1", "highlight2", "highlight3"],
    "description": "1-2 sentence neighborhood description"
  }},
  "storm_risk_section": {{
    "headline": "storm awareness headline",
    "description": "reassuring but factual risk description",
    "action_text": "what the visitor should do"
  }},
  "about_section": {{
    "headline": "about headline",
    "body": "2-3 sentence company description",
    "trust_signals": ["trust_signal1", "trust_signal2"]
  }},
  "cta_section": {{
    "headline": "final CTA headline",
    "subheadline": "final CTA subheadline",
    "button_text": "final button text",
    "urgency_note": "optional urgency message"
  }},
  "seo": {{
    "page_title": "SEO title tag (max 60 chars)",
    "meta_description": "SEO meta description (max 155 chars)",
    "keywords": ["kw1", "kw2", "kw3"]
  }},
  "og": {{
    "og_title": "OG title for social sharing (max 60 chars)",
    "og_description": "OG description (max 120 chars)",
    "og_image_alt": "alt text for social share image"
  }}
}}"""

        prompt = (
            f"Address: {address}\n"
            f"Metro: {metro}\n"
            f"Niche: {niche}\n"
            f"Property: {prop_summary}\n"
            f"Neighborhood: {hood_summary}\n"
            f"Storm: {storm_summary}\n"
            f"Style: {style}\n"
            f"Write conversion-optimized landing page content. Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.5)
        if "_error" in result:
            self.stats["errors"] += 1
            result = self._fallback_landing_page(address, metro, niche, style)

        result["address"] = address
        result["metro"] = metro
        result["niche"] = niche
        result["style"] = style
        result["content_type"] = "landing_page"
        result["generated_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["landing_pages"] += 1
        self.stats["content_runs"] += 1
        self._cache[cache_key] = dict(result)
        await self._persist_content(result)
        return result

    # ── PROPERTY DESCRIPTION ───────────────────────────────────────
    async def generate_property_description(
        self,
        property_data: Dict,
        niche: str = "Roofing Restoration",
        word_count: int = 350,
    ) -> Dict:
        """
        Generate an SEO-optimized property description that highlights
        the property's features and positions it within the niche's
        service offerings.
        """
        system = f"""You are an SEO content writer for commercial property services.
Write a persuasive, SEO-optimized property description.
Target: ~{word_count} words.
Return ONLY JSON:
{{
  "title": "SEO-optimized title (max 70 chars)",
  "meta_description": "meta description (max 155 chars)",
  "description": "full property description ({word_count} words)",
  "key_highlights": ["highlight1", "highlight2"],
  "target_keywords": ["kw1", "kw2"],
  "tone": "professional|urgent|informative",
  "reading_time_seconds": integer
}}"""

        prop_json = json.dumps(property_data, default=str)[:800]
        prompt = (
            f"Property data: {prop_json}\n"
            f"Niche: {niche}\n"
            f"Write a commercial property description optimized for {niche} services. "
            f"Focus on the property's characteristics that are relevant to {niche} needs. "
            f"Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.4)
        if "_error" in result:
            self.stats["errors"] += 1
            result = {
                "title": f"Professional {niche} Services Available | Commercial Property",
                "meta_description": f"Expert {niche.lower()} for commercial properties. Fast, reliable service with insurance-friendly documentation.",
                "description": f"This commercial property is ideally suited for professional {niche.lower()} services. "
                              f"Our team provides comprehensive assessments and prompt service delivery.",
                "key_highlights": ["Commercial-grade service", "Insurance documentation", "Fast response time"],
                "target_keywords": [niche.lower(), "commercial property", "professional service"],
                "tone": "professional",
                "reading_time_seconds": 90,
                "_fallback": True,
            }

        result["content_type"] = "property_desc"
        result["generated_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["property_descs"] += 1
        self.stats["content_runs"] += 1
        await self._persist_content(result)
        return result

    # ── NEIGHBORHOOD GUIDE ─────────────────────────────────────────
    async def generate_neighborhood_guide(
        self,
        neighborhood_data: Dict,
        metro: str = "",
    ) -> Dict:
        """
        Generate a neighborhood guide content piece — schools, amenities,
        commute, lifestyle — optimized for local SEO.
        """
        system = """You are a neighborhood content writer for real estate.
Write an engaging, informative neighborhood guide. Return ONLY JSON:
{
  "title": "SEO title (max 70 chars)",
  "meta_description": "meta desc (max 155 chars)",
  "overview": "2-3 sentence neighborhood overview",
  "schools": {"rating": "int/10 on GreatSchools", "top_schools": ["school1", "school2"]},
  "commute": {"avg_commute_minutes": int, "major_routes": ["route1", "route2"]},
  "amenities": [
    {"category": "parks|shopping|dining|transit", "name": "name", "description": "short desc"}
  ],
  "lifestyle": "2-3 sentence lifestyle description",
  "local_seo_keywords": ["kw1", "kw2"],
  "best_for": "who this neighborhood is best for"
}"""

        hood_json = json.dumps(neighborhood_data, default=str)[:800]
        prompt = (
            f"Neighborhood data: {hood_json}\n"
            f"Metro: {metro or 'unknown'}\n"
            f"Write a neighborhood guide optimized for local SEO. "
            f"Highlight schools, commute, amenities, and lifestyle. "
            f"Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.4)
        if "_error" in result:
            self.stats["errors"] += 1
            result = {
                "title": f"Living in {metro or 'This Neighborhood'} | Local Guide",
                "meta_description": f"Complete guide to {metro or 'this neighborhood'} — schools, commute, amenities, and lifestyle.",
                "overview": f"{metro or 'This neighborhood'} offers a blend of urban convenience and suburban comfort.",
                "schools": {"rating": 6, "top_schools": ["Local Elementary", "Regional High School"]},
                "commute": {"avg_commute_minutes": 30, "major_routes": ["I-35", "I-635"]},
                "amenities": [
                    {"category": "parks", "name": "City Park", "description": "Nearest public park"},
                    {"category": "shopping", "name": "Shopping Center", "description": "Retail and dining"},
                ],
                "lifestyle": "Family-friendly with growing commercial infrastructure.",
                "local_seo_keywords": [f"{metro.lower()} neighborhood", f"living in {metro.lower()}"],
                "best_for": "Professionals and families seeking suburban access with urban proximity.",
                "_fallback": True,
            }

        result["content_type"] = "neighborhood"
        result["generated_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["neighborhood_guides"] += 1
        self.stats["content_runs"] += 1
        await self._persist_content(result)
        return result

    # ── STORM RISK CONTENT ─────────────────────────────────────────
    async def generate_storm_risk_content(
        self,
        storm_data: Dict,
        property_data: Optional[Dict] = None,
        niche: str = "Roofing Restoration",
    ) -> Dict:
        """
        Generate storm risk assessment content for a property. Used in
        landing pages, email outreach, and SEO content to address the
        storm damage angle.
        """
        system = """You are a storm risk content writer for commercial property services.
Write factual, reassuring content about storm risk and property protection.
Return ONLY JSON:
{
  "title": "Risk assessment title (max 70 chars)",
  "meta_description": "meta desc (max 155 chars)",
  "risk_summary": "2-3 sentence risk summary for this location",
  "damage_scenarios": [
    {"event_type": "hail|wind|tornado|flood", "probability": "low|medium|high", "typical_damage": "description"}
  ],
  "protection_measures": ["measure1", "measure2"],
  "why_act_now": "urgency message",
  "localized_keywords": ["kw1", "kw2"]
}"""

        storm_json = json.dumps(storm_data, default=str)[:600]
        prop_type = property_data.get("property_type", "Commercial") if property_data else "Commercial"
        roof = property_data.get("roof_type", "Unknown") if property_data else "Unknown"

        prompt = (
            f"Storm data: {storm_json}\n"
            f"Property type: {prop_type}\n"
            f"Roof type: {roof}\n"
            f"Niche: {niche}\n"
            f"Write storm risk content that informs and motivates property owners "
            f"to take protective action. Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.4)
        if "_error" in result:
            self.stats["errors"] += 1
            result = {
                "title": f"Storm Risk Assessment | {prop_type} Property",
                "meta_description": f"Severe weather risk analysis for {prop_type.lower()} properties. Understand your exposure and protect your asset.",
                "risk_summary": "This property is located in an area with moderate severe weather risk, "
                              "primarily from thunderstorms and hail events common to the region.",
                "damage_scenarios": [
                    {"event_type": "hail", "probability": "medium", "typical_damage": "Roof surface damage, dented HVAC units"},
                    {"event_type": "wind", "probability": "medium", "typical_damage": "Roof membrane tears, debris impact"},
                    {"event_type": "tornado", "probability": "low", "typical_damage": "Catastrophic structural damage"},
                ],
                "protection_measures": [
                    "Schedule a professional roof inspection after any severe weather event",
                    "Document existing roof condition with photos for insurance purposes",
                    "Maintain gutter and drainage systems to prevent water intrusion",
                ],
                "why_act_now": "Insurance claim deadlines are tight. Most policies require damage documentation within 72 hours.",
                "localized_keywords": ["storm damage", "roof inspection", f"{prop_type.lower()} protection"],
                "_fallback": True,
            }

        result["content_type"] = "storm_risk"
        result["generated_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["storm_risk_pieces"] += 1
        self.stats["content_runs"] += 1
        await self._persist_content(result)
        return result

    # ── SOCIAL / OPEN GRAPH ────────────────────────────────────────
    async def generate_social_og(
        self,
        address: str = "",
        metro: str = "",
        niche: str = "Roofing Restoration",
        landing_page: Optional[Dict] = None,
        property_data: Optional[Dict] = None,
    ) -> Dict:
        """
        Generate Open Graph / social sharing metadata optimized for
        Facebook, LinkedIn, and Twitter.
        """
        hero = (landing_page or {}).get("hero", {}) if landing_page else {}
        seo = (landing_page or {}).get("seo", {}) if landing_page else {}

        system = """You are a social media copywriter for real estate / property services.
Write high-engagement social sharing content. Return ONLY JSON:
{
  "og_title": "OG title (max 60 chars) — for Facebook, LinkedIn",
  "og_description": "OG description (max 120 chars)",
  "twitter_title": "Twitter/X title (max 60 chars)",
  "twitter_description": "Twitter/X description (max 120 chars)",
  "linkedin_headline": "LinkedIn headline (max 80 chars)",
  "linkedin_body": "LinkedIn post body (1-2 sentences)",
  "hashtags": ["#tag1", "#tag2"],
  "facebook_post": "Facebook post preview text (1-2 sentences)"
}"""

        prompt = (
            f"Address: {address}\n"
            f"Metro: {metro}\n"
            f"Niche: {niche}\n"
            f"Hero headline: {hero.get('headline', '')}\n"
            f"Page title: {seo.get('page_title', '')}\n"
            f"Write social sharing content for this property landing page. "
            f"Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.6)
        if "_error" in result:
            self.stats["errors"] += 1
            result = {
                "og_title": f"Property Storm Protection | {metro}",
                "og_description": f"Expert {niche.lower()} services for commercial properties in {metro}. Get a free assessment today.",
                "twitter_title": f"Protect Your {metro} Property",
                "twitter_description": f"Severe weather risk assessment and {niche.lower()} for commercial properties.",
                "linkedin_headline": f"Commercial Property Storm Intelligence — {metro}",
                "linkedin_body": f"Our team provides comprehensive {niche.lower()} services for commercial properties in the {metro} area.",
                "hashtags": ["#" + niche.replace(" ", ""), "#StormDamage", "#PropertyProtection"],
                "facebook_post": f"Is your commercial property ready for the next storm? Get a professional assessment.",
                "_fallback": True,
            }

        result["content_type"] = "social_og"
        result["generated_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["social_og_pieces"] += 1
        self.stats["content_runs"] += 1
        await self._persist_content(result)
        return result

    # ── EMAIL OUTREACH CONTENT ────────────────────────────────────
    async def generate_email_content(
        self,
        property_data: Dict,
        storm_data: Optional[Dict] = None,
        niche: str = "Roofing Restoration",
    ) -> Dict:
        """
        Generate email outreach content for property owners after a
        storm event. Designed to be used by the existing email sequence
        engine or as standalone outreach.
        """
        system = """You are an email copywriter for property storm damage services.
Write a compelling outreach email for a commercial property owner.
Return ONLY JSON:
{
  "subject_line": "email subject (max 60 chars, urgent but professional)",
  "preheader": "preheader text (max 100 chars)",
  "greeting": "personalized greeting",
  "body_paragraphs": ["p1", "p2", "p3"],
  "call_to_action": "CTA button text (3-5 words)",
  "ps_line": "optional P.S. for urgency",
  "compliance_note": "CAN-SPAM compliance footer note"
}"""

        prop_json = json.dumps(property_data, default=str)[:600]
        storm_context = ""
        if storm_data:
            storm_context = f"Risk level: {storm_data.get('risk_level', 'unknown')}, " \
                          f"Recent events: {storm_data.get('total_events_last_5yr', 'N/A')}"

        prompt = (
            f"Property: {prop_json}\n"
            f"Storm context: {storm_context}\n"
            f"Niche: {niche}\n"
            f"Write a professional outreach email for a commercial property owner. "
            f"Focus on storm damage prevention and inspection services. "
            f"Return JSON only."
        )

        result = await _ollama_json(prompt, system, temperature=0.5)
        if "_error" in result:
            self.stats["errors"] += 1
            prop_addr = property_data.get("address", "your property")
            result = {
                "subject_line": f"Storm Risk Alert | {prop_addr[:30]}",
                "preheader": "Free commercial property storm damage assessment available now.",
                "greeting": "Dear Property Owner,",
                "body_paragraphs": [
                    f"Our records indicate that {prop_addr} is in an area recently affected by severe weather.",
                    "We specialize in commercial property storm damage assessments and insurance documentation.",
                    "Schedule a free inspection today — no obligation, no upfront cost.",
                ],
                "call_to_action": "Schedule Free Inspection",
                "ps_line": "Insurance claim deadlines are tight. Most policies require documentation within 72 hours of the event.",
                "compliance_note": "You are receiving this because your property was flagged in a recent severe weather event.",
                "_fallback": True,
            }

        result["content_type"] = "email_content"
        result["generated_at"] = datetime.now(timezone.utc).isoformat()

        self.stats["email_pieces"] += 1
        self.stats["content_runs"] += 1
        await self._persist_content(result)
        return result

    # ── BULK GENERATE FROM RESEARCH ────────────────────────────────
    async def bulk_generate_for_research(self, research_package: Dict) -> Dict:
        """
        Given a research package (from ResearchAgent.full_research()),
        generate all appropriate content types in parallel.
        Returns a dict of {content_type: result}.
        """
        address = research_package.get("address", "")
        metro = research_package.get("metro", "")
        niche = research_package.get("niche", "Roofing Restoration")
        property_data = research_package.get("property")
        neighborhood_data = research_package.get("neighborhood")
        storm_data = research_package.get("storm_history")
        buyer_intent = research_package.get("buyer_intent")

        tasks = []

        # Landing page (most important — always generate)
        tasks.append(self.generate_landing_page(
            address=address, metro=metro, niche=niche,
            property_data=property_data,
            neighborhood_data=neighborhood_data,
            storm_data=storm_data,
            style="cinematic",
        ))

        # Property description
        if property_data:
            tasks.append(self.generate_property_description(property_data, niche))

        # Neighborhood guide
        if neighborhood_data:
            tasks.append(self.generate_neighborhood_guide(neighborhood_data, metro))

        # Storm risk content
        if storm_data:
            tasks.append(self.generate_storm_risk_content(storm_data, property_data, niche))

        # Social OG
        tasks.append(self.generate_social_og(address=address, metro=metro, niche=niche))

        # Email content
        if property_data:
            tasks.append(self.generate_email_content(property_data, storm_data, niche))

        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {
            "address": address,
            "metro": metro,
            "niche": niche,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "content_count": 0,
            "errors": 0,
        }

        for r in results:
            if isinstance(r, Exception):
                log.warning(f"[content] bulk_generate sub-task failed: {r}")
                output["errors"] += 1
                continue
            if not isinstance(r, dict):
                continue
            ctype = r.get("content_type", "unknown")
            output[ctype] = r
            output["content_count"] += 1

        return output

    # ── PERIST TO SUPABASE ─────────────────────────────────────────
    async def _persist_content(self, result: Dict):
        """Save content generation result to seo_content table."""
        try:
            sb = _get_sb()
            content_type = result.get("content_type", "unknown")
            title = ""
            desc = ""
            if content_type == "landing_page":
                seo = result.get("seo") or {}
                title = seo.get("page_title", "")
                desc = seo.get("meta_description", "")
            elif content_type == "property_desc":
                title = result.get("title", "")
                desc = result.get("meta_description", "")
            elif content_type == "storm_risk":
                title = result.get("title", "")
                desc = result.get("meta_description", "")

            sb.table("seo_content").insert({
                "keyword": title[:100] if title else f"{content_type}-{result.get('metro', 'unknown')}",
                "niche": result.get("niche", ""),
                "metro": result.get("metro", "national"),
                "title_tag": title[:200] if title else "",
                "meta_description": desc[:300] if desc else "",
                "body": json.dumps(result, default=str)[:5000],
                "content_type": content_type,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            }).execute()
        except Exception as e:
            log.debug(f"[content] persist failed: {e}")

    # ── FALLBACK LANDING PAGE ──────────────────────────────────────
    @staticmethod
    def _fallback_landing_page(address: str, metro: str, niche: str, style: str) -> Dict:
        return {
            "style": style,
            "hero": {
                "headline": f"Protect Your {metro} Commercial Property",
                "subheadline": f"Expert {niche.lower()} — Fast, Professional, Insurance-Ready",
                "cta_text": "Get Your Free Assessment",
                "trust_badge": "Trusted by 500+ Property Owners",
            },
            "property_section": {
                "headline": "Your Property, Protected",
                "features": [
                    {"icon": "shield", "label": "Insurance-Ready", "value": "Full documentation for claims"},
                    {"icon": "hard-hat", "label": "Licensed Experts", "value": "Certified commercial inspectors"},
                    {"icon": "sun", "label": "Fast Response", "value": "48-hour assessment guarantee"},
                ],
                "description": f"Your property at {address} deserves proactive protection against {niche.lower()} needs.",
            },
            "neighborhood_section": {
                "headline": f"About {metro}",
                "highlights": ["Growing commercial district", "Strong property values", "Active business community"],
                "description": f"{metro} is a thriving commercial hub. Protect your investment with professional oversight.",
            },
            "storm_risk_section": {
                "headline": "Storm Awareness",
                "description": "Severe weather can strike without warning. Be prepared with a professional assessment.",
                "action_text": "Schedule your inspection before the next storm hits.",
            },
            "about_section": {
                "headline": "Why Choose Us",
                "body": f"We specialize in commercial {niche.lower()} services with a focus on insurance documentation and fast response times.",
                "trust_signals": ["Licensed & Insured", "5-Star Reviews", "Same-Week Service"],
            },
            "cta_section": {
                "headline": "Don't Wait Until It's Too Late",
                "subheadline": "Free inspection · No obligation · Insurance documentation included",
                "button_text": "Schedule Now",
                "urgency_note": "Availability is limited. Most properties are assessed within 48 hours.",
            },
            "seo": {
                "page_title": f"{niche} Services | {metro} Commercial Property | Free Assessment",
                "meta_description": f"Professional {niche.lower()} for commercial properties in {metro}. Free inspection, insurance documentation, and fast response. Schedule today.",
                "keywords": [niche.lower(), metro.lower(), "commercial property", "storm damage", "free inspection"],
            },
            "og": {
                "og_title": f"{niche} | {metro} Commercial Property Protection",
                "og_description": f"Free commercial property {niche.lower()} assessment in {metro}. Licensed experts, insurance documentation included.",
                "og_image_alt": f"Commercial property in {metro} - {niche} services",
            },
            "_fallback": True,
        }

    # ── PERFORMANCE SNAPSHOT ───────────────────────────────────────
    async def performance_snapshot(self) -> Dict:
        """Return stats + recent content."""
        try:
            sb = _get_sb()
            r = sb.table("seo_content") \
                .select("keyword,content_type,niche,metro,generated_at") \
                .order("generated_at", desc=True) \
                .limit(20) \
                .execute()
            recent = r.data or []
        except Exception:
            recent = []

        return {
            "stats": dict(self.stats),
            "cache_size": len(self._cache),
            "content_types": self.CONTENT_TYPES,
            "recent_content": recent,
        }


# ── GLOBAL SINGLETON ─────────────────────────────────────────────────
_CONTENT_AGENT: Optional[ContentAgent] = None


def get_content_agent() -> ContentAgent:
    global _CONTENT_AGENT
    if _CONTENT_AGENT is None:
        _CONTENT_AGENT = ContentAgent()
    return _CONTENT_AGENT


# ── STANDALONE CLI ───────────────────────────────────────────────────
if __name__ == "__main__":
    import sys

    async def _demo():
        agent = get_content_agent()

        if "--landing" in sys.argv:
            result = await agent.generate_landing_page(
                address="500 Industrial Blvd",
                metro="Fort Worth",
                niche="Roofing Restoration",
                style="cinematic",
            )
            print(json.dumps(result, indent=2, default=str)[:3000])
        elif "--social" in sys.argv:
            result = await agent.generate_social_og(
                address="500 Industrial Blvd",
                metro="Fort Worth",
                niche="Roofing Restoration",
            )
            print(json.dumps(result, indent=2, default=str))
        elif "--email" in sys.argv:
            result = await agent.generate_email_content(
                property_data={"address": "500 Industrial Blvd", "property_type": "Commercial", "roof_type": "TPO"},
                niche="Roofing Restoration",
            )
            print(json.dumps(result, indent=2, default=str))
        else:
            snap = await agent.performance_snapshot()
            print(json.dumps(snap, indent=2, default=str))

    asyncio.run(_demo())
