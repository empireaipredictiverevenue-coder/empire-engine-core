#!/usr/bin/env python3
"""
VISUAL VERIFICATION — Playwright SPA Smoke Test
=================================================
Opens /fleet, /command, and /agent-os in a real Chromium browser,
captures screenshots and console errors, and reports pass/fail.

Usage:
    python3 tests/visual_verify_pages.py
    python3 tests/visual_verify_pages.py --url http://localhost:8001 --token "$HUB_TOKEN"
    python3 tests/visual_verify_pages.py --fleet --command         # specific pages only
    python3 tests/visual_verify_pages.py --headed                   # watch the browser
    python3 tests/visual_verify_pages.py --screenshot-dir /tmp/screenshots

Requirements:
    pip install playwright
    playwright install chromium
"""

import os
import sys
import json
import time
import argparse
import logging
from pathlib import Path
from datetime import datetime

# ── Project path for imports (matching existing test convention) ──────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("visual-verify")


# ── Page definitions ─────────────────────────────────────────────────
PAGES = {
    "fleet": {
        "route": "/fleet",
        "requires_auth": True,
        "title": "Empire AI · Fleet Dashboard",
        "selector": ".agent-card, .fleet-agents, #root",
        "description": "Fleet dashboard SPA — agent cards grid",
    },
    "command": {
        "route": "/command",
        "requires_auth": True,
        "title": "Empire AI · Command",
        "selector": ".main-content, .fleet-topbar, #root, .main",
        "description": "Command deck SPA — operator console",
    },
    "agent-os": {
        "route": "/agent-os",
        "requires_auth": False,
        "title": "Agent OS · Empire AI",
        "selector": ".header",
        "description": "Agent OS kernel page — public visualization",
    },
}

# ── Console error filters ────────────────────────────────────────────
# Ignored patterns: benign errors that occur during normal page load
IGNORED_CONSOLE_PATTERNS = [
    "favicon.ico",
    "Failed to load resource: the server responded with a status of 404",
    "net::ERR_NAME_NOT_RESOLVED",
    "net::ERR_CONNECTION_REFUSED",
    "third-party cookie",
    "third-party context",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Visual verification of Empire AI SPA pages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  %(prog)s\n"
            "  %(prog)s --url http://localhost:8001 --token $HUB_TOKEN\n"
            "  %(prog)s --fleet --agent-os\n"
            "  %(prog)s --headed --screenshot-dir /tmp/screenshots\n"
        ),
    )
    parser.add_argument(
        "--url",
        default=os.environ.get("HUB_URL", "http://localhost:8001"),
        help="Base URL of the hub (default: $HUB_URL or http://localhost:8001)",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HUB_TOKEN", ""),
        help="Auth token for protected pages (default: $HUB_TOKEN)",
    )
    parser.add_argument(
        "--screenshot-dir",
        default=os.environ.get("SCREENSHOT_DIR", ""),
        help="Directory for screenshots (default: screenshots/<timestamp>/ in project root)",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run with visible browser window",
    )
    parser.add_argument(
        "--slow-mo",
        type=int,
        default=0,
        help="Slow down Playwright by N milliseconds",
    )

    # Per-page flags — default all
    for name in PAGES:
        parser.add_argument(
            f"--{name}",
            action="store_true",
            dest=f"do_{name}",
            help=f"Test /{name} page",
        )

    args = parser.parse_args()

    # If no specific page flags, default to all
    any_set = any(getattr(args, f"do_{name}") for name in PAGES)
    if not any_set:
        for name in PAGES:
            setattr(args, f"do_{name}", True)

    # Screenshot dir default
    if not args.screenshot_dir:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.screenshot_dir = os.path.join(PROJECT_ROOT, "screenshots", ts)

    return args


def should_ignore(error_text: str) -> bool:
    """Return True if a console error is benign and should not fail the test."""
    error_lower = error_text.lower()
    return any(p.lower() in error_lower for p in IGNORED_CONSOLE_PATTERNS)


async def verify_page(
    page,
    name: str,
    config: dict,
    base_url: str,
    args: argparse.Namespace,
) -> dict:
    """Navigate to a single page, capture results, return a result dict."""
    url = f"{base_url.rstrip('/')}{config['route']}"
    log.info("━━━ %s ━━━  %s", name.upper(), url)

    result = {
        "page": name,
        "url": url,
        "status": "pending",
        "console_errors": [],
        "screenshot_path": None,
        "js_errors": [],
        "duration_ms": 0,
        "error": None,
    }

    start = time.monotonic()

    try:
        # ── Navigate ──────────────────────────────────────────────
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        status_code = response.status if response else 0
        result["status_code"] = status_code

        # ── Wait for render ───────────────────────────────────────
        try:
            await page.wait_for_selector(config["selector"], timeout=15000)
            log.info("  ✓ Selector '%s' found", config["selector"])
        except Exception:
            log.warning("  ⚠ Selector '%s' not found (page may be loading)", config["selector"])

        # Allow JS rendering to settle
        await page.wait_for_timeout(2000)

        # ── Collect JS errors from page's accumulated logs ────────
        try:
            js_errors_js = await page.evaluate("""() => {
                const errors = window.__playwright_errors || [];
                return errors.slice(0, 20);
            }""")
            result["js_errors"] = js_errors_js or []
        except Exception:
            pass

        # ── Screenshot ────────────────────────────────────────────
        screenshot_dir = Path(args.screenshot_dir)
        screenshot_dir.mkdir(parents=True, exist_ok=True)
        screenshot_path = screenshot_dir / f"{name}.png"
        await page.screenshot(path=str(screenshot_path), full_page=True)
        result["screenshot_path"] = str(screenshot_path)
        log.info("  ✓ Screenshot saved to %s", screenshot_path)

        # ── Page title check ───────────────────────────────────────
        actual_title = await page.title()
        if config["title"].lower() in actual_title.lower():
            log.info("  ✓ Title contains '%s'", config["title"])
        else:
            log.warning("  ⚠ Title mismatch: expected '%s', got '%s'",
                        config["title"], actual_title)

        # ── Status ────────────────────────────────────────────────
        result["title"] = actual_title
        result["duration_ms"] = int((time.monotonic() - start) * 1000)

        if status_code >= 400:
            result["status"] = "http_error"
            result["error"] = f"HTTP {status_code}"
            log.error("  ✗ HTTP %s", status_code)
        else:
            result["status"] = "pass"
            log.info("  ✓ OK  (%d ms)", result["duration_ms"])

    except Exception as e:
        result["status"] = "error"
        result["error"] = str(e)
        result["duration_ms"] = int((time.monotonic() - start) * 1000)
        log.error("  ✗ %s", e)

    return result


# ── Playwright import guard (helpful error if not installed) ──────
try:
    from playwright.async_api import async_playwright
except ImportError:
    log.error("Playwright not installed. Run: pip install playwright && playwright install chromium")
    sys.exit(1)


async def main():
    args = parse_args()
    log.info("Visual verification started")
    log.info("  URL:          %s", args.url)
    log.info("  Token:        %s", "✓ set" if args.token else "✗ not set")
    log.info("  Screenshots:  %s", args.screenshot_dir)
    log.info("  Pages:        %s",
             ", ".join(n for n in PAGES if getattr(args, f"do_{n}")))

    results = []
    pages_tested = [n for n in PAGES if getattr(args, f"do_{n}")]

    # Check auth for protected pages
    protected = [n for n in pages_tested if PAGES[n]["requires_auth"]]
    if protected and not args.token:
        log.warning("  ⚠ Protected pages (%s) need --token or $HUB_TOKEN", ", ".join(protected))
        log.warning("  → Skipping auth pages; only /agent-os (public) will be tested")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=not args.headed,
            slow_mo=args.slow_mo,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu",
            ],
        )
        context = await browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36"
            ),
            ignore_https_errors=True,
        )

        # ── Set up console error capture ──────────────────────────────
        console_errors = []

        def on_console(msg):
            if msg.type == "error":
                text = msg.text
                if not should_ignore(text):
                    console_errors.append(text)
                    log.warning("  ⚠ Console error: %s", text[:160])
            elif msg.type == "warning":
                log.debug("  Console warn: %s", msg.text[:120])

        context.on("console", on_console)

        # ── Inject auth token before page scripts run ─────────────────
        import json
        if args.token:
            safe_token = json.dumps(args.token)
            await context.add_init_script(
                f"localStorage.setItem('hub_token', {safe_token});"
            )
            log.debug("  Token injection registered via init_script")

        # ── Set up JS error capture (via page evaluate on each nav) ───
        # Inject error collector before each page load
        init_script = """
        (function() {
            window.__playwright_errors = [];
            window.addEventListener('error', function(e) {
                if (window.__playwright_errors.length < 20) {
                    window.__playwright_errors.push({
                        message: e.message || String(e),
                        filename: e.filename || '',
                        lineno: e.lineno || 0,
                        colno: e.colno || 0,
                    });
                }
            });
            // Capture unhandled promise rejections
            window.addEventListener('unhandledrejection', function(e) {
                if (window.__playwright_errors.length < 20) {
                    window.__playwright_errors.push({
                        message: 'Unhandled rejection: ' + (e.reason?.message || String(e.reason)),
                        filename: '',
                        lineno: 0,
                        colno: 0,
                    });
                }
            });
        })();
        """
        await context.add_init_script(init_script)

        page = await context.new_page()

        for page_name in pages_tested:
            config = PAGES[page_name]
            protected_test = config["requires_auth"] and not args.token

            if protected_test:
                log.info("━━━ %s ━━━  skipped (no token)", page_name.upper())
                results.append({
                    "page": page_name,
                    "status": "skipped",
                    "error": "no auth token provided",
                })
                continue

            result = await verify_page(page, page_name, config, args.url, args)
            page_errors = list(console_errors)
            console_errors.clear()
            result["console_errors_during"] = page_errors
            results.append(result)

        await browser.close()

    # ── Summary ───────────────────────────────────────────────────────
    log.info("")
    log.info("══════════════════════  RESULTS  ══════════════════════")
    passed = sum(1 for r in results if r["status"] == "pass")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"] != "pass" and r["status"] != "skipped")

    for r in results:
        status_icon = {"pass": "✓", "skipped": "—", "error": "✗", "http_error": "✗"}.get(r["status"], "?")
        duration = f"{r.get('duration_ms', 0)} ms" if r.get("duration_ms") else ""
        err = f"  {r.get('error', '')}" if r.get("error") else ""
        console_count = len(r.get("console_errors_during", []))
        console_note = f"  ({console_count} console errors)" if console_count else ""
        js_err_count = len(r.get("js_errors", []))
        js_note = f"  ({js_err_count} JS errors)" if js_err_count else ""
        log.info("  %s  %s  %s%s%s%s",
                 status_icon,
                 r["page"].ljust(10),
                 r["status"].ljust(12),
                 duration,
                 console_note,
                 js_note)

    log.info("")
    log.info("  Passed: %d  |  Skipped: %d  |  Failed: %d",
             passed, skipped, failed)
    log.info("  Screenshots: %s", args.screenshot_dir)
    log.info("")

    # Print detailed console errors if any
    for r in results:
        console_errs = r.get("console_errors_during", [])
        if console_errs:
            log.info("Console errors for /%s:", r["page"])
            for err in console_errs[:10]:
                log.info("  • %s", err[:200])
            if len(console_errs) > 10:
                log.info("  … and %d more", len(console_errs) - 10)

    sys.exit(0 if failed == 0 else 1)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
