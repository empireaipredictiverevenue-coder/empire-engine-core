"""EMPIRE V49 · OUTREACH WRITER (ELITE + COMPLIANT)
Drafts and sends personalized outreach with full compliance gating.
"""

import os
import json
import logging
from datetime import datetime
from typing import Optional, Dict

from supabase import create_client
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("outreach.writer")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY")
_sb = create_client(SUPABASE_URL, SUPABASE_KEY)

def is_unsubscribed(email: str) -> bool:
    """Check global unsubscribe registry"""
    res = _sb.table("unsubscribes").select("email").eq("email", email).execute()
    return len(res.data) > 0

async def draft_and_send(email: str, subject: str, body: str, metadata: Dict = None) -> bool:
    """Draft and send with compliance check"""
    if is_unsubscribed(email):
        log.warning(f"[Outreach] Skipped unsubscribed email: {email}")
        return False
    
    # TODO: Send via Resend / empire_email.py
    log.info(f"[Outreach] Sending to {email}: {subject}")
    return True

async def process_task(task: Dict):
    payload = task.get("payload", {})
    if isinstance(payload, str):
        payload = json.loads(payload)
    
    email = payload.get("email")
    subject = payload.get("subject", "Empire AI Opportunity")
    body = payload.get("body", "")
    
    if email:
        await draft_and_send(email, subject, body, payload)
