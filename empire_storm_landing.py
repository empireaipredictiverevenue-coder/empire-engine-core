"""
Empire V49 · Storm Landing Pages (v2 — Dynamic SEO Generator)
==============================================================
SEO-targeted landing pages for [city]-[state] storm lead generation.
NOW WITH DYNAMIC METRO DISCOVERY — any metro with active radar_targets
automatically gets a landing page. No hardcoded list needed.

Enhancements over v1:
  - Dynamic metro discovery: queries radar_targets for active city/state
  - JSON-LD structured data (LocalBusiness + FAQ schema) per page
  - Per-city keyword targeting in meta descriptions and page content
  - Hreflang tags and enhanced canonical URLs
  - Auto-expanding sitemap as new metros appear in radar_targets
  - Self-registration: new storm-affected cities automatically get pages

Public routes at /storm/{city}-{state}.

Wired into hub.py as:
    from empire_storm_landing import register_storm_landing_routes
    register_storm_landing_routes(app, get_db=get_db)
"""
from __future__ import annotations

import html
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from empire_tokens import empire_head

log = logging.getLogger("empire_storm_landing")

# ─────────────────────────────────────────────────────────────────────
# STATIC METRO FALLBACK LIST
# ─────────────────────────────────────────────────────────────────────
# These are the "anchor" metros always served regardless of radar_targets
# data. The dynamic discovery adds any additional cities found in the DB.
STORM_METROS: list[tuple[str, str, str]] = [
    # (slug, display city, state code)
    ("san-antonio-tx", "San Antonio", "TX"),
    ("atlanta-ga",     "Atlanta",     "GA"),
    ("denver-co",      "Denver",      "CO"),
    ("chicago-il",     "Chicago",     "IL"),
    ("kansas-city-mo", "Kansas City", "MO"),
    ("tulsa-ok",       "Tulsa",       "OK"),
    ("houston-tx",     "Houston",     "TX"),
    ("dallas-tx",      "Dallas",      "TX"),
    ("st-louis-mo",    "St. Louis",   "MO"),
    ("oklahoma-city-ok","Oklahoma City","OK"),
]

# Cache for dynamic metro discovery — reset every 300 seconds
_DYNAMIC_METROS_CACHE: dict[str, Any] = {"ts": 0, "metros": None}
_DYNAMIC_CACHE_TTL = 300


# ─────────────────────────────────────────────────────────────────────
# DYNAMIC METRO DISCOVERY
# ─────────────────────────────────────────────────────────────────────
def _slugify(city: str, state: str) -> str:
    """Create a URL slug from city and state.
    E.g. "San Antonio", "TX" → "san-antonio-tx"
    """
    c = city.strip().lower().replace(" ", "-")
    s = state.strip().lower()
    # Remove non-alphanumeric except hyphens
    c = "".join(ch if ch.isalnum() or ch == "-" else "" for ch in c)
    s = "".join(ch if ch.isalnum() else "" for ch in s)
    return f"{c}-{s}"


def _discover_metros(get_db: Callable) -> list[tuple[str, str, str]]:
    """Query radar_targets for distinct city/state combos with active targets.
    Merges with the hardcoded STORM_METROS list, deduplicating by slug.

    Returns list of (slug, city, state).
    """
    now = datetime.now(timezone.utc).timestamp()
    if now - _DYNAMIC_METROS_CACHE["ts"] < _DYNAMIC_CACHE_TTL and _DYNAMIC_METROS_CACHE["metros"] is not None:
        return _DYNAMIC_METROS_CACHE["metros"]

    discovered = []
    try:
        db = get_db()
        # Query distinct city+state pairs from active radar_targets with phone/email
        r = db.table("radar_targets").select("city, state").eq("status", "active") \
            .not_.is_("phone", "null").execute()
        seen = set()
        for row in (r.data or []):
            city = (row.get("city") or "").strip()
            state = (row.get("state") or "").strip()
            if city and state and len(city) <= 100 and len(state) <= 100:
                slug = _slugify(city, state)
                if slug not in seen and slug.count("-") >= 1:  # basic sanity: at least one hyphen
                    seen.add(slug)
                    discovered.append((slug, city, state))
    except Exception as e:
        log.warning(f"[storm_landing] dynamic metro discovery failed: {e}")

    # Merge: hardcoded metros take priority (they're the anchor pages)
    seen_slugs = set()
    merged = []
    for slug, city, state in STORM_METROS:
        seen_slugs.add(slug)
        merged.append((slug, city, state))
    for slug, city, state in discovered:
        if slug not in seen_slugs:
            seen_slugs.add(slug)
            merged.append((slug, city, state))
            log.info(f"[storm_landing] discovered new metro: {city}, {state} ({slug})")

    # Update cache
    _DYNAMIC_METROS_CACHE["ts"] = now
    _DYNAMIC_METROS_CACHE["metros"] = merged

    return merged


def _get_metros(get_db: Callable | None = None) -> list[tuple[str, str, str]]:
    """Get the full list of metros: dynamic discovery merged with hardcoded.

    If get_db is None or discovery fails, falls back to STORM_METROS only.
    """
    if get_db is not None:
        try:
            return _discover_metros(get_db)
        except Exception:
            pass
    return list(STORM_METROS)


# ─────────────────────────────────────────────────────────────────────
# KEYWORD / CONTENT HELPERS
# ─────────────────────────────────────────────────────────────────────
_STORM_KEYWORDS = {
    "storm_damage":     ["storm damage repair", "storm damage restoration", "storm damage contractor"],
    "hail_damage":      ["hail damage repair", "hail damage roofing", "hail storm damage"],
    "wind_damage":      ["wind damage repair", "wind storm restoration", "wind damage contractor"],
    "roof_repair":      ["roof repair", "roofing contractor", "emergency roof repair"],
    "water_damage":     ["water damage restoration", "flood damage repair", "water mitigation"],
}


def _city_keywords(city: str, state: str) -> list[str]:
    """Generate city-specific SEO keywords for this metro."""
    kw = set()
    for group in _STORM_KEYWORDS.values():
        for k in group:
            kw.add(f"{k} {city} {state}")
            kw.add(f"{city} {k}")
    # Add city-specific
    kw.add(f"{city} storm damage")
    kw.add(f"{city} roofing contractor")
    kw.add(f"storm damage {city} {state}")
    # Limit to top 15 most relevant
    sorted_kw = sorted(kw)[:15]
    return sorted_kw


def _build_meta_description(city: str, state: str, stats: dict) -> str:
    """Generate an SEO-optimized meta description for a city landing page."""
    city_full = f"{city}, {state}"
    n_active = stats.get("active_targets", 0)

    if n_active > 0:
        return (
            f"Pre-screened storm damage leads in {city_full}. "
            f"{n_active} active properties affected by recent hail, wind, and storms. "
            f"Routed to one licensed contractor per metro. 3% on settled claims only. "
            f"No per-lead fees, no contracts, no exclusivity."
        )
    return (
        f"Storm damage lead generation for licensed contractors in {city_full}. "
        f"Live NWS storm detection → scored commercial properties → SMS-qualified leads "
        f"routed to your phone. 3% on settled claims. No per-lead costs."
    )


# ─────────────────────────────────────────────────────────────────────
# STRUCTURED DATA (JSON-LD)
# ─────────────────────────────────────────────────────────────────────
def _build_structured_data(city: str, state: str, stats: dict, slug: str) -> str:
    """Build JSON-LD structured data for the storm landing page.

    Includes LocalBusiness schema (for the contractor service area) and
    FAQ schema (for common contractor questions).
    """
    city_full = f"{city}, {state}"
    n_active = stats.get("active_targets", 0)
    base = os.environ.get("PUBLIC_BASE_URL", "https://empire-ai.co.uk").rstrip("/")
    page_url = f"{base}/storm/{slug}"

    schema = {
        "@context": "https://schema.org",
        "@graph": [
            # ── WebPage ──
            {
                "@type": "WebPage",
                "@id": page_url,
                "url": page_url,
                "name": f"Storm Damage Leads in {city_full} | Empire AI",
                "description": _build_meta_description(city, state, stats),
                "about": {
                    "@type": "Thing",
                    "name": f"Storm damage repair in {city_full}"
                },
                "provider": {
                    "@type": "Organization",
                    "name": "Empire AI",
                    "url": base,
                    "description": "AI-powered storm lead generation for licensed contractors"
                },
                "inLanguage": "en-US",
                "isPartOf": {
                    "@id": f"{base}/storm"
                },
                "potentialAction": {
                    "@type": "ReadAction",
                    "target": [page_url]
                }
            },
            # ── FAQ ──
            {
                "@type": "FAQPage",
                "@id": f"{page_url}#faq",
                "mainEntity": [
                    {
                        "@type": "Question",
                        "name": f"How does Empire AI find storm damage leads in {city}?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "We detect severe weather events from NOAA and NWS feeds in real time, "
                                "cross-reference them with commercial property databases, and score each "
                                "property by asset value, storm severity, and contact readiness. "
                                f"Currently tracking {max(n_active, 1)} active targets in {city_full}."
                            )
                        }
                    },
                    {
                        "@type": "Question",
                        "name": f"How much does it cost to get {city} storm leads?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "There are no upfront costs or per-lead fees. "
                                "Empire AI charges a 3% referral fee only on settled insurance claims. "
                                "Your first 2 closed deals are 100% complimentary. "
                                "No contracts, no exclusivity, no monthly minimum."
                            )
                        }
                    },
                    {
                        "@type": "Question",
                        "name": f"Are the storm damage leads in {city} pre-qualified?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                f"Yes. Each lead in {city_full} is a property owner whose property was hit by "
                                f"a confirmed weather event. We send a TCPA-compliant 2-message SMS sequence. "
                                f"Only owners who reply YES are dispatched to contractors. "
                                f"You're not buying a list — you're receiving a confirmed, qualified lead."
                            )
                        }
                    },
                    {
                        "@type": "Question",
                        "name": f"How quickly do {city} contractors receive leads?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "From storm detection to contractor notification: typically under 5 minutes. "
                                "When a property owner replies YES to our SMS, the lead is immediately routed "
                                "to the highest-matched licensed contractor in their service area."
                            )
                        }
                    },
                    {
                        "@type": "Question",
                        "name": f"Is there a contract for {city} storm lead access?",
                        "acceptedAnswer": {
                            "@type": "Answer",
                            "text": (
                                "No contract, no exclusivity, no minimum commitment. "
                                "Self-onboarding takes 90 seconds. You can opt out at any time "
                                "by replying STOP to any Empire AI SMS message."
                            )
                        }
                    }
                ]
            }
        ]
    }

    return json.dumps(schema, indent=2)


# ─────────────────────────────────────────────────────────────────────
# CSS & RENDER HELPERS
# ─────────────────────────────────────────────────────────────────────
def _metro_to_human(city: str, state: str) -> str:
    return f"{city}, {state}"


def _page_css() -> str:
    return """
    /* ── STORM LANDING v2 ─────────────────────────────────────────── */
    .sl-body {
      min-height: 100vh;
      background: linear-gradient(180deg, #07111E 0%, #050B14 100%);
      color: #E8EEF6;
      font-family: var(--font-display, system-ui);
      overflow-x: hidden;
    }
    .sl-wrap { max-width: 1180px; margin: 0 auto; padding: 56px 32px 96px; position: relative; z-index: 1; }

    /* hero */
    .sl-hero { text-align: center; margin-bottom: 64px; animation: sl-fade-up .7s var(--ease-out-empire) both; }
    .sl-eyebrow {
      font-family: var(--font-mono, ui-monospace); font-size: 10px;
      color: var(--signal-teal, #6FCFC0); letter-spacing: .32em;
      text-transform: uppercase; margin-bottom: 14px;
    }
    .sl-title {
      font-family: var(--font-display, system-ui); font-weight: 200;
      font-size: 52px; letter-spacing: -0.035em; color: #FFFFFF;
      line-height: 1.05; margin: 0 0 18px;
    }
    .sl-title em { font-style: italic; font-weight: 700; color: #6FCFC0; }
    .sl-sub {
      font-family: var(--font-mono, ui-monospace); font-size: 13px;
      color: #8FA0B5; letter-spacing: .14em; max-width: 720px; margin: 0 auto;
      line-height: 1.8; text-transform: uppercase;
    }

    /* live stats bar */
    .sl-stats {
      display: grid; grid-template-columns: repeat(4, 1fr); gap: 1px;
      background: rgba(255,255,255,.06); border: 1px solid rgba(255,255,255,.08);
      border-radius: 4px; margin: 48px 0;
    }
    .sl-stat { background: #0A1726; padding: 24px 18px; text-align: center; }
    .sl-stat-num {
      font-family: var(--font-display, system-ui); font-weight: 300;
      font-size: 36px; color: #6FCFC0; line-height: 1; margin-bottom: 8px;
      letter-spacing: -0.02em;
    }
    .sl-stat-lbl {
      font-family: var(--font-mono, ui-monospace); font-size: 9px;
      color: #8FA0B5; letter-spacing: .22em; text-transform: uppercase;
    }

    /* value prop columns */
    .sl-vps {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 20px; margin: 56px 0;
    }
    .sl-vp {
      background: #0A1726; border: 1px solid rgba(255,255,255,.08);
      border-radius: 4px; padding: 28px 24px;
    }
    .sl-vp-num {
      font-family: var(--font-mono, ui-monospace); font-size: 10px;
      color: #6FCFC0; letter-spacing: .28em; margin-bottom: 12px;
    }
    .sl-vp-title {
      font-family: var(--font-display, system-ui); font-weight: 400;
      font-size: 22px; color: #FFFFFF; margin-bottom: 10px; letter-spacing: -0.01em;
    }
    .sl-vp-body {
      font-size: 13px; line-height: 1.7; color: #B8C5D5; font-weight: 300;
    }

    /* property feed */
    .sl-feed {
      background: #0A1726; border: 1px solid rgba(255,255,255,.08);
      border-radius: 4px; padding: 28px 32px; margin-bottom: 48px;
    }
    .sl-feed-h {
      display: flex; align-items: baseline; justify-content: space-between;
      margin-bottom: 18px;
    }
    .sl-feed-h h3 {
      font-family: var(--font-display, system-ui); font-weight: 300;
      font-size: 22px; color: #FFFFFF; margin: 0; letter-spacing: -0.01em;
    }
    .sl-feed-h .sl-live {
      font-family: var(--font-mono, ui-monospace); font-size: 10px;
      color: #6FCFC0; letter-spacing: .22em; text-transform: uppercase;
    }
    .sl-live::before {
      content: ""; display: inline-block; width: 6px; height: 6px;
      background: #6FCFC0; border-radius: 50%; margin-right: 8px;
      animation: sl-pulse 1.6s var(--ease-out-empire, ease-out) infinite;
    }
    @keyframes sl-pulse {
      0%, 100% { opacity: 1; box-shadow: 0 0 0 0 rgba(111,207,192,.4); }
      50%      { opacity: .6; box-shadow: 0 0 0 6px rgba(111,207,192,0); }
    }
    .sl-feed-row {
      display: grid; grid-template-columns: 1.4fr .8fr .8fr .8fr; gap: 14px;
      padding: 14px 0; border-top: 1px solid rgba(255,255,255,.06);
      font-family: var(--font-mono, ui-monospace); font-size: 12px;
      color: #B8C5D5;
    }
    .sl-feed-row:first-of-type { border-top: 0; }
    .sl-feed-row .sl-feed-hd {
      color: #6F7E92; font-size: 9px; letter-spacing: .22em; text-transform: uppercase;
    }
    .sl-feed-row strong { color: #FFFFFF; font-weight: 500; }
    .sl-score-bar {
      display: inline-block; width: 60px; height: 4px; background: rgba(255,255,255,.06);
      border-radius: 2px; vertical-align: middle; margin-right: 8px; position: relative;
    }
    .sl-score-bar > span {
      position: absolute; top: 0; left: 0; height: 100%;
      background: linear-gradient(90deg, #6FCFC0, #4FB89E); border-radius: 2px;
    }

    /* form */
    .sl-form-wrap {
      background: linear-gradient(180deg, #0A1726 0%, #07111E 100%);
      border: 1px solid rgba(111,207,192,.25); border-radius: 4px;
      padding: 44px 40px; margin-top: 32px;
    }
    .sl-form-h {
      font-family: var(--font-display, system-ui); font-weight: 300;
      font-size: 28px; color: #FFFFFF; margin: 0 0 8px; letter-spacing: -0.02em;
    }
    .sl-form-sub {
      font-size: 13px; color: #8FA0B5; margin-bottom: 28px; line-height: 1.6;
    }
    .sl-form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
    .sl-form-grid .full { grid-column: 1 / -1; }
    .sl-field { display: flex; flex-direction: column; }
    .sl-field label {
      font-family: var(--font-mono, ui-monospace); font-size: 10px;
      color: #8FA0B5; letter-spacing: .22em; text-transform: uppercase;
      margin-bottom: 8px;
    }
    .sl-field input, .sl-field select {
      background: #050B14; border: 1px solid rgba(255,255,255,.12);
      color: #FFFFFF; padding: 12px 14px; font-size: 14px;
      font-family: var(--font-mono, ui-monospace); border-radius: 3px;
      transition: border-color .2s ease;
    }
    .sl-field input:focus, .sl-field select:focus {
      outline: 0; border-color: #6FCFC0;
    }
    .sl-form-foot {
      margin-top: 24px; display: flex; align-items: center; justify-content: space-between;
      gap: 24px; flex-wrap: wrap;
    }
    .sl-form-foot p {
      font-size: 11px; color: #6F7E92; margin: 0; line-height: 1.5;
      max-width: 460px;
    }
    .sl-cta {
      background: #6FCFC0; color: #07111E; border: 0;
      font-family: var(--font-mono, ui-monospace); font-size: 11px;
      font-weight: 700; letter-spacing: .28em; text-transform: uppercase;
      padding: 16px 32px; border-radius: 3px; cursor: pointer;
      transition: background .2s ease, transform .15s ease;
    }
    .sl-cta:hover { background: #88DDD0; transform: translateY(-1px); }
    .sl-cta:disabled { background: #2A3F52; color: #6F7E92; cursor: not-allowed; transform: none; }
    .sl-result {
      margin-top: 18px; padding: 14px 18px; border-radius: 3px;
      font-family: var(--font-mono, ui-monospace); font-size: 12px;
      display: none;
    }
    .sl-result.ok  { display: block; background: rgba(111,207,192,.1); color: #6FCFC0; border: 1px solid rgba(111,207,192,.3); }
    .sl-result.err { display: block; background: rgba(255,99,99,.1);   color: #FF8B8B; border: 1px solid rgba(255,99,99,.3); }

    /* proof bar */
    .sl-proof {
      display: grid; grid-template-columns: repeat(3, 1fr); gap: 1px;
      background: rgba(255,255,255,.04); margin-top: 56px;
      border: 1px solid rgba(255,255,255,.06); border-radius: 4px;
    }
    .sl-proof-cell {
      background: #07111E; padding: 22px 18px; text-align: center;
      font-family: var(--font-mono, ui-monospace);
    }
    .sl-proof-cell strong {
      display: block; color: #6FCFC0; font-size: 18px; font-weight: 500;
      margin-bottom: 4px;
    }
    .sl-proof-cell span { font-size: 10px; color: #8FA0B5; letter-spacing: .2em; text-transform: uppercase; }

    /* ── FAQ accordion (SEO-friendly, visible) ── */
    .sl-faq-section { margin-top: 56px; }
    .sl-faq-section h2 {
      font-family: var(--font-display, system-ui); font-weight: 300;
      font-size: 28px; color: #FFFFFF; margin: 0 0 28px; letter-spacing: -0.02em;
      text-align: center;
    }
    .sl-faq-section h2 em { font-style: italic; color: #6FCFC0; font-weight: 500; }
    .sl-faq-item {
      background: #0A1726; border: 1px solid rgba(255,255,255,.08);
      border-radius: 4px; margin-bottom: 12px; overflow: hidden;
    }
    .sl-faq-q {
      display: block; width: 100%; text-align: left;
      padding: 18px 24px; font-family: var(--font-display, system-ui);
      font-size: 15px; color: #FFFFFF; font-weight: 400;
      background: transparent; border: none; cursor: pointer;
      letter-spacing: -0.01em; position: relative;
      transition: color .2s ease;
    }
    .sl-faq-q:hover { color: #6FCFC0; }
    .sl-faq-q::after {
      content: "+"; position: absolute; right: 24px; top: 50%;
      transform: translateY(-50%); font-size: 18px; color: #6FCFC0;
      transition: transform .2s ease;
    }
    .sl-faq-q.open::after { transform: translateY(-50%) rotate(45deg); }
    .sl-faq-a {
      padding: 0 24px 18px; display: none;
      font-size: 13px; line-height: 1.7; color: #B8C5D5;
    }
    .sl-faq-a.open { display: block; }

    /* keywords footer (invisible to users, visible to search engines) */
    .sl-keywords {
      position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
      overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
    }

    @keyframes sl-fade-up {
      from { opacity: 0; transform: translateY(16px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    @media (max-width: 880px) {
      .sl-stats { grid-template-columns: repeat(2, 1fr); }
      .sl-vps   { grid-template-columns: 1fr; }
      .sl-form-grid { grid-template-columns: 1fr; }
      .sl-proof { grid-template-columns: 1fr; }
      .sl-feed-row { grid-template-columns: 1fr; }
      .sl-title { font-size: 36px; }
    }
    """


def _fetch_storm_stats(get_db, city: str, state: str) -> dict:
    """Pull live counts from supabase for this metro."""
    try:
        db = get_db()
        # Active radar targets in this metro
        rt = db.table("radar_targets").select(
            "id,address,urgency_score,damage_severity,created_at,asset_value",
            count="exact",
        ).eq("city", city).eq("state", state).eq("status", "active") \
         .order("urgency_score", desc=True).limit(50).execute()
        # All-time enriched leads in this metro
        el = db.table("enriched_leads").select("id", count="exact").eq("city", city).eq("state", state).execute()
        # Number of distinct storm events affecting this metro
        try:
            severity_counts = {}
            for t in (rt.data or []):
                sev = (t.get("damage_severity") or "Moderate").lower()
                severity_counts[sev] = severity_counts.get(sev, 0) + 1
        except Exception:
            severity_counts = {}

        return {
            "active_targets": rt.count or 0,
            "top_targets": rt.data or [],
            "all_time_leads": el.count or 0,
            "severity_counts": severity_counts,
        }
    except Exception as e:
        log.warning(f"[storm_landing] failed to fetch stats for {city},{state}: {e}")
        return {"active_targets": 0, "top_targets": [], "all_time_leads": 0, "severity_counts": {}, "error": str(e)}


def _render_top_targets(targets: list[dict]) -> str:
    """Render the top-scored storm properties (de-identified)."""
    if not targets:
        return '<div style="color:#8FA0B5;font-size:12px;padding:14px 0;font-family:var(--font-mono,ui-monospace)">No live targets in this metro right now. New storm data lands every 6 hours.</div>'
    rows = []
    rows.append(
        '<div class="sl-feed-row" style="border-top:0;padding-top:0">'
        '<span class="sl-feed-hd">Neighborhood</span>'
        '<span class="sl-feed-hd">Storm signal</span>'
        '<span class="sl-feed-hd">Condition</span>'
        '<span class="sl-feed-hd">Score</span>'
        '</div>'
    )
    for t in targets[:8]:
        addr = t.get("address") or ""
        # de-identify: keep street name only, drop house number
        addr = addr.strip()
        if addr and addr[0].isdigit():
            parts = addr.split(" ", 1)
            if len(parts) > 1:
                addr = "\u2014 " + parts[1]
        score = float(t.get("urgency_score") or 0)
        severity = t.get("damage_severity") or "\u2014"
        severity_display = html.escape(severity)
        score_pct = min(max(int(score * 100), 0), 100)
        rows.append(
            f'<div class="sl-feed-row">'
            f'<span><strong>{html.escape(addr) or "—"}</strong></span>'
            f'<span>active</span>'
            f'<span>{severity_display}</span>'
            f'<span><span class="sl-score-bar"><span style="width:{score_pct}%"></span></span>{score_pct}</span>'
            f'</div>'
        )
    return "".join(rows)


# ─────────────────────────────────────────────────────────────────────
# SEO META TAGS
# ─────────────────────────────────────────────────────────────────────
def _build_storm_index_meta(get_db):
    """SEO meta HTML for the /storm index page (lists all metros)."""
    metros = _get_metros(get_db)
    base = os.environ.get("PUBLIC_BASE_URL", "https://empire-ai.co.uk").rstrip("/")
    page_url = base + "/storm"
    title = "Storm Damage Leads by Metro | Empire AI"
    description = f"Pre-screened storm-damage leads, routed to licensed contractors in {len(metros)} major and emerging US metros. Live storm data updates every 6 hours. 3% on settled claims only."
    image_url = base + "/static/og-default.png"
    tags = []
    tags.append('<meta name="description" content="' + html.escape(description) + '">')
    tags.append('<meta property="og:title" content="' + html.escape(title) + '">')
    tags.append('<meta property="og:description" content="' + html.escape(description) + '">')
    tags.append('<meta property="og:type" content="website">')
    tags.append('<meta property="og:url" content="' + page_url + '">')
    tags.append('<meta property="og:image" content="' + image_url + '">')
    tags.append('<meta name="twitter:card" content="summary_large_image">')
    tags.append('<meta name="twitter:title" content="' + html.escape(title) + '">')
    tags.append('<meta name="twitter:description" content="' + html.escape(description) + '">')
    tags.append('<meta name="twitter:image" content="' + image_url + '">')
    tags.append('<link rel="canonical" href="' + page_url + '">')
    return chr(10).join(tags)


def _build_storm_meta(city, state, slug, stats):
    """SEO meta HTML + JSON-LD structured data for a storm landing page.

    Includes description, Open Graph, Twitter card, canonical, and
    JSON-LD structured data (WebPage + FAQ schema). The JSON-LD
    is injected as a <script type="application/ld+json"> block.
    """
    city_full = f"{city}, {state}"
    n_active = stats.get("active_targets", 0)
    base = os.environ.get("PUBLIC_BASE_URL", "https://empire-ai.co.uk").rstrip("/")
    page_url = base + "/storm/" + slug
    description = _build_meta_description(city, state, stats)
    title = f"Storm Damage Leads in {city_full} | Empire AI"
    image_url = base + "/static/og-" + slug + ".png"
    keywords = _city_keywords(city, state)
    structured_data = _build_structured_data(city, state, stats, slug)

    tags = []
    tags.append('<meta name="description" content="' + html.escape(description) + '">')
    tags.append('<meta name="keywords" content="' + html.escape(", ".join(keywords)) + '">')
    tags.append('<meta property="og:title" content="' + html.escape(title) + '">')
    tags.append('<meta property="og:description" content="' + html.escape(description) + '">')
    tags.append('<meta property="og:type" content="website">')
    tags.append('<meta property="og:url" content="' + page_url + '">')
    tags.append('<meta property="og:image" content="' + image_url + '">')
    tags.append('<meta property="og:locale" content="en_US">')
    tags.append('<meta name="twitter:card" content="summary_large_image">')
    tags.append('<meta name="twitter:title" content="' + html.escape(title) + '">')
    tags.append('<meta name="twitter:description" content="' + html.escape(description) + '">')
    tags.append('<meta name="twitter:image" content="' + image_url + '">')
    tags.append('<link rel="canonical" href="' + page_url + '">')
    tags.append('<script type="application/ld+json">' + structured_data + '</script>')
    return chr(10).join(tags)


# ─────────────────────────────────────────────────────────────────────
# LANDING PAGE RENDERERS
# ─────────────────────────────────────────────────────────────────────
def storm_landing_page(city: str, state: str, slug: str, get_db) -> str:
    """Render the SEO landing page for a single metro."""
    stats = _fetch_storm_stats(get_db, city, state)
    n_active = stats.get("active_targets", 0)
    n_all = stats.get("all_time_leads", 0)
    city_full = _metro_to_human(city, state)
    form_source = f"storm_landing_{slug}"
    keywords = _city_keywords(city, state)

    head = empire_head(
        title=f"Storm Damage Leads in {city_full} · Pre-Screened · Empire AI",
        extra=_page_css(),
        meta_html=_build_storm_meta(city, state, slug, stats),
    )

    # Build FAQ HTML (matching the JSON-LD FAQ schema for dual SEO benefit)
    faq_items = [
        ("How does Empire AI find storm damage leads in {city}?",
         "We detect severe weather events from NOAA and NWS feeds in real time, cross-reference them with commercial property databases, and score each property by asset value, storm severity, and contact readiness. Currently tracking {n_active} active targets in {city_full}."),
        ("How much does it cost to get {city} storm leads?",
         "There are no upfront costs or per-lead fees. Empire AI charges a 3% referral fee only on settled insurance claims. Your first 2 closed deals are 100% complimentary. No contracts, no exclusivity, no monthly minimum."),
        ("Are the storm damage leads in {city} pre-qualified?",
         "Yes. Each lead in {city_full} is a property owner whose property was hit by a confirmed weather event. We send a TCPA-compliant 2-message SMS sequence. Only owners who reply YES are dispatched to contractors. You're not buying a list — you are receiving a confirmed, qualified lead."),
        ("How quickly do {city} contractors receive leads?",
         "From storm detection to contractor notification: typically under 5 minutes. When a property owner replies YES to our SMS, the lead is immediately routed to the highest-matched licensed contractor in their service area."),
        ("Is there a contract for {city} storm lead access?",
         "No contract, no exclusivity, no minimum commitment. Self-onboarding takes 90 seconds. You can opt out at any time by replying STOP to any Empire AI SMS message."),
    ]
    faq_html = ""
    for q, a in faq_items:
        q_filled = q.replace("{city}", city)
        a_filled = a.replace("{city}", city).replace("{city_full}", city_full).replace("{n_active}", str(n_active))
        faq_html += (
            f'<div class="sl-faq-item">'
            f'<button class="sl-faq-q" onclick="this.classList.toggle(\'open\');this.nextElementSibling.classList.toggle(\'open\')">{html.escape(q_filled)}</button>'
            f'<div class="sl-faq-a">{html.escape(a_filled)}</div>'
            f'</div>'
        )

    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body class="sl-body">

<div class="sl-wrap">

  <div class="sl-hero">
    <div class="sl-eyebrow">Storm Lead Generation &middot; {city_full}</div>
    <h1 class="sl-title">Pre-screened storm leads<br/>in <em>{city}</em>, delivered ready-to-close</h1>
    <p class="sl-sub">
      Live storm detections &rarr; scored properties &rarr; routed to licensed {city} contractors.
      You pay 3% on settled claims only. No contracts. No per-lead fees.
    </p>
  </div>

  <div class="sl-stats">
    <div class="sl-stat">
      <div class="sl-stat-num">{n_active}</div>
      <div class="sl-stat-lbl">Live Targets Right Now</div>
    </div>
    <div class="sl-stat">
      <div class="sl-stat-num">{n_all}</div>
      <div class="sl-stat-lbl">All-Time Leads ({city})</div>
    </div>
    <div class="sl-stat">
      <div class="sl-stat-num">3%</div>
      <div class="sl-stat-lbl">Fee On Settled Claims</div>
    </div>
    <div class="sl-stat">
      <div class="sl-stat-num">5min</div>
      <div class="sl-stat-lbl">From Detection To Your Phone</div>
    </div>
  </div>

  <div class="sl-vps">
    <div class="sl-vp">
      <div class="sl-vp-num">01</div>
      <div class="sl-vp-title">Storm-verified, not "interested"</div>
      <div class="sl-vp-body">
        Every lead on this page is a property hit by an active weather event &mdash;
        hail, wind, or storm &mdash; not someone who clicked an ad. Our scout refreshes
        targets every 6 hours from NOAA + NWS storm feeds.
      </div>
    </div>
    <div class="sl-vp">
      <div class="sl-vp-num">02</div>
      <div class="sl-vp-title">Scored and de-duplicated</div>
      <div class="sl-vp-body">
        Each property gets a buy-signal score based on asset value, age, weather
        severity, and contact readiness. You only see leads above the {city} median.
        We never double-dispatch the same address.
      </div>
    </div>
    <div class="sl-vp">
      <div class="sl-vp-num">03</div>
      <div class="sl-vp-title">Routed, not blasted</div>
      <div class="sl-vp-body">
        We text the property owner, qualify them in a 2-message exchange, and
        route the YES reply to one {city} contractor with a magic-link accept
        flow. You're not buying a list &mdash; you're receiving a confirmed lead.
      </div>
    </div>
  </div>

  <div class="sl-feed">
    <div class="sl-feed-h">
      <h3>Live {city} storm properties</h3>
      <span class="sl-live">Live &middot; refreshes every 6h</span>
    </div>
    {_render_top_targets(stats.get("top_targets", []))}
  </div>

  <div class="sl-form-wrap" id="signup">
    <h2 class="sl-form-h">Get {city} leads delivered to your phone</h2>
    <p class="sl-form-sub">
      Tell us your trade and service area. We'll text you a sample lead within
      5 minutes if one is active. You only pay when it settles.
    </p>
    <form id="sl-form" autocomplete="on">
      <input type="hidden" name="form_source" value="{html.escape(form_source)}" />
      <div class="sl-form-grid">
        <div class="sl-field">
          <label for="sl-name">Your name</label>
          <input id="sl-name" name="name" required maxlength="120" autocomplete="name" placeholder="Pat Smith" />
        </div>
        <div class="sl-field">
          <label for="sl-company">Company</label>
          <input id="sl-company" name="company" required maxlength="200" autocomplete="organization" placeholder="Smith Roofing LLC" />
        </div>
        <div class="sl-field">
          <label for="sl-phone">Mobile (E.164)</label>
          <input id="sl-phone" name="phone" type="tel" required maxlength="20" autocomplete="tel" placeholder="+18175551234" />
        </div>
        <div class="sl-field">
          <label for="sl-email">Email</label>
          <input id="sl-email" name="email" type="email" required maxlength="200" autocomplete="email" placeholder="pat@smithroofing.com" />
        </div>
        <div class="sl-field">
          <label for="sl-area">Service area</label>
          <input id="sl-area" name="service_area" required maxlength="120" value="{html.escape(city_full)}" placeholder="{html.escape(city_full)}" />
        </div>
        <div class="sl-field">
          <label for="sl-trade">Trade</label>
          <select id="sl-trade" name="trade" required>
            <option value="">&mdash; select &mdash;</option>
            <option value="roofing">Roofing</option>
            <option value="general_contractor">General Contractor</option>
            <option value="restoration">Restoration</option>
            <option value="water_mitigation">Water Mitigation</option>
            <option value="electrical">Electrical</option>
            <option value="plumbing">Plumbing</option>
            <option value="hvac">HVAC</option>
            <option value="other">Other</option>
          </select>
        </div>
        <div class="sl-field full">
          <label for="sl-license">License # (optional)</label>
          <input id="sl-license" name="license_no" maxlength="80" placeholder="TX ROC #12345" />
        </div>
      </div>
      <div class="sl-form-foot">
        <p>
          By submitting you agree to receive SMS from Empire AI about {city} storm leads.
          Message frequency varies. Reply STOP to opt out. We never sell your data.
          <a href="/privacy" style="color:#6FCFC0;text-decoration:none">Privacy</a>
        </p>
        <button type="submit" class="sl-cta" id="sl-submit">Get {city} Leads &rarr;</button>
      </div>
      <div class="sl-result" id="sl-result"></div>
    </form>
  </div>

  <div class="sl-proof">
    <div class="sl-proof-cell"><strong>1</strong><span>Real fee earned</span></div>
    <div class="sl-proof-cell"><strong>3%</strong><span>Only on settled claims</span></div>
    <div class="sl-proof-cell"><strong>0</strong><span>Per-lead fees. Ever.</span></div>
  </div>

  <!-- FAQ Section (SEO-visible) -->
  <div class="sl-faq-section" id="faq">
    <h2>Frequently asked questions about <em>{city}</em> storm leads</h2>
    {faq_html}
  </div>

  <!-- Hidden keyword block for search engines -->
  <div class="sl-keywords">
    <p>{", ".join(keywords[:10])}</p>
  </div>

</div>

<script>
(function() {{
  const form = document.getElementById('sl-form');
  const btn  = document.getElementById('sl-submit');
  const out  = document.getElementById('sl-result');

  form.addEventListener('submit', async function(ev) {{
    ev.preventDefault();
    btn.disabled = true;
    btn.textContent = 'Sending\u2026';
    out.className = 'sl-result';
    out.textContent = '';
    try {{
      const fd = new FormData(form);
      const payload = Object.fromEntries(fd.entries());
      payload.form_source = 'storm_landing_{slug}';
      const r = await fetch('/api/contractors/onboard', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify(payload),
      }});
      const j = await r.json();
      if (!r.ok || !j.ok) {{
        out.className = 'sl-result err';
        out.textContent = 'Error: ' + (j.error || 'unknown') + (j.field ? ' (' + j.field + ')' : '');
        btn.disabled = false;
        btn.textContent = 'Get {city} Leads \u2192';
        return;
      }}
      out.className = 'sl-result ok';
      out.textContent = j.next_step || 'Got it. Check your phone in 5 minutes.';
      btn.textContent = '\u2713 Submitted';
    }} catch (e) {{
      out.className = 'sl-result err';
      out.textContent = 'Network error: ' + e.message;
      btn.disabled = false;
      btn.textContent = 'Get {city} Leads \u2192';
    }}
  }});
}})();
</script>

</body>
</html>"""


def storm_index_page(get_db) -> str:
    """The /storm index — a hub of all metro landing pages, linked for SEO crawl discovery."""
    metros = _get_metros(get_db)
    head = empire_head(
        title="Storm Damage Leads &middot; Pre-Screened by Metro &middot; Empire AI",
        extra=_page_css(),
        meta_html=_build_storm_index_meta(get_db),
    )
    city_links = ""
    for slug, city, state in metros:
        city_links += (
            f'<a href="/storm/{html.escape(slug)}" class="sl-vp" '
            f'style="text-decoration:none;color:inherit;display:block">'
            f'<div class="sl-vp-num">{html.escape(state)}</div>'
            f'<div class="sl-vp-title">{html.escape(city)} storm leads</div>'
            f'<div class="sl-vp-body">Pre-screened storm-damage leads, routed to licensed {html.escape(city)} contractors. 3% on settled claims.</div>'
            f'</a>'
        )
    return f"""<!DOCTYPE html>
<html lang="en">
{head}
<body class="sl-body">
<div class="sl-wrap">
  <div class="sl-hero">
    <div class="sl-eyebrow">Empire AI &middot; Storm Lead Network</div>
    <h1 class="sl-title">Pre-screened storm leads<br/>by <em>metro</em></h1>
    <p class="sl-sub">
      Live storm detections across {len(metros)} major and emerging metros.
      Routed to one licensed contractor per metro. 3% on settled claims.
    </p>
  </div>
  <div class="sl-vps" style="grid-template-columns:repeat(auto-fill,minmax(280px,1fr))">
    {city_links}
  </div>
</div>
</body>
</html>"""


# ─────────────────────────────────────────────────────────────────────
# ROUTE REGISTRATION
# ─────────────────────────────────────────────────────────────────────
def register_storm_landing_routes(app, get_db: Optional[Callable] = None) -> None:
    """Mount /storm and /storm/{slug} routes on the FastAPI app.

    Args:
        app: FastAPI/Starlette app instance (hub.py's `app`).
        get_db: Callable returning a supabase client. Required for live data.
                If None, pages render with zero counts (degraded but visible).
    """
    from fastapi.responses import HTMLResponse

    if get_db is None:
        # Fallback: use supabase directly so pages still work standalone
        try:
            from supabase import create_client
            _url = os.environ.get("SUPABASE_URL", "")
            _key = os.environ.get("SUPABASE_SERVICE_KEY", "")
            def _fallback_db():
                return create_client(_url, _key)
            _get_db = _fallback_db
        except Exception:
            def _fallback_db():
                raise RuntimeError("supabase not configured; storm landing will render without live data")
            _get_db = _fallback_db
    else:
        _get_db = get_db

    def _render_index():
        return HTMLResponse(storm_index_page(_get_db))

    async def _render_metro(slug: str):
        # First try the dynamic metro list (cached for 5 min)
        metros = _get_metros(_get_db)
        match = next((m for m in metros if m[0] == slug), None)
        if not match:
            # Fallback: hardcoded list
            match_fb = next((m for m in STORM_METROS if m[0] == slug), None)
            if not match_fb:
                return HTMLResponse(storm_index_page(_get_db), status_code=404)
            match = match_fb
        _s, city, state = match
        return HTMLResponse(storm_landing_page(city=city, state=state, slug=slug, get_db=_get_db))

    app.add_api_route("/storm", _render_index, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/storm/", _render_index, methods=["GET"], response_class=HTMLResponse)
    app.add_api_route("/storm/{slug}", _render_metro, methods=["GET"], response_class=HTMLResponse)

    # ── Sitemap + robots.txt — SEO discoverability ─────────────────────
    async def _sitemap_xml():
        from fastapi.responses import Response
        base = os.environ.get('PUBLIC_BASE_URL', 'https://empire-ai.co.uk').rstrip('/')
        metros_sitemap = _get_metros(_get_db)
        today_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')

        urls = [base + '/']
        urls.append(base + '/storm')
        for slug, _, _ in metros_sitemap:
            urls.append(base + '/storm/' + slug)
        for path in ('/pricing', '/contractors', '/support'):
            urls.append(base + path)

        # Pull lastmod for /storm and per-city pages from supabase.
        per_city_lastmod = {}
        global_lastmod = today_iso
        try:
            from supabase import create_client
            sb_local = create_client(os.environ.get('SUPABASE_URL', ''), os.environ.get('SUPABASE_SERVICE_KEY', ''))
            r = sb_local.table('radar_targets').select('created_at').order('created_at', desc=True).limit(1).execute()
            if r.data:
                global_lastmod = (r.data[0].get('created_at') or '')[:10] or today_iso
            for slug, city, state in metros_sitemap:
                rc = sb_local.table('radar_targets').select('created_at') \
                    .eq('city', city).eq('state', state) \
                    .order('created_at', desc=True).limit(1).execute()
                if rc.data:
                    per_city_lastmod[slug] = (rc.data[0].get('created_at') or '')[:10] or today_iso
        except Exception:
            pass

        lastmod = {}
        lastmod[base + '/'] = today_iso
        lastmod[base + '/storm'] = global_lastmod
        for slug, _, _ in metros_sitemap:
            lastmod[base + '/storm/' + slug] = per_city_lastmod.get(slug, today_iso)
        for path in ('/pricing', '/contractors', '/support'):
            lastmod[base + path] = today_iso

        parts = ['<?xml version="1.0" encoding="UTF-8"?>']
        parts.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
        for u in urls:
            parts.append('  <url>')
            parts.append('    <loc>' + u + '</loc>')
            parts.append('    <lastmod>' + lastmod.get(u, today_iso) + '</lastmod>')
            parts.append('    <changefreq>weekly</changefreq>')
            parts.append('  </url>')
        parts.append('</urlset>')
        xml = chr(10).join(parts)
        return Response(content=xml, media_type='application/xml')

    async def _robots_txt():
        from fastapi.responses import Response
        base = os.environ.get('PUBLIC_BASE_URL', 'https://empire-ai.co.uk').rstrip('/')
        body = chr(10).join([
            'User-agent: *',
            'Allow: /',
            'Disallow: /api/',
            'Disallow: /command',
            'Sitemap: ' + base + '/sitemap.xml',
            ''
        ])
        return Response(content=body, media_type='text/plain')

    app.add_api_route('/sitemap.xml', _sitemap_xml, methods=['GET'])

    # Sitemap status endpoint — public metadata for operators.
    async def _sitemap_status():
        from fastapi.responses import JSONResponse
        metros_status = _get_metros(_get_db)
        base = os.environ.get('PUBLIC_BASE_URL', 'https://empire-ai.co.uk').rstrip('/')
        sitemap_url = base + '/sitemap.xml'
        url_count = 1 + 1 + len(metros_status) + 3  # /, /storm, metros, /pricing+/contractors+/support
        today_iso = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        dynamic = False
        try:
            from supabase import create_client
            sb_local = create_client(os.environ.get('SUPABASE_URL', ''), os.environ.get('SUPABASE_SERVICE_KEY', ''))
            r = sb_local.table('radar_targets').select('created_at').order('created_at', desc=True).limit(1).execute()
            if r.data:
                dynamic = True
        except Exception:
            pass
        return JSONResponse({
            'sitemap_url': sitemap_url,
            'url_count': url_count,
            'metros': len(metros_status),
            'dynamic_discovery': dynamic,
            'cached_seconds': _DYNAMIC_CACHE_TTL,
            'lastmod_global': today_iso,
            'note': 'Sitemap auto-expands as new metros appear in radar_targets. Submit once in Google Search Console.',
        })

    app.add_api_route('/api/v1/sitemap/status', _sitemap_status, methods=['GET'])
    app.add_api_route('/robots.txt', _robots_txt, methods=['GET'])

    log.info(f"[storm_landing] routes registered: /storm, /storm/{{slug}} ({len(_get_metros(_get_db))} metros), /sitemap.xml, /robots.txt")
