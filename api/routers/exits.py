"""Helm exit-bracket visibility. The hunt cron evaluates; this router only reads."""

from typing import Optional

from fastapi import APIRouter, Depends
from sqlmodel import Session

from api.core.config import settings
from api.core.db import get_session
from api.services.exit_bracket import RULE_TEXT, bracket_to_dict, list_brackets

router = APIRouter(prefix="/exits", tags=["exit-brackets"])


@router.get("")
@router.get("/")
def list_exit_brackets(
    status: Optional[str] = None,
    session: Session = Depends(get_session),
):
    """Stop, target, trail, and exit-idea status for every bracket."""
    rows = list_brackets(session, status=status)
    return {
        "paper_trading": bool(settings.PAPER_TRADING),
        "live_exit": "paper_auto" if settings.PAPER_TRADING else "approval_required",
        "rule": RULE_TEXT,
        "count": len(rows),
        "brackets": [bracket_to_dict(session, row) for row in rows],
    }
