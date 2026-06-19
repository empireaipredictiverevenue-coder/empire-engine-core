from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class Lead(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None
    city: Optional[str] = None
    state: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    website: Optional[str] = None
    vertical: str
    source: str
    status: str = "active"
    meta: dict = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
