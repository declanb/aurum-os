from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field

class MarketNote(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    symbol: str = Field(default="XAUUSD")
    timeframe: str = Field(default="4H")
    content: str
    market_state: Optional[str] = None # e.g., "Trending Bullish", "Ranging"
    support_levels: Optional[str] = None
    resistance_levels: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
