from datetime import datetime, timezone
from typing import Optional, List
from sqlmodel import SQLModel, Field, Relationship

class TradeIdeaBase(SQLModel):
    user_id: str = Field(index=True)
    symbol: str = Field(default="BTC-EUR")
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
    approval_event_id: Optional[int] = Field(default=None, foreign_key="approvalevent.id")
    adapter_status: str = Field(default="Pending")
    provider_response: Optional[str] = None
    # Broker fill data — populated by polling after order placement
    broker_order_id: Optional[str] = Field(default=None, index=True)
    symbol: Optional[str] = None
    side: Optional[str] = None  # "buy" | "sell"
    fill_qty: Optional[float] = None  # Base-asset quantity actually filled
    fill_price: Optional[float] = None  # Avg fill price (quote currency)
    fees_eur: Optional[float] = None
    filled_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class ExitBracket(SQLModel, table=True):
    """Strategy-layer protective exit for one filled spot LONG.

    Revolut X spot cannot attach a native stop or take-profit. This row is the
    bracket the hunt monitor ratchets and, on a breach, turns into an EXIT idea.
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    entry_ticket_id: int = Field(foreign_key="executionticket.id", index=True)
    trade_idea_id: int = Field(foreign_key="tradeidea.id", index=True)
    exit_trade_idea_id: Optional[int] = Field(default=None, foreign_key="tradeidea.id", index=True)
    symbol: str = Field(index=True)
    direction: str = Field(default="LONG")
    qty: float
    entry_price: float
    initial_stop_price: float
    stop_price: float
    target_price: float
    high_water_price: float
    trail_armed: bool = Field(default=False)
    status: str = Field(default="armed", index=True)
    exit_reason: Optional[str] = None
    last_price: Optional[float] = None
    last_trigger: Optional[str] = None
    pending_clear: bool = Field(default=False)
    cooldown_until: Optional[datetime] = None
    last_checked_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
