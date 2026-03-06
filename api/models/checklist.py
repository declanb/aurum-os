from typing import Optional
from sqlmodel import SQLModel, Field

class TradeChecklist(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trade_idea_id: int = Field(foreign_key="tradeidea.id", unique=True)
    target_verified: bool = Field(default=False)
    invalidation_clear: bool = Field(default=False)
    risk_acceptable: bool = Field(default=False)
    bias_challenged: bool = Field(default=False)
    score: int = Field(default=0)
