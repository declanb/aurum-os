"""Paper copy-book tables.

A session is a virtual EUR book. Positions are simulated spot longs.
Nothing here is an ExecutionTicket, and nothing here is sent to Revolut X.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CopySession(SQLModel, table=True):
    """One dry-run copy session. ``dry_run`` is stored true and must stay true."""

    __tablename__ = "copysession"

    id: Optional[int] = Field(default=None, primary_key=True)
    status: str = Field(default="running", index=True)  # running | stopped
    dry_run: bool = Field(default=True)
    starting_bankroll_eur: float
    cash_eur: float
    realized_pnl_eur: float = Field(default=0.0)
    position_pct: float
    max_notional_eur: float
    max_positions: int
    any_green: bool = Field(default=False)
    # "symmetric" = Helm TP/SL brackets on scout's top ideas (default).
    # "any_green" = legacy overnight copy mode, kept for old rows.
    strategy: str = Field(default="symmetric")
    tp_pct: Optional[float] = None
    sl_pct: Optional[float] = None
    max_new_per_day: Optional[int] = None
    sources: str = Field(default="trade_ideas,gainers")
    gainer_limit: int = Field(default=3)
    lookback_hours: float = Field(default=24.0)
    note: str
    started_at: datetime = Field(default_factory=_utcnow)
    stopped_at: Optional[datetime] = None
    last_tick_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class CopyPosition(SQLModel, table=True):
    """One paper spot long opened by the copy book.

    Stop and target mirror the optional ExitBracket fields. They are evaluated
    on the paper mark only. They never arm a live bracket and never stage an
    EXIT idea.
    """

    __tablename__ = "copyposition"

    id: Optional[int] = Field(default=None, primary_key=True)
    session_id: int = Field(foreign_key="copysession.id", index=True)
    symbol: str = Field(index=True)  # DB form, e.g. UNI-EUR
    status: str = Field(default="open", index=True)  # open | closed
    direction: str = Field(default="LONG")
    qty: float
    entry_price: float
    entry_notional_eur: float
    entry_fee_eur: float = Field(default=0.0)
    opened_at: datetime = Field(default_factory=_utcnow)
    signal_source: str  # trade_idea | gainer
    signal_reason: str
    trade_idea_id: Optional[int] = Field(default=None, foreign_key="tradeidea.id", index=True)
    initial_stop_price: Optional[float] = None
    stop_price: Optional[float] = None
    target_price: Optional[float] = None
    high_water_price: Optional[float] = None
    last_mark: Optional[float] = None
    last_marked_at: Optional[datetime] = None
    exit_price: Optional[float] = None
    exit_fee_eur: Optional[float] = None
    exit_proceeds_eur: Optional[float] = None
    realized_pnl_eur: Optional[float] = None
    exit_reason: Optional[str] = None
    closed_at: Optional[datetime] = None
    updated_at: datetime = Field(default_factory=_utcnow)
