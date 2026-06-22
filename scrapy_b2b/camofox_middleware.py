"""
Camofox-browser Scrapy downloader middleware.

Routes ALL spider requests through camofox-browser (localhost:9377) instead
of raw HTTP. This solves the anti-bot problem for BBB, Yelp, and Google Maps
— all three sites require JS rendering that plain Scrapy can't provide.

Each request:
  1. Creates a tab in camofox-browser
  2. Navigates to the URL
  3. Waits for networkidle (10s timeout)
  4. Fetches the a11y snapshot (text representation of rendered page)
  5. Returns a Scrapy HtmlResponse with the snapshot as body

Activated by settings.CAMOFOX_ENABLED = True (off by default for testing).
Uses sync httpx (acceptable since Scrapy runs single-threaded with polite delays).
"""
import json
import logging

import httpx
from scrapy import signals
from scrapy.http import HtmlResponse

log = logging.getLogger("scrapy_b2b.camofox")

DEFAULT_CAMOFOX_URL = "http://localhost:9377"
USER_ID = "empire-scrapy"
WAIT_CONDITION = "networkidle"
WAIT_TIMEOUT_MS = 10000


class CamofoxDownloaderMiddleware:
    """Replace Scrapy's HTTP downloader with camofox-browser rendering.

    Every request is sent through camofox-browser instead of the default
    HTTP downloader. The response body is the a11y snapshot text (which
    includes all visible text, links, and metadata from the rendered page).

    Must be placed at a high priority (e.g. 50) in DOWNLOADER_MIDDLEWARES
    to intercept before the default downloader.
    """

    def __init__(self, camofox_url: str = DEFAULT_CAMOFOX_URL, enabled: bool = True):
        self.camofox_url = camofox_url.rstrip("/")
        self.enabled = enabled
        self._client = None
        log.info(f"[camofox] Middleware initialized, target: {camofox_url}, enabled: {enabled}")

    @classmethod
    def from_crawler(cls, crawler):
        url = crawler.settings.get("CAMOFOX_URL", DEFAULT_CAMOFOX_URL)
        enabled = crawler.settings.getbool("CAMOFOX_ENABLED", True)
        mw = cls(camofox_url=url, enabled=enabled)
        crawler.signals.connect(mw.spider_closed, signal=signals.spider_closed)
        return mw

    def spider_closed(self, spider):
        log.info("[camofox] Middleware shutdown")

    @property
    def client(self):
        """Lazy httpx client."""
        if self._client is None:
            self._client = httpx.Client(timeout=30.0)
        return self._client

    def process_request(self, request, spider):
        """Intercept requests and route through camofox-browser when enabled."""
        # Pass through when camofox is disabled (use default HTTP downloader)
        if not self.enabled:
            return None
        # Skip non-HTTP requests
        if not request.url.startswith("http"):
            return None

        url = request.url
        spider.logger.debug(f"[camofox] Processing: {url[:100]}")

        try:
            # Create tab
            tab = self._create_tab()
            tab_id = tab.get("id") or tab.get("tabId")
            if not tab_id:
                spider.logger.warning("[camofox] create_tab returned no id")
                return self._fallback_response(url, request, "no tab id")

            # Navigate
            nav_ok = self._navigate(tab_id, url)
            if not nav_ok:
                self._close_tab(tab_id)
                spider.logger.warning(f"[camofox] navigate failed for {url[:100]}")
                return self._fallback_response(url, request, "navigate failed")

            # Wait for page load
            try:
                self.client.post(
                    f"{self.camofox_url}/tabs/{tab_id}/wait",
                    json={
                        "userId": USER_ID,
                        "condition": WAIT_CONDITION,
                        "timeoutMs": WAIT_TIMEOUT_MS,
                    },
                )
            except Exception:
                pass  # wait timeout is non-fatal

            # Get page content: try raw HTML first (spiders parse HTML regex),
            # fall back to a11y snapshot if HTML endpoint unavailable.
            body = self._get_html(tab_id)
            if body is None:
                body = self._get_snapshot(tab_id)

            # Clean up tab
            self._close_tab(tab_id)

            if body is None:
                spider.logger.warning(f"[camofox] both html and snapshot empty for {url[:100]}")
                return self._fallback_response(url, request, "empty response")

            # Build Scrapy HtmlResponse from camofox snapshot
            spider.logger.debug(f"[camofox] Got {len(body)} chars for {url[:80]}")
            return HtmlResponse(
                url=url,
                status=200,
                body=body.encode("utf-8"),
                request=request,
                encoding="utf-8",
            )

        except Exception as e:
            spider.logger.error(f"[camofox] Error processing {url[:100]}: {e}")
            return self._fallback_response(url, request, str(e)[:100])

    def _create_tab(self) -> dict:
        """Create a new tab in camofox-browser."""
        resp = self.client.post(
            f"{self.camofox_url}/tabs",
            json={"userId": USER_ID},
        )
        if resp.status_code >= 400:
            log.warning(f"[camofox] create_tab failed: {resp.status_code} {resp.text[:200]}")
            return {}
        try:
            return resp.json()
        except json.JSONDecodeError:
            return {}

    def _navigate(self, tab_id: str, url: str) -> bool:
        """Navigate a tab to a URL. Returns True on success."""
        resp = self.client.post(
            f"{self.camofox_url}/tabs/{tab_id}/navigate",
            json={"userId": USER_ID, "url": url},
        )
        return resp.status_code < 400

    def _get_html(self, tab_id: str) -> str | None:
        """Get raw rendered HTML from camofox tab. Returns text or None."""
        try:
            resp = self.client.get(
                f"{self.camofox_url}/tabs/{tab_id}/html",
                params={"userId": USER_ID},
            )
            if resp.status_code >= 400:
                return None
            return resp.text
        except Exception:
            return None

    def _get_snapshot(self, tab_id: str) -> str | None:
        """Get a11y snapshot from camofox tab. Fallback when /html unavailable."""
        try:
            resp = self.client.get(
                f"{self.camofox_url}/tabs/{tab_id}/snapshot",
                params={"userId": USER_ID},
            )
            if resp.status_code >= 400:
                return None
            return resp.text
        except Exception:
            return None

    def _close_tab(self, tab_id: str):
        """Close a camofox tab (best-effort)."""
        try:
            self.client.request(
                "DELETE",
                f"{self.camofox_url}/tabs/{tab_id}",
                json={"userId": USER_ID},
            )
        except Exception:
            pass

    def _fallback_response(self, url, request, reason: str) -> HtmlResponse:
        """Return a minimal response when camofox fails."""
        log.warning(f"[camofox] Fallback: {reason} — url={url[:100]}")
        return HtmlResponse(
            url=url,
            status=200,
            body=b"<html><body></body></html>",
            request=request,
            encoding="utf-8",
        )
