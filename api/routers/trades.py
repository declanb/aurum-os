from fastapi import APIRouter, Depends, HTTPException
from sqlmodel import Session, select
from typing import List
from datetime import datetime, timezone

from api.core.db import get_session
from api.models.trade import TradeIdea, TradeIdeaVersion
from api.schemas.trade import TradeIdeaCreate, TradeIdeaRead, TradeIdeaUpdate

router = APIRouter(prefix="/trades", tags=["trade-ideas"])

MOCK_USER_ID = "seed_user"

@router.post("/", response_model=TradeIdeaRead)
def create_trade(*, session: Session = Depends(get_session), trade: TradeIdeaCreate):
    db_trade = TradeIdea.model_validate(trade, update={"user_id": MOCK_USER_ID})
    session.add(db_trade)
    session.commit()
    session.refresh(db_trade)
    
    # Create initial version snapshot
    version = TradeIdeaVersion.model_validate(trade, update={
        "user_id": MOCK_USER_ID,
        "trade_idea_id": db_trade.id,
        "version_number": 1
    })
    session.add(version)
    session.commit()
    
    return db_trade

@router.get("/", response_model=List[TradeIdeaRead])
def read_trades(*, session: Session = Depends(get_session), status: str = None):
    query = select(TradeIdea).where(TradeIdea.user_id == MOCK_USER_ID)
    if status:
        query = query.where(TradeIdea.status == status)
    query = query.order_by(TradeIdea.created_at.desc())
    trades = session.exec(query).all()
    return trades

@router.get("/{trade_id}", response_model=TradeIdeaRead)
def read_trade(*, session: Session = Depends(get_session), trade_id: int):
    trade = session.get(TradeIdea, trade_id)
    if not trade or trade.user_id != MOCK_USER_ID:
        raise HTTPException(status_code=404, detail="Trade idea not found")
    return trade

@router.patch("/{trade_id}", response_model=TradeIdeaRead)
def update_trade(*, session: Session = Depends(get_session), trade_id: int, trade_update: TradeIdeaUpdate):
    db_trade = session.get(TradeIdea, trade_id)
    if not db_trade or db_trade.user_id != MOCK_USER_ID:
        raise HTTPException(status_code=404, detail="Trade idea not found")
        
    update_data = trade_update.model_dump(exclude_unset=True)
    
    # Important: if critical fields change after approval, revert status to Draft
    if db_trade.status in ["Approved", "Ready for Approval"]:
        critical_fields = ["direction", "entry_price", "stop_price", "target_price"]
        if any(field in update_data for field in critical_fields):
            update_data["status"] = "Draft"
            
    db_trade.sqlmodel_update(update_data)
    db_trade.updated_at = datetime.now(timezone.utc)
    
    session.add(db_trade)
    session.commit()
    session.refresh(db_trade)
    
    # Create new version snapshot on update
    latest_version = session.exec(
        select(TradeIdeaVersion)
        .where(TradeIdeaVersion.trade_idea_id == trade_id)
        .order_by(TradeIdeaVersion.version_number.desc())
    ).first()
    
    next_ver_num = (latest_version.version_number + 1) if latest_version else 1
    
    # We copy the state of db_trade into the version snapshot
    version_data = db_trade.model_dump()
    version_data.pop("id")
    version_data.pop("created_at", None)
    version_data.pop("updated_at", None)
    version_data.pop("status", None)
    
    version = TradeIdeaVersion(**version_data, trade_idea_id=trade_id, version_number=next_ver_num)
    session.add(version)
    session.commit()
    
    return db_trade
