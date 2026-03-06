from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class MarketNoteBase(BaseModel):
    symbol: str = "XAUUSD"
    timeframe: str = "4H"
    content: str
    market_state: Optional[str] = None
    support_levels: Optional[str] = None
    resistance_levels: Optional[str] = None

class MarketNoteCreate(MarketNoteBase):
    pass

class MarketNoteRead(MarketNoteBase):
    id: int
    user_id: str
    created_at: datetime
    
    class Config:
        from_attributes = True
