#!/usr/bin/env python3
"""
Submit Empire AI sitemap to Google for indexing.

Two methods (tried in order):
  1. Manual Google Search Console submission (most reliable — paste sitemap URL)
  2. Google Ping (legacy/deprecated — may or may not work)
  NOTE: Indexing API only works for JobPosting/BroadcastEvent pages, not general web.

Usage:
    python3 scripts/submit_sitemap_gsc.py           # submit all 14 pages
    python3 scripts/submit_sitemap_gsc.py --dry-run  # show what would be submitted
    python3 scripts/submit_sitemap_gsc.py --ping-only # only do the Google ping
"""
import os
import sys
import argparse
import logging
from pathlib import Path
from urllib.parse import quote

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from dotenv import load_dotenv
load_dotenv("/root/.env")

log = logging.getLogger("gsc_submit")

SITEMAP_URL = "https://empire-ai.co.uk/sitemap.xml"
GOOGLE_PING_URL = "https://www.google.com/ping"
INDEXING_API_URL = "https://indexing.googleapis.com/v3/urlNotifications:publish"


def ping_google(sitemap_url: str = SITEMAP_URL) -> bool:
    """Ping Google's public sitemap submission endpoint.

    This doesn't require auth — Google discovers the sitemap via ping.
    Works for any sitemap, but is less reliable than GSC submission.
    """
    try:
        import httpx
        ping_url = f"{GOOGLE_PING_URL}?sitemap={quote(sitemap_url, safe='')}"
        resp = httpx.get(ping_url, timeout=httpx.Timeout(10.0))
        if resp.status_code < 400:
            log.info(f"Google ping OK: {resp.status_code} — {sitemap_url}")
            return True
        else:
            log.warning(f"Google ping returned {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        log.warning(f"Google ping failed: {e}")
        return False


def submit_via_indexing_api(sitemap_url: str = SITEMAP_URL) -> bool:
    """Submit via Google Indexing API (requires service account + API key).

    Notifies Google to crawl each URL defined in the sitemap.
    Requires GOOGLE_INDEXING_API_KEY in environment.
    """
    api_key = os.environ.get("GOOGLE_INDEXING_API_KEY", "")
    if not api_key:
        log.warning("GOOGLE_INDEXING_API_KEY not set — skipping Indexing API")
        return False

    try:
        from empire_sitemap import PAGES, BASE_URL
        import httpx

        headers = {
            "Content-Type": "application/json",
        }
        submitted = 0
        for page in PAGES:
            url = f"{BASE_URL}{page['path']}"
            body = {
                "url": url,
                "type": "URL_UPDATED",
            }
            try:
                resp = httpx.post(
                    f"{INDEXING_API_URL}?key={api_key}",
                    json=body,
                    headers=headers,
                    timeout=httpx.Timeout(10.0),
                )
                if resp.status_code < 400:
                    submitted += 1
                    log.info(f"  Indexed: {url}")
                else:
                    log.warning(f"  Failed ({resp.status_code}): {url} — {resp.text[:150]}")
            except Exception as e:
                log.warning(f"  Error: {url} — {e}")

        log.info(f"Indexing API: {submitted}/{len(PAGES)} URLs submitted")
        return submitted > 0
    except ImportError:
        log.warning("httpx not available for Indexing API")
        return False


def print_manual_instructions():
    """Print manual submission steps for Google Search Console."""
    log.info("=" * 60)
    log.info("MANUAL GOOGLE SEARCH CONSOLE SUBMISSION")
    log.info("=" * 60)
    log.info("1. Go to https://search.google.com/search-console")
    log.info("2. Select property: empire-ai.co.uk")
    log.info("3. Navigate to: Indexing > Sitemaps")
    log.info(f"4. Paste sitemap URL: {SITEMAP_URL}")
    log.info("5. Click 'Submit'")
    log.info("")
    log.info("Alternatively, use Google's public ping:")
    log.info(f"  curl '{GOOGLE_PING_URL}?sitemap={quote(SITEMAP_URL, safe='')}'")
    log.info("")
    log.info(f"Sitemap live at: {SITEMAP_URL}")
    log.info("Verify: curl -s https://empire-ai.co.uk/sitemap.xml")
    log.info("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Submit Empire AI sitemap to Google")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would be submitted without actually pinging Google")
    parser.add_argument("--ping-only", action="store_true",
                        help="Only run the Google ping (skip Indexing API + manual instructions)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

    from empire_sitemap import list_pages, get_page_count

    log.info(f"Sitemap: {get_page_count()} pages at {SITEMAP_URL}")
    log.info("Pages:")
    for p in list_pages():
        log.info(f"  {p['priority']}  {p['changefreq']:8s}  {p['url']}")

    if args.dry_run:
        log.info("\nDRY RUN — not submitting to Google.")
        log.info(f"To submit manually, paste {SITEMAP_URL} into Google Search Console.")
        return

    # ── Method 1: Indexing API (best, requires API key) ──
    api_ok = submit_via_indexing_api()

    # ── Method 2: Google Ping (works without auth) ──
    ping_ok = ping_google()

    # ── Method 3: Manual instructions ──
    if not args.ping_only:
        print_manual_instructions()

    if ping_ok or api_ok:
        log.info("\n✅ Sitemap submitted to Google — pages should be indexed within 1-7 days.")
    else:
        log.info("\n⚠ Could not auto-submit — follow manual instructions above.")


if __name__ == "__main__":
    main()
