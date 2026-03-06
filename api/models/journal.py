from datetime import datetime, timezone
from typing import Optional
from sqlmodel import SQLModel, Field

class JournalEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: str = Field(index=True)
    trade_idea_id: Optional[int] = Field(default=None, foreign_key="tradeidea.id")
    expected_behaviour: Optional[str] = None
    actual_behaviour: Optional[str] = None
    thesis_validity: Optional[str] = None
    should_have_skipped: bool = Field(default=False)
    lesson_learned: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
