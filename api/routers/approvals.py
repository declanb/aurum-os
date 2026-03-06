from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime, timezone

from api.core.db import get_session
from api.models.trade import TradeIdea, ApprovalEvent
from pydantic import BaseModel

class ApprovalRequest(BaseModel):
    action: str # "APPROVE" or "REJECT"
    reasoning: str = ""

router = APIRouter(prefix="/approvals", tags=["approvals"])

MOCK_USER_ID = "seed_user"

@router.post("/{trade_id}", response_model=dict)
def process_approval(*, session: Session = Depends(get_session), trade_id: int, request: ApprovalRequest):
    trade = session.get(TradeIdea, trade_id)
    
    if not trade or trade.user_id != MOCK_USER_ID:
        raise HTTPException(status_code=404, detail="Trade not found")
        
    if trade.status not in ["Needs Work", "Ready for Approval"]:
        raise HTTPException(status_code=400, detail="Trade is not pending approval")

    # Record the immutable event
    event = ApprovalEvent(
        trade_idea_id=trade.id,
        user_id=MOCK_USER_ID,
        action=request.action,
        reasoning=request.reasoning
    )
    session.add(event)
    
    # Mutate the trade state
    if request.action == "APPROVE":
        trade.status = "Approved"
    else:
        trade.status = "Needs Work"
        
    trade.updated_at = datetime.now(timezone.utc)
    session.add(trade)
    session.commit()
    
    return {"status": "success", "new_state": trade.status}

@router.get("/events/{trade_id}", response_model=List[dict])
def get_approval_events(*, session: Session = Depends(get_session), trade_id: int):
    events = session.exec(
        select(ApprovalEvent)
        .where(ApprovalEvent.trade_idea_id == trade_id)
        .order_by(ApprovalEvent.timestamp.desc())
    ).all()
    
    return [e.model_dump() for e in events]
