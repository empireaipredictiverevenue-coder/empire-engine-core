"""
EMPIRE V49 · Agent Orchestrator Standalone Entry
=================================================
Re-exports the FastAPI app from the products module so that
`uvicorn agent_orchestrator:app` resolves correctly from the project root.
"""
from products.agent_orchestrator import app  # noqa: F401
