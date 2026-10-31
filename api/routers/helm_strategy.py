"""Helm strategy rules HTTP surface. Never approves an idea or sends an order."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session

from api.core.db import get_session
from api.services import helm_strategy

router = APIRouter(prefix="/strategy", tags=["helm-strategy"])


class ExpireBody(BaseModel):
    hours: Optional[float] = None
    dry_run: bool = True


@router.get("/rules")
def strategy_rules():
    return helm_strategy.rules()


@router.post("/expire-stale")
def expire_stale(body: Optional[ExpireBody] = None, db: Session = Depends(get_session)):
    """Cancel Ready-for-Approval ideas older than HELM_STALE_IDEA_HOURS (48h).

    Dry run unless ``dry_run`` is false. EXIT proposals are never touched.
    """
    payload = body or ExpireBody()
    try:
        return helm_strategy.expire_stale_ideas(db, payload.hours, dry_run=payload.dry_run)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
