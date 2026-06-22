"""
Custom Scrapy middlewares for B2B enrichment:
  - RotatingUserAgentMiddleware: Cycles through USER_AGENTS list
  - ProxyMiddleware: Proxy rotation via scrapers_v2 proxy support
"""
import random
import logging
from urllib.parse import urlparse

log = logging.getLogger("scrapy_b2b.middlewares")


class RotatingUserAgentMiddleware:
    """Rotate User-Agent header per request from settings.USER_AGENTS."""

    def __init__(self, user_agents):
        self.user_agents = user_agents

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings.getlist("USER_AGENTS"))

    def process_request(self, request, spider):
        if self.user_agents:
            ua = random.choice(self.user_agents)
            request.headers["User-Agent"] = ua


class ProxyMiddleware:
    """Rotate through proxy list from scrapers_v2/proxy_support.py if enabled.

    Controlled by settings.PROXY_ENABLED. Loads proxies from environment
    or the proxy_support module.
    """

    def __init__(self, enabled: bool, proxy_list: list):
        self.enabled = enabled
        self.proxy_list = proxy_list
        self._idx = 0

    @classmethod
    def from_crawler(cls, crawler):
        enabled = crawler.settings.getbool("PROXY_ENABLED", False)
        proxy_list = []
        if enabled:
            try:
                from scrapers_v2.proxy_support import get_proxy_list
                proxy_list = get_proxy_list()
                log.info(f"[proxy] Loaded {len(proxy_list)} proxies")
            except ImportError:
                log.warning("[proxy] scrapers_v2.proxy_support not available")
            except Exception as e:
                log.warning(f"[proxy] Failed to load proxies: {e}")
        return cls(enabled, proxy_list)

    def process_request(self, request, spider):
        if not self.enabled or not self.proxy_list:
            return None
        proxy = self.proxy_list[self._idx % len(self.proxy_list)]
        self._idx += 1
        if proxy.startswith("http"):
            request.meta["proxy"] = proxy
        else:
            request.meta["proxy"] = f"http://{proxy}"
        return None

    def process_exception(self, request, exception, spider):
        """Rotate to next proxy on connection error."""
        if self.enabled and self.proxy_list:
            self._idx += 1
            proxy = self.proxy_list[self._idx % len(self.proxy_list)]
            if proxy.startswith("http"):
                request.meta["proxy"] = proxy
            else:
                request.meta["proxy"] = f"http://{proxy}"
            spider.logger.debug(f"[proxy] Rotating to next proxy after error: {exception}")
            return request  # retry with new proxy
        return None
