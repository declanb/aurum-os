from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TradeIdeaBase(BaseModel):
    symbol: str = "XAUUSD"
    direction: str
    entry_price: float
    stop_price: float
    target_price: float
    invalidation_notes: Optional[str] = None
    thesis: str
    status: str = "Draft"

class TradeIdeaCreate(TradeIdeaBase):
    pass

class TradeIdeaRead(TradeIdeaBase):
    id: int
    user_id: str
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class TradeIdeaUpdate(BaseModel):
    direction: Optional[str] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    invalidation_notes: Optional[str] = None
    thesis: Optional[str] = None
    status: Optional[str] = None
