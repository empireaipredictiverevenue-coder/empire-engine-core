"""Empire AI - Customer Container Reporting Agent"""
import os
import json
import httpx
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

HUB_URL = os.getenv("EMPIRE_HUB_URL", "https://hub.empire-ai.co.uk")
API_KEY = os.getenv("EMPIRE_API_KEY")

class ReportingAgent:
    def __init__(self):
        self.client = httpx.Client(timeout=30.0)

    def send_event(self, event_type: str, payload: dict):
        """Send event to central Empire AI Hub"""
        data = {
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "payload": payload,
            "container_id": os.getenv("HOSTNAME", "unknown")
        }
        
        try:
            response = self.client.post(
                f"{HUB_URL}/api/v1/customer/events",
                json=data,
                headers={"X-Empire-API-Key": API_KEY}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"[ReportingAgent] Failed to send event: {e}")
            return None

    def report_opportunity(self, opportunity: dict):
        return self.send_event("opportunity_found", opportunity)

    def report_metric(self, metric: str, value: float):
        return self.send_event("metric", {"name": metric, "value": value})

if __name__ == "__main__":
    agent = ReportingAgent()
    agent.report_metric("test_metric", 42.0)
