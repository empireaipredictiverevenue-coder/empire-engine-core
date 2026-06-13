"""
EMPIRE V49 · B2B Pro Standalone Entry
======================================
Re-exports the FastAPI app from the products module so that
`uvicorn b2b_pro:app` resolves correctly from the project root.
"""
from products.b2b_pro import app  # noqa: F401
