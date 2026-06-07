from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime, timezone
import hashlib
import json

from api.core.db import get_session
from api.models.trade import TradeIdea, TradeIdeaVersion, ApprovalEvent
from pydantic import BaseModel

class ApprovalRequest(BaseModel):
    action: str # "APPROVE" or "REJECT"
    reasoning: str = ""

router = APIRouter(prefix="/approvals", tags=["approvals"])

MOCK_USER_ID = "seed_user"


def _compute_snapshot_hash(trade: TradeIdea) -> str:
    """Deterministic hash of the trade's immutable fields."""
    snapshot = {
        "symbol": trade.symbol,
        "direction": trade.direction,
        "entry_price": trade.entry_price,
        "stop_price": trade.stop_price,
        "target_price": trade.target_price,
        "thesis": trade.thesis,
        "invalidation_notes": trade.invalidation_notes,
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True).encode()).hexdigest()[:16]


@router.post("/{trade_id}", response_model=dict)
def process_approval(*, session: Session = Depends(get_session), trade_id: int, request: ApprovalRequest):
    trade = session.get(TradeIdea, trade_id)
    
    if not trade or trade.user_id != MOCK_USER_ID:
        raise HTTPException(status_code=404, detail="Trade not found")
        
    if trade.status not in ["Needs Work", "Ready for Approval"]:
        raise HTTPException(status_code=400, detail="Trade is not pending approval")

    # Get or create the latest version
    stmt = (
        select(TradeIdeaVersion)
        .where(TradeIdeaVersion.trade_idea_id == trade.id)
        .order_by(TradeIdeaVersion.version_number.desc())
    )
    version = session.exec(stmt).first()
    
    if not version:
        # Scout-staged trades already have a version, but legacy manual ones might not
        version = TradeIdeaVersion(
            user_id=MOCK_USER_ID,
            symbol=trade.symbol,
            direction=trade.direction,
            entry_price=trade.entry_price,
            stop_price=trade.stop_price,
            target_price=trade.target_price,
            thesis=trade.thesis,
            invalidation_notes=trade.invalidation_notes,
            trade_idea_id=trade.id,
            version_number=1,
        )
        session.add(version)
        session.commit()
        session.refresh(version)

    # Record the immutable approval event
    if request.action == "APPROVE":
        event = ApprovalEvent(
            trade_idea_id=trade.id,
            version_id=version.id,
            user_id=MOCK_USER_ID,
            snapshot_hash=_compute_snapshot_hash(trade),
        )
        session.add(event)
        trade.status = "Approved"
    else:
        # REJECTs don't create an ApprovalEvent (only APPROVEs do in this schema)
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
