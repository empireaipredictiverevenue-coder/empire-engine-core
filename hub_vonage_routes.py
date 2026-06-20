"""
Vonage Webhook Routes Registration
====================================

Vonage webhook endpoints for voice and SMS event handling.
The main routes are registered via register_voice_routes and
register_sms_routes in hub.py. This file provides additional
proxy handlers for any Vonage dashboard config pointing to
/webhook/vonage-* paths.

The hub.py also registers these aliases directly:
    POST /webhook/vonage-answer → voice_router.answer_webhook
    POST /webhook/vonage-event  → voice_router.event_webhook

This file is kept for compatibility but currently registers
no additional routes — all Vonage routing is handled through
the main route registrations in hub.py.
"""
from fastapi import FastAPI


def register_vonage_routes(app: FastAPI):
    """Register Vonage webhook proxy routes.

    Currently a no-op. All Vonage webhook handling is done via
    register_voice_routes + register_sms_routes in hub.py.
    """
    pass
