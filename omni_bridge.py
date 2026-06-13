"""
EMPIRE V49 · OMNI BRIDGE WRAPPER
=================================
Thin root-level wrapper for standalone uvicorn deployment.
Re-exports the standalone FastAPI app from products/omni_bridge.py.

Usage:
    uvicorn omni_bridge:app --host 0.0.0.0 --port 8040
"""
import logging
logging.basicConfig(level=logging.INFO)
log = logging.getLogger("empire.omni_bridge")

from products.omni_bridge import app  # noqa: E402, F401

log.info("[omni_bridge] Standalone app loaded from products.omni_bridge")
