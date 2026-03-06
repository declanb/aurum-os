from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List

from api.core.db import get_session
from api.models.note import MarketNote
from api.schemas.note import MarketNoteCreate, MarketNoteRead

router = APIRouter(prefix="/notes", tags=["market-notes"])

# Mock User ID until Clerk is integrated on backend
MOCK_USER_ID = "seed_user"

@router.post("/", response_model=MarketNoteRead)
def create_note(*, session: Session = Depends(get_session), note: MarketNoteCreate):
    db_note = MarketNote.model_validate(note, update={"user_id": MOCK_USER_ID})
    session.add(db_note)
    session.commit()
    session.refresh(db_note)
    return db_note

@router.get("/", response_model=List[MarketNoteRead])
def read_notes(*, session: Session = Depends(get_session), limit: int = 50):
    notes = session.exec(select(MarketNote).where(MarketNote.user_id == MOCK_USER_ID).limit(limit).order_by(MarketNote.created_at.desc())).all()
    return notes
