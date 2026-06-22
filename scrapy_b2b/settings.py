"""
Scrapy settings for B2B lead enrichment (BBB, Yelp, Google Business).

Polite by default: 3-5s delays, rotating user agents, proxy support from
scrapers_v2/proxy_support.py, circuit breaker from scrapers_v2/circuit_breaker.py.
"""

import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

BOT_NAME = "empire_b2b_enricher"
SPIDER_MODULES = ["scrapy_b2b.spiders"]
NEWSPIDER_MODULE = "scrapy_b2b.spiders"

# ── Politeness ──────────────────────────────────────────────────────────
ROBOTSTXT_OBEY = False  # BBB/Yelp/Google block crawlers; we manually rate-limit
CONCURRENT_REQUESTS = 1  # One domain at a time = polite
CONCURRENT_REQUESTS_PER_DOMAIN = 1
CONCURRENT_REQUESTS_PER_IP = 1
DOWNLOAD_DELAY = 4       # 4 seconds between requests (polite)
RANDOMIZE_DOWNLOAD_DELAY = True
DOWNLOAD_TIMEOUT = 30

# ── Retry + error handling ─────────────────────────────────────────────
RETRY_ENABLED = True
RETRY_TIMES = 2
RETRY_HTTP_CODES = [403, 429, 500, 502, 503, 504]
DOWNLOADER_MIDDLEWARES = {
    # Camofox-browser transport (high priority — intercepts all HTTP requests)
    "scrapy_b2b.camofox_middleware.CamofoxDownloaderMiddleware": 50,
    # Standard middleware chain (only used when camofox is disabled)
    "scrapy.downloadermiddlewares.retry.RetryMiddleware": 500,
    "scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware": 750,
    "scrapy_b2b.middlewares.RotatingUserAgentMiddleware": 400,
    "scrapy_b2b.middlewares.ProxyMiddleware": 410,
}

# ── Camofox-browser transport (JS rendering + anti-bot) ─────────────────
# When True, ALL requests go through camofox-browser instead of raw HTTP.
# Required for BBB, Yelp, and Google Maps (all three block raw HTTP scrapers).
# Without this, spiders will silently return zero results.
CAMOFOX_ENABLED = True
CAMOFOX_URL = os.environ.get("CAMOFOX_URL", "http://localhost:9377")

# ── Pipelines ───────────────────────────────────────────────────────────
ITEM_PIPELINES = {
    "scrapy_b2b.pipelines.B2BEnrichmentPipeline": 300,
}

# ── User agents (rotated by middleware) ─────────────────────────────────
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:127.0) Gecko/20100101 Firefox/127.0",
]

# ── Proxy pool (from scrapers_v2/proxy_support.py if available) ────────
PROXY_ENABLED = os.environ.get("SCRAPER_PROXY_ENABLED", "0") == "1"
PROXY_LIST = []  # populated by middleware if PROXY_ENABLED

# ── Cookie / session ────────────────────────────────────────────────────
COOKIES_ENABLED = False  # Fresh session each request
DEFAULT_REQUEST_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "DNT": "1",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
}

# ── Logging ─────────────────────────────────────────────────────────────
LOG_LEVEL = "INFO"
LOG_FILE = "logs/scrapy_b2b.log"
LOG_STDOUT = False

# ── Feed exports ────────────────────────────────────────────────────────
FEED_EXPORT_ENCODING = "utf-8"
FEED_FORMAT = "jsonlines"
FEED_URI = "logs/scrapy_b2b_results.jl"

# ── Autothrottle (graceful backpressure) ────────────────────────────────
AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 4
AUTOTHROTTLE_MAX_DELAY = 15
AUTOTHROTTLE_TARGET_CONCURRENCY = 1.0
AUTOTHROTTLE_DEBUG = False

# ── Memory / performance ────────────────────────────────────────────────
MEMUSAGE_ENABLED = True
MEMUSAGE_LIMIT_MB = 512
REACTOR_THREADPOOL_MAXSIZE = 20
