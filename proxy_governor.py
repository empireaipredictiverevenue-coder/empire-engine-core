import random

class ProxyGovernor:
    def __init__(self):
        # Your rotating proxy pool (e.g., residential proxies)
        self.proxies = ["http://user:pass@proxy1.com", "http://user:pass@proxy2.com"]
        self.usage_count = {}

    def get_proxy(self):
        # Rotate to the proxy with the least usage to avoid blocks
        proxy = min(self.proxies, key=lambda p: self.usage_count.get(p, 0))
        self.usage_count[proxy] = self.usage_count.get(proxy, 0) + 1
        return proxy

# This makes your outreach invisible to platform anti-spam systems
