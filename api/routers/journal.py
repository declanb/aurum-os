from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime, timezone

from api.core.db import get_session
from api.models.journal import JournalEntry
from api.models.trade import TradeIdea, TradeIdeaVersion
from pydantic import BaseModel

class JournalEntryCreate(BaseModel):
    trade_idea_id: int
    content: str
    mistakes_made: str = ""
    lessons_learned: str = ""
    execution_rating: int = 5 # 1-10

router = APIRouter(prefix="/journal", tags=["journal"])

MOCK_USER_ID = "seed_user"

@router.post("/", response_model=dict)
def create_journal_entry(*, session: Session = Depends(get_session), entry: JournalEntryCreate):
    db_entry = JournalEntry(
        **entry.model_dump(),
        user_id=MOCK_USER_ID
    )
    session.add(db_entry)
    session.commit()
    return {"status": "success", "id": db_entry.id}

@router.get("/", response_model=List[dict])
def get_journal_entries(*, session: Session = Depends(get_session)):
    entries = session.exec(
         select(JournalEntry)
         .where(JournalEntry.user_id == MOCK_USER_ID)
         .order_by(JournalEntry.created_at.desc())
    ).all()
    
    return [e.model_dump() for e in entries]

@router.get("/versions/{trade_id}", response_model=List[dict])
def get_trade_versions(*, session: Session = Depends(get_session), trade_id: int):
    # Returns structural history of a trade idea
    versions = session.exec(
        select(TradeIdeaVersion)
        .where(TradeIdeaVersion.trade_idea_id == trade_id)
        .order_by(TradeIdeaVersion.version_number.desc())
    ).all()
    
    return [v.model_dump() for v in versions]
