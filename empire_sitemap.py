"""
EMPIRE V49 · SITEMAP GENERATOR
===============================
Generates a standard XML sitemap for all 15 public-facing pages on empire-ai.co.uk.
Includes lastmod, changefreq, and priority metadata per page.

Usage:
    from empire_sitemap import generate_sitemap
    xml = generate_sitemap()  # returns XML string

Also provides a robots.txt generator that points to the sitemap.
"""
from datetime import datetime, timezone

BASE_URL = "https://empire-ai.co.uk"

# ── All 15 public pages ───────────────────────────────────────────────
PAGES = [
    # Core pages
    {"path": "/",                       "changefreq": "daily",   "priority": "1.0"},
    {"path": "/pricing",                "changefreq": "weekly",  "priority": "0.9"},
    {"path": "/demo",                   "changefreq": "monthly", "priority": "0.8"},
    # Product pages
    {"path": "/ppc",                    "changefreq": "weekly",  "priority": "0.9"},
    {"path": "/ppl",                    "changefreq": "weekly",  "priority": "0.9"},
    {"path": "/mrr",                    "changefreq": "daily",   "priority": "0.8"},
    {"path": "/products/meetily",       "changefreq": "weekly",  "priority": "0.8"},
    {"path": "/products/elite-scraper", "changefreq": "weekly",  "priority": "0.8"},
    # Operational pages
    {"path": "/support",                "changefreq": "monthly", "priority": "0.7"},
    {"path": "/command",                "changefreq": "daily",   "priority": "0.9"},
    {"path": "/fleet",                  "changefreq": "daily",   "priority": "0.8"},
    {"path": "/agent-os",               "changefreq": "daily",   "priority": "0.8"},
    {"path": "/cold-inbound",           "changefreq": "daily",   "priority": "0.7"},
    # Extras
    {"path": "/carrier/enroll",         "changefreq": "monthly", "priority": "0.6"},
    # B2B
    {"path": "/b2b",                   "changefreq": "daily",   "priority": "0.8"},
]


def generate_sitemap(lastmod: str = None) -> str:
    """Generate XML sitemap for all 15 public pages.

    Args:
        lastmod: ISO date string for <lastmod> (defaults to today)

    Returns:
        Full XML sitemap string
    """
    if lastmod is None:
        lastmod = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    urls = []
    for page in PAGES:
        loc = f"{BASE_URL}{page['path']}"
        urls.append(
            "  <url>\n"
            f"    <loc>{loc}</loc>\n"
            f"    <lastmod>{lastmod}</lastmod>\n"
            f"    <changefreq>{page['changefreq']}</changefreq>\n"
            f"    <priority>{page['priority']}</priority>\n"
            "  </url>"
        )

    urls_xml = "\n".join(urls)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        f"{urls_xml}\n"
        "</urlset>\n"
    )


def generate_robots_txt() -> str:
    """Generate robots.txt pointing to the sitemap."""
    return (
        "User-agent: *\n"
        "Allow: /\n\n"
        f"Sitemap: {BASE_URL}/sitemap.xml\n"
    )


def get_page_count() -> int:
    """Return the number of pages in the sitemap."""
    return len(PAGES)


def list_pages() -> list:
    """Return the list of pages for inspection."""
    return [{"url": f"{BASE_URL}{p['path']}", **p} for p in PAGES]
