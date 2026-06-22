"""
Crawlee-based B2B website scraper — service pages, pricing, contact forms.

Uses Crawlee's PlaywrightCrawler for JavaScript-rendered page extraction.
Extracts clean text, headings, pricing mentions, and CTA buttons from
each B2B lead's website. Feeds the STORM copywriting engine.

Architecture:
  - PlaywrightCrawler with built-in request queue + auto-scaling
  - Text cleaned via native text extraction (strips nav, scripts, boilerplate)
  - Page type classification: homepage, services, pricing, contact, about
  - Pricing regex extraction: "$X/mo", "starting at $X", "from $X"
  - CTA button detection: "Get a quote", "Contact us", "Free demo", etc.
  - Stores results via crawlee_b2b.pipeline.SiteContentPipeline

Config:
  max_concurrency: 3 (polite — don't hammer 775 sites)
  max_requests_per_crawl: 3 per site (homepage + services + contact)
  navigation_timeout: 30s
"""
import re
import asyncio
import logging
from typing import List, Optional
from urllib.parse import urljoin, urlparse

from crawlee.playwright_crawler import PlaywrightCrawler, PlaywrightCrawlingContext
from crawlee.router import Router
from crawlee.request import Request

log = logging.getLogger("crawlee_b2b.scraper")

# ── Page type detection ─────────────────────────────────────────────────
PAGE_TYPE_PATTERNS = {
    "pricing": [
        r"/pricing", r"/plans", r"/packages", r"/rates", r"/quote",
        r"/cost", r"/fee", r"price", r"buy-now",
    ],
    "services": [
        r"/services?", r"/solutions?", r"/products?", r"/offerings?",
        r"/what-we-do", r"/capabilities", r"/expertise",
    ],
    "contact": [
        r"/contact", r"/get-in-touch", r"/reach-us", r"/location",
        r"/support", r"/help", r"/request",
    ],
    "about": [
        r"/about", r"/team", r"/company", r"/who-we-are",
        r"/story", r"/mission", r"/careers",
    ],
}


def classify_page_type(url: str) -> str:
    """Classify a page URL into a content type based on path patterns."""
    path = urlparse(url).path.lower().rstrip("/")
    for ptype, patterns in PAGE_TYPE_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, path):
                return ptype
    return "homepage"


# ── Pricing extraction regex ────────────────────────────────────────────
PRICING_RE = re.compile(
    r'(?P<prefix>(?:starting\s+at|from|as\s+low\s+as|just|only)?\s*)'
    r'(?P<currency>[\$\€\£])'
    r'(?P<amount>[\d,]+(?:\.\d{2})?)'
    r'\s*(?:/|per\s+)?(?P<period>mo|month|yr|year|one.?time|user|seat|license)?',
    re.IGNORECASE,
)

CTA_BUTTONS = re.compile(
    r'(?:<button[^>]*>|<a[^>]*class="[^"]*btn[^"]*"[^>]*>|'
    r'<a[^>]*href="[^"]*(?:contact|demo|signup|register|pricing|quote)[^"]*"[^>]*>)'
    r'\s*([A-Za-z][A-Za-z\s&!\-]{2,40})\s*</(?:button|a)>',
    re.IGNORECASE,
)


# ── Router ──────────────────────────────────────────────────────────────
router = Router[PlaywrightCrawlingContext]()


@router.default_handler
async def default_handler(context: PlaywrightCrawlingContext) -> None:
    """Handle each page: extract text, classify type, enqueue internal links."""
    url = context.request.loaded_url or context.request.url
    page = context.page
    title = await page.title()

    # Wait for content to settle
    try:
        await page.wait_for_load_state("networkidle", timeout=10000)
    except Exception:
        pass  # continue even if networkidle times out

    # ── Classify page type ──
    page_type = classify_page_type(url)

    # ── Extract raw text (clean — no scripts, styles, nav) ──
    try:
        # Get visible text from the main content area
        body_text = await page.evaluate("""() => {
            // Remove script, style, nav, footer, header elements from text
            const clone = document.body.cloneNode(true);
            const remove = clone.querySelectorAll(
                'script, style, nav, footer, header, noscript, iframe, svg'
            );
            remove.forEach(el => el.remove());
            return clone.innerText || '';
        }""")
    except Exception:
        body_text = ""

    # ── Clean text ──
    cleaned = _clean_text(body_text)
    word_count = len(cleaned.split())

    # ── Extract headings ──
    try:
        headings = await page.evaluate("""() => {
            return Array.from(document.querySelectorAll('h1, h2'))
                .map(h => h.innerText.trim())
                .filter(t => t.length > 0)
                .slice(0, 15);
        }""")
    except Exception:
        headings = []

    # ── Meta description ──
    try:
        meta_desc = await page.evaluate(
            """() => {
                const m = document.querySelector('meta[name="description"]');
                return m ? m.getAttribute('content') : '';
            }"""
        )
    except Exception:
        meta_desc = ""

    # ── Pricing mentions ──
    pricing = []
    for m in PRICING_RE.finditer(cleaned):
        pricing.append({
            "text": m.group(0).strip(),
            "amount": m.group("amount"),
            "currency": m.group("currency"),
            "period": m.group("period") or "",
        })
        if len(pricing) >= 10:
            break

    # ── CTA buttons ──
    cta_buttons = []
    try:
        buttons = await page.evaluate("""() => {
            const btns = document.querySelectorAll(
                'a[href*="contact"], a[href*="demo"], a[href*="signup"], ' +
                'a[href*="pricing"], a[href*="quote"], a[href*="get-started"], ' +
                'button, a.btn, a.button, a[role="button"]'
            );
            return Array.from(btns).map(b => ({
                text: b.innerText.trim().slice(0, 80),
                link: b.href || '',
            })).filter(b => b.text.length > 1 && b.text.length < 80).slice(0, 10);
        }""")
        cta_buttons = buttons or []
    except Exception:
        pass

    # ── Contact info ──
    contact_info = {}
    email_match = re.search(r'[\w.+-]+@[\w-]+\.[\w.-]+', cleaned)
    if email_match:
        contact_info["email"] = email_match.group(0)
    phone_match = re.search(r'(?:\+1[-\s]?)?\(?\d{3}\)?[-\s]?\d{3}[-\s]?\d{4}', cleaned)
    if phone_match:
        contact_info["phone"] = phone_match.group(0)
    form_match = re.search(r'(?:href|action)="([^"]*(?:contact|form|inquiry)[^"]*)"', body_text)
    if form_match:
        contact_info["form_url"] = urljoin(url, form_match.group(1))

    # ── Push to dataset ──
    lead_id = context.request.user_data.get("lead_id", "")
    lead_website = context.request.user_data.get("website", "")

    await context.push_data({
        "b2b_lead_id": lead_id,
        "company_name": context.request.user_data.get("company_name", ""),
        "website": lead_website,
        "page_url": url,
        "page_type": page_type,
        "title": title,
        "meta_desc": meta_desc,
        "headings": headings,
        "raw_text": cleaned,
        "word_count": word_count,
        "pricing_mentions": pricing,
        "cta_buttons": cta_buttons,
        "contact_info": contact_info,
    })

    # ── Enqueue internal links for deeper crawling ──
    if page_type == "homepage":
        # From homepage, follow links to services, pricing, contact
        links = await page.evaluate("""() => {
            const targets = ['/services', '/service', '/solutions', '/pricing',
                '/contact', '/about', '/products', '/plans', '/offerings'];
            return Array.from(document.querySelectorAll('a[href]'))
                .map(a => a.href)
                .filter(h => {
                    try {
                        const p = new URL(h).pathname.toLowerCase();
                        return targets.some(t => p.includes(t)) && !p.includes('/blog/');
                    } catch { return false; }
                })
                .slice(0, 5);
        }""")

        for link in (links or []):
            await context.add_requests([
                Request.from_url(link, user_data={
                    "lead_id": lead_id,
                    "website": lead_website,
                    "company_name": context.request.user_data.get("company_name", ""),
                }),
            ])


def _clean_text(text: str) -> str:
    """Clean extracted text: collapse whitespace, remove boilerplate."""
    if not text:
        return ""
    # Collapse whitespace
    text = re.sub(r'[ \t]+', ' ', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    # Remove lines that are clearly nav/boilerplate
    lines = text.split('\n')
    cleaned_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # Skip very short lines (< 10 chars) that aren't headings
        if len(stripped) < 10 and not stripped.isupper():
            continue
        # Skip cookie/privacy consent boilerplate
        if re.search(r'(cookie|privacy|gdpr|ccpa|consent|opt.out|unsubscribe)', stripped, re.I):
            continue
        cleaned_lines.append(stripped)
    return '\n'.join(cleaned_lines)


async def crawl_site(
    website: str,
    lead_id: str,
    company_name: str,
    max_pages: int = 3,
    max_concurrency: int = 1,
) -> List[dict]:
    """Crawl a single B2B lead's website.

    Args:
        website: Full URL (e.g. https://example.com)
        lead_id: UUID from b2b_leads
        company_name: Business name
        max_pages: Max pages to crawl per site (default 3)
        max_concurrency: Max concurrent pages for this crawl

    Returns:
        List of page data dicts extracted by the router
    """
    if not website.startswith("http"):
        website = f"https://{website}"

    crawler = PlaywrightCrawler(
        router=router,
        max_requests_per_crawl=max_pages,
        max_concurrency=max_concurrency,
        request_handler_timeout_secs=45,
        headless=True,
    )

    await crawler.run([
        Request.from_url(website, user_data={
            "lead_id": lead_id,
            "website": website,
            "company_name": company_name,
        }),
    ])

    # Collect results from dataset (API varies by Crawlee version)
    data = await crawler.get_data()
    if isinstance(data, list):
        return data
    if hasattr(data, 'items'):
        items = data.items
        return list(items) if not callable(items) else []
    return []
