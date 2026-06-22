"""
EMPIRE V49 · JSON-LD STRUCTURED DATA
======================================
Generates Schema.org JSON-LD structured data for rich search results.

Schemas:
  - Organization — splash page (company info, logo, sameAs, contactPoint)
  - Product — pricing page (Suite products + Strike Packs)
  - FAQ — pricing page (common questions about lead gen, pricing, fees)

Usage:
    from empire_structured_data import organization_jsonld, products_jsonld, faq_jsonld

    # In splash_page():
    meta_html = organization_jsonld()
    head = empire_head(..., meta_html=meta_html)

    # In pricing_page():
    meta_html = products_jsonld() + faq_jsonld()
    head = empire_head(..., meta_html=meta_html)
"""
import json


BASE_URL = "https://empire-ai.co.uk"


def _jsonld_script(data: dict) -> str:
    """Wrap a Python dict as a JSON-LD <script> tag."""
    return (
        '<script type="application/ld+json">\n'
        + json.dumps(data, indent=2, ensure_ascii=False)
        + '\n</script>\n'
    )


# ══════════════════════════════════════════════════════════════════════════════
# ORGANIZATION SCHEMA — splash page
# ══════════════════════════════════════════════════════════════════════════════
def organization_jsonld() -> str:
    """Generate Organization JSON-LD for empire-ai.co.uk (splash page)."""
    data = {
        "@context": "https://schema.org",
        "@type": "Organization",
        "@id": f"{BASE_URL}/#organization",
        "name": "Empire AI",
        "alternateName": "Empire AI · Storm Revenue Engine",
        "url": BASE_URL,
        "logo": f"{BASE_URL}/static/logo.png",
        "description": (
            "AI-powered lead generation and contractor dispatch platform. "
            "Automated storm damage detection, SMS outreach, lead qualification, "
            "and settlement tracking. 3% fee on settled claims only."
        ),
        "foundingDate": "2025",
        "sameAs": [
            "https://empire-ai.co.uk",
        ],
        "contactPoint": {
            "@type": "ContactPoint",
            "contactType": "sales",
            "email": "ops@empire-ai.co.uk",
            "url": f"{BASE_URL}/support",
            "availableLanguage": ["English"],
        },
        "address": {
            "@type": "PostalAddress",
            "addressCountry": "GB",
        },
        "slogan": "Storm Damage Leads \u00b7 3% on Settled Claims Only",
        "knowsAbout": [
            "Lead Generation",
            "Contractor Dispatch",
            "Storm Damage Detection",
            "AI-Powered Outreach",
            "Insurance Claims",
            "SMS Marketing",
        ],
    }
    return _jsonld_script(data)


# ══════════════════════════════════════════════════════════════════════════════
# PRODUCT SCHEMAS — pricing page
# ══════════════════════════════════════════════════════════════════════════════

def products_jsonld() -> str:
    """Generate Product JSON-LD for Suite products and Strike Packs (pricing page)."""
    products = []

    # Suite Products
    suite_products = [
        {
            "name": "Inbound Router",
            "description": "Traffic control & intelligent routing for inbound leads. Parse intent, score urgency, and dispatch to the right channel.",
            "url": f"{BASE_URL}/pricing#suite-products",
            "offers": {
                "@type": "Offer",
                "price": "499.00",
                "priceCurrency": "USD",
                "priceValidUntil": "2027-01-01",
            },
        },
        {
            "name": "Data Vault",
            "description": "Secure data retention & asset storage with configurable retention policies, encryption, and compliance logging.",
            "url": f"{BASE_URL}/pricing#suite-products",
            "offers": {
                "@type": "Offer",
                "price": "799.00",
                "priceCurrency": "USD",
                "priceValidUntil": "2027-01-01",
            },
        },
        {
            "name": "Buyer Spy AI",
            "description": "Network bypass & buyer intelligence. Analyze transcripts, map buyer networks, and uncover hidden buying signals.",
            "url": f"{BASE_URL}/pricing#suite-products",
            "offers": {
                "@type": "Offer",
                "price": "1499.00",
                "priceCurrency": "USD",
                "priceValidUntil": "2027-01-01",
            },
        },
    ]

    for p in suite_products:
        products.append({
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "applicationCategory": "BusinessApplication",
            "operatingSystem": "Web",
            "name": p["name"],
            "description": p["description"],
            "url": p["url"],
            "offers": p["offers"],
            "provider": {
                "@type": "Organization",
                "name": "Empire AI",
                "url": BASE_URL,
            },
        })

    # Strike Packs (as Service products)
    strike_packs = [
        {"name": "Roofing Strike",     "price": "499.00",  "lanes": 4},
        {"name": "Property Strike",    "price": "999.00",  "lanes": 8},
        {"name": "Commercial Strike",  "price": "2999.00", "lanes": 16},
        {"name": "Full Spectrum",      "price": "7999.00", "lanes": 41},
    ]

    for sp in strike_packs:
        products.append({
            "@context": "https://schema.org",
            "@type": "Service",
            "name": sp["name"],
            "description": (
                f"{sp['name']} — {sp['lanes']} lead lanes with monthly caps "
                f"and configurable delivery channels (email, SMS, voice, API)."
            ),
            "provider": {
                "@type": "Organization",
                "name": "Empire AI",
                "url": BASE_URL,
            },
            "offers": {
                "@type": "Offer",
                "price": sp["price"],
                "priceCurrency": "USD",
                "priceValidUntil": "2027-01-01",
            },
            "areaServed": {
                "@type": "Country",
                "name": "United States",
            },
        })

    # All Access bundle
    products.append({
        "@context": "https://schema.org",
        "@type": "Service",
        "name": "Empire AI All Access Bundle",
        "description": "All 3 Suite Products (Inbound Router, Data Vault, Buyer Spy AI) with priority support, custom SLA, and dedicated onboarding.",
        "provider": {
            "@type": "Organization",
            "name": "Empire AI",
            "url": BASE_URL,
        },
        "offers": {
            "@type": "Offer",
            "price": "2499.00",
            "priceCurrency": "USD",
            "priceValidUntil": "2027-01-01",
        },
        "areaServed": {
            "@type": "Country",
            "name": "United States",
        },
    })

    return "\n".join(_jsonld_script(p) for p in products)


# ══════════════════════════════════════════════════════════════════════════════
# FAQ SCHEMA — pricing page
# ══════════════════════════════════════════════════════════════════════════════

def faq_jsonld() -> str:
    """Generate FAQPage JSON-LD for the pricing page."""
    data = {
        "@context": "https://schema.org",
        "@type": "FAQPage",
        "mainEntity": [
            {
                "@type": "Question",
                "name": "How does Empire AI's 3% settlement fee work?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Empire AI charges a 3% fee only on settled insurance claims. "
                        "There are no upfront costs, no monthly minimums, and no fee if "
                        "the claim does not settle. The fee covers contractor dispatch, "
                        "AI-powered negotiation support, and compliance infrastructure."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "What is the difference between PPL and PPC lead generation?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "PPL (Pay Per Lead) delivers form-fill leads for top-of-funnel volume "
                        "at lower cost. PPC (Pay Per Call) delivers live inbound calls from "
                        "qualified prospects for bottom-of-funnel conversion at higher close rates. "
                        "Empire AI supports both models across 41 lanes in 16 verticals."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "Which verticals does Empire AI cover?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Empire AI covers 16 verticals including roofing, HVAC, plumbing, "
                        "legal (personal injury, mass tort, workers comp), insurance "
                        "(Medicare, life, final expense), financial services (debt relief, "
                        "mortgage, MCA), healthcare (addiction treatment, mental health), "
                        "senior care, education, and business services (managed IT, "
                        "merchant services, HR & staffing)."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "Can I get a free trial of Empire AI's Suite products?",
                "acceptedAnswer": {
                    "@type": "Answer",
            "text": (
                "Yes. Empire AI offers a 7-day free trial for all Suite products. "
                "No credit card required. Contact ops@empire-ai.co.uk or sign in "
                "at empire-ai.co.uk/command to activate your trial."
            ),
                },
            },
            {
                "@type": "Question",
                "name": "How are leads delivered to contractors?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "Leads are delivered via SMS, email, voice calls, API, and webhook. "
                        "Each Strike Pack includes configurable delivery channels. Contractors "
                        "can set daily/monthly caps and receive real-time notifications when "
                        "new leads are dispatched."
                    ),
                },
            },
            {
                "@type": "Question",
                "name": "What is the average cost per lead?",
                "acceptedAnswer": {
                    "@type": "Answer",
                    "text": (
                        "CPL varies by vertical and model. PPL ranges from $15 (education) "
                        "to $400+ (legal, financial). PPC ranges from $10 (HVAC) to $500 "
                        "(healthcare). Empire AI provides transparent per-vertical pricing "
                        "on the pricing page and recommends optimal models based on close "
                        "rates and ROI data."
                    ),
                },
            },
        ],
    }
    return _jsonld_script(data)


# ══════════════════════════════════════════════════════════════════════════════
# WEBPAGE SCHEMA — splash page (complements Organization)
# ══════════════════════════════════════════════════════════════════════════════

def webpage_jsonld(title: str, description: str, url: str) -> str:
    """Generate WebPage JSON-LD for any page."""
    data = {
        "@context": "https://schema.org",
        "@type": "WebPage",
        "name": title,
        "description": description,
        "url": url,
        "isPartOf": {
            "@type": "WebSite",
            "name": "Empire AI",
            "url": BASE_URL,
        },
    }
    return _jsonld_script(data)
