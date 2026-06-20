"""
Customer Routes Registration
=============================
The customer_router is registered directly in hub.py via:
    from hub_customer_endpoints import router as customer_router
    app.include_router(customer_router)

This file is kept for compatibility but its register_customer_routes()
is no longer called from hub.py to avoid duplicate route registration.
"""
from fastapi import FastAPI


def register_customer_routes(app: FastAPI):
    """Register customer routes.

    Currently a no-op. Customer routes are registered directly
    in hub.py via app.include_router(customer_router).
    """
    pass
