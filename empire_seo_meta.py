"""
EMPIRE V49 · SEO METADATA MODULE
=================================
Centralized SEO metadata for all public-facing pages.
Provides title, description, keywords, Open Graph, and Twitter Card tags.

Usage:
    from empire_seo_meta import SEO_TAGS, seo_head

    # Get tags for a specific page:
    tags = seo_head("splash")
    html = f"<head>{tags}</head>..."

    # Or look up raw metadata:
    meta = SEO_TAGS["splash"]
"""

SEO_TAGS = {
    "splash": {
        "title": "Empire AI — AI-Powered Lead Generation & Contractor Dispatch",
        "description": (
            "Empire AI connects storm-affected property owners with vetted contractors. "
            "AI-powered lead generation, SMS qualification, and automated dispatch. "
            "3% fee only on settled claims. First 2 deals complimentary."
        ),
        "keywords": "lead generation, contractor dispatch, storm damage leads, AI lead gen, "
                    "roofing leads, insurance claims, contractor matching, pay per lead",
        "canonical": "https://empire-ai.co.uk/",
    },
    "pricing": {
        "title": "Empire AI Pricing — Suite Products & Lead Generation Plans",
        "description": (
            "Empire AI suite product pricing. SEO optimization, lead scoring, compliance, "
            "strike campaigns, competitor intelligence, and more. Plans from $99/mo."
        ),
        "keywords": "AI pricing, SEO pricing, lead scoring pricing, compliance software pricing, "
                    "contractor lead generation pricing",
        "canonical": "https://empire-ai.co.uk/pricing",
    },
    "demo": {
        "title": "Empire AI Demo — See AI Lead Generation in Action",
        "description": (
            "Watch Empire AI's automated lead generation pipeline: storm detection, SMS outreach, "
            "YES reply qualification, contractor matching, and dispatch — all automated."
        ),
        "keywords": "AI demo, lead generation demo, contractor dispatch demo, storm leads demo",
        "canonical": "https://empire-ai.co.uk/demo",
    },
    "support": {
        "title": "Empire AI Support — Help Center & Contact",
        "description": (
            "Get help with Empire AI. FAQ, documentation, and live chat support. "
            "Email support@empire-ai.co.uk for direct assistance."
        ),
        "keywords": "Empire AI support, help center, contractor support, lead generation help",
        "canonical": "https://empire-ai.co.uk/support",
    },
    "ppc": {
        "title": "Pay-Per-Call Marketplace — Buy Live Inbound Calls by Niche",
        "description": (
            "Empire AI's pay-per-call marketplace. Buy live inbound calls from qualified leads "
            "in roofing, HVAC, legal, insurance, healthcare, and more. Real-time call routing."
        ),
        "keywords": "pay per call, buy calls, live inbound calls, call marketplace, "
                    "roofing calls, HVAC calls, legal calls, insurance calls",
        "canonical": "https://empire-ai.co.uk/ppc",
    },
    "ppl": {
        "title": "Pay-Per-Lead Marketplace — Buy Qualified Leads by Vertical",
        "description": (
            "Empire AI's pay-per-lead marketplace. Buy verified leads across roofing, HVAC, "
            "legal, insurance, financial services, healthcare, and education verticals."
        ),
        "keywords": "pay per lead, buy leads, qualified leads, lead marketplace, "
                    "roofing leads, legal leads, insurance leads",
        "canonical": "https://empire-ai.co.uk/ppl",
    },
    "mrr": {
        "title": "Empire AI MRR Dashboard — Monthly Recurring Revenue Report",
        "description": (
            "Empire AI monthly recurring revenue dashboard. Track suite product subscriptions, "
            "trial conversions, churn rate, and revenue growth in real-time."
        ),
        "keywords": "MRR dashboard, recurring revenue, SaaS metrics, subscription tracking, revenue report",
        "canonical": "https://empire-ai.co.uk/mrr",
    },
    "meetily": {
        "title": "Meetily — Privacy-First AI Meeting Assistant | Empire AI",
        "description": (
            "Meetily by Empire AI. Privacy-first AI meeting assistant with real-time transcription, "
            "smart summaries, action items, and CRM integration. No cloud storage of recordings."
        ),
        "keywords": "AI meeting assistant, meeting transcription, meeting notes, privacy-first AI, "
                    "smart summaries, action items",
        "canonical": "https://empire-ai.co.uk/products/meetily",
    },
    "elite_scraper": {
        "title": "Elite Scraper V2 — AI-Powered Lead Intelligence | Empire AI",
        "description": (
            "Elite Scraper V2 by Empire AI. Multi-source lead intelligence engine with "
            "camofox stealth browser, YouTube channel scraping, phone validation (PhoneInfoga), "
            "and AI content extraction. Find qualified leads at scale."
        ),
        "keywords": "lead scraper, web scraper, lead intelligence, stealth browser, "
                    "phone validation, contractor leads, business intelligence",
        "canonical": "https://empire-ai.co.uk/products/elite-scraper",
    },
    "command": {
        "title": "Empire AI Command Deck — Operator Console",
        "description": (
            "Empire AI command deck. Real-time operator console for lead pipeline monitoring, "
            "dispatch tracking, contractor management, and revenue analytics."
        ),
        "keywords": "command deck, operator console, lead pipeline, dispatch tracking, contractor management",
        "canonical": "https://empire-ai.co.uk/command",
    },
    "fleet": {
        "title": "Empire AI Agent Fleet — Autonomous AI Agent Dashboard",
        "description": (
            "Empire AI autonomous agent fleet dashboard. Monitor 20+ AI agents running lead generation, "
            "contractor outreach, SMS dispatch, and revenue operations in real-time."
        ),
        "keywords": "AI agents, autonomous agents, agent fleet, AI dashboard, agent monitoring",
        "canonical": "https://empire-ai.co.uk/fleet",
    },
    "agent_os": {
        "title": "Empire AI Agent OS — Autonomous Agent Operating System",
        "description": (
            "Empire AI Agent OS kernel. Real-time agent orchestration with inter-process communication, "
            "capability registry, and autonomous decision-making engine."
        ),
        "keywords": "agent OS, AI operating system, agent orchestration, autonomous AI, agent kernel",
        "canonical": "https://empire-ai.co.uk/agent-os",
    },
    "cold_inbound": {
        "title": "Cold Inbound Dashboard — Lead Assessment & Dispatch | Empire AI",
        "description": (
            "Empire AI cold inbound lead assessment. Track qualification progress, call history, "
            "worksheet completion, and dispatch status for every cold inbound lead."
        ),
        "keywords": "cold inbound, lead assessment, lead qualification, dispatch tracking, call tracking",
        "canonical": "https://empire-ai.co.uk/cold-inbound",
    },
}

def seo_head(page: str) -> str:
    """Return a complete <head> SEO block for a page.

    Includes: title, meta description, meta keywords, og:title, og:description,
    og:type, og:url, twitter:card, twitter:title, twitter:description,
    canonical link, and viewport.

    Args:
        page: One of the keys in SEO_TAGS (e.g., 'splash', 'pricing', 'ppc')

    Returns:
        HTML string with all SEO meta tags, ready to insert into <head>.
    """
    import html as _html
    meta = SEO_TAGS.get(page)
    if not meta:
        return ""

    title = _html.escape(meta["title"])
    desc = _html.escape(meta["description"])
    kw = _html.escape(meta.get("keywords", ""))
    canonical = meta.get("canonical", "https://empire-ai.co.uk/")

    return f"""<title>{title}</title>
<meta name="description" content="{desc}">
<meta name="keywords" content="{kw}">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="index, follow">
<meta property="og:type" content="website">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{desc}">
<meta property="og:url" content="{canonical}">
<meta property="og:site_name" content="Empire AI">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{desc}">
<link rel="canonical" href="{canonical}">"""
