from proxy_governor import ProxyGovernor
from local_brain import LocalBrain

class OutreachEngine:
    def __init__(self):
        self.pg = ProxyGovernor()
        self.brain = LocalBrain()

    def craft_message(self, lead_data):
        # Inject dynamic context to make the outreach feel human
        prompt = f"Write a 1-sentence hook for {lead_data['name']} who works in {lead_data['niche']}."
        return self.brain.think(prompt)

    def send(self, message, target):
        proxy = self.pg.get_proxy()
        # Simulation: send message via proxy
        print(f"[OUTREACH] Sending via {proxy} to {target}")

from security_layer import SecurityLayer

# Inside OutreachEngine class:
    def get_secure_headers(self):
        sec = SecurityLayer()
        return sec.get_headers()
