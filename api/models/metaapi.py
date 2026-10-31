"""MetaApi (MT4/MT5) commodities venue tables.

``MetaApiIdea`` is a sidecar for a ``TradeIdea`` with ``venue=metaapi``. The
TradeIdea table is shared with Revolut X and is not altered.
``MetaApiPaperPosition`` is the paper ledger. Nothing here is a broker order.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class MetaApiIdea(SQLModel, table=True):
    __tablename__ = "metaapiidea"

    id: Optional[int] = Field(default=None, primary_key=True)
    trade_idea_id: int = Field(foreign_key="tradeidea.id", unique=True, index=True)
    venue: str = Field(default="metaapi", index=True)
    symbol: str = Field(index=True)  # MT form, e.g. XAUUSD
    lots: float
    leveraged_ok: bool = Field(default=False)
    leveraged_ack_at: Optional[datetime] = None
    source: str = Field(default="scout")  # scout | manual
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class MetaApiPaperPosition(SQLModel, table=True):
    """One paper CFD position. P&L is in the symbol's quote currency (USD)."""

    __tablename__ = "metaapipaperposition"

    id: Optional[int] = Field(default=None, primary_key=True)
    trade_idea_id: Optional[int] = Field(default=None, foreign_key="tradeidea.id", index=True)
    symbol: str = Field(index=True)
    direction: str  # LONG | SHORT
    status: str = Field(default="open", index=True)  # open | closed
    lots: float
    contract_size: float
    entry_price: float
    stop_price: float
    target_price: float
    spread_cost: float = Field(default=0.0)
    swap_rate_per_night: float = Field(default=0.0)
    swap_estimate: float = Field(default=0.0)
    last_mark: Optional[float] = None
    unrealized_pnl: Optional[float] = None
    last_marked_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    realized_pnl: Optional[float] = None
    exit_reason: Optional[str] = None
    opened_at: datetime = Field(default_factory=_utcnow)
    closed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=_utcnow)
