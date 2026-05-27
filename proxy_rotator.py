import os
import random
from typing import Optional


class ProxyRotator:
    """Round-robin/random proxy selector. Returns None if no proxies configured."""

    def __init__(self, proxy_list: Optional[list] = None):
        # Filter out placeholders and empty values
        self.proxies = [
            p for p in (proxy_list or [])
            if p and "user:pass" not in p and ":port" not in p
        ]
        self._index = 0

    def get_next(self) -> Optional[str]:
        if not self.proxies:
            return None
        # Round-robin for predictable rotation; swap to random.choice if preferred
        proxy = self.proxies[self._index % len(self.proxies)]
        self._index += 1
        return proxy

    def get_random(self) -> Optional[str]:
        if not self.proxies:
            return None
        return random.choice(self.proxies)


# Load from environment variable (comma-separated) or hardcoded list
# Example: export EMPIRE_PROXIES="http://user:pass@gate.smartproxy.com:7000,http://user:pass@gate2.smartproxy.com:7000"
ENV_PROXIES = os.environ.get("EMPIRE_PROXIES", "")
MY_PROXIES = [p.strip() for p in ENV_PROXIES.split(",") if p.strip()] or [
    # Paste real proxy URLs here, e.g.:
    # "http://username:password@gate.smartproxy.com:7000",
]

rotator = ProxyRotator(MY_PROXIES)
