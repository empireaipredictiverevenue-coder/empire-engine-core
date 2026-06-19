from typing import Optional, List
import random
import httpx

class ProxyManager:
    def __init__(self, proxies: List[str] = None):
        self.proxies = proxies or []
        self.index = 0

    def get_next(self) -> Optional[str]:
        if not self.proxies:
            return None
        proxy = self.proxies[self.index % len(self.proxies)]
        self.index += 1
        return proxy

    def get_client(self) -> httpx.AsyncClient:
        proxy = self.get_next()
        if proxy:
            return httpx.AsyncClient(proxies={"http://": proxy, "https://": proxy})
        return httpx.AsyncClient()

    def rotate(self):
        if self.proxies:
            self.index = (self.index + 1) % len(self.proxies)
