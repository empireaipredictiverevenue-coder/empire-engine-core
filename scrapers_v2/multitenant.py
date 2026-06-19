from typing import Dict, List
from models import Lead

class TenantManager:
    def __init__(self):
        self.tenants: Dict[str, Dict] = {}

    def register_tenant(self, tenant_id: str, verticals: List[str], config: Dict):
        self.tenants[tenant_id] = {
            "verticals": verticals,
            "config": config,
            "leads": []
        }

    def add_lead(self, tenant_id: str, lead: Lead):
        if tenant_id in self.tenants:
            self.tenants[tenant_id]["leads"].append(lead)

    def get_tenant_leads(self, tenant_id: str) -> List[Lead]:
        return self.tenants.get(tenant_id, {}).get("leads", [])
