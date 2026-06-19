"""Customer Container Endpoints for Empire AI Hub"""
from fastapi import APIRouter, Request, HTTPException, Header
from typing import Optional
import logging
import os

log = logging.getLogger("hub.customer")

router = APIRouter(prefix="/api/v1/customer", tags=["customer"])

VALID_API_KEYS = set(os.getenv("CUSTOMER_API_KEYS", "").split(",")) if os.getenv("CUSTOMER_API_KEYS") else set()

@router.post("/events")
async def receive_customer_event(
    request: Request,
    x_empire_api_key: Optional[str] = Header(None, alias="X-Empire-API-Key")
):
    if not x_empire_api_key or x_empire_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
    
    data = await request.json()
    event_type = data.get("event_type")
    payload = data.get("payload", {})
    container_id = data.get("container_id")
    
    log.info(f"[Customer] Event: {event_type} from {container_id}")
    
    # TODO: Route to Striker / AGI based on event_type
    if event_type == "opportunity_found":
        log.info(f"[Customer] Opportunity: {payload}")
    
    return {"status": "accepted"}

@router.get("/health")
async def customer_health():
    return {"status": "ok", "service": "customer-api"}
# === Enhanced Hub + Customer Container Wiring ===
@router.post("/command")
async def send_command_to_customer(request: Request):
    """Send commands from hub to customer containers"""
    data = await request.json()
    # TODO: Forward command to specific container
    log.info(f"[Hub] Sending command to customer: {data}")
    return {"status": "command_sent"}
# === Bidirectional Hub ↔ Customer Container Wiring ===
@router.post("/report")
async def customer_report(request: Request):
    """Receive detailed reports from customer containers"""
    data = await request.json()
    log.info(f"[Hub] Detailed report received: {data.get(type)}")
    return {"status": "report_received"}

@router.get("/config/{container_id}")
async def get_customer_config(container_id: str):
    """Send configuration updates to customer containers"""
    return {"config": {"update_interval": 3600, "enabled": True}}
