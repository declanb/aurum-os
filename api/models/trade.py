from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

class TradeIdeaBase(SQLModel):
    user_id: str = Field(index=True)
    symbol: str = Field(default="XAUUSD")
    direction: str
    entry_price: float
    stop_price: float
    target_price: float
    invalidation_notes: Optional[str] = None
    thesis: str
    status: str = Field(default="Draft")

class TradeIdea(TradeIdeaBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    versions: List["TradeIdeaVersion"] = Relationship(back_populates="trade_idea")
    approval_events: List["ApprovalEvent"] = Relationship(back_populates="trade_idea")

class TradeIdeaVersion(TradeIdeaBase, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trade_idea_id: int = Field(foreign_key="tradeidea.id")
    version_number: int
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    trade_idea: TradeIdea = Relationship(back_populates="versions")

class ApprovalEvent(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    trade_idea_id: int = Field(foreign_key="tradeidea.id")
    version_id: int = Field(foreign_key="tradeideaversion.id")
    user_id: str
    snapshot_hash: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    
    trade_idea: TradeIdea = Relationship(back_populates="approval_events")

class ExecutionTicket(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    approval_event_id: int = Field(foreign_key="approvalevent.id", unique=True)
    adapter_status: str = Field(default="Pending")
    provider_response: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
